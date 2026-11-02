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

    first = client.get("/setup/qr", params={"token": raw})
    assert first.status_code == 200
    body = first.text
    assert "LingoCoach" in body
    assert "works once" in body.lower() or "This link works once" in body
    assert TEST_SECRET in body
    assert "otpauth://totp/" in totp_gate.provisioning_uri(TEST_SECRET)
    # Manual setup key is the primary path.
    assert "Enter a setup key" in body
    assert "Recommended" in body
    assert "Copy" in body
    assert totp_qr.format_manual_key(TEST_SECRET) in body
    # Default is segno PNG data-URL (SVG only as fallback).
    qr_chunk = body.split('class="qr-wrap"', 1)[1].split("</div>", 1)[0]
    assert 'src="data:image/png;base64,' in qr_chunk
    _assert_qr_markup_scannable(qr_chunk)
    assert "Cache-Control" in first.headers
    assert "no-store" in first.headers.get("cache-control", "")

    second = client.get("/setup/qr", params={"token": raw})
    assert second.status_code == 404
    assert TEST_SECRET not in second.text
    assert not totp_qr.token_file_path().is_file()


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
    qr = totp_qr._qr_factory(uri)
    matrix = totp_qr._matrix_with_quiet_zone(qr)
    assert matrix[0][0] is False
    core = qr.symbol_size(scale=1, border=0)[0]
    assert len(matrix) == core + 2 * totp_qr.QR_BORDER


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
    core = qr.symbol_size(scale=1, border=0)[0]
    assert len(matrix) == core + 2 * totp_qr.QR_BORDER

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


def test_qr_png_bytes_decodable_otpauth():
    """PNG bytes must be a valid image whose QR payload is otpauth://totp/…"""
    uri = totp_gate.provisioning_uri(TEST_SECRET)
    png = totp_qr.qr_png_bytes(uri)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    w, h = totp_qr.png_ihdr_size(png)
    assert w == h and w >= totp_qr.QR_MIN_PX
    assert totp_qr.png_corner_rgb(png, 0, 0) == (255, 255, 255)

    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")
    import io

    im = Image.open(io.BytesIO(png))
    val, pts, _ = cv2.QRCodeDetector().detectAndDecode(
        np.array(im.convert("RGB"))
    )
    assert pts is not None
    assert val.startswith("otpauth://totp/")
    assert val == uri


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


def test_setup_page_qr_payload_is_otpauth(monkeypatch, tmp_path):
    """End-to-end: /setup/qr HTML QR was built from otpauth://totp/ modules."""
    _enable(monkeypatch, tmp_path)
    raw, _ = totp_qr.mint_enroll_token()
    client = TestClient(app)
    response = client.get("/setup/qr", params={"token": raw})
    assert response.status_code == 200
    body = response.text
    qr_chunk = body.split('class="qr-wrap"', 1)[1].split("</div>", 1)[0]
    _assert_qr_markup_scannable(qr_chunk)
    assert "Enter a setup key" in body
    assert totp_qr.format_manual_key(TEST_SECRET) in body
    expected = pyotp.TOTP(TEST_SECRET).provisioning_uri(
        name=totp_gate.ACCOUNT, issuer_name="LingoCoach"
    )
    assert expected.startswith("otpauth://totp/")
    assert "/setup/qr?token=" not in body
    assert totp_qr.qr_encoded_payload(expected).startswith("otpauth://totp/")


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


def test_setup_qr_public_when_gate_on(monkeypatch, tmp_path):
    """Route is on the public allowlist (no session cookie needed)."""
    _enable(monkeypatch, tmp_path)
    raw, _ = totp_qr.mint_enroll_token()
    client = TestClient(app)
    assert client.get("/api/catalogue").status_code == 401
    assert client.get("/setup/qr", params={"token": raw}).status_code == 200
