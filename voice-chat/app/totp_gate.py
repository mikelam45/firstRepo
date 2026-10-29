"""TOTP unlock gate for the voice-chat UI and API.

Secret sources (never logged), first match wins:
1. LINGOCOACH_TOTP_SECRET (base32) — preferred
2. TOTP_SECRET (base32) — alias
3. voice-chat/.totp_secret (gitignored), mode 600

When none are set, the gate is off (local/dev open access) and the process
logs "TOTP not configured". On a VPS, put the secret in ~/lingocoach.env so
the gate stays on. Session cookie is HttpOnly after a valid 6-digit code.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from pathlib import Path

import pyotp

logger = logging.getLogger("lingocoach")

COOKIE_NAME = "lc_session"
SESSION_MAX_AGE = 7 * 24 * 3600
ISSUER = "LingoCoach"
ACCOUNT = "unlock"

_ROOT = Path(__file__).resolve().parents[1]
_SECRET_FILE = _ROOT / ".totp_secret"

_secret: str | None = None
_enabled: bool = False
_just_created: bool = False
_configured: bool = False


def secret_file_path() -> Path:
    return _SECRET_FILE


def reset_for_tests() -> None:
    """Clear cached config so tests can swap env/files."""
    global _secret, _enabled, _just_created, _configured
    _secret = None
    _enabled = False
    _just_created = False
    _configured = False


def ensure_configured() -> bool:
    """Load secret once. Returns True when the gate is active."""
    global _secret, _enabled, _just_created, _configured
    if _configured:
        return _enabled
    _configured = True
    raw = (
        os.environ.get("LINGOCOACH_TOTP_SECRET", "").strip()
        or os.environ.get("TOTP_SECRET", "").strip()
    )
    if raw:
        _secret = raw
        _enabled = True
        logger.info("TOTP gate enabled (env secret).")
        return True
    if _SECRET_FILE.is_file():
        try:
            text = _SECRET_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            text = ""
        if text:
            _secret = text
            _enabled = True
            logger.info("TOTP gate enabled (secret file).")
            return True
    _secret = None
    _enabled = False
    logger.info("TOTP not configured")
    return False


def create_secret_file() -> tuple[str, str]:
    """Write a new base32 secret to .totp_secret (mode 600). Returns (secret, otpauth_uri)."""
    global _secret, _enabled, _just_created, _configured
    secret = pyotp.random_base32()
    _SECRET_FILE.write_text(secret + "\n", encoding="utf-8")
    try:
        os.chmod(_SECRET_FILE, 0o600)
    except OSError:
        pass
    _secret = secret
    _enabled = True
    _just_created = True
    _configured = True
    logger.info("TOTP secret created; scan setup URL once")
    return secret, provisioning_uri(secret)


def provisioning_uri(secret: str | None = None) -> str:
    value = secret if secret is not None else (_secret or "")
    totp = pyotp.TOTP(value)
    return totp.provisioning_uri(name=ACCOUNT, issuer_name=ISSUER)


def consume_setup_uri() -> str | None:
    """Return otpauth URI once after auto-create; then clear the one-shot flag."""
    global _just_created
    ensure_configured()
    if not _just_created or not _secret:
        return None
    _just_created = False
    return provisioning_uri(_secret)


def mark_just_created() -> None:
    global _just_created
    _just_created = True


def is_enabled() -> bool:
    return ensure_configured()


def current_secret() -> str | None:
    ensure_configured()
    return _secret


def verify_code(code: str) -> bool:
    ensure_configured()
    if not _secret:
        return False
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    if len(digits) != 6:
        return False
    totp = pyotp.TOTP(_secret)
    return bool(totp.verify(digits, valid_window=1))


def _signing_key(secret: str) -> bytes:
    return hashlib.sha256(f"lingocoach-session:{secret}".encode("utf-8")).digest()


def mint_session_token() -> str | None:
    ensure_configured()
    if not _secret:
        return None
    exp = int(time.time()) + SESSION_MAX_AGE
    payload = str(exp)
    sig = hmac.new(_signing_key(_secret), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def session_valid(token: str | None) -> bool:
    ensure_configured()
    if not _secret or not token:
        return False
    try:
        payload, sig = token.split(".", 1)
        exp = int(payload)
    except (ValueError, AttributeError):
        return False
    if exp < int(time.time()):
        return False
    expected = hmac.new(_signing_key(_secret), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def new_nonce() -> str:
    return secrets.token_hex(8)


PUBLIC_EXACT = {"/health", "/login", "/api/totp/verify", "/api/totp/setup"}


def is_public_path(path: str) -> bool:
    if path in PUBLIC_EXACT:
        return True
    # Login page may request a tiny dedicated asset set.
    if path.startswith("/static/login"):
        return True
    return False
