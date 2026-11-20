import asyncio

import pytest

from novatrek.agents import budget
from novatrek.agents.intent import parse_offline
from novatrek.cache import TTLCache
from novatrek.llm import LLMError, extract_json
from novatrek.models import Hotel, Intent
from novatrek.tools import flights as flight_tool
from novatrek.tools.geo import haversine


def test_parse_offline_full_sentence():
    d = parse_offline("Plan a 10 day trip to Rome from Delhi in April for 2 people, luxury, food")
    assert d["destination"] == "Rome"
    assert d["origin"] == "Delhi"
    assert d["days"] == 10 and d["month"] == "april"
    assert d["travelers"] == 2 and d["budget"] == "luxury"
    assert "food" in d["interests"]


def test_parse_offline_no_destination():
    assert parse_offline("hello there")["destination"] == ""


def test_intent_clamps_and_coerces():
    i = Intent.model_validate({"destination": "Tokyo", "days": "45", "travelers": 0,
                               "budget": "super cheap", "month": "sept", "interests": "food, art"})
    assert (i.days, i.travelers, i.budget, i.month) == (21, 1, "budget", "September")
    assert i.interests == ["food", "art"]


def test_hotel_price_coercion():
    assert Hotel.model_validate({"name": "X", "price_per_night": "$1,250 / night"}).price_per_night == 1250


def test_extract_json_variants():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! {"a": 2} hope that helps') == {"a": 2}
    with pytest.raises(LLMError):
        extract_json("no json here")


def test_haversine_paris_london():
    assert 330 < haversine(48.8566, 2.3522, 51.5072, -0.1276) < 350


def test_flight_estimate_scales_with_distance():
    from novatrek.models import Place
    a = Place(name="A", lat=48.85, lon=2.35)
    near = Place(name="B", lat=51.5, lon=-0.12)
    far = Place(name="C", lat=-33.87, lon=151.2)
    short = flight_tool.estimate(a, near, "mid", None, 1)
    long = flight_tool.estimate(a, far, "mid", None, 1)
    assert short["fare_mid"] < long["fare_mid"] and short["duration_h"] < long["duration_h"]
    assert long["stops"] >= 1


def test_budget_adds_up_and_scales_with_travellers():
    intent = Intent(destination="X", days=5, travelers=2, budget="mid")
    hotels = {"hotels": [{"tier": "mid", "price_per_night": 150}]}
    flights = {"available": True, "total_round_trip": 1000}
    b = budget.compute(intent, flights, hotels, {"days": []})
    assert sum(i["amount"] for i in b["items"]) in range(b["total"] - 3, b["total"] + 4)
    solo = budget.compute(intent.model_copy(update={"travelers": 1}), flights, hotels, {"days": []})
    assert b["total"] > solo["total"]


def test_cache_single_flight_and_ttl():
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return "v"

    async def go():
        c = TTLCache()
        out = await asyncio.gather(*[c.get_or_set("k", 10, factory) for _ in range(20)])
        assert out == ["v"] * 20 and calls == 1
        await c.get_or_set("k", 10, factory)
        assert calls == 1  # served from cache

    asyncio.run(go())


def test_cache_does_not_store_failures():
    async def boom():
        raise RuntimeError("x")

    async def go():
        c = TTLCache()
        with pytest.raises(RuntimeError):
            await c.get_or_set("k", 10, boom)
        assert c.get("k") is not None and c.stats()["items"] == 0

    asyncio.run(go())
