"""One-time QR enrollment link for Google Authenticator.

Mint a high-entropy token (CLI), store only its hash + expiry next to
.totp_secret (mode 600). GET /setup/qr?token=… shows the otpauth QR + manual
key once, then invalidates the token. TTL defaults to 20 minutes.

Usage (from voice-chat/):
  .venv/bin/python -m app.totp_qr
  .venv/bin/python -m app.totp_setup --qr-link

Public URL is built from LINGOCOACH_PUBLIC_BASE, or
LINGOCOACH_DOMAIN + LINGOCOACH_HTTPS_PORT (default 8066). Example host:
https://103-195-5-86.as-cloud-xip.com:8066
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import logging
import os
import secrets
import sys
import time
from pathlib import Path

import qrcode
from qrcode.image.svg import SvgPathImage

from app import totp_gate

logger = logging.getLogger("lingocoach")

TOKEN_TTL_SECONDS = 20 * 60  # 20 minutes (within 15–30)
TOKEN_BYTES = 32

_ROOT = Path(__file__).resolve().parents[1]
_TOKEN_FILE = _ROOT / ".totp_qr_token"


def token_file_path() -> Path:
    return _TOKEN_FILE


def reset_for_tests(path: Path | None = None) -> None:
    """Point the token file at a temp path (tests) or restore default."""
    global _TOKEN_FILE
    if path is None:
        _TOKEN_FILE = _ROOT / ".totp_qr_token"
    else:
        _TOKEN_FILE = path


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _write_token_record(token_hash: str, exp: int) -> None:
    payload = json.dumps({"v": 1, "hash": token_hash, "exp": exp}, separators=(",", ":"))
    _TOKEN_FILE.write_text(payload + "\n", encoding="utf-8")
    try:
        os.chmod(_TOKEN_FILE, 0o600)
    except OSError:
        pass


def _read_token_record() -> dict | None:
    if not _TOKEN_FILE.is_file():
        return None
    try:
        text = _TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    h = data.get("hash")
    exp = data.get("exp")
    if not isinstance(h, str) or not isinstance(exp, int):
        return None
    return data


def mint_enroll_token(ttl_seconds: int = TOKEN_TTL_SECONDS) -> tuple[str, int]:
    """Create a one-time enroll token. Returns (raw_token, exp_unix)."""
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    exp = int(time.time()) + max(60, int(ttl_seconds))
    _write_token_record(_hash_token(raw), exp)
    logger.info("TOTP QR enroll token minted (ttl_s=%s); link is one-shot", ttl_seconds)
    return raw, exp


def consume_enroll_token(raw: str | None) -> bool:
    """Validate and invalidate a one-time token. True only on first valid use."""
    if not raw or not isinstance(raw, str):
        return False
    raw = raw.strip()
    if not raw:
        return False
    record = _read_token_record()
    if not record:
        return False
    now = int(time.time())
    if record["exp"] < now:
        try:
            _TOKEN_FILE.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    expected = record["hash"]
    actual = _hash_token(raw)
    if not hmac.compare_digest(expected, actual):
        return False
    # Invalidate before returning success (first successful view wins).
    try:
        _TOKEN_FILE.unlink(missing_ok=True)
    except OSError:
        return False
    logger.info("TOTP QR enroll token consumed")
    return True


def public_base_url(override: str | None = None) -> str:
    """Build https://host:port with no trailing slash."""
    if override:
        return override.rstrip("/")
    base = (
        os.environ.get("LINGOCOACH_PUBLIC_BASE", "").strip()
        or os.environ.get("PUBLIC_BASE", "").strip()
    )
    if base:
        return base.rstrip("/")
    domain = (
        os.environ.get("LINGOCOACH_DOMAIN", "").strip()
        or os.environ.get("DOMAIN", "").strip()
        or os.environ.get("VPS_HOST", "").strip()
    )
    if not domain:
        raise SystemExit(
            "Set LINGOCOACH_PUBLIC_BASE or LINGOCOACH_DOMAIN "
            "(example: LINGOCOACH_DOMAIN=103-195-5-86.as-cloud-xip.com)."
        )
    port = (
        os.environ.get("LINGOCOACH_HTTPS_PORT", "").strip()
        or os.environ.get("HTTPS_PORT", "").strip()
        or "8066"
    )
    return f"https://{domain}:{port}"


def enroll_url(raw_token: str, base: str | None = None) -> str:
    root = public_base_url(base)
    return f"{root}/setup/qr?token={raw_token}"


def otpauth_uri() -> str | None:
    totp_gate.ensure_configured()
    secret = totp_gate.current_secret()
    if not secret:
        return None
    return totp_gate.provisioning_uri(secret)


def qr_svg_markup(otpauth: str) -> str:
    """Offline SVG QR (no Pillow). Safe to embed in HTML."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(otpauth)
    qr.make(fit=True)
    img = qr.make_image(image_factory=SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    svg = buf.getvalue().decode("utf-8")
    if svg.startswith("<?xml"):
        svg = svg.split("?>", 1)[-1].lstrip()
    # Keep contrast on the dark login-style page.
    svg = svg.replace("<svg ", '<svg role="img" aria-label="Authenticator QR code" ', 1)
    return svg


def render_setup_page(template: str, secret: str, otpauth: str) -> str:
    svg = qr_svg_markup(otpauth)
    return (
        template.replace("__QR_SVG__", svg)
        .replace("__MANUAL_KEY__", secret)
        .replace("__ISSUER__", totp_gate.ISSUER)
        .replace("__ACCOUNT__", totp_gate.ACCOUNT)
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    base_override = None
    ttl = TOKEN_TTL_SECONDS
    i = 0
    while i < len(args):
        if args[i] in {"--base", "--public-base"} and i + 1 < len(args):
            base_override = args[i + 1]
            i += 2
            continue
        if args[i] == "--ttl" and i + 1 < len(args):
            ttl = int(args[i + 1])
            i += 2
            continue
        if args[i] in {"-h", "--help"}:
            print(
                "Mint a one-time Authenticator QR page link.\n"
                "  python -m app.totp_qr [--base URL] [--ttl SECONDS]\n"
                "Requires LINGOCOACH_TOTP_SECRET / TOTP_SECRET / .totp_secret.\n"
                "URL from LINGOCOACH_PUBLIC_BASE or LINGOCOACH_DOMAIN + port."
            )
            return 0
        print(f"Unknown argument: {args[i]}", file=sys.stderr)
        return 2

    totp_gate.ensure_configured()
    if not totp_gate.is_enabled() or not totp_gate.current_secret():
        print(
            "No TOTP secret configured. Set LINGOCOACH_TOTP_SECRET or run "
            "python -m app.totp_setup first.",
            file=sys.stderr,
        )
        return 1

    raw, exp = mint_enroll_token(ttl_seconds=ttl)
    url = enroll_url(raw, base=base_override)
    # Print only the link + metadata — never the TOTP secret.
    print(url)
    print(f"Expires in ~{max(0, exp - int(time.time()))}s; works once (first successful page load).")
    print("Open on your phone, scan with Google Authenticator, then use /login.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
