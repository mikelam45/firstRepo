"""Load OPENROUTER_API_KEY from the environment or a local file.

The value is never logged or returned to the client. Tests skip disk files
unless LINGOCOACH_ENV_FILE is set, so a developer key on disk does not turn
the fixture suite into live calls.

VPS: systemd EnvironmentFile=~/lingocoach.env is a snapshot at process start
and does not accept ``export KEY=value`` lines. This loader also reads
``~/lingocoach.env`` and ``voice-chat/.env`` itself, strips wrapping
quotes/spaces (same idea as TOTP ``normalize_secret``), and accepts optional
``export``. Mac paths are still tried; they simply do not exist on Linux.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def normalize_key(raw: str | None) -> str:
    """Strip wrapping quotes/spaces/BOM/Bearer, like TOTP secret cleanup.

    systemd EnvironmentFile and shell ``export`` often leave quotes on the
    value. OpenRouter then returns 401 for ``"sk-or-…"`` and the UI used to
    call that a wrong key. Never log the result.
    """
    if not raw:
        return ""
    text = str(raw).replace("\r", "").strip().lstrip("\ufeff")
    for _ in range(2):
        text = text.strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
            text = text[1:-1]
        else:
            break
    text = text.strip()
    if text.lower().startswith("bearer "):
        text = text[7:].strip()
    return text


def _candidates() -> list[Path]:
    here = Path(__file__).resolve().parents[1]
    home = Path.home()
    raw = [
        os.environ.get("LINGOCOACH_ENV_FILE", "").strip(),
        str(home / "lingocoach.env"),
        "/Users/mikelam/firstRepo/openrouter_key/.env_voice_chat",
        "/Users/mikelam/firstRepo/voice-chat/.env",
        str(home / "firstRepo" / "openrouter_key" / ".env_voice_chat"),
        str(here.parent / "openrouter_key" / ".env_voice_chat"),
        str(here / ".env"),
    ]
    found: list[Path] = []
    seen: set[str] = set()
    for item in raw:
        if not item or item in seen:
            continue
        seen.add(item)
        found.append(Path(item))
    return found


def parse_key_text(text: str) -> str:
    for raw in text.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if not line.startswith("OPENROUTER_API_KEY="):
            continue
        value = line.split("=", 1)[1].strip().strip("\r")
        quoted = len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}
        if not quoted and " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        return normalize_key(value)
    lines = [line.strip().strip("\r") for line in text.splitlines() if line.strip()]
    if len(lines) == 1 and " " not in lines[0] and "=" not in lines[0]:
        return normalize_key(lines[0])
    return ""


def _skip_disk() -> bool:
    if os.environ.get("LINGOCOACH_ENV_FILE", "").strip():
        return False
    return "pytest" in sys.modules


def _read_key(path: Path) -> str:
    try:
        if not path.is_file():
            return ""
        return parse_key_text(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return ""


def current_openrouter_key() -> str:
    """Normalized key now in the environment, or empty. Never log it."""
    return normalize_key(os.environ.get("OPENROUTER_API_KEY", ""))


def ensure_openrouter_key() -> bool:
    """Load a usable key into ``os.environ``. Disk files refresh each call.

    File order matches ``run-local.sh``: ``LINGOCOACH_ENV_FILE``,
    ``~/lingocoach.env``, Mac paths, then ``voice-chat/.env``. A readable
    file wins over a stale systemd snapshot so Check can pick up an edit
    without a restart when the file is the source. Env-only launches
    (``-e OPENROUTER_API_KEY`` with no file) still work.
    """
    if not _skip_disk():
        for path in _candidates():
            key = _read_key(path)
            if key:
                os.environ["OPENROUTER_API_KEY"] = key
                return True
    existing = current_openrouter_key()
    if existing:
        os.environ["OPENROUTER_API_KEY"] = existing
        return True
    return False


def missing_key_reason() -> str:
    """``no_key`` or ``path``. Call when ``ensure_openrouter_key`` is false.

    ``path``: no candidate file exists (Mac path on Linux, or the VPS env
    file was never created). ``no_key``: a file exists but has no usable
    ``OPENROUTER_API_KEY`` assignment. Never returns the key.
    """
    if _skip_disk():
        return "no_key"
    for path in _candidates():
        try:
            if path.is_file():
                return "no_key"
        except OSError:
            continue
    return "path"
