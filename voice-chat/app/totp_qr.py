"""One-time Authenticator enrollment page (Google Authenticator on iPhone).

Every CLI mint (``python -m app.totp_qr`` / ``./lingocoachctl.sh qr`` /
``new-qr``) generates a fresh cryptographically random one-time token via
``secrets.token_urlsafe``, stores only its hash + expiry next to
.totp_secret (mode 600), and immediately invalidates any previous token.
Never reuses an unexpired record; never derives the token from the TOTP
secret. GET /setup/qr?token=… shows a huge grouped setup key (primary:
Google Authenticator → + → Enter a setup key / 輸入設定密鑰), a secondary
otpauth:// SVG-module QR for GA’s in-app scanner / Android, and an
otpauth:// deep link if the page is opened on the phone. First successful
page load also invalidates the token. TTL defaults to 20 minutes.

QR modules encode otpauth://totp/… only — never the HTTPS enroll URL.
Do **not** tell users to scan with iPhone Camera: modern iOS Camera treats
``otpauth://`` as Apple Passwords / 安全金鑰 and does not hand off to
Google Authenticator. GA’s “請改用相機” is the wrong product advice here.

Usage (from voice-chat/):
  .venv/bin/python -m app.totp_qr
  .venv/bin/python -m app.totp_setup --qr-link
  ./lingocoachctl.sh qr   # alias: new-qr

Public URL is built from LINGOCOACH_PUBLIC_BASE, or
LINGOCOACH_DOMAIN + LINGOCOACH_HTTPS_PORT (default 8066). Example host:
https://103-195-5-86.as-cloud-xip.com:8066
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import os
import secrets
import struct
import sys
import time
import zlib
from pathlib import Path

import segno

from app import totp_gate

# On-screen QR is a grid of SVG <rect> modules (same segno matrix as PNG).
# Secondary path only: Google Authenticator → + → Scan a QR code (or Android).
# iPhone Camera must not be the advised path (opens Apple 安全金鑰, not GA).
# Quiet zone ≥4, prefer 8. Display ~360–420 CSS px. PNG remains a hidden
# fallback only — never the only scannable surface.
# Critical: QR *modules* encode otpauth://totp/… only — never the HTTPS
# /setup/qr?token=… page URL (a browser would open a webpage instead of GA).
QR_BOX_SIZE = 10  # PNG fallback module scale in px
QR_BORDER = 8  # modules; GA expects ≥4 — 8 helps phone cameras on a monitor
QR_MIN_PX = 320  # PNG fallback raster size
QR_DISPLAY_PX = 400  # target on-screen SVG size (360–420 CSS px)
QR_ERROR = "m"
_PNG_SIG = b"\x89PNG\r\n\x1a\n"

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


def _invalidate_token_file() -> None:
    """Remove any existing enroll-token record (previous raw tokens stop working)."""
    try:
        _TOKEN_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _write_token_record(token_hash: str, exp: int) -> None:
    """Atomically replace `.totp_qr_token` with hashed token + expiry (mode 600)."""
    payload = json.dumps({"v": 1, "hash": token_hash, "exp": exp}, separators=(",", ":"))
    _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _TOKEN_FILE.with_name(_TOKEN_FILE.name + ".tmp")
    try:
        tmp.write_text(payload + "\n", encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, _TOKEN_FILE)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
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
    # Never persist or return a raw token — only hash + exp are valid.
    if "raw" in data or "token" in data:
        logger.warning("Ignoring legacy plaintext fields in enroll token file")
    return {"v": data.get("v", 1), "hash": h, "exp": exp}


def mint_enroll_token(ttl_seconds: int = TOKEN_TTL_SECONDS) -> tuple[str, int]:
    """Always mint a fresh one-time enroll token. Returns (raw_token, exp_unix).

    Every call generates a new cryptographically random token via
    ``secrets.token_urlsafe``, overwrites ``.totp_qr_token`` (hash only), and
    immediately invalidates any previously minted token. Never reuses an
    unexpired record, never derives the token from the TOTP secret.
    """
    # Invalidate first so a crashed write cannot leave a stale usable token
    # paired with a newly printed URL from a partial run.
    _invalidate_token_file()
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    if not raw or len(raw) < 16:
        raise RuntimeError("failed to mint enroll token (entropy)")
    exp = int(time.time()) + max(60, int(ttl_seconds))
    _write_token_record(_hash_token(raw), exp)
    logger.info("TOTP QR enroll token minted (ttl_s=%s); previous tokens invalidated", ttl_seconds)
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
    """Build otpauth://totp/… via pyotp (issuer LingoCoach). Never an https URL."""
    totp_gate.ensure_configured()
    secret = totp_gate.current_secret()
    if not secret:
        return None
    return totp_gate.provisioning_uri(secret)


def require_otpauth_payload(otpauth: str) -> str:
    """Refuse anything that is not an Authenticator otpauth://totp/ URI.

    Encoding the enroll page (`https://…/setup/qr?token=…`) makes a phone
    camera open a webpage instead of offering an authenticator.
    """
    if not isinstance(otpauth, str):
        raise ValueError("QR payload must be an otpauth://totp/ string")
    value = otpauth.strip()
    if not value.startswith("otpauth://totp/"):
        raise ValueError(
            "QR modules must encode otpauth://totp/… only "
            "(refusing non-Authenticator payload)"
        )
    # Defense in depth: never allow page / enroll URLs into the matrix.
    lowered = value.lower()
    if (
        "https://" in lowered
        or "http://" in lowered
        or "/setup/qr" in lowered
        or "token=" in lowered
    ):
        raise ValueError("Refusing to encode enroll-page URL into Authenticator QR")
    return value


def _module_px(modules_count: int) -> int:
    """Pixels per QR module: at least QR_BOX_SIZE, and whole image ≥ QR_MIN_PX."""
    n = max(1, int(modules_count))
    return max(QR_BOX_SIZE, (QR_MIN_PX + n - 1) // n)


def onpage_display_px(modules_count: int) -> int:
    """CSS px for the on-screen SVG: integer px/module, about 360–420.

    Integer module size keeps Chrome's crispEdges raster on a Mac display
    aligned to device pixels (Retina 2x). Prefer 8 CSS px/module when that
    lands in range; never shrink below 280.
    """
    n = max(1, int(modules_count))
    for module_px in (8, 7, 9, 10, 6):
        size = n * module_px
        if 360 <= size <= 420:
            return size
    size = n * 8
    return max(280, min(480, max(size, QR_DISPLAY_PX)))


def _segno_qr(otpauth: str) -> tuple[segno.QRCode, str]:
    """Build a segno QR whose payload is exactly the otpauth://totp/ URI."""
    payload = require_otpauth_payload(otpauth)
    qr = segno.make(payload, error=QR_ERROR)
    if not payload.startswith("otpauth://totp/"):
        raise RuntimeError("QR matrix payload is not otpauth://totp/…")
    return qr, payload


def _qr_factory(otpauth: str) -> segno.QRCode:
    """Test/helper alias: segno QR for an otpauth://totp/ payload."""
    qr, _payload = _segno_qr(otpauth)
    return qr


def qr_encoded_payload(otpauth: str) -> str:
    """Return the string that will be encoded into QR modules (otpauth only)."""
    return require_otpauth_payload(otpauth)


def _matrix_with_quiet_zone(qr: segno.QRCode) -> list[list[bool]]:
    """Boolean matrix including QR_BORDER quiet zone (dark=True).

    ``qr.matrix`` is the core only — Authenticator needs the white border
    baked into the raster, not just CSS padding around the <img>.
    """
    border = QR_BORDER
    core = qr.matrix
    if not core:
        raise RuntimeError("QR matrix is empty")
    n = len(core)
    side = n + 2 * border
    out: list[list[bool]] = [[False] * side for _ in range(side)]
    for y in range(n):
        row = core[y]
        for x in range(n):
            # segno: non-zero = dark module
            out[y + border][x + border] = bool(row[x])
    return out


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    """One PNG chunk: length + type + data + CRC32(type||data)."""
    crc = zlib.crc32(tag)
    crc = zlib.crc32(data, crc) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def encode_qr_matrix_png(modules: list[list[bool]], module_px: int | None = None) -> bytes:
    """Encode a boolean matrix as an RGB PNG (white bg, black modules).

    Kept for tests / emergency fallback. Prefer ``qr_png_bytes`` (segno).
    """
    if not modules:
        raise RuntimeError("QR matrix is empty")
    n = len(modules)
    if any(len(row) != n for row in modules):
        raise RuntimeError("QR matrix is not square")
    scale = max(1, int(module_px if module_px is not None else _module_px(n)))
    size = n * scale
    white = b"\xff\xff\xff"
    black = b"\x00\x00\x00"
    rows: list[bytes] = []
    for y in range(n):
        row = modules[y]
        scan = bytearray()
        for x in range(n):
            pix = black if row[x] else white
            scan.extend(pix * scale)
        line = b"\x00" + bytes(scan)  # filter None
        rows.extend(line for _ in range(scale))
    raw = b"".join(rows)
    compressed = zlib.compress(raw, 9)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (
        _PNG_SIG
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )


def png_ihdr_size(png: bytes) -> tuple[int, int]:
    """Return (width, height) from a PNG IHDR; raises on bad signature/header."""
    if len(png) < 33 or not png.startswith(_PNG_SIG):
        raise ValueError("not a PNG")
    length = struct.unpack(">I", png[8:12])[0]
    if length != 13 or png[12:16] != b"IHDR":
        raise ValueError("missing IHDR")
    width, height = struct.unpack(">II", png[16:24])
    return width, height


def png_ihdr_fields(png: bytes) -> tuple[int, int, int, int]:
    """Return (width, height, bit_depth, color_type) from IHDR."""
    width, height = png_ihdr_size(png)
    return width, height, png[24], png[25]


def _png_idat_raw(png: bytes) -> bytes:
    pos = 8
    idat = bytearray()
    while pos + 8 <= len(png):
        length = struct.unpack(">I", png[pos : pos + 4])[0]
        tag = png[pos + 4 : pos + 8]
        data = png[pos + 8 : pos + 8 + length]
        pos = pos + 12 + length
        if tag == b"IDAT":
            idat.extend(data)
        elif tag == b"IEND":
            break
    return zlib.decompress(bytes(idat))


def png_corner_rgb(png: bytes, x: int = 0, y: int = 0) -> tuple[int, int, int]:
    """Read one RGB pixel from a filter-0 PNG we emitted (RGB8 or grey1)."""
    width, height, bit_depth, color_type = png_ihdr_fields(png)
    if not (0 <= x < width and 0 <= y < height):
        raise ValueError("pixel out of bounds")
    raw = _png_idat_raw(png)
    if color_type == 2 and bit_depth == 8:
        stride = 1 + width * 3
        if len(raw) != stride * height:
            raise ValueError("unexpected PNG raster size")
        off = y * stride + 1 + x * 3
        return raw[off], raw[off + 1], raw[off + 2]
    if color_type == 0 and bit_depth == 1:
        # 1-bit greyscale: 0=black, 1=white. Filter byte per row.
        stride = 1 + math.ceil(width / 8)
        if len(raw) != stride * height:
            raise ValueError("unexpected PNG raster size")
        row_start = y * stride
        if raw[row_start] != 0:
            raise ValueError("unsupported PNG filter (expected None/0)")
        bit_index = x
        byte = raw[row_start + 1 + (bit_index // 8)]
        bit = (byte >> (7 - (bit_index % 8))) & 1
        v = 255 if bit else 0
        return v, v, v
    if color_type == 0 and bit_depth == 8:
        stride = 1 + width
        if len(raw) != stride * height:
            raise ValueError("unexpected PNG raster size")
        off = y * stride + 1 + x
        v = raw[off]
        return v, v, v
    raise ValueError(f"unsupported PNG type bit={bit_depth} color={color_type}")


def _render_scale(qr: segno.QRCode) -> int:
    """Pixels per module so the full symbol (core + quiet zone) is ≥ QR_MIN_PX."""
    core_n = qr.symbol_size(scale=1, border=0)[0]
    return _module_px(core_n + 2 * QR_BORDER)


def qr_png_bytes(otpauth: str) -> bytes:
    """High-contrast black-on-white PNG bytes via segno (pure-Python wheel)."""
    qr, _payload = _segno_qr(otpauth)
    scale = _render_scale(qr)
    from io import BytesIO

    buf = BytesIO()
    qr.save(
        buf,
        kind="png",
        scale=scale,
        border=QR_BORDER,
        dark="#000000",
        light="#ffffff",
    )
    png = buf.getvalue()
    if not png.startswith(_PNG_SIG):
        raise RuntimeError("segno did not return a PNG")
    return png


def qr_png_data_url(otpauth: str) -> str:
    """High-contrast black-on-white PNG as a data URL (segno; no Pillow).

    Hidden fallback only. The visible enroll QR is SVG module rects.
    Payload is always otpauth://totp/… (never the /setup/qr HTTPS link).
    """
    qr, _payload = _segno_qr(otpauth)
    scale = _render_scale(qr)
    return qr.png_data_uri(
        scale=scale,
        border=QR_BORDER,
        dark="#000000",
        light="#ffffff",
    )


def qr_svg_module_markup(otpauth: str) -> str:
    """On-screen QR: SVG ``<rect>`` per dark run from the segno matrix.

    This is what Mac Chrome paints onto the display. Google Authenticator’s
    in-app scanner photographs those pixels — not the PNG bytes OpenCV
    decoded. Hard-edged black/white rects with ``shape-rendering="crispEdges"``
    stay scannable on Retina; a CSS-scaled ``<img>`` PNG does not.
    """
    qr, _payload = _segno_qr(otpauth)
    matrix = _matrix_with_quiet_zone(qr)
    n = len(matrix)
    if n < 21 + 2 * QR_BORDER:
        raise RuntimeError("QR matrix unexpectedly small")
    display = onpage_display_px(n)
    parts = [
        '<svg class="qr-svg" role="img" aria-label="Authenticator QR code" ',
        'xmlns="http://www.w3.org/2000/svg" ',
        f'viewBox="0 0 {n} {n}" width="{display}" height="{display}" ',
        'shape-rendering="crispEdges" color-scheme="only light" ',
        f'data-modules="{n}" data-quiet-zone="{QR_BORDER}">',
        f'<rect class="qr-bg" x="0" y="0" width="{n}" height="{n}" fill="#ffffff"/>',
    ]
    for y, row in enumerate(matrix):
        x = 0
        while x < n:
            if not row[x]:
                x += 1
                continue
            x2 = x + 1
            while x2 < n and row[x2]:
                x2 += 1
            parts.append(
                f'<rect class="qr-mod" x="{x}" y="{y}" width="{x2 - x}" '
                f'height="1" fill="#000000"/>'
            )
            x = x2
    parts.append("</svg>")
    return "".join(parts)


def qr_svg_markup(otpauth: str) -> str:
    """On-screen SVG QR (module rects). Alias used by tests and fallbacks."""
    return qr_svg_module_markup(otpauth)


def qr_markup(otpauth: str) -> str:
    """Embeddable QR: visible SVG module grid; hidden PNG ``<img>`` fallback.

    The SVG is the scannable surface on a Mac display. PNG stays for tests /
    noscript but is not shown (a second on-screen QR confuses finders).
    """
    require_otpauth_payload(otpauth)
    svg = qr_svg_module_markup(otpauth)
    fallback = ""
    try:
        data_url = qr_png_data_url(otpauth)
        fallback = (
            f'<img class="qr-png-fallback" hidden src="{data_url}" '
            f'alt="" width="0" height="0" decoding="sync"/>'
        )
    except Exception:
        logger.exception("PNG QR fallback encode failed; SVG-only page")
    return svg + fallback


def format_manual_key(secret: str) -> str:
    """Group base32 into 4-char chunks for easier phone typing."""
    clean = "".join(ch for ch in secret.strip().upper() if ch.isalnum())
    return " ".join(clean[i : i + 4] for i in range(0, len(clean), 4))


def _html_attr_escape(value: str) -> str:
    """Escape a string for use inside a double-quoted HTML attribute."""
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_setup_page(template: str, secret: str, otpauth: str) -> str:
    """Embed grouped setup key (primary), SVG QR (secondary), otpauth deep link.

    otpauth must be otpauth://totp/… — encoded into on-screen SVG modules
    (GA in-app scanner / Android) and as a phone-browser deep-link href.
    """
    uri = require_otpauth_payload(otpauth)
    markup = qr_markup(uri)
    return (
        template.replace("__OTPAUTH_URI__", _html_attr_escape(uri))
        .replace("__QR_MARKUP__", markup)
        .replace("__MANUAL_KEY__", format_manual_key(secret))
        .replace("__MANUAL_KEY_RAW__", secret.strip())
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
                "Mint a one-time Authenticator enroll page link.\n"
                "  python -m app.totp_qr [--base URL] [--ttl SECONDS]\n"
                "Open the URL on Mac Chrome. In Google Authenticator: + → "
                "Enter a setup key / 輸入設定密鑰 (do not use iPhone Camera).\n"
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
    # Every invocation mints a NEW ?token=; previous enroll URLs are dead.
    print(url)
    print(
        f"Fresh one-time token minted (len={len(raw)}); "
        "previous enroll URLs are now invalid."
    )
    print(f"Expires in ~{max(0, exp - int(time.time()))}s; works once (first successful page load).")
    print(
        "Open on Mac Chrome. In Google Authenticator: + → Enter a setup key "
        "(do not use iPhone Camera — it opens Apple Passwords / 安全金鑰, not GA). "
        "Leave page open. Then /login."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
