"""Resolve the OpenRouter API key and check it without exposing the secret.

Order: process environment ``OPENROUTER_API_KEY``, then the file named by
``OPENROUTER_ENV_FILE`` when that variable is set, then
``/Users/mikelam/firstRepo/openrouter_key/.env_RAG_portal`` when the file exists.

A configured file may be dotenv (``OPENROUTER_API_KEY`` or ``OPENROUTER_KEY``)
or a single raw key line. Blank lines and comments are ignored. Callers receive
only a boolean and a short status. The key and the provider body stay out of
return values, logs, and error text.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

MAC_KEY_PATH = Path("/Users/mikelam/firstRepo/openrouter_key/.env_RAG_portal")
# /api/v1/models is public and returns 200 with no key. /api/v1/key requires the
# bearer token, so a 200 means OpenRouter accepted it. The body can contain a
# shortened label of the key, so callers must not read or return it.
OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"
OPENROUTER_TIMEOUT_SECONDS = 5.0

STATUS_ACCEPTED = "key_accepted"
STATUS_REJECTED = "key_rejected"
STATUS_NOT_CONFIGURED = "not_configured"

_NAMED_KEYS = ("OPENROUTER_API_KEY", "OPENROUTER_KEY")


def _strip_wrapping_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()
    return value


def parse_key_text(text: str) -> str | None:
    """Return the key from dotenv text or a one-line raw key file."""
    named: dict[str, str] = {}
    raw_key: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].strip()
        name, separator, value = stripped.partition("=")
        if separator and name.strip() in _NAMED_KEYS:
            named[name.strip()] = _strip_wrapping_quotes(value)
            continue
        if separator:
            continue
        if raw_key is None:
            raw_key = _strip_wrapping_quotes(stripped)
    for name in _NAMED_KEYS:
        if named.get(name):
            return named[name]
    if raw_key:
        return raw_key
    return None


def read_key_file(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    return parse_key_text(text)


def load_openrouter_api_key() -> str | None:
    """Return the configured key, or None when no source has one."""
    from_env = _strip_wrapping_quotes(os.environ.get("OPENROUTER_API_KEY", ""))
    if from_env:
        return from_env
    env_file = os.environ.get("OPENROUTER_ENV_FILE", "").strip()
    if env_file:
        return read_key_file(Path(env_file))
    if MAC_KEY_PATH.is_file():
        return read_key_file(MAC_KEY_PATH)
    return None


def probe_openrouter(api_key: str | None, *, timeout: float = OPENROUTER_TIMEOUT_SECONDS) -> str:
    """Ask OpenRouter whether the key is accepted. Never return provider text."""
    if not api_key:
        return STATUS_NOT_CONFIGURED
    try:
        response = httpx.get(
            OPENROUTER_KEY_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            follow_redirects=False,
        )
        status_code = response.status_code
    except Exception:
        return STATUS_REJECTED
    if status_code == 200:
        return STATUS_ACCEPTED
    return STATUS_REJECTED


def openrouter_status_fields(*, probe: bool = True) -> dict[str, object]:
    """Public fields only: a boolean and, when probed, a short status."""
    try:
        api_key = load_openrouter_api_key()
    except Exception:
        api_key = None
    configured = bool(api_key)
    fields: dict[str, object] = {"openrouter_configured": configured}
    if not probe:
        return fields
    try:
        fields["openrouter_status"] = probe_openrouter(api_key)
    except Exception:
        fields["openrouter_status"] = STATUS_REJECTED if configured else STATUS_NOT_CONFIGURED
    return fields
