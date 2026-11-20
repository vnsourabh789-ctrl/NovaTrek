# ◈ NovaTrek

**Autonomous multi-agent travel mission control.** Describe a trip in plain English; a squad of agents scouts flights, weather and stays *in parallel*, then composes an itinerary and a budget — streamed live to a futuristic dashboard.

> A ground-up redesign of [TravelBrain](https://github.com/KalyanM45/TravelBrain-Multi-Agent-AI-Travel-Planner). See [NOTICE.md](NOTICE.md).

## Why it's different

| | TravelBrain (original) | **NovaTrek** |
|---|---|---|
| Agent flow | 5 agents strictly in sequence | Flights ‖ Weather ‖ Hotels run **concurrently** (≈2 s end-to-end offline; with an LLM, dominated by its 3 calls) |
| Feedback | One blocking request, ~60 s of nothing | **Live SSE stream** — each agent lights up with its timing |
| Required setup | Groq + Tavily + AviationStack + OpenWeather keys **and** PostgreSQL | **Zero keys to start.** Optional LLM key. SQLite built in |
| LLM calls per plan | 5 | **3** (intent, hotels, itinerary) — flights, weather and budget are deterministic |
| Weather | Paid API | [Open-Meteo](https://open-meteo.com) — free, keyless, live forecast *or* monthly climate for your travel month |
| Budget | LLM-written prose | **Computed** from route model, hotel rates and spend tiers — adds up, every time |
| Output | Markdown blob | Structured JSON → route map, fare gauge, weather strip, donut budget, timeline |
| Dependencies | LangChain, LangGraph, MCP, Redis, psycopg… | FastAPI, httpx, pydantic — **6 packages** |
| LLM provider | Groq only | Any OpenAI-compatible API (Groq, OpenAI, OpenRouter, Ollama…) |
| Robustness | A failing agent fails the plan | Every agent degrades gracefully; the plan always completes |

## Quick start

**One click:** double-click `start.bat` (Windows) or run `./start.sh` (macOS/Linux). It creates the venv, installs dependencies, and opens the app.

> **"Failed to fetch" in the UI?** The server isn't running (or the page was opened from a stopped server). Start it and reload. It is never caused by a missing API key — without a key NovaTrek simply runs in offline mode.

Manual steps:

```bash
git clone <your-repo-url> novatrek && cd novatrek
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m novatrek
```

Open **http://127.0.0.1:8000**. That's it — it works immediately in *offline simulation* mode (real weather + route maths, template itinerary).

### Unlock AI plans

```bash
cp .env.example .env      # then set LLM_API_KEY
```

Free option: create a key at [console.groq.com](https://console.groq.com) and paste it as `LLM_API_KEY`. For others, change `LLM_BASE_URL` / `LLM_MODEL`:

```dotenv
# OpenAI
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
# Local Ollama (no key needed)
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3.1
```

Your old `GROQ_API_KEY` / `GROQ_MODEL` variables are still honoured.

### Windows .exe (no Python needed)

Run `build_exe.bat` to produce `dist\NovaTrek.exe` (~26 MB). Double-click it: it starts the server, opens your browser, and keeps `.env` and `data\` next to the exe. To enable AI plans, put a `.env` file containing `LLM_API_KEY=...` beside the exe.

On GitHub, push a tag (`git tag v2.0.0 && git push --tags`) and the **Build Windows exe** workflow attaches `NovaTrek.exe` to the release automatically.

### Docker

```bash
docker compose up --build        # http://localhost:8000, data persisted in a volume
```

## Architecture

```
                 ┌──────────── SSE stream ────────────┐
 Browser ──POST /api/plan──▶ Orchestrator             ▼
                              │
        1. Intent agent  (LLM → JSON, regex fallback)
                              │  geocode origin+dest (cached, single-flight)
              ┌───────────────┼───────────────┐
        2. Flight agent  Weather agent   Hotel agent      ← run concurrently
         great-circle     Open-Meteo      LLM (+Tavily)
         model + IATA     forecast/       tier-aware
                          climate
              └───────────────┼───────────────┘
        3. Itinerary agent (LLM, weather- & area-aware, template fallback)
                              │
        4. Budget engine  (pure code)  →  SQLite  →  result event
```

```
novatrek/
├── main.py            FastAPI app, SSE endpoint, security headers, rate limit
├── agents/            intent · flights · weather · hotels · itinerary · budget · copilot · orchestrator
├── tools/             geo (Open-Meteo geocoding) · weather · flights (airports + route model) · search (Tavily)
├── llm.py             provider-agnostic client: retries, JSON mode fallback, robust JSON extraction
├── cache.py           TTL cache with single-flight de-duplication (no Redis)
├── store.py           SQLite (WAL) mission log
├── models.py          lenient pydantic models — LLM output is coerced & clamped, never trusted
└── web/               zero-build UI (vanilla JS + CSS, CSP-safe, no innerHTML)
```

**Efficiency choices**
- Independent agents overlap, so latency ≈ `intent + max(flights, weather, hotels) + itinerary`.
- One pooled `httpx` client; geocodes cached 7 days, forecasts 30 min, climate 30 days; concurrent identical lookups share one request.
- Deterministic work (distance, fares, budget, advice) never touches the LLM — cheaper, faster, reproducible.
- Disconnecting mid-plan cancels the pipeline so no tokens are wasted.

**Safety**: model output is validated/clamped; the UI renders it as text nodes only; strict CSP; per-IP rate limiting; prompt text is fenced as data.

## Usage

- Type a request (or click an example), press **Enter**. Use **⚙ Builder** to fill fields instead.
- Missions are saved to the sidebar; reopen any, **export Markdown**, **print**, or ask the **copilot** follow-ups ("how can I cut the cost?").
- Deep-link a mission with `#trip=<id>`.

### API

| Method | Path | |
|---|---|---|
| POST | `/api/plan` | `{message}` → SSE: `start`, `stage`*, `result` \| `error` |
| GET | `/api/trips` · `/api/trips/{id}` | list / fetch |
| DELETE | `/api/trips/{id}` | delete |
| GET | `/api/trips/{id}/export.md` | Markdown download |
| POST | `/api/trips/{id}/chat` | `{message}` → `{reply}` |
| GET | `/api/health` | engine mode, cache stats |

Interactive docs at `/api/docs`.

## Development

```bash
pip install -r requirements.txt pytest
pytest -q        # 14 tests, fully offline
```

## Honest limitations

- **Fares are model-based estimates**, not live quotes (no paid flight API). The UI says so.
- **Hotel suggestions are not live availability.** With an LLM they are real, well-known properties where the model is confident; offline they are labelled illustrative.
- Open-Meteo's free tier is for non-commercial use; check their terms before commercial deployment.

## License

GPL-3.0 — see [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
