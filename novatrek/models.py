"""Typed data shapes shared by every agent.

LLM output is untrusted, so every model coerces leniently (``"$120"`` -> 120.0)
and clamps to sane ranges instead of failing the whole plan.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, field_validator

Tier = Literal["budget", "mid", "luxury"]

MONTHS = [
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
]


def to_num(value, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d[\d,]*\.?\d*", str(value))
    if not match:
        return default
    try:
        return float(match.group().replace(",", ""))
    except ValueError:
        return default


def to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(str(v) for v in value)
    return str(value).strip()


Num = Annotated[float, BeforeValidator(to_num)]
Text = Annotated[str, BeforeValidator(to_text)]


def normalize_tier(value) -> str:
    text = str(value or "").lower()
    if any(w in text for w in ("lux", "high", "premium", "splurge", "upscale", "5")):
        return "luxury"
    if any(w in text for w in ("budget", "cheap", "low", "backpack", "econom", "shoestring")):
        return "budget"
    return "mid"


def normalize_month(value) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    for name in MONTHS:
        if text.startswith(name.lower()[:3]):
            return name
    return None


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Place(_Lenient):
    name: str
    country: str = ""
    country_code: str = ""
    lat: float
    lon: float
    timezone: str = ""


class Intent(_Lenient):
    destination: str
    origin: str | None = None
    days: int = 5
    month: str | None = None
    travelers: int = 1
    budget: Tier = "mid"
    interests: list[str] = []
    scope: str = ""

    @field_validator("destination", mode="before")
    @classmethod
    def _dest(cls, v):
        v = to_text(v)
        if not v or v.lower() in ("null", "none", "unknown", "n/a"):
            raise ValueError("destination missing")
        return v[:80]

    @field_validator("origin", mode="before")
    @classmethod
    def _origin(cls, v):
        v = to_text(v)
        return None if not v or v.lower() in ("null", "none", "unknown", "n/a") else v[:80]

    @field_validator("days", mode="before")
    @classmethod
    def _days(cls, v):
        return max(1, min(21, int(to_num(v, 5))))

    @field_validator("travelers", mode="before")
    @classmethod
    def _travelers(cls, v):
        return max(1, min(12, int(to_num(v, 1))))

    @field_validator("budget", mode="before")
    @classmethod
    def _budget(cls, v):
        return normalize_tier(v)

    @field_validator("month", mode="before")
    @classmethod
    def _month(cls, v):
        return normalize_month(v)

    @field_validator("interests", mode="before")
    @classmethod
    def _interests(cls, v):
        if isinstance(v, str):
            v = re.split(r"[,;/]", v)
        if not isinstance(v, list):
            return []
        return [to_text(i).lower()[:30] for i in v if to_text(i)][:6]


class Hotel(_Lenient):
    name: Text
    area: Text = ""
    tier: Text = "mid"
    price_per_night: Num = 0.0
    why: Text = ""

    @field_validator("tier", mode="before")
    @classmethod
    def _tier(cls, v):
        return normalize_tier(v)


class Day(_Lenient):
    day: int = 0
    title: Text = ""
    theme: Text = ""
    morning: Text = ""
    afternoon: Text = ""
    evening: Text = ""
    est_cost: Num = 0.0
    tip: Text = ""

    @field_validator("day", mode="before")
    @classmethod
    def _day(cls, v):
        return int(to_num(v, 0))


class Itinerary(_Lenient):
    summary: Text = ""
    highlights: list[Text] = []
    days: list[Day]
    packing: list[Text] = []
    tips: list[Text] = []


class PlanError(Exception):
    """A problem the user can fix by rephrasing (shown verbatim in the UI)."""
