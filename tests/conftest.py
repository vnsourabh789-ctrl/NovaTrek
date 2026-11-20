import os
import tempfile

# Must run before novatrek is imported: force offline mode + throwaway database.
os.environ["LLM_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""
os.environ["TAVILY_API_KEY"] = ""
os.environ["LLM_BASE_URL"] = "https://llm.invalid/v1"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["RATE_LIMIT_PER_MIN"] = "0"

import pytest  # noqa: E402

from novatrek.models import Place  # noqa: E402


@pytest.fixture
def fake_network(monkeypatch):
    """Replace every outbound call with deterministic local data."""
    from novatrek.agents import orchestrator, weather as weather_agent

    places = {
        "paris": Place(name="Paris", country="France", country_code="FR", lat=48.8566, lon=2.3522),
        "delhi": Place(name="Delhi", country="India", country_code="IN", lat=28.6139, lon=77.209),
    }

    async def geocode(name):
        return places.get(name.strip().lower())

    async def fetch_weather(place, month):
        return {"available": True, "kind": "climate", "label": "Typical April climate",
                "current": None, "daily": [], "avg_hi": 17.0, "avg_lo": 8.0, "rain_days": 9,
                "sample_days": 30, "advice": ["Pack a light rain shell."], "source": "Open-Meteo"}

    monkeypatch.setattr(orchestrator, "geocode", geocode)
    monkeypatch.setattr(weather_agent, "fetch_weather", fetch_weather)
    return places
