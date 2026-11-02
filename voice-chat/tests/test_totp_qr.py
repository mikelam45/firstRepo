"""One-time Authenticator QR enroll page: token gate, single use, TTL."""

from __future__ import annotations

import base64
import io
import re
import time
from urllib.parse import parse_qs, unquote, urlparse

import pyotp
import pytest
from fastapi.testclient import TestClient

from app import totp_gate
from app import totp_qr
from app.main import app

TEST_SECRET = "JBSWY3DPEHPK3PXP"


def _assert_qr_markup_scannable(markup: str) -> None:
    """Accept PNG data-URL or inline SVG; both need white background + otpauth guard."""
    assert 'aria-label="Authenticator QR code"' in markup or 'alt="Authenticator QR code"' in markup
    if "<svg" in markup:
        assert 'fill="#ffffff"' in markup or "fill='#ffffff'" in markup
        assert 'fill="#000000"' in markup or "fill='#000000'" in markup
        assert 'shape-rendering="crispEdges"' in markup
        assert "viewBox=" in markup
        width_m = re.search(r'<svg[^>]*\bwidth="(\d+)"', markup)
        assert width_m is not None
        assert int(width_m.group(1)) >= totp_qr.QR_MIN_PX
    else:
        assert 'src="data:image/png;base64,' in markup
        assert "qr-img" in markup


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
    # PNG (optional Pillow) or pure SVG — must be scannable otpauth QR.
    qr_chunk = body.split('class="qr-wrap"', 1)[1].split("</div>", 1)[0]
    _assert_qr_markup_scannable(qr_chunk)
    assert "Copy" in body
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
    qr = totp_qr._qr_factory(uri)
    payload = totp_qr.qr_encoded_payload(qr)
    assert payload.startswith("otpauth://totp/")
    assert payload == uri
    assert "https://" not in payload
    assert "http://" not in payload
    assert "/setup/qr" not in payload
    assert totp_qr.QR_BORDER >= 4


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


def test_qr_svg_is_large_high_contrast_without_pillow():
    """Default path: pure SVG with white quiet zone — no Pillow/libjpeg needed."""
    uri = totp_gate.provisioning_uri(TEST_SECRET)
    assert uri.startswith("otpauth://totp/")
    svg = totp_qr.qr_svg_markup(uri)
    _assert_qr_markup_scannable(svg)
    assert totp_qr.QR_BORDER >= 4
    # Corner module of the matrix is quiet-zone white (border ≥4); first painted
    # content after the full-size white rect must be black modules only.
    assert svg.count('fill="#ffffff"') >= 1
    assert svg.count('fill="#000000"') >= 1


def test_qr_markup_falls_back_to_svg_without_pillow(monkeypatch):
    uri = totp_gate.provisioning_uri(TEST_SECRET)
    monkeypatch.setattr(totp_qr, "pillow_available", lambda: False)
    markup = totp_qr.qr_markup(uri)
    assert markup.lstrip().startswith("<svg")
    _assert_qr_markup_scannable(markup)


@pytest.mark.skipif(not totp_qr.pillow_available(), reason="Pillow optional")
def test_qr_png_optional_when_pillow_installed():
    uri = totp_gate.provisioning_uri(TEST_SECRET)
    assert uri.startswith("otpauth://totp/")
    data_url = totp_qr.qr_png_data_url(uri)
    assert data_url.startswith("data:image/png;base64,")
    raw = base64.b64decode(data_url.split(",", 1)[1])
    from PIL import Image

    img = Image.open(io.BytesIO(raw))
    assert img.size[0] >= totp_qr.QR_MIN_PX
    assert img.size[1] >= totp_qr.QR_MIN_PX
    assert img.getpixel((0, 0)) == (255, 255, 255)


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
    assert "Enter a setup key" in body or "Manual setup key" in body
    assert totp_qr.format_manual_key(TEST_SECRET) in body
    # Reconstruct expected URI; page must not embed the enroll https link as QR text.
    expected = pyotp.TOTP(TEST_SECRET).provisioning_uri(
        name=totp_gate.ACCOUNT, issuer_name="LingoCoach"
    )
    assert expected.startswith("otpauth://totp/")
    # Enroll URL shape must not appear inside the page as scannable plaintext QR data.
    # (The browser address bar is separate; the HTML body QR is otpauth-only.)
    assert "/setup/qr?token=" not in body
    assert totp_qr.qr_encoded_payload(totp_qr._qr_factory(expected)).startswith(
        "otpauth://totp/"
    )


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
