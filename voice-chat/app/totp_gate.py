"""TOTP unlock gate for the voice-chat UI and API.

Secret sources (never logged), first match wins — one canonical loader
used by both ``/setup/qr`` (setup key + otpauth URI) and verify:
1. LINGOCOACH_TOTP_SECRET (base32) — preferred
2. TOTP_SECRET (base32) — alias
3. voice-chat/.totp_secret (gitignored), mode 600

Values are normalized (strip quotes/spaces/padding, uppercase RFC 4648
base32) before use so the on-page key matches ``pyotp.TOTP(secret).verify``.
Algorithm is SHA1 / 6 digits / 30s with valid_window=2 (UTC).

When none are set, the gate is off (local/dev open access) and the process
logs "TOTP not configured". On a VPS, put the secret in ~/lingocoach.env so
the gate stays on. Session cookie is HttpOnly after a valid 6-digit code.
On HTTPS (LINGOCOACH_HTTPS=1 / X-Forwarded-Proto), the cookie also sets Secure.

``lc_session`` is a sliding **40-minute idle timeout** (``SESSION_MAX_AGE_S``).
The cookie value is a signed expiry timestamp; each authenticated HTML/API
request remints it so active use stays signed in. After 40 minutes without a
request, the next HTML hit 303s to ``/login`` and APIs return 401
``session_expired``. POST ``/logout`` (or ``/api/totp/logout``) clears the
cookie. Never log the secret or the session token.
"""

from __future__ import annotations

import binascii
import hashlib
import hmac
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

import pyotp

logger = logging.getLogger("lingocoach")

COOKIE_NAME = "lc_session"
# Sliding idle timeout: each authenticated request remints the signed cookie.
SESSION_MAX_AGE_S = 40 * 60
SESSION_MAX_AGE = SESSION_MAX_AGE_S
ISSUER = "LingoCoach"
ACCOUNT = "unlock"
DIGITS = 6
PERIOD_SECONDS = 30
# ±2 steps (60–90s): VPS clock vs iPhone NTP; pyotp default valid_window=0 is too tight.
VALID_WINDOW = 2
_BASE32_ALPHABET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")

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


def normalize_secret(raw: str | None) -> str:
    """Canonical base32 secret used by both /setup/qr and verify.

    Env files and systemd EnvironmentFile often wrap values in quotes or
    keep grouped spaces / ``=`` padding. Google Authenticator's "Enter a
    setup key" ignores spaces and padding; pyotp.TOTP(raw).verify() does
    not — quotes, spaces, or extra ``=`` raise ``binascii.Error`` (the
    login page then shows "That code is not valid").
    """
    if not raw:
        return ""
    text = str(raw).strip().replace("\r", "")
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    compact = "".join(ch for ch in text.upper() if not ch.isspace()).rstrip("=")
    return "".join(ch for ch in compact if ch in _BASE32_ALPHABET)


def _totp(secret: str) -> pyotp.TOTP:
    """SHA1 / 6 digits / 30s — same parameters as the otpauth URI."""
    return pyotp.TOTP(
        secret,
        digits=DIGITS,
        digest=hashlib.sha1,
        interval=PERIOD_SECONDS,
        name=ACCOUNT,
        issuer=ISSUER,
    )


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_ts() -> int:
    """Unix seconds for session mint/expiry. Tests patch this, not time.time."""
    return int(time.time())


def _try_enable(raw: str, source: str) -> bool:
    """Normalize and cache ``raw``. Never logs the secret."""
    global _secret, _enabled
    secret = normalize_secret(raw)
    if not secret:
        if str(raw).strip():
            logger.warning("TOTP %s secret ignored (not valid base32).", source)
        return False
    _secret = secret
    _enabled = True
    logger.info("TOTP gate enabled (%s secret).", source)
    return True


def ensure_configured() -> bool:
    """Load secret once from env, then ``.totp_secret``. Returns True when on.

    Same loader for the QR/setup-key page and ``/api/totp/verify``. First
    match wins: ``LINGOCOACH_TOTP_SECRET``, ``TOTP_SECRET``, then the file.
    """
    global _secret, _enabled, _just_created, _configured
    if _configured:
        return _enabled
    _configured = True
    raw = os.environ.get("LINGOCOACH_TOTP_SECRET", "") or os.environ.get("TOTP_SECRET", "")
    if _try_enable(raw, "env"):
        return True
    if _SECRET_FILE.is_file():
        try:
            text = _SECRET_FILE.read_text(encoding="utf-8")
        except OSError:
            text = ""
        if _try_enable(text, "file"):
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
    """Google Key Uri Format otpauth://totp/… (SHA1 / 6 digits / 30s).

    pyotp omits algorithm/digits/period when they are the defaults. We keep
    them explicit so Google Authenticator and other apps see the same values
    as verify (must not change the generated codes).
    """
    value = normalize_secret(secret if secret is not None else (_secret or ""))
    totp = _totp(value)
    uri = totp.provisioning_uri(name=ACCOUNT, issuer_name=ISSUER)
    if "algorithm=" not in uri:
        uri += "&algorithm=SHA1"
    if "digits=" not in uri:
        uri += "&digits=6"
    if "period=" not in uri:
        uri += "&period=30"
    return uri


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
    """Accept the current 6-digit code, plus ±VALID_WINDOW steps.

    Strips whitespace/punctuation so a pasted ``123 456`` still works.
    Uses timezone-aware UTC (Google Authenticator is Unix time, not VPS TZ).
    """
    ensure_configured()
    if not _secret:
        return False
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    if len(digits) != DIGITS:
        return False
    try:
        totp = _totp(_secret)
        return bool(
            totp.verify(digits, for_time=_now_utc(), valid_window=VALID_WINDOW)
        )
    except (binascii.Error, ValueError, TypeError):
        logger.warning("TOTP verify failed (secret/code not usable)")
        return False


def _signing_key(secret: str) -> bytes:
    return hashlib.sha256(f"lingocoach-session:{secret}".encode("utf-8")).digest()


def mint_session_token() -> str | None:
    ensure_configured()
    if not _secret:
        return None
    exp = _now_ts() + SESSION_MAX_AGE_S
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
    if exp < _now_ts():
        return False
    expected = hmac.new(_signing_key(_secret), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def session_error(token: str | None) -> str:
    """Reason for a failed gate check. Never logs the token."""
    if token:
        return "session_expired"
    return "auth_required"


def new_nonce() -> str:
    return secrets.token_hex(8)


PUBLIC_EXACT = {
    "/health",
    "/login",
    "/logout",
    "/api/totp/verify",
    "/api/totp/logout",
    "/api/totp/setup",
    "/setup/qr",
}


def is_public_path(path: str) -> bool:
    if path in PUBLIC_EXACT:
        return True
    # Login / one-time QR enroll pages may request a tiny dedicated asset set.
    if path.startswith("/static/login") or path.startswith("/static/setup"):
        return True
    return False
