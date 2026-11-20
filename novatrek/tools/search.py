"""Optional web grounding via Tavily for hotel suggestions."""

from __future__ import annotations

import logging

from novatrek.cache import cache
from novatrek.config import get_settings
from novatrek.http import get_client

log = logging.getLogger("novatrek.search")


async def _search(query: str) -> str:
    key = get_settings().tavily_api_key
    resp = await get_client().post(
        "https://api.tavily.com/search",
        json={"query": query, "max_results": 5, "search_depth": "basic"},
        headers={"Authorization": f"Bearer {key}"},
        timeout=12.0,
    )
    resp.raise_for_status()
    rows = resp.json().get("results", [])
    return "\n".join(f"- {r.get('title','')}: {r.get('content','')[:240]}" for r in rows)[:1800]


async def web_snippets(query: str) -> str:
    """Return short search snippets, or '' when no key is set / the call fails."""
    if not get_settings().tavily_api_key:
        return ""
    try:
        return await cache.get_or_set(f"web:{query.lower()}", 6 * 3600, lambda: _search(query))
    except Exception as exc:
        log.warning("web search failed: %s", exc)
        return ""
