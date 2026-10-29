"""Load OPENROUTER_API_KEY from the environment or a local file.

The value is never logged. Tests skip the file unless LINGOCOACH_ENV_FILE is set,
so a developer key on disk does not turn the fixture suite into live calls.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

def _candidates() -> list[Path]:
    here = Path(__file__).resolve().parents[1]
    home = Path.home()
    raw = [
        os.environ.get("LINGOCOACH_ENV_FILE", "").strip(),
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
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        return value.strip()
    lines = [line.strip().strip("\r") for line in text.splitlines() if line.strip()]
    if len(lines) == 1 and " " not in lines[0] and "=" not in lines[0]:
        return lines[0]
    return ""


def ensure_openrouter_key() -> bool:
    if os.environ.get("OPENROUTER_API_KEY", "").strip():
        return True
    if "pytest" in sys.modules and not os.environ.get("LINGOCOACH_ENV_FILE"):
        return False
    for path in _candidates():
        try:
            if not path.is_file():
                continue
            key = parse_key_text(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if key:
            os.environ["OPENROUTER_API_KEY"] = key
            return True
    return False
