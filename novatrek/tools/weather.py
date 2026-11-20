"""Weather from Open-Meteo (keyless): live forecast, or last-year climate for a target month."""

from __future__ import annotations

import calendar
from datetime import date

from novatrek.cache import cache
from novatrek.http import get_client
from novatrek.models import MONTHS, Place

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

WMO = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Freezing drizzle", 61: "Light rain", 63: "Rain",
    65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain", 71: "Light snow",
    73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Rain showers",
    81: "Rain showers", 82: "Violent showers", 85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm, hail", 99: "Thunderstorm, hail",
}


def _round(v, nd=1):
    return None if v is None else round(float(v), nd)


def _advice(avg_hi: float | None, avg_lo: float | None, rain_days: int, n: int) -> list[str]:
    tips: list[str] = []
    if avg_hi is not None and avg_hi >= 31:
        tips.append("Hot days — plan outdoor sights early or late, carry water and sunscreen.")
    elif avg_hi is not None and avg_hi >= 24:
        tips.append("Warm and pleasant — light breathable clothing works well.")
    if avg_lo is not None and avg_lo <= 3:
        tips.append("Near-freezing nights — pack a warm coat, hat and gloves.")
    elif avg_lo is not None and avg_lo <= 12:
        tips.append("Cool evenings — bring a jacket or an extra layer.")
    if n and rain_days / n >= 0.35:
        tips.append("Frequent rain — pack a compact umbrella and keep indoor backups.")
    elif rain_days:
        tips.append("Occasional showers possible — a light rain shell is enough.")
    return tips or ["Mild, settled conditions expected — comfortable for sightseeing."]


def _summarise(kind: str, label: str, daily: list[dict], current: dict | None) -> dict:
    his = [d["hi"] for d in daily if d["hi"] is not None]
    los = [d["lo"] for d in daily if d["lo"] is not None]
    rain_days = sum(1 for d in daily if (d["rain"] or 0) >= 1.0)
    avg_hi = round(sum(his) / len(his), 1) if his else None
    avg_lo = round(sum(los) / len(los), 1) if los else None
    return {
        "available": True,
        "kind": kind,
        "label": label,
        "current": current,
        "daily": daily[:7],
        "avg_hi": avg_hi,
        "avg_lo": avg_lo,
        "rain_days": rain_days,
        "sample_days": len(daily),
        "advice": _advice(avg_hi, avg_lo, rain_days, len(daily)),
        "provider": "Open-Meteo",
    }


async def _forecast(place: Place) -> dict:
    resp = await get_client().get(
        FORECAST_URL,
        params={
            "latitude": place.lat,
            "longitude": place.lon,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
            "forecast_days": 7,
            "timezone": "auto",
        },
    )
    resp.raise_for_status()
    j = resp.json()
    d = j["daily"]
    daily = [
        {
            "date": d["time"][i],
            "hi": _round(d["temperature_2m_max"][i]),
            "lo": _round(d["temperature_2m_min"][i]),
            "rain": _round(d["precipitation_sum"][i]),
            "cond": WMO.get(d["weather_code"][i], "—"),
        }
        for i in range(len(d["time"]))
    ]
    c = j.get("current") or {}
    current = {
        "temp": _round(c.get("temperature_2m")),
        "humidity": c.get("relative_humidity_2m"),
        "wind": _round(c.get("wind_speed_10m")),
        "cond": WMO.get(c.get("weather_code"), "—"),
    }
    return _summarise("forecast", "Live 7-day forecast", daily, current)


async def _climate(place: Place, month: str) -> dict:
    today = date.today()
    m = MONTHS.index(month) + 1
    year = today.year if m < today.month else today.year - 1
    last = calendar.monthrange(year, m)[1]
    resp = await get_client().get(
        ARCHIVE_URL,
        params={
            "latitude": place.lat,
            "longitude": place.lon,
            "start_date": f"{year}-{m:02d}-01",
            "end_date": f"{year}-{m:02d}-{last:02d}",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "auto",
        },
    )
    resp.raise_for_status()
    d = resp.json()["daily"]
    daily = [
        {
            "date": d["time"][i],
            "hi": _round(d["temperature_2m_max"][i]),
            "lo": _round(d["temperature_2m_min"][i]),
            "rain": _round(d["precipitation_sum"][i]),
            "cond": "Rain" if (d["precipitation_sum"][i] or 0) >= 1 else "Dry",
        }
        for i in range(len(d["time"]))
    ]
    out = _summarise("climate", f"Typical {month} climate (based on {year})", daily, None)
    out["daily"] = daily[:: max(1, len(daily) // 7)][:7]  # evenly sampled across the month
    return out


async def fetch_weather(place: Place, month: str | None) -> dict:
    """Live forecast unless the trip is in a different month — then use climate data."""
    today = date.today()
    use_climate = bool(month) and month != MONTHS[today.month - 1]
    if use_climate:
        return await cache.get_or_set(
            f"wx:c:{place.lat:.2f},{place.lon:.2f}:{month}",
            30 * 86400,
            lambda: _climate(place, month),
        )
    return await cache.get_or_set(
        f"wx:f:{place.lat:.2f},{place.lon:.2f}", 1800, lambda: _forecast(place)
    )
