"""Flight intelligence without paid APIs: nearest hub + great-circle route model."""

from __future__ import annotations

from functools import lru_cache

from novatrek.models import Place, Tier
from novatrek.tools.geo import haversine

try:  # optional dependency — the app degrades gracefully without it
    import airportsdata
except ImportError:  # pragma: no cover
    airportsdata = None

# Large international hubs: preferred over small airfields that share a city name.
_MAJOR = set(
    "ATL PEK DXB LAX HND ORD LHR PVG CDG DFW CAN AMS FRA IST DEL CGK ICN SIN BKK DEN JFK "
    "KUL SFO LAS CLT MIA MAD BCN PHX SEA EWR MCO MUC BOM BLR HYD MAA CCU GOI JAI SYD MEL "
    "AKL ZRH VIE FCO MXP LIS DUB CPH ARN OSL HEL ATH PRG BUD WAW CAI JNB CPT GRU GIG EZE "
    "BOG LIM SCL MEX YYZ YVR HKG TPE NRT KIX DOH AUH RUH JED TLV AMM NBO ADD LOS CMN DPS "
    "HNL IAD BOS IAH DTW MSP PHL BER LGW ORY BRU DUS HAM NCE VCE ATQ KTM CMB MLE MNL SGN "
    "HAN".split()
)


@lru_cache(maxsize=1)
def _airports() -> dict:
    return airportsdata.load("IATA") if airportsdata else {}


def nearest_airport(place: Place) -> dict | None:
    db = _airports()
    best_major = best_any = None
    d_major = d_any = float("inf")
    for code, a in db.items():
        dist = haversine(place.lat, place.lon, a["lat"], a["lon"])
        if code in _MAJOR and dist < d_major:
            best_major, d_major = (code, a, dist), dist
        if dist < d_any:
            best_any, d_any = (code, a, dist), dist
    pick = best_major if best_major and d_major <= 150 else best_any
    if not pick or (pick[2] > 200):
        return None
    code, a, dist = pick
    return {"iata": code, "name": a.get("name", code), "city": a.get("city", ""),
            "distance_km": round(dist)}


_TIER_MULT: dict[str, float] = {"budget": 0.85, "mid": 1.0, "luxury": 2.4}
_PEAK_MONTHS = {"June", "July", "August", "December"}


def estimate(
    origin: Place, dest: Place, tier: Tier, month: str | None, travelers: int
) -> dict:
    km = haversine(origin.lat, origin.lon, dest.lat, dest.lon)
    # Cruise ~850 km/h plus ~45 min climb/descent/taxi.
    hours = km / 850 + 0.75
    stops = 0 if km < 5500 else (1 if km < 12000 else 2)
    hours += stops * 1.6
    # Piecewise fare model (USD, one-way, economy): short hauls cost more per km.
    base = 45 + 0.075 * km if km < 2500 else 150 + 0.062 * km
    mult = _TIER_MULT[tier]
    if month in _PEAK_MONTHS:
        mult *= 1.18
    mid = base * mult
    low, high = mid * 0.72, mid * 1.35
    round_trip_pp = mid * 2

    peak = month in _PEAK_MONTHS
    advice = [
        f"Book {'3–4 months' if peak else '6–10 weeks'} ahead for the best fares."
        + (" Peak season pushes prices up." if peak else ""),
        "Compare the departure-day mix: midweek flights are usually cheapest.",
    ]
    if stops:
        advice.append("Likely connecting itinerary — keep 2h+ layovers for safety.")
    if km < 600:
        advice.append("Short hop: compare train or coach — often faster door to door.")

    return {
        "available": True,
        "distance_km": round(km),
        "duration_h": round(hours, 1),
        "stops": stops,
        "fare_low": round(low),
        "fare_high": round(high),
        "fare_mid": round(mid),
        "round_trip_pp": round(round_trip_pp),
        "total_round_trip": round(round_trip_pp * travelers),
        "cabin": {"budget": "Economy (light)", "mid": "Economy", "luxury": "Business"}[tier],
        "advice": advice,
        "basis": "Great-circle route model — indicative, not a live quote",
    }
