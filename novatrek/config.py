"""Runtime configuration, read once from the environment (and .env)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# When packaged with PyInstaller, keep .env and the database next to NovaTrek.exe
# (the bundle itself lives in a temp folder that is deleted on exit).
if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env")
load_dotenv()  # also honour a .env in the current directory


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


def _first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default


@dataclass(frozen=True)
class Settings:
    # LLM — any OpenAI-compatible /chat/completions endpoint.
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    llm_json_mode: bool
    llm_timeout: float
    # Optional grounding for hotel suggestions.
    tavily_api_key: str
    # Storage / server
    db_path: Path
    host: str
    port: int
    reload: bool
    rate_limit_per_min: int
    cors_origins: tuple[str, ...]

    @property
    def llm_enabled(self) -> bool:
        # Local servers (Ollama, LM Studio) accept any key, so a base URL on
        # localhost counts as "enabled" even with an empty key.
        local = "localhost" in self.llm_base_url or "127.0.0.1" in self.llm_base_url
        return bool(self.llm_api_key) or local


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    origins = tuple(
        o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()
    )
    return Settings(
        # GROQ_API_KEY is accepted so the original TravelBrain .env keeps working.
        llm_api_key=_first("LLM_API_KEY", "GROQ_API_KEY"),
        llm_base_url=_first(
            "LLM_BASE_URL", default="https://api.groq.com/openai/v1"
        ).rstrip("/"),
        llm_model=_first("LLM_MODEL", "GROQ_MODEL", default="llama-3.3-70b-versatile"),
        llm_json_mode=_bool("LLM_JSON_MODE", True),
        llm_timeout=float(os.getenv("LLM_TIMEOUT", "45")),
        tavily_api_key=_first("TAVILY_API_KEY"),
        db_path=Path(os.getenv("DB_PATH", str(ROOT / "data" / "novatrek.db"))),
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=_bool("RELOAD", False),
        rate_limit_per_min=int(os.getenv("RATE_LIMIT_PER_MIN", "12")),
        cors_origins=origins,
    )
