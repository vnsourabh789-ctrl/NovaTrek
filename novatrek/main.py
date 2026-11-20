"""FastAPI app: SSE planning stream, saved missions, copilot chat, static UI."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Path as PathParam, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from novatrek import __version__, store
from novatrek.agents import copilot
from novatrek.agents.orchestrator import plan_trip
from novatrek.cache import cache
from novatrek.config import get_settings
from novatrek.export import trip_to_markdown
from novatrek.http import close_client
from novatrek.ratelimit import RateLimiter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

WEB = Path(__file__).parent / "web"
settings = get_settings()
limiter = RateLimiter(settings.rate_limit_per_min)

TripId = PathParam(..., pattern=r"^[a-f0-9]{12}$")


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.init()
    yield
    await close_client()


app = FastAPI(title="NovaTrek", version=__version__, lifespan=lifespan,
              docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")

if settings.cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type"])

_CSP = ("default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    if not request.url.path.startswith("/api/docs"):  # Swagger UI needs inline assets
        resp.headers.setdefault("Content-Security-Policy", _CSP)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp


def rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    if not limiter.allow(ip):
        raise HTTPException(429, "Too many requests — give the engines a minute to cool down.")


class PlanRequest(BaseModel):
    message: str = Field(min_length=3, max_length=1000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=600)


# ───────────────────────── planning ─────────────────────────

@app.post("/api/plan", dependencies=[Depends(rate_limit)])
async def plan(body: PlanRequest, request: Request):
    """Server-sent events: start → stage* → result | error."""

    async def stream():
        try:
            async for event in plan_trip(body.message.strip()):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if await request.is_disconnected():
                    break
        except asyncio.CancelledError:
            raise

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# ───────────────────────── missions ─────────────────────────

@app.get("/api/trips")
async def trips():
    return await asyncio.to_thread(store.list_trips)


@app.get("/api/trips/{trip_id}")
async def get_trip(trip_id: str = TripId):
    trip = await asyncio.to_thread(store.get_trip, trip_id)
    if trip is None:
        raise HTTPException(404, "Mission not found")
    return trip


@app.delete("/api/trips/{trip_id}", status_code=204)
async def delete_trip(trip_id: str = TripId):
    if not await asyncio.to_thread(store.delete_trip, trip_id):
        raise HTTPException(404, "Mission not found")


@app.get("/api/trips/{trip_id}/export.md", response_class=PlainTextResponse)
async def export_trip(trip_id: str = TripId):
    trip = await asyncio.to_thread(store.get_trip, trip_id)
    if trip is None:
        raise HTTPException(404, "Mission not found")
    return PlainTextResponse(
        trip_to_markdown(trip), media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="novatrek-{trip_id}.md"'},
    )


@app.post("/api/trips/{trip_id}/chat", dependencies=[Depends(rate_limit)])
async def chat(body: ChatRequest, trip_id: str = TripId):
    trip = await asyncio.to_thread(store.get_trip, trip_id)
    if trip is None:
        raise HTTPException(404, "Mission not found")
    question = body.message.strip()
    reply, source = await copilot.answer(trip, question, trip.get("chat", []))
    await asyncio.to_thread(store.append_chat, trip_id, "user", question)
    await asyncio.to_thread(store.append_chat, trip_id, "assistant", reply)
    return {"reply": reply, "source": source}


# ───────────────────────── system ─────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": __version__,
        "engine": "ai" if settings.llm_enabled else "offline",
        "model": settings.llm_model if settings.llm_enabled else None,
        "cache": cache.stats(),
    }


app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})
