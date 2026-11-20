"""Geocoding (Open-Meteo, keyless) with a small offline fallback table."""

from __future__ import annotations

import logging
import math

from novatrek.cache import cache
from novatrek.http import get_client
from novatrek.models import Place

log = logging.getLogger("novatrek.geo")

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"

# name -> (display, country, cc, lat, lon, tz). Used only if the API is unreachable.
_FALLBACK = {
    "paris": ("Paris", "France", "FR", 48.8566, 2.3522, "Europe/Paris"),
    "london": ("London", "United Kingdom", "GB", 51.5072, -0.1276, "Europe/London"),
    "rome": ("Rome", "Italy", "IT", 41.9028, 12.4964, "Europe/Rome"),
    "barcelona": ("Barcelona", "Spain", "ES", 41.3874, 2.1686, "Europe/Madrid"),
    "madrid": ("Madrid", "Spain", "ES", 40.4168, -3.7038, "Europe/Madrid"),
    "amsterdam": ("Amsterdam", "Netherlands", "NL", 52.3676, 4.9041, "Europe/Amsterdam"),
    "berlin": ("Berlin", "Germany", "DE", 52.52, 13.405, "Europe/Berlin"),
    "lisbon": ("Lisbon", "Portugal", "PT", 38.7223, -9.1393, "Europe/Lisbon"),
    "vienna": ("Vienna", "Austria", "AT", 48.2082, 16.3738, "Europe/Vienna"),
    "prague": ("Prague", "Czechia", "CZ", 50.0755, 14.4378, "Europe/Prague"),
    "athens": ("Athens", "Greece", "GR", 37.9838, 23.7275, "Europe/Athens"),
    "istanbul": ("Istanbul", "Türkiye", "TR", 41.0082, 28.9784, "Europe/Istanbul"),
    "zurich": ("Zurich", "Switzerland", "CH", 47.3769, 8.5417, "Europe/Zurich"),
    "tokyo": ("Tokyo", "Japan", "JP", 35.6762, 139.6503, "Asia/Tokyo"),
    "kyoto": ("Kyoto", "Japan", "JP", 35.0116, 135.7681, "Asia/Tokyo"),
    "seoul": ("Seoul", "South Korea", "KR", 37.5665, 126.978, "Asia/Seoul"),
    "singapore": ("Singapore", "Singapore", "SG", 1.3521, 103.8198, "Asia/Singapore"),
    "bangkok": ("Bangkok", "Thailand", "TH", 13.7563, 100.5018, "Asia/Bangkok"),
    "bali": ("Denpasar", "Indonesia", "ID", -8.6705, 115.2126, "Asia/Makassar"),
    "hong kong": ("Hong Kong", "Hong Kong", "HK", 22.3193, 114.1694, "Asia/Hong_Kong"),
    "dubai": ("Dubai", "United Arab Emirates", "AE", 25.2048, 55.2708, "Asia/Dubai"),
    "delhi": ("Delhi", "India", "IN", 28.6139, 77.209, "Asia/Kolkata"),
    "mumbai": ("Mumbai", "India", "IN", 19.076, 72.8777, "Asia/Kolkata"),
    "bengaluru": ("Bengaluru", "India", "IN", 12.9716, 77.5946, "Asia/Kolkata"),
    "hyderabad": ("Hyderabad", "India", "IN", 17.385, 78.4867, "Asia/Kolkata"),
    "goa": ("Panaji", "India", "IN", 15.4909, 73.8278, "Asia/Kolkata"),
    "jaipur": ("Jaipur", "India", "IN", 26.9124, 75.7873, "Asia/Kolkata"),
    "sydney": ("Sydney", "Australia", "AU", -33.8688, 151.2093, "Australia/Sydney"),
    "new york": ("New York", "United States", "US", 40.7128, -74.006, "America/New_York"),
    "los angeles": ("Los Angeles", "United States", "US", 34.0522, -118.2437, "America/Los_Angeles"),
    "san francisco": ("San Francisco", "United States", "US", 37.7749, -122.4194, "America/Los_Angeles"),
    "toronto": ("Toronto", "Canada", "CA", 43.6532, -79.3832, "America/Toronto"),
    "mexico city": ("Mexico City", "Mexico", "MX", 19.4326, -99.1332, "America/Mexico_City"),
    "rio de janeiro": ("Rio de Janeiro", "Brazil", "BR", -22.9068, -43.1729, "America/Sao_Paulo"),
    "cairo": ("Cairo", "Egypt", "EG", 30.0444, 31.2357, "Africa/Cairo"),
    "cape town": ("Cape Town", "South Africa", "ZA", -33.9249, 18.4241, "Africa/Johannesburg"),
}


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


async def _lookup(name: str) -> Place | None:
    resp = await get_client().get(
        GEOCODE_URL, params={"name": name, "count": 1, "language": "en", "format": "json"}
    )
    resp.raise_for_status()
    results = resp.json().get("results") or []
    if not results:
        return None
    r = results[0]
    return Place(
        name=r.get("name", name),
        country=r.get("country", ""),
        country_code=r.get("country_code", ""),
        lat=r["latitude"],
        lon=r["longitude"],
        timezone=r.get("timezone", ""),
    )


def _fallback(name: str) -> Place | None:
    row = _FALLBACK.get(name.strip().lower())
    if not row:
        return None
    n, country, cc, lat, lon, tz = row
    return Place(name=n, country=country, country_code=cc, lat=lat, lon=lon, timezone=tz)


async def geocode(name: str) -> Place | None:
    """Resolve a place name to coordinates; ``None`` if it cannot be pinned down."""
    name = (name or "").strip()
    if not name:
        return None
    try:
        place = await cache.get_or_set(
            f"geo:{name.lower()}", 7 * 86400, lambda: _lookup(name)
        )
    except Exception as exc:  # network down / rate-limited
        log.warning("geocode(%r) via API failed: %s", name, exc)
        return _fallback(name)
    return place or _fallback(name)
