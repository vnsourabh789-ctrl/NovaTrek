"""One shared, connection-pooled async HTTP client."""

from __future__ import annotations

import httpx

from novatrek import __version__

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            limits=httpx.Limits(max_connections=40, max_keepalive_connections=20),
            headers={"User-Agent": f"NovaTrek/{__version__}"},
            follow_redirects=True,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
