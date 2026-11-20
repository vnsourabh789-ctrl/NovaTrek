"""Flight agent: route model + nearest major airports (no paid API)."""

from __future__ import annotations

import asyncio

from novatrek.models import Intent, Place
from novatrek.tools import flights as tool


async def run(intent: Intent, origin: Place | None, dest: Place | None) -> dict:
    if not intent.origin:
        return {"available": False, "source": "skipped",
                "note": "No departure city given — add \"from <city>\" to get flight estimates."}
    if origin is None or dest is None:
        return {"available": False, "source": "skipped",
                "note": "Couldn't locate one of the cities, so the route can't be estimated."}

    est = tool.estimate(origin, dest, intent.budget, intent.month, intent.travelers)
    # Airport scan is CPU-bound over ~7k rows; keep it off the event loop.
    o_air, d_air = await asyncio.gather(
        asyncio.to_thread(tool.nearest_airport, origin),
        asyncio.to_thread(tool.nearest_airport, dest),
    )
    return {**est, "origin_airport": o_air, "dest_airport": d_air, "source": "model"}
