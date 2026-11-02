"""One-time Authenticator QR enroll page: token gate, single use, TTL."""

from __future__ import annotations

import base64
import io
import time
from urllib.parse import parse_qs, unquote, urlparse

import pyotp
from fastapi.testclient import TestClient

from app import totp_gate
from app import totp_qr
from app.main import app

TEST_SECRET = "JBSWY3DPEHPK3PXP"


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
    # Prefer PNG data-URL for Google Authenticator camera reliability.
    assert 'src="data:image/png;base64,' in body
    assert 'alt="Authenticator QR code"' in body
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
        name=totp_gate.ACCOUNT, issuer_name=totp_gate.ISSUER
    ) == uri


def test_qr_png_is_large_high_contrast():
    uri = totp_gate.provisioning_uri(TEST_SECRET)
    data_url = totp_qr.qr_png_data_url(uri)
    assert data_url.startswith("data:image/png;base64,")
    raw = base64.b64decode(data_url.split(",", 1)[1])
    from PIL import Image

    img = Image.open(io.BytesIO(raw))
    assert img.size[0] >= totp_qr.QR_MIN_PX
    assert img.size[1] >= totp_qr.QR_MIN_PX
    # Corner quiet zone should be white (high contrast pad).
    assert img.getpixel((0, 0)) == (255, 255, 255)
    # Markup wraps PNG for the setup page.
    markup = totp_qr.qr_markup(uri)
    assert 'src="data:image/png;base64,' in markup
    assert "qr-img" in markup


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
