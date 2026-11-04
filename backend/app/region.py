"""Probe catalog models for Hong Kong region blocks. Never log the key."""

from __future__ import annotations

from typing import Any

import httpx

from .catalog import MODELS, catalog_available_in_hong_kong
from .openrouter_key import load_openrouter_api_key

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
PROBE_TIMEOUT_SECONDS = 8.0
PROBE_MAX_TOKENS = 1

_cache_hidden: frozenset[str] | None = None
_cache_ok: frozenset[str] | None = None
_cache_ran = False


def reset_probe_cache() -> None:
    global _cache_hidden, _cache_ok, _cache_ran
    _cache_hidden = None
    _cache_ok = None
    _cache_ran = False


def _error_message(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if isinstance(error, str):
        return error
    if isinstance(error, dict):
        raw = error.get("message")
        if isinstance(raw, str):
            return raw
    return ""


def is_region_unavailable(status_code: int | None, payload: Any = None) -> bool:
    if status_code != 403:
        return False
    lowered = _error_message(payload).lower()
    return "region" in lowered or "not available in your" in lowered


def _probe_one(api_key: str, model_id: str) -> tuple[int | None, Any]:
    try:
        response = httpx.post(
            OPENROUTER_CHAT_URL,
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": PROBE_MAX_TOKENS,
                "stream": False,
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=PROBE_TIMEOUT_SECONDS,
            follow_redirects=False,
        )
        status_code = response.status_code
    except Exception:
        return None, None
    body: Any = None
    try:
        body = response.json()
    except Exception:
        body = None
    return status_code, body


def _probe_catalog_ids_impl(api_key: str | None) -> tuple[frozenset[str], frozenset[str]]:
    """Return (hidden_ids, ok_ids). Never logs or returns the key."""
    if not api_key:
        return frozenset(), frozenset()
    hidden: set[str] = set()
    ok: set[str] = set()
    for model in MODELS:
        model_id = str(model["id"])
        if not catalog_available_in_hong_kong(model):
            hidden.add(model_id)
            continue
        status_code, body = _probe_one(api_key, model_id)
        if is_region_unavailable(status_code, body):
            hidden.add(model_id)
        elif status_code == 200:
            ok.add(model_id)
    return frozenset(hidden), frozenset(ok)


def probe_catalog_ids(api_key: str | None) -> tuple[frozenset[str], frozenset[str]]:
    return _probe_catalog_ids_impl(api_key)


def extra_hidden_ids(*, force: bool = False) -> frozenset[str]:
    """Probe when a key exists. Cached. Empty when no key."""
    global _cache_hidden, _cache_ok, _cache_ran
    if _cache_ran and not force:
        return _cache_hidden or frozenset()
    try:
        api_key = load_openrouter_api_key()
    except Exception:
        api_key = None
    hidden, ok = probe_catalog_ids(api_key)
    _cache_hidden = hidden
    _cache_ok = ok
    _cache_ran = True
    return hidden
