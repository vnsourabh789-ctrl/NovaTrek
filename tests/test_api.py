import json

from fastapi.testclient import TestClient

from novatrek.main import app


def _events(resp):
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]


def test_full_plan_stream_save_chat_export(fake_network):
    with TestClient(app) as client:
        r = client.post("/api/plan", json={
            "message": "7 days in Paris from Delhi in April for 2 people, mid-range, food"})
        assert r.status_code == 200
        ev = _events(r)
        assert ev[0]["type"] == "start" and ev[-1]["type"] == "result"
        done = {e["id"] for e in ev if e["type"] == "stage" and e["status"] == "done"}
        assert done == {"intent", "flights", "weather", "hotels", "itinerary", "budget"}

        trip = ev[-1]["trip"]
        assert trip["destination"]["name"] == "Paris"
        assert len(trip["itinerary"]["days"]) == 7
        assert trip["flights"]["available"] and trip["flights"]["distance_km"] > 6000
        assert trip["budget"]["total"] > 0 and trip["engine"] == "offline"

        tid = trip["id"]
        assert client.get("/api/trips").json()[0]["id"] == tid
        assert client.get(f"/api/trips/{tid}").json()["title"] == trip["title"]

        reply = client.post(f"/api/trips/{tid}/chat", json={"message": "what is the budget?"}).json()
        assert "$" in reply["reply"] and reply["source"] == "offline"
        assert len(client.get(f"/api/trips/{tid}").json()["chat"]) == 2

        md = client.get(f"/api/trips/{tid}/export.md")
        assert md.status_code == 200 and "## Itinerary" in md.text

        assert client.delete(f"/api/trips/{tid}").status_code == 204
        assert client.get(f"/api/trips/{tid}").status_code == 404


def test_unplannable_message_returns_friendly_error(fake_network):
    with TestClient(app) as client:
        ev = _events(client.post("/api/plan", json={"message": "hello there friend"}))
        assert ev[-1]["type"] == "error" and "where you want to go" in ev[-1]["message"]


def test_validation_and_bad_ids():
    with TestClient(app) as client:
        assert client.post("/api/plan", json={"message": "x"}).status_code == 422
        assert client.get("/api/trips/not-a-valid-id").status_code == 422


def test_health_and_headers():
    with TestClient(app) as client:
        r = client.get("/api/health")
        assert r.json()["engine"] == "offline"
        assert "script-src 'self'" in r.headers["content-security-policy"]
