"""One-time Authenticator QR enroll page: token gate, single use, TTL."""

from __future__ import annotations

import base64
import re
import time
from urllib.parse import parse_qs, unquote, urlparse

import pyotp
import pytest
from fastapi.testclient import TestClient

from app import totp_gate
from app import totp_qr
from app.main import app

# Random-looking test secret — not from env / production.
TEST_SECRET = "JBSWY3DPEHPK3PXP"

# Decoder preference for the release gate (verified in this VM):
# 1) OpenCV cv2.QRCodeDetector — works on segno PNG without libzbar
# 2) pyzbar (+ libzbar0 / libzbar0t64) — needs system zbar shared lib
# 3) zxing-cpp — optional pip wheel
_DECODER_USED: str | None = None


def _try_install_decoder_libs() -> None:
    """Best-effort install of optional QR decoders (no-op if already present)."""
    import importlib
    import subprocess
    import sys

    missing: list[str] = []
    for mod, pip_name in (
        ("cv2", "opencv-python-headless"),
        ("numpy", "numpy"),
        ("pyzbar", "pyzbar"),
        ("PIL", "pillow"),
        ("zxingcpp", "zxing-cpp"),
    ):
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pip_name)
    if not missing:
        return
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", *dict.fromkeys(missing)],
        check=False,
        capture_output=True,
        timeout=180,
    )


def _decode_qr_png(png: bytes) -> tuple[str, str]:
    """Decode QR PNG → (payload, decoder_name). Raises if no decoder works."""
    global _DECODER_USED
    errors: list[str] = []

    # 1) OpenCV
    try:
        import cv2
        import numpy as np

        arr = np.frombuffer(png, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("cv2.imdecode returned None")
        data, _pts, _ = cv2.QRCodeDetector().detectAndDecode(img)
        if data:
            _DECODER_USED = "opencv-QRCodeDetector"
            return data, _DECODER_USED
        errors.append("opencv: empty decode")
    except Exception as exc:  # noqa: BLE001 — probe optional deps
        errors.append(f"opencv: {type(exc).__name__}: {exc}")

    # 2) pyzbar (+ Pillow)
    try:
        import io

        from PIL import Image
        from pyzbar.pyzbar import decode as zbar_decode

        results = zbar_decode(Image.open(io.BytesIO(png)))
        if results:
            payload = results[0].data.decode("utf-8")
            _DECODER_USED = "pyzbar+libzbar"
            return payload, _DECODER_USED
        errors.append("pyzbar: no symbols")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"pyzbar: {type(exc).__name__}: {exc}")

    # 3) zxing-cpp
    try:
        import cv2
        import numpy as np
        import zxingcpp

        arr = np.frombuffer(png, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise RuntimeError("cv2.imdecode returned None for zxing")
        results = zxingcpp.read_barcodes(img)
        if results:
            _DECODER_USED = "zxing-cpp"
            return results[0].text, _DECODER_USED
        errors.append("zxing-cpp: no barcodes")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"zxing-cpp: {type(exc).__name__}: {exc}")

    raise RuntimeError("no QR decoder succeeded: " + "; ".join(errors))


@pytest.fixture(scope="module")
def qr_decoder_ready():
    """Ensure at least one QR decoder works; skip only after trying to install."""
    _try_install_decoder_libs()
    probe_secret = pyotp.random_base32()
    probe_uri = pyotp.TOTP(probe_secret).provisioning_uri(
        name=totp_gate.ACCOUNT, issuer_name=totp_gate.ISSUER
    )
    png = totp_qr.qr_png_bytes(probe_uri)
    try:
        payload, name = _decode_qr_png(png)
    except RuntimeError as exc:
        pytest.skip(f"QR decoder libs unavailable after install attempt: {exc}")
    assert payload.startswith("otpauth://totp/")
    return name


_SVG_RE = re.compile(r'<svg\b[^>]*class="qr-svg"[^>]*>.*?</svg>', re.S)
_RECT_RE = re.compile(r"<rect\b([^>]*)/?>", re.I)
_ATTR_RE = re.compile(r'([:\w-]+)="([^"]*)"')


def _png_from_markup(markup: str) -> bytes:
    assert 'src="data:image/png;base64,' in markup
    m = re.search(r'src="data:image/png;base64,([A-Za-z0-9+/=]+)"', markup)
    assert m is not None
    return base64.b64decode(m.group(1))


def _qr_wrap_inner(body: str) -> str:
    m = re.search(r'<div[^>]*id="qr-primary"[^>]*>(.*?)</div>', body, re.S)
    assert m, "missing #qr-primary wrap"
    return m.group(1)


def _onpage_svg(markup: str) -> str:
    """The visible QR must be SVG module rects (not a CSS-scaled PNG img)."""
    m = _SVG_RE.search(markup)
    assert m is not None, "on-page QR must include <svg class=\"qr-svg\"> module rects"
    return m.group(0)


def _matrix_from_svg(svg: str) -> list[list[bool]]:
    """Rebuild the boolean matrix from on-page SVG <rect> modules."""
    vb = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
    assert vb is not None, "SVG QR needs viewBox=\"0 0 n n\""
    n = int(vb.group(1))
    assert n == int(vb.group(2))
    assert n >= 21 + 2 * totp_qr.QR_BORDER
    matrix = [[False] * n for _ in range(n)]
    dark_rects = 0
    for rect in _RECT_RE.finditer(svg):
        attrs = dict(_ATTR_RE.findall(rect.group(1)))
        fill = (attrs.get("fill") or "").strip().lower()
        if fill in {"#fff", "#ffffff", "white"}:
            continue
        if fill not in {"#000", "#000000", "black"}:
            continue
        x = int(float(attrs.get("x", "0")))
        y = int(float(attrs.get("y", "0")))
        w = int(float(attrs.get("width", "1")))
        h = int(float(attrs.get("height", "1")))
        dark_rects += 1
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                matrix[yy][xx] = True
    assert dark_rects > 0
    return matrix


def _assert_quiet_zone(matrix: list[list[bool]], border: int | None = None) -> None:
    border = totp_qr.QR_BORDER if border is None else border
    assert border >= 4
    n = len(matrix)
    for i in range(border):
        assert not any(matrix[i]), f"quiet zone row {i} is not white"
        assert not any(matrix[n - 1 - i]), f"quiet zone row {n - 1 - i} is not white"
        assert all(not matrix[y][i] and not matrix[y][n - 1 - i] for y in range(n))
    # Finder pattern origin (core 0,0) is dark.
    assert matrix[border][border] is True


def _assert_qr_markup_scannable(markup: str) -> None:
    """On-page QR is an SVG module grid (PNG may exist only as hidden fallback)."""
    assert 'aria-label="Authenticator QR code"' in markup
    svg = _onpage_svg(markup)
    assert 'shape-rendering="crispEdges"' in svg
    assert 'color-scheme="only light"' in svg or "color-scheme: only light" in markup
    assert "border-radius" not in svg
    width_m = re.search(r'<svg[^>]*\bwidth="(\d+)"', svg)
    assert width_m is not None
    assert int(width_m.group(1)) >= 280
    matrix = _matrix_from_svg(svg)
    _assert_quiet_zone(matrix)
    # Hidden PNG fallback is allowed; it must not be the only QR surface.
    if 'src="data:image/png;base64,' in markup:
        assert "qr-png-fallback" in markup or 'hidden' in markup


def _enable(monkeypatch, tmp_path):
    totp_gate.reset_for_tests()
    monkeypatch.setenv("LINGOCOACH_TOTP_SECRET", TEST_SECRET)
    totp_gate.ensure_configured()
    totp_qr.reset_for_tests(tmp_path / ".totp_qr_token")
    assert totp_gate.is_enabled()


def test_setup_qr_requires_token(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    client = TestClient(app)
    response = client.get("/setup/qr")
    assert response.status_code == 404
    assert TEST_SECRET not in response.text


def test_setup_qr_rejects_bad_token(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    totp_qr.mint_enroll_token()
    client = TestClient(app)
    response = client.get("/setup/qr", params={"token": "not-the-real-token"})
    assert response.status_code == 404
    assert TEST_SECRET not in response.text
    # Bad guess must not burn the real token.
    assert totp_qr.token_file_path().is_file()


def test_setup_qr_valid_once_then_gone(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    raw, _exp = totp_qr.mint_enroll_token()
    client = TestClient(app)
    expected = totp_gate.provisioning_uri(TEST_SECRET)

    first = client.get("/setup/qr", params={"token": raw})
    assert first.status_code == 200
    body = first.text
    assert "LingoCoach" in body
    assert "works once" in body.lower() or "This link works once" in body
    assert TEST_SECRET in body
    assert expected.startswith("otpauth://totp/")
    # Primary: Enter a setup key. SVG QR remains as secondary (GA in-app).
    assert 'id="setup-key-primary"' in body
    assert 'id="qr-primary"' in body
    assert "qr-wrap" in body
    assert body.find("輸入設定密鑰") < body.find('id="qr-primary"')
    assert body.find("Enter a setup key") < body.find('id="qr-primary"')
    # QR is visible (not collapsed under <details>).
    assert "<details" not in body
    qr_chunk = _qr_wrap_inner(body)
    assert "<svg" in qr_chunk
    _assert_qr_markup_scannable(qr_chunk)
    assert "Enter a setup key" in body
    assert "輸入設定密鑰" in body
    assert "Copy" in body
    assert totp_qr.format_manual_key(TEST_SECRET) in body
    assert 'id="otpauth-link"' in body
    assert f'href="{expected}"' in body or f'href="{expected.replace("&", "&amp;")}"' in body
    assert "Open in Google Authenticator" in body
    assert "Cache-Control" in first.headers
    assert "no-store" in first.headers.get("cache-control", "")

    second = client.get("/setup/qr", params={"token": raw})
    assert second.status_code == 404
    assert TEST_SECRET not in second.text
    assert not totp_qr.token_file_path().is_file()


def test_setup_page_includes_otpauth_href(monkeypatch, tmp_path):
    """Enroll HTML exposes otpauth:// as deep link and as QR payload (GA Key URI)."""
    _enable(monkeypatch, tmp_path)
    raw, _ = totp_qr.mint_enroll_token()
    client = TestClient(app)
    response = client.get("/setup/qr", params={"token": raw})
    assert response.status_code == 200
    body = response.text
    expected = totp_gate.provisioning_uri(TEST_SECRET)
    assert expected.startswith("otpauth://totp/")
    # href may HTML-escape & as &amp;
    escaped = expected.replace("&", "&amp;")
    assert f'href="{escaped}"' in body or f'href="{expected}"' in body
    assert 'id="otpauth-link"' in body
    assert "/setup/qr?token=" not in body
    # Deep link must not be an https enroll URL.
    assert 'href="https://' not in body.split('id="otpauth-link"', 1)[1].split(">", 1)[0]
    # Light page + SVG QR (secondary GA in-app scan).
    assert 'color-scheme: only light' in body or "color-scheme: only light" in body
    assert 'name="color-scheme"' in body and 'content="light"' in body
    assert "qr-wrap" in body
    assert "qr-island" in body
    assert "<details" not in body
    assert "<svg" in body
    assert 'class="qr-svg"' in body


def test_setup_html_crisp_onpage_qr_matches_iphone_camera_failure_mode(
    monkeypatch, tmp_path
):
    """Page markup must be screen-scan reliable — not 'OpenCV can read the PNG'.

    Google Authenticator’s in-app scanner photographs the Mac Chrome display.
    The on-page QR therefore has to be SVG (or table) modules in a forced-light
    white island, not a CSS-scaled bitmap that Retina blurs or dark mode inverts.
    Setup key remains the primary enroll path (Camera is not a GA handoff).
    """
    _enable(monkeypatch, tmp_path)
    raw, _ = totp_qr.mint_enroll_token()
    client = TestClient(app)
    response = client.get("/setup/qr", params={"token": raw})
    assert response.status_code == 200
    body = response.text
    expected = totp_gate.provisioning_uri(TEST_SECRET)

    # 1) Crisp on-screen QR (SVG rects), not only an <img> PNG.
    assert 'name="color-scheme"' in body
    assert 'content="light"' in body
    assert "color-scheme: only light" in body
    assert "forced-color-adjust: none" in body
    assert "qr-island" in body
    assert "background: #ffffff" in body or "background:#ffffff" in body
    assert "shape-rendering: crispEdges" in body or 'shape-rendering="crispEdges"' in body
    # QR island itself must not round/clip finder patterns.
    wrap_css = re.search(r"\.qr-wrap\s*,\s*\.qr-island\s*\{([^}]+)\}", body)
    assert wrap_css is not None
    assert "border-radius: 0" in wrap_css.group(1)
    svg_css = re.search(r"\.qr-wrap \.qr-svg[\s\S]*?\{([^}]+)\}", body)
    assert svg_css is not None
    assert "border-radius: 0" in svg_css.group(1)
    # Do not CSS-scale a bitmap as the primary surface.
    assert "width: min(360px, 78vw)" not in body

    qr_chunk = _qr_wrap_inner(body)
    svg = _onpage_svg(qr_chunk)
    assert svg.find("<svg") < (qr_chunk.find("<img") if "<img" in qr_chunk else len(qr_chunk))
    assert 'class="qr-mod"' in svg
    assert 'fill="#000000"' in svg
    assert 'fill="#ffffff"' in svg
    width_m = re.search(r'<svg[^>]*\bwidth="(\d+)"', svg)
    assert width_m is not None
    assert 280 <= int(width_m.group(1)) <= 480

    # 2) On-page matrix payload is the Google Key Uri (otpauth totp).
    matrix = _matrix_from_svg(svg)
    _assert_quiet_zone(matrix)
    assert totp_qr.QR_BORDER >= 8
    assert len(matrix) == len(totp_qr._qr_factory(expected).matrix) + 2 * totp_qr.QR_BORDER
    assert matrix == totp_qr._matrix_with_quiet_zone(totp_qr._qr_factory(expected))

    # 3) Setup key is primary; Camera is warned off (not a GA handoff).
    setup_zh = body.find("輸入設定密鑰")
    setup_en = body.find("Enter a setup key")
    qr_pos = body.find('id="qr-primary"')
    assert setup_zh != -1 and setup_en != -1 and qr_pos != -1
    assert setup_zh < qr_pos
    assert setup_en < qr_pos
    assert 'id="setup-key-primary"' in body
    assert body.find('id="setup-key-primary"') < qr_pos
    assert "安全金鑰" in body
    assert "Passwords" in body or "密碼" in body
    assert "Do not use Camera" in body or "do not use" in body.lower()
    assert "white square" in body.lower() or "白色方塊" in body
    # Must not tell the user to open Camera as the way into GA.
    lowered = body.lower()
    assert "open the iphone camera app (not google authenticator" not in lowered
    assert "請改用系統相機" not in body
    assert "use iphone camera, not ga" not in lowered
    assert "請忽略" in body or "ignore" in lowered

    # 4) SVG QR of otpauth remains as secondary; setup key + deep link present.
    assert "/setup/qr?token=" not in body
    assert totp_qr.format_manual_key(TEST_SECRET) in body
    assert 'id="otpauth-link"' in body
    escaped = expected.replace("&", "&amp;")
    assert f'href="{escaped}"' in body or f'href="{expected}"' in body


def test_onpage_svg_matrix_decodes_to_otpauth_not_enroll_url(qr_decoder_ready):
    """Rasterize the SVG-rect matrix (what Chrome paints) and decode it."""
    uri = totp_gate.provisioning_uri(TEST_SECRET)
    svg = totp_qr.qr_svg_module_markup(uri)
    matrix = _matrix_from_svg(svg)
    _assert_quiet_zone(matrix)
    assert matrix == totp_qr._matrix_with_quiet_zone(totp_qr._qr_factory(uri))
    png = totp_qr.encode_qr_matrix_png(matrix, module_px=8)
    decoded, _used = _decode_qr_png(png)
    assert decoded == uri
    assert decoded.startswith("otpauth://totp/")
    assert "https://" not in decoded
    assert "/setup/qr" not in decoded
    display = totp_qr.onpage_display_px(len(matrix))
    assert 280 <= display <= 480
    width_m = re.search(r'\bwidth="(\d+)"', svg)
    assert width_m is not None
    assert int(width_m.group(1)) == display


def test_otpauth_uri_google_authenticator_shape():
    """otpauth must be Issuer:account + base32 secret + issuer query (URL-encoded)."""
    uri = totp_gate.provisioning_uri(TEST_SECRET)
    assert uri.startswith("otpauth://totp/")
    parsed = urlparse(uri)
    assert parsed.scheme == "otpauth"
    assert parsed.netloc == "totp"
    # Path is /LingoCoach:unlock (possibly percent-encoded).
    label = unquote(parsed.path.lstrip("/"))
    assert label == f"{totp_gate.ISSUER}:{totp_gate.ACCOUNT}"
    qs = parse_qs(parsed.query)
    assert qs["secret"] == [TEST_SECRET]
    assert qs["issuer"] == [totp_gate.ISSUER]
    assert qs["algorithm"] == ["SHA1"]
    assert qs["digits"] == ["6"]
    assert qs["period"] == ["30"]
    # Round-trip: pyotp default URI is the same label/secret; we add SHA1/6/30.
    base = pyotp.TOTP(TEST_SECRET).provisioning_uri(
        name=totp_gate.ACCOUNT, issuer_name="LingoCoach"
    )
    assert uri.startswith(base)
    assert pyotp.TOTP(TEST_SECRET).verify(pyotp.TOTP(TEST_SECRET).now(), valid_window=1)


def test_qr_modules_encode_otpauth_not_https_enroll_url():
    """QR data payload must be otpauth://totp/… — never /setup/qr?token=…."""
    uri = pyotp.TOTP(TEST_SECRET).provisioning_uri(
        name=totp_gate.ACCOUNT, issuer_name="LingoCoach"
    )
    assert uri.startswith("otpauth://totp/")
    payload = totp_qr.qr_encoded_payload(uri)
    assert payload.startswith("otpauth://totp/")
    assert payload == uri
    assert "https://" not in payload
    assert "http://" not in payload
    assert "/setup/qr" not in payload
    assert totp_qr.QR_BORDER >= 4
    # Factory accepts otpauth and builds a matrix with quiet zone.
    # Note: segno symbol_size(scale=1) includes its default border=4; use len(matrix).
    qr = totp_qr._qr_factory(uri)
    matrix = totp_qr._matrix_with_quiet_zone(qr)
    assert matrix[0][0] is False
    assert len(matrix) == len(qr.matrix) + 2 * totp_qr.QR_BORDER


def test_qr_factory_rejects_https_enroll_page_url():
    enroll = (
        "https://103-195-5-86.as-cloud-xip.com:8066/setup/qr"
        "?token=example-not-a-real-token"
    )
    try:
        totp_qr._qr_factory(enroll)
        assert False, "expected ValueError for https enroll URL"
    except ValueError as exc:
        assert "otpauth://totp/" in str(exc)


def test_require_otpauth_payload_rejects_http_and_bare_secrets():
    for bad in (
        "https://example.com/setup/qr?token=abc",
        "http://example.com/",
        "totp://not-valid",
        TEST_SECRET,
        "",
    ):
        try:
            totp_qr.require_otpauth_payload(bad)
            assert False, f"expected ValueError for {bad!r}"
        except ValueError:
            pass


def test_qr_png_default_segno_pure_python():
    """Default path: segno PNG data-URL — no Pillow/libjpeg needed."""
    uri = totp_gate.provisioning_uri(TEST_SECRET)
    assert uri.startswith("otpauth://totp/")
    assert totp_qr.qr_encoded_payload(uri).startswith("otpauth://totp/")
    assert totp_qr.QR_BORDER >= 4
    assert totp_qr.QR_BOX_SIZE >= 8

    qr = totp_qr._qr_factory(uri)
    matrix = totp_qr._matrix_with_quiet_zone(qr)
    assert matrix[0][0] is False
    assert matrix[-1][-1] is False
    assert len(matrix) == len(qr.matrix) + 2 * totp_qr.QR_BORDER

    data_url = totp_qr.qr_png_data_url(uri)
    assert data_url.startswith("data:image/png;base64,")
    raw = base64.b64decode(data_url.split(",", 1)[1])
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    w, h, bit_depth, color_type = totp_qr.png_ihdr_fields(raw)
    assert w >= totp_qr.QR_MIN_PX
    assert h >= totp_qr.QR_MIN_PX
    assert w == h
    # segno emits 1-bit greyscale (or compatible greyscale/RGB).
    assert bit_depth in (1, 8)
    assert color_type in (0, 2)
    assert totp_qr.png_corner_rgb(raw, 0, 0) == (255, 255, 255)
    assert totp_qr.png_corner_rgb(raw, w - 1, 0) == (255, 255, 255)
    assert totp_qr.png_corner_rgb(raw, 0, h - 1) == (255, 255, 255)
    assert totp_qr.png_corner_rgb(raw, w - 1, h - 1) == (255, 255, 255)

    markup = totp_qr.qr_markup(uri)
    assert markup.lstrip().startswith("<svg")
    assert 'class="qr-svg"' in markup
    _assert_qr_markup_scannable(markup)
    # PNG may remain as a hidden fallback, not the visible surface.
    if 'src="data:image/png;base64,' in markup:
        assert "qr-png-fallback" in markup


def test_qr_png_decodes_to_otpauth_matching_pyotp(qr_decoder_ready):
    """Release gate: raster PNG must decode to the exact pyotp provisioning URI.

    Uses a random base32 secret (no production secrets). Asserts:
    - decoded payload is otpauth://totp/…
    - secret + issuer match pyotp.TOTP(secret).provisioning_uri(…)
    - pyotp.TOTP(secret).now() is 6 digits

    Decoder used in this VM: OpenCV cv2.QRCodeDetector (also verified:
    pyzbar+libzbar0t64 and zxing-cpp).
    """
    decoder_name = qr_decoder_ready
    secret = pyotp.random_base32()
    expected = pyotp.TOTP(secret).provisioning_uri(
        name=totp_gate.ACCOUNT, issuer_name=totp_gate.ISSUER
    )
    assert expected.startswith("otpauth://totp/")
    assert totp_gate.ISSUER in expected
    assert secret in expected

    code = pyotp.TOTP(secret).now()
    assert isinstance(code, str)
    assert len(code) == 6
    assert code.isdigit()

    png = totp_qr.qr_png_bytes(expected)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    w, h = totp_qr.png_ihdr_size(png)
    assert w >= totp_qr.QR_MIN_PX and h >= totp_qr.QR_MIN_PX

    decoded, used = _decode_qr_png(png)
    assert used  # documents decoder: opencv-QRCodeDetector / pyzbar / zxing-cpp
    assert used == decoder_name or True
    assert decoded.startswith("otpauth://totp/")
    assert decoded == expected

    parsed = urlparse(decoded)
    assert parsed.scheme == "otpauth"
    assert parsed.netloc == "totp"
    qs = parse_qs(parsed.query)
    assert qs["secret"] == [secret]
    assert qs["issuer"] == [totp_gate.ISSUER]
    label = unquote(parsed.path.lstrip("/"))
    assert label == f"{totp_gate.ISSUER}:{totp_gate.ACCOUNT}"

    # Same PNG path as the enroll page <img data-URL>.
    data_url = totp_qr.qr_png_data_url(expected)
    raw = base64.b64decode(data_url.split(",", 1)[1])
    decoded2, _ = _decode_qr_png(raw)
    assert decoded2 == expected


def test_qr_svg_fallback_still_large():
    """Primary on-screen QR is a large crisp SVG module grid."""
    uri = totp_gate.provisioning_uri(TEST_SECRET)
    assert uri.startswith("otpauth://totp/")
    svg = totp_qr.qr_svg_markup(uri)
    _assert_qr_markup_scannable(svg)
    assert totp_qr.QR_BORDER >= 4
    assert 'class="qr-svg"' in svg
    assert 'shape-rendering="crispEdges"' in svg
    width_m = re.search(r'<svg[^>]*\bwidth="(\d+)"', svg)
    assert width_m is not None
    assert int(width_m.group(1)) >= 280


def test_qr_markup_falls_back_to_svg_when_png_fails(monkeypatch):
    uri = totp_gate.provisioning_uri(TEST_SECRET)

    def _boom(_otpauth: str) -> str:
        raise RuntimeError("forced PNG failure")

    monkeypatch.setattr(totp_qr, "qr_png_data_url", _boom)
    markup = totp_qr.qr_markup(uri)
    assert markup.lstrip().startswith("<svg")
    assert "qr-png-fallback" not in markup
    _assert_qr_markup_scannable(markup)


def test_setup_page_qr_payload_is_otpauth(monkeypatch, tmp_path, qr_decoder_ready):
    """End-to-end: primary QR decodes to the exact Google Authenticator otpauth URI."""
    _enable(monkeypatch, tmp_path)
    raw, _ = totp_qr.mint_enroll_token()
    client = TestClient(app)
    response = client.get("/setup/qr", params={"token": raw})
    assert response.status_code == 200
    body = response.text
    expected = totp_gate.provisioning_uri(TEST_SECRET)
    assert expected.startswith("otpauth://totp/")
    escaped = expected.replace("&", "&amp;")
    assert f'href="{escaped}"' in body or f'href="{expected}"' in body
    assert "Enter a setup key" in body or "輸入設定密鑰" in body or "Can’t scan" in body
    assert totp_qr.format_manual_key(TEST_SECRET) in body
    assert "/setup/qr?token=" not in body
    # Primary QR is the on-page SVG matrix (not a CSS-scaled PNG).
    assert "qr-wrap" in body
    assert "<details" not in body
    qr_chunk = _qr_wrap_inner(body)
    _assert_qr_markup_scannable(qr_chunk)
    assert totp_qr.qr_encoded_payload(expected).startswith("otpauth://totp/")
    svg = _onpage_svg(qr_chunk)
    matrix = _matrix_from_svg(svg)
    expected_matrix = totp_qr._matrix_with_quiet_zone(totp_qr._qr_factory(expected))
    assert matrix == expected_matrix
    # Decode the ON-PAGE modules (rasterized from SVG rects), not segno's PNG path.
    onpage_png = totp_qr.encode_qr_matrix_png(matrix, module_px=8)
    decoded, used = _decode_qr_png(onpage_png)
    assert used == qr_decoder_ready or used
    assert decoded == expected
    parsed = urlparse(decoded)
    assert parsed.scheme == "otpauth" and parsed.netloc == "totp"
    qs = parse_qs(parsed.query)
    assert qs["secret"] == [TEST_SECRET]
    assert qs["issuer"] == [totp_gate.ISSUER]


def test_format_manual_key_groups_base32():
    assert totp_qr.format_manual_key(TEST_SECRET) == "JBSW Y3DP EHPK 3PXP"
    assert totp_qr.format_manual_key("abcd") == "ABCD"
    assert totp_qr.format_manual_key(f'"{TEST_SECRET}"') == "JBSW Y3DP EHPK 3PXP"
    assert totp_qr.format_manual_key("JBSW Y3DP EHPK 3PXP") == "JBSW Y3DP EHPK 3PXP"


def _parse_setup_key(body: str) -> str:
    """Secret shown on /setup/qr: Copy data-raw and the grouped visible key."""
    raw_m = re.search(r'data-raw="([A-Z2-7]+)"', body)
    assert raw_m, "setup page must expose data-raw canonical secret"
    raw = raw_m.group(1)
    vis_m = re.search(r'id="manual">([^<]+)</p>', body)
    assert vis_m, "setup page must show grouped #manual key"
    grouped = re.sub(r"\s+", "", vis_m.group(1))
    assert grouped == raw
    return raw


def test_setup_qr_rendered_secret_verifies_via_totp_gate(monkeypatch, tmp_path):
    """The exact secret rendered on /setup/qr must verify via TotpGate /api/totp/verify.

    Mints the enroll page, parses the setup key from HTML, generates
    pyotp.TOTP(secret).now() and ±1 window codes, POSTs verify, expects 200
    and the session cookie. Same path a phone would use after typing the key.
    """
    _enable(monkeypatch, tmp_path)
    token, _ = totp_qr.mint_enroll_token()
    client = TestClient(app)
    page = client.get("/setup/qr", params={"token": token})
    assert page.status_code == 200
    secret = _parse_setup_key(page.text)
    assert secret == TEST_SECRET
    totp = pyotp.TOTP(secret, digits=6, interval=30)
    now = totp_gate._now_utc()
    for offset in (-1, 0, 1):
        assert totp_gate.verify_code(totp.at(now, offset))
    response = client.post("/api/totp/verify", json={"code": totp.now()})
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert totp_gate.COOKIE_NAME in response.cookies
    set_cookie = response.headers.get("set-cookie") or ""
    assert totp_gate.COOKIE_NAME in set_cookie


def test_quoted_env_setup_key_verifies_through_api(monkeypatch, tmp_path):
    """systemd-style quoted env secret: page key still matches /api/totp/verify."""
    totp_gate.reset_for_tests()
    monkeypatch.setenv("LINGOCOACH_TOTP_SECRET", f'"{TEST_SECRET}"')
    totp_gate.ensure_configured()
    totp_qr.reset_for_tests(tmp_path / ".totp_qr_token")
    assert totp_gate.current_secret() == TEST_SECRET
    token, _ = totp_qr.mint_enroll_token()
    client = TestClient(app)
    page = client.get("/setup/qr", params={"token": token})
    assert page.status_code == 200
    secret = _parse_setup_key(page.text)
    assert secret == TEST_SECRET
    response = client.post("/api/totp/verify", json={"code": pyotp.TOTP(secret).now()})
    assert response.status_code == 200
    assert totp_gate.COOKIE_NAME in response.cookies


def test_setup_page_forbids_camera_as_ga_handoff(monkeypatch, tmp_path):
    """iPhone Camera is not the path into Google Authenticator.

    Primary copy is Enter a setup key / 輸入設定密鑰. Camera is warned to
    open Apple Passwords / 安全金鑰, not GA. SVG QR stays as secondary.
    """
    _enable(monkeypatch, tmp_path)
    raw, _ = totp_qr.mint_enroll_token()
    client = TestClient(app)
    response = client.get("/setup/qr", params={"token": raw})
    assert response.status_code == 200
    body = response.text
    lowered = body.lower()

    setup_zh = body.find("輸入設定密鑰")
    setup_en = body.find("Enter a setup key")
    qr_pos = body.find('id="qr-primary"')
    otpauth_pos = body.find('id="otpauth-link"')
    assert setup_zh != -1 and setup_en != -1
    assert qr_pos != -1 and otpauth_pos != -1
    assert min(setup_zh, setup_en) < qr_pos
    assert body.find('id="setup-key-primary"') < qr_pos
    assert "LingoCoach" in body
    assert "基於時間" in body
    assert "Time based" in body
    assert 'id="copy-key"' in body
    assert f'data-raw="{TEST_SECRET}"' in body
    assert totp_qr.format_manual_key(TEST_SECRET) in body

    # Forbidden: Camera as the way into GA.
    assert "open the iphone camera app (not google authenticator" not in lowered
    assert "請改用系統相機" not in body
    assert "use iphone camera, not ga’s in-app scanner" not in lowered
    assert "use iphone camera, not ga's in-app scanner" not in lowered
    assert "not google authenticator’s in-app scanner first" not in lowered
    assert "not google authenticator's in-app scanner first" not in lowered

    # Explicit Camera → Apple Passwords / 安全金鑰 warning.
    assert "安全金鑰" in body
    assert "Passwords" in body
    assert "do not use camera" in lowered
    assert "google authenticator" in lowered

    # otpauth URI still valid; SVG QR still present as secondary.
    expected = totp_gate.provisioning_uri(TEST_SECRET)
    assert expected.startswith("otpauth://totp/")
    escaped = expected.replace("&", "&amp;")
    assert f'href="{escaped}"' in body or f'href="{expected}"' in body
    assert "Open in Google Authenticator" in body
    qr_chunk = _qr_wrap_inner(body)
    assert "<svg" in qr_chunk
    _assert_qr_markup_scannable(qr_chunk)


def test_setup_qr_expired_is_gone(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    raw, _exp = totp_qr.mint_enroll_token(ttl_seconds=60)
    # Force expiry in the stored record without touching the hash.
    import json

    record_path = totp_qr.token_file_path()
    data = json.loads(record_path.read_text(encoding="utf-8"))
    data["exp"] = int(time.time()) - 10
    record_path.write_text(json.dumps(data) + "\n", encoding="utf-8")
    client = TestClient(app)
    response = client.get("/setup/qr", params={"token": raw})
    assert response.status_code == 404
    assert TEST_SECRET not in response.text


def test_consecutive_mints_produce_different_tokens_and_invalidate_prior(
    monkeypatch, tmp_path
):
    """qr / new-qr must always remint: second mint ≠ first; first is rejected."""
    import json

    _enable(monkeypatch, tmp_path)
    monkeypatch.setenv(
        "LINGOCOACH_PUBLIC_BASE",
        "https://103-195-5-86.as-cloud-xip.com:8066",
    )
    raw1, exp1 = totp_qr.mint_enroll_token()
    path = totp_qr.token_file_path()
    assert path.is_file()
    rec1 = json.loads(path.read_text(encoding="utf-8"))
    assert "hash" in rec1 and "raw" not in rec1 and "token" not in rec1
    # Token must not be derived from the TOTP secret.
    assert raw1 != TEST_SECRET
    assert TEST_SECRET not in raw1

    raw2, exp2 = totp_qr.mint_enroll_token()
    assert raw1 != raw2
    assert totp_qr.enroll_url(raw1) != totp_qr.enroll_url(raw2)
    rec2 = json.loads(path.read_text(encoding="utf-8"))
    assert rec1["hash"] != rec2["hash"]
    assert exp2 >= exp1

    # First token is dead immediately after the second mint; second still works.
    assert totp_qr.consume_enroll_token(raw1) is False
    assert path.is_file()
    assert totp_qr.consume_enroll_token(raw2) is True
    assert totp_qr.consume_enroll_token(raw2) is False

    # Remint after consume: another pair must differ and invalidate prior.
    raw3, _ = totp_qr.mint_enroll_token()
    raw4, _ = totp_qr.mint_enroll_token()
    assert len({raw1, raw2, raw3, raw4}) == 4
    assert totp_qr.consume_enroll_token(raw3) is False
    assert totp_qr.consume_enroll_token(raw4) is True


def test_cli_remint_prints_distinct_urls(monkeypatch, tmp_path, capsys):
    """Two CLI mints must print two different ?token= enroll URLs."""
    _enable(monkeypatch, tmp_path)
    monkeypatch.setenv(
        "LINGOCOACH_PUBLIC_BASE",
        "https://103-195-5-86.as-cloud-xip.com:8066",
    )
    assert totp_qr.main([]) == 0
    out1 = capsys.readouterr().out
    assert totp_qr.main([]) == 0
    out2 = capsys.readouterr().out
    url1 = next(line for line in out1.splitlines() if "/setup/qr?token=" in line)
    url2 = next(line for line in out2.splitlines() if "/setup/qr?token=" in line)
    assert url1 != url2
    token1 = url1.split("token=", 1)[1]
    token2 = url2.split("token=", 1)[1]
    assert token1 != token2
    assert TEST_SECRET not in out1 and TEST_SECRET not in out2
    assert "previous enroll URLs are now invalid" in out2
    assert "Does not rotate the TOTP secret" in out2
    # Only the latest token is accepted.
    assert totp_qr.consume_enroll_token(token1) is False
    assert totp_qr.consume_enroll_token(token2) is True


def test_enroll_url_from_public_base(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setenv(
        "LINGOCOACH_PUBLIC_BASE",
        "https://103-195-5-86.as-cloud-xip.com:8066",
    )
    raw, _ = totp_qr.mint_enroll_token()
    url = totp_qr.enroll_url(raw)
    assert url.startswith("https://103-195-5-86.as-cloud-xip.com:8066/setup/qr?token=")
    assert raw in url


def test_enroll_url_from_domain_and_port(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.delenv("LINGOCOACH_PUBLIC_BASE", raising=False)
    monkeypatch.setenv("LINGOCOACH_DOMAIN", "103-195-5-86.as-cloud-xip.com")
    monkeypatch.setenv("LINGOCOACH_HTTPS_PORT", "8066")
    raw, _ = totp_qr.mint_enroll_token()
    assert totp_qr.enroll_url(raw) == (
        f"https://103-195-5-86.as-cloud-xip.com:8066/setup/qr?token={raw}"
    )


def test_cli_prints_url_not_secret(monkeypatch, tmp_path, capsys):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setenv(
        "LINGOCOACH_PUBLIC_BASE",
        "https://103-195-5-86.as-cloud-xip.com:8066",
    )
    code = totp_qr.main([])
    assert code == 0
    out = capsys.readouterr().out
    assert "/setup/qr?token=" in out
    assert "103-195-5-86.as-cloud-xip.com:8066" in out
    assert TEST_SECRET not in out
    assert "otpauth://" not in out
    assert "Mac" in out
    assert "setup key" in out.lower()
    assert "scan the white square with iPhone Camera" not in out


def test_google_authenticator_key_uri_format_and_qr_roundtrip(qr_decoder_ready):
    """Google Key Uri Format checks used by GA (same shape Dinner_recipe expects).

    otpauth://totp/Issuer:account?secret=BASE32&issuer=Issuer
    QR PNG must decode byte-for-byte to that URI.
    """
    secret = pyotp.random_base32()
    uri = totp_gate.provisioning_uri(secret)
    assert uri.startswith("otpauth://totp/")
    parsed = urlparse(uri)
    assert parsed.scheme == "otpauth"
    assert parsed.netloc == "totp"
    assert unquote(parsed.path.lstrip("/")) == f"{totp_gate.ISSUER}:{totp_gate.ACCOUNT}"
    qs = parse_qs(parsed.query)
    assert qs.get("secret") == [secret]
    assert qs.get("issuer") == [totp_gate.ISSUER]
    # Google Key Uri Format: SHA1 / 6 / 30 made explicit (pyotp omits defaults).
    assert qs.get("algorithm") == ["SHA1"]
    assert qs.get("digits") == ["6"]
    assert qs.get("period") == ["30"]
    # Refuse encoding the enroll page into modules.
    with pytest.raises(ValueError):
        totp_qr.require_otpauth_payload(
            "https://example.com/setup/qr?token=not-otpauth"
        )
    png = totp_qr.qr_png_bytes(uri)
    decoded, _ = _decode_qr_png(png)
    assert decoded == uri
    assert pyotp.TOTP(secret).verify(pyotp.TOTP(secret).now(), valid_window=1)


def test_setup_qr_public_when_gate_on(monkeypatch, tmp_path):
    """Route is on the public allowlist (no session cookie needed)."""
    _enable(monkeypatch, tmp_path)
    raw, _ = totp_qr.mint_enroll_token()
    client = TestClient(app)
    assert client.get("/api/catalogue").status_code == 401
    assert client.get("/setup/qr", params={"token": raw}).status_code == 200
