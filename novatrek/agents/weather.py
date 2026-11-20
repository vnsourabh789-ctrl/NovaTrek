"""Weather agent: live forecast or monthly climate."""

from __future__ import annotations

from novatrek.models import Intent, Place
from novatrek.tools.weather import fetch_weather


async def run(intent: Intent, dest: Place | None) -> dict:
    if dest is None:
        return {"available": False, "source": "skipped",
                "note": "Couldn't pin down a specific city, so weather is unavailable."}
    try:
        data = await fetch_weather(dest, intent.month)
    except Exception as exc:  # network / provider hiccup — degrade, don't fail the plan
        return {"available": False, "source": "error",
                "note": f"Weather service unreachable ({type(exc).__name__})."}
    return {**data, "source": "live"}
