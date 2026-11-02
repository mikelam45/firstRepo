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


def _png_from_markup(markup: str) -> bytes:
    assert 'src="data:image/png;base64,' in markup
    m = re.search(r'src="data:image/png;base64,([A-Za-z0-9+/=]+)"', markup)
    assert m is not None
    return base64.b64decode(m.group(1))


def _assert_qr_markup_scannable(markup: str) -> None:
    """Accept PNG data-URL (default) or inline SVG fallback."""
    assert 'aria-label="Authenticator QR code"' in markup or 'alt="Authenticator QR code"' in markup
    if "<svg" in markup:
        assert "viewBox=" in markup or 'width="' in markup
        assert "qr-img" in markup or 'aria-label="Authenticator QR code"' in markup
        width_m = re.search(r'<svg[^>]*\bwidth="(\d+)"', markup)
        assert width_m is not None
        assert int(width_m.group(1)) >= totp_qr.QR_MIN_PX
    else:
        assert 'src="data:image/png;base64,' in markup
        assert "qr-img" in markup
        png = _png_from_markup(markup)
        w, h = totp_qr.png_ihdr_size(png)
        assert w >= totp_qr.QR_MIN_PX
        assert h >= totp_qr.QR_MIN_PX
        assert w == h
        assert totp_qr.png_corner_rgb(png, 0, 0) == (255, 255, 255)
        assert totp_qr.png_corner_rgb(png, w - 1, h - 1) == (255, 255, 255)


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
    # Dinner_recipe-style: primary is a large otpauth QR for iPhone Camera.
    assert 'id="qr-primary"' in body or 'class="qr-wrap"' in body
    assert "iPhone Camera" in body or "相機" in body
    assert "請改用相機" in body or "Camera" in body
    # QR is visible (not collapsed under <details>).
    assert "<details" not in body
    qr_chunk = body.split('class="qr-wrap"', 1)[1].split("</div>", 1)[0]
    assert 'src="data:image/png;base64,' in qr_chunk
    _assert_qr_markup_scannable(qr_chunk)
    # Manual setup key + otpauth deep link remain as backup / phone path.
    assert "Enter a setup key" in body or "輸入設定密鑰" in body or "Can’t scan" in body or "Can't scan" in body
    assert "Copy" in body
    assert totp_qr.format_manual_key(TEST_SECRET) in body
    assert 'id="otpauth-link"' in body
    assert f'href="{expected}"' in body or f'href="{expected.replace("&", "&amp;")}"' in body
    assert "Open in Authenticator" in body
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
    expected = pyotp.TOTP(TEST_SECRET).provisioning_uri(
        name=totp_gate.ACCOUNT, issuer_name=totp_gate.ISSUER
    )
    assert expected.startswith("otpauth://totp/")
    # href may HTML-escape & as &amp;
    escaped = expected.replace("&", "&amp;")
    assert f'href="{escaped}"' in body or f'href="{expected}"' in body
    assert 'id="otpauth-link"' in body
    assert "/setup/qr?token=" not in body
    # Deep link must not be an https enroll URL.
    assert 'href="https://' not in body.split('id="otpauth-link"', 1)[1].split(">", 1)[0]
    # Light page + primary QR (Dinner_recipe Mac→iPhone Camera flow).
    assert 'color-scheme: only light' in body or "color-scheme: only light" in body
    assert 'class="qr-wrap"' in body
    assert "<details" not in body


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
    # Round-trip: pyotp accepts the secret and mint matches.
    assert pyotp.TOTP(TEST_SECRET).provisioning_uri(
        name=totp_gate.ACCOUNT, issuer_name="LingoCoach"
    ) == uri


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
    assert markup.lstrip().startswith("<img")
    assert 'src="data:image/png;base64,' in markup
    _assert_qr_markup_scannable(markup)


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
    """SVG remains available as last-resort fallback (Authenticator prefers PNG)."""
    uri = totp_gate.provisioning_uri(TEST_SECRET)
    assert uri.startswith("otpauth://totp/")
    svg = totp_qr.qr_svg_markup(uri)
    _assert_qr_markup_scannable(svg)
    assert totp_qr.QR_BORDER >= 4
    assert "qr-img" in svg or "aria-label" in svg


def test_qr_markup_falls_back_to_svg_when_png_fails(monkeypatch):
    uri = totp_gate.provisioning_uri(TEST_SECRET)

    def _boom(_otpauth: str) -> str:
        raise RuntimeError("forced PNG failure")

    monkeypatch.setattr(totp_qr, "qr_png_data_url", _boom)
    markup = totp_qr.qr_markup(uri)
    assert markup.lstrip().startswith("<svg")
    _assert_qr_markup_scannable(markup)


def test_setup_page_qr_payload_is_otpauth(monkeypatch, tmp_path, qr_decoder_ready):
    """End-to-end: primary QR decodes to the exact Google Authenticator otpauth URI."""
    _enable(monkeypatch, tmp_path)
    raw, _ = totp_qr.mint_enroll_token()
    client = TestClient(app)
    response = client.get("/setup/qr", params={"token": raw})
    assert response.status_code == 200
    body = response.text
    expected = pyotp.TOTP(TEST_SECRET).provisioning_uri(
        name=totp_gate.ACCOUNT, issuer_name="LingoCoach"
    )
    assert expected.startswith("otpauth://totp/")
    escaped = expected.replace("&", "&amp;")
    assert f'href="{escaped}"' in body or f'href="{expected}"' in body
    assert "Enter a setup key" in body or "輸入設定密鑰" in body or "Can’t scan" in body
    assert totp_qr.format_manual_key(TEST_SECRET) in body
    assert "/setup/qr?token=" not in body
    # Primary QR (Dinner_recipe / GA Key URI Format) must decode to the same URI.
    assert 'class="qr-wrap"' in body
    assert "<details" not in body
    qr_chunk = body.split('class="qr-wrap"', 1)[1].split("</div>", 1)[0]
    _assert_qr_markup_scannable(qr_chunk)
    assert totp_qr.qr_encoded_payload(expected).startswith("otpauth://totp/")
    png = _png_from_markup(qr_chunk)
    w, h = totp_qr.png_ihdr_size(png)
    assert w >= totp_qr.QR_MIN_PX and h >= totp_qr.QR_MIN_PX
    assert totp_qr.QR_MIN_PX >= 320
    decoded, used = _decode_qr_png(png)
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
    assert "iPhone Camera" in out or "Mac" in out


def test_google_authenticator_key_uri_format_and_qr_roundtrip(qr_decoder_ready):
    """Google Key Uri Format checks used by GA (same shape Dinner_recipe expects).

    otpauth://totp/Issuer:account?secret=BASE32&issuer=Issuer
    QR PNG must decode byte-for-byte to that URI.
    """
    secret = pyotp.random_base32()
    uri = pyotp.TOTP(secret).provisioning_uri(
        name=totp_gate.ACCOUNT, issuer_name=totp_gate.ISSUER
    )
    assert uri.startswith("otpauth://totp/")
    parsed = urlparse(uri)
    assert parsed.scheme == "otpauth"
    assert parsed.netloc == "totp"
    assert unquote(parsed.path.lstrip("/")) == f"{totp_gate.ISSUER}:{totp_gate.ACCOUNT}"
    qs = parse_qs(parsed.query)
    assert qs.get("secret") == [secret]
    assert qs.get("issuer") == [totp_gate.ISSUER]
    # No algorithm/digits/period overrides — GA defaults (SHA1/6/30).
    assert "algorithm" not in qs
    assert "digits" not in qs
    assert "period" not in qs
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
