"""Mission orchestrator.

Pipeline (the original ran five agents strictly in sequence; independent
agents now run concurrently, cutting wall-clock time roughly in half):

    intent ─┬─ flights ─┐
            ├─ weather ─┼─ itinerary ─ budget ─ result
            └─ hotels ──┘

Progress is streamed as events so the UI can light up each agent live.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import AsyncIterator, Awaitable, Callable

from novatrek import store
from novatrek.agents import budget, flights, hotels, intent as intent_agent, itinerary, weather
from novatrek.config import get_settings
from novatrek.models import PlanError, Place
from novatrek.tools.geo import geocode

log = logging.getLogger("novatrek.orchestrator")

STAGES = [
    {"id": "intent", "label": "Intent decoder", "desc": "Parsing your request"},
    {"id": "flights", "label": "Flight vector", "desc": "Modelling the route"},
    {"id": "weather", "label": "Atmos scan", "desc": "Reading the skies"},
    {"id": "hotels", "label": "Stay finder", "desc": "Scouting where to sleep"},
    {"id": "itinerary", "label": "Itinerary composer", "desc": "Sequencing your days"},
    {"id": "budget", "label": "Budget engine", "desc": "Crunching the costs"},
]

Emit = Callable[[dict], Awaitable[None]]


def _place_dict(p: Place | None) -> dict | None:
    return p.model_dump() if p else None


async def _stage(emit: Emit, timings: dict, sid: str, coro: Awaitable, fallback: dict | None = None):
    """Run one agent, emitting running/done events and timing it."""
    await emit({"type": "stage", "id": sid, "status": "running"})
    t0 = time.perf_counter()
    try:
        out = await coro
    except PlanError:
        raise
    except Exception as exc:
        log.exception("stage %s crashed", sid)
        if fallback is None:
            raise
        out = {**fallback, "source": "error", "note": f"{type(exc).__name__}"}
    ms = round((time.perf_counter() - t0) * 1000)
    timings[sid] = ms
    src = out.get("source") if isinstance(out, dict) else None
    await emit({"type": "stage", "id": sid, "status": "done", "ms": ms, "source": src})
    return out


async def _pipeline(message: str, emit: Emit) -> dict:
    t_start = time.perf_counter()
    timings: dict[str, int] = {}

    await emit({"type": "start", "stages": STAGES,
                "engine": "ai" if get_settings().llm_enabled else "offline"})

    # 1) Intent
    await emit({"type": "stage", "id": "intent", "status": "running"})
    t0 = time.perf_counter()
    intent, intent_src = await intent_agent.run(message)
    timings["intent"] = round((time.perf_counter() - t0) * 1000)
    await emit({"type": "stage", "id": "intent", "status": "done", "ms": timings["intent"],
                "source": intent_src,
                "summary": f"{intent.destination} · {intent.days}d · {intent.budget}"})

    # 2) Geocode both ends concurrently (cached)
    dest, origin = await asyncio.gather(
        geocode(intent.destination),
        geocode(intent.origin) if intent.origin else asyncio.sleep(0, result=None),
    )
    dest_name = dest.name if dest else intent.destination

    # 3) Independent agents in parallel
    skip = {"available": False}
    f_task = _stage(emit, timings, "flights", flights.run(intent, origin, dest), skip)
    w_task = _stage(emit, timings, "weather", weather.run(intent, dest), skip)
    h_task = _stage(emit, timings, "hotels", hotels.run(intent, dest_name),
                    {"available": False, "hotels": []})
    flights_r, weather_r, hotels_r = await asyncio.gather(f_task, w_task, h_task)

    # 4) Itinerary needs weather + hotel area
    async def _it():
        data, _ = await itinerary.run(intent, dest_name, weather_r, hotels_r)
        return data

    itinerary_r = await _stage(emit, timings, "itinerary", _it())

    # 5) Deterministic budget
    async def _bud():
        return {**budget.compute(intent, flights_r, hotels_r, itinerary_r), "source": "calc"}

    budget_r = await _stage(emit, timings, "budget", _bud())

    sources = [intent_src, hotels_r.get("source"), itinerary_r.get("source")]
    ai_n = sources.count("ai")
    engine = "ai" if ai_n == len(sources) else ("offline" if ai_n == 0 else "mixed")

    trip = {
        "id": uuid.uuid4().hex[:12],
        "created_at": time.time(),
        "query": message,
        "title": f"{dest_name} · {intent.days} day{'s' if intent.days != 1 else ''}",
        "engine": engine,
        "intent": intent.model_dump(),
        "destination": _place_dict(dest),
        "origin": _place_dict(origin),
        "flights": flights_r,
        "weather": weather_r,
        "hotels": hotels_r,
        "itinerary": itinerary_r,
        "budget": budget_r,
        "timings": timings,
        "total_ms": round((time.perf_counter() - t_start) * 1000),
    }
    await asyncio.to_thread(store.save_trip, trip)
    return trip


async def plan_trip(message: str) -> AsyncIterator[dict]:
    """Yield progress events, ending with a ``result`` (or ``error``) event."""
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def emit(ev: dict) -> None:
        await queue.put(ev)

    async def driver() -> None:
        try:
            trip = await _pipeline(message, emit)
            await emit({"type": "result", "trip": trip})
        except PlanError as exc:
            await emit({"type": "error", "message": str(exc)})
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("pipeline failed")
            await emit({"type": "error",
                        "message": "Something went wrong while planning. Please try again."})
        finally:
            await queue.put(None)

    task = asyncio.create_task(driver())
    try:
        while (ev := await queue.get()) is not None:
            yield ev
    finally:  # client disconnected mid-plan -> stop burning tokens
        if not task.done():
            task.cancel()
