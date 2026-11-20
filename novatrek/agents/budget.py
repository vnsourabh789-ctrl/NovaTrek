"""Budget engine: deterministic cost model — no LLM, no hallucinated totals."""

from __future__ import annotations

import math

from novatrek.models import Intent

_FOOD = {"budget": 25, "mid": 55, "luxury": 130}
_ACTIVITY = {"budget": 15, "mid": 40, "luxury": 110}
_TRANSPORT = {"budget": 8, "mid": 18, "luxury": 60}
_HOTEL_BASE = {"budget": 55, "mid": 135, "luxury": 340}


def compute(intent: Intent, flights: dict, hotels: dict, itinerary: dict) -> dict:
    n, pax, tier = intent.days, intent.travelers, intent.budget
    nights = max(1, n - 1)
    rooms = math.ceil(pax / 2)

    # Hotel nightly rate: average of suggestions at the chosen tier (fallback: all, then base).
    picks = hotels.get("hotels") or []
    at_tier = [h["price_per_night"] for h in picks if h["tier"] == tier and h["price_per_night"] > 0]
    pool = at_tier or [h["price_per_night"] for h in picks if h["price_per_night"] > 0]
    nightly = sum(pool) / len(pool) if pool else _HOTEL_BASE[tier]

    # Expensive cities cost more everywhere, not just for beds (damped).
    scale = max(0.6, min(2.5, nightly / _HOTEL_BASE[tier])) ** 0.6

    # Prefer the itinerary's own per-day estimates when the model supplied them.
    est = [d["est_cost"] for d in itinerary.get("days", []) if d.get("est_cost", 0) > 0]
    if len(est) >= max(1, n // 2):
        per_day_pp = sum(est) / len(est)
        food = per_day_pp * 0.45 * n * pax
        activities = per_day_pp * 0.40 * n * pax
        transport = per_day_pp * 0.15 * n * pax
    else:
        food = _FOOD[tier] * scale * n * pax
        activities = _ACTIVITY[tier] * scale * n * pax
        transport = _TRANSPORT[tier] * scale * n * pax

    lodging = nightly * nights * rooms
    flight = flights.get("total_round_trip", 0) if flights.get("available") else 0

    items = [
        ("Flights", flight, "#5eead4"),
        ("Lodging", lodging, "#a78bfa"),
        ("Food", food, "#fbbf24"),
        ("Activities", activities, "#f472b6"),
        ("Local transport", transport, "#60a5fa"),
    ]
    subtotal = sum(v for _, v, _ in items)
    buffer = subtotal * 0.10
    items.append(("Contingency (10%)", buffer, "#94a3b8"))
    total = subtotal + buffer

    return {
        "currency": "USD",
        "items": [{"label": k, "amount": round(v), "color": c} for k, v, c in items if v > 0],
        "total": round(total),
        "per_person": round(total / pax),
        "per_day": round(total / n),
        "flights_included": bool(flight),
        "assumptions": (
            f"{rooms} room(s) × {nights} night(s) at ~${round(nightly)}/night; "
            f"{pax} traveller(s); {tier} spending tier. Estimates in USD."
        ),
    }
