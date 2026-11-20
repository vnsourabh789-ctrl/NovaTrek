"""Minimal provider-agnostic LLM client (any OpenAI-compatible endpoint).

Works with Groq, OpenAI, OpenRouter, Together, Ollama, LM Studio, vLLM...
Agents catch ``LLMUnavailable`` / ``LLMError`` and fall back to offline
heuristics, so the app still works with no key configured.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

import httpx

from novatrek.config import get_settings
from novatrek.http import get_client

log = logging.getLogger("novatrek.llm")


class LLMUnavailable(Exception):
    """No LLM configured."""


class LLMError(Exception):
    """The provider failed or returned something unusable."""


def extract_json(text: str) -> dict:
    """Parse a JSON object out of model output, tolerating code fences/prose."""
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise LLMError("model returned no JSON object")
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError(f"invalid JSON from model: {exc}") from exc
    if not isinstance(data, dict):
        raise LLMError("model returned JSON that is not an object")
    return data


async def chat(
    system: str,
    user: str,
    *,
    json_mode: bool = False,
    max_tokens: int = 1500,
    temperature: float = 0.4,
) -> str:
    s = get_settings()
    if not s.llm_enabled:
        raise LLMUnavailable("LLM_API_KEY is not set")

    payload: dict = {
        "model": s.llm_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode and s.llm_json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {"Authorization": f"Bearer {s.llm_api_key or 'local'}"}
    url = f"{s.llm_base_url}/chat/completions"
    last: Exception | None = None

    for attempt in range(3):
        try:
            resp = await get_client().post(
                url, json=payload, headers=headers, timeout=s.llm_timeout
            )
        except httpx.HTTPError as exc:
            last = exc
            await asyncio.sleep(0.6 * (attempt + 1))
            continue

        if resp.status_code in (429, 500, 502, 503, 504):
            last = LLMError(f"HTTP {resp.status_code}")
            try:
                wait = min(8.0, float(resp.headers.get("retry-after", 0)))
            except ValueError:
                wait = 0.0
            await asyncio.sleep(max(wait, 0.8 * (attempt + 1)))
            continue

        if resp.status_code == 400 and "response_format" in payload:
            # Some providers reject JSON mode; retry once without it.
            payload.pop("response_format")
            continue

        if resp.status_code >= 400:
            raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")

        try:
            return resp.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError("unexpected response shape") from exc

    raise LLMError(f"provider unreachable after retries: {last}")


async def ask_json(system: str, user: str, *, max_tokens: int = 1500) -> dict:
    """Ask for a JSON object; one stricter retry if the first reply is malformed."""
    text = await chat(system, user, json_mode=True, max_tokens=max_tokens)
    try:
        return extract_json(text)
    except LLMError:
        log.warning("malformed JSON from model, retrying once")
        text = await chat(
            system + "\nReply with a single valid JSON object and nothing else.",
            user,
            json_mode=True,
            max_tokens=max_tokens,
            temperature=0.0,
        )
        return extract_json(text)
