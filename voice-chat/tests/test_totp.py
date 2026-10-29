"""TOTP unlock gate: invalid codes, session cookie, protected routes, public health."""

from __future__ import annotations

import pyotp
from fastapi.testclient import TestClient

from app import totp_gate
from app.main import app

# Fixed test-only base32 secret (not a production value).
TEST_SECRET = "JBSWY3DPEHPK3PXP"


def _enable(monkeypatch):
    totp_gate.reset_for_tests()
    monkeypatch.setenv("LINGOCOACH_TOTP_SECRET", TEST_SECRET)
    totp_gate.ensure_configured()
    assert totp_gate.is_enabled()


def _disable(monkeypatch):
    totp_gate.reset_for_tests()
    monkeypatch.delenv("LINGOCOACH_TOTP_SECRET", raising=False)
    monkeypatch.delenv("TOTP_SECRET", raising=False)
    # Avoid picking up a developer .totp_secret during tests.
    monkeypatch.setattr(totp_gate, "_SECRET_FILE", totp_gate._SECRET_FILE.with_name(".totp_secret_test_missing"))
    totp_gate.ensure_configured()
    assert not totp_gate.is_enabled()


def test_health_public_without_cookie(monkeypatch):
    _enable(monkeypatch)
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_turn_without_cookie_is_401(monkeypatch):
    _enable(monkeypatch)
    client = TestClient(app)
    response = client.post(
        "/api/turn",
        json={
            "session_id": "s",
            "scenario_id": "hk-cha-chaan-teng",
            "settings": {
                "target": "yue",
                "support": "en",
                "level": "beginner",
                "script": "Hant",
                "accent": "en-GB",
                "pinyin_tone": "mark",
            },
            "history": [],
        },
    )
    assert response.status_code == 401
    assert response.json()["error"] == "auth_required"


def test_index_redirects_to_login(monkeypatch):
    _enable(monkeypatch)
    client = TestClient(app, follow_redirects=False)
    response = client.get("/", headers={"Accept": "text/html"})
    assert response.status_code == 303
    assert response.headers.get("location") == "/login"


def test_invalid_code_is_401(monkeypatch):
    _enable(monkeypatch)
    client = TestClient(app)
    response = client.post("/api/totp/verify", json={"code": "000000"})
    assert response.status_code == 401
    assert response.json()["error"] == "invalid_code"
    assert totp_gate.COOKIE_NAME not in response.cookies


def test_valid_code_sets_session_and_unlocks(monkeypatch):
    _enable(monkeypatch)
    client = TestClient(app)
    code = pyotp.TOTP(TEST_SECRET).now()
    response = client.post("/api/totp/verify", json={"code": code})
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert totp_gate.COOKIE_NAME in response.cookies
    # Local HTTP: Secure must stay off so the browser stores lc_session.
    set_cookie = response.headers.get("set-cookie") or ""
    assert "Secure" not in set_cookie

    catalogue = client.get("/api/catalogue")
    assert catalogue.status_code == 200
    assert "partners" in catalogue.json()

    turn = client.post(
        "/api/turn",
        json={
            "session_id": "s",
            "scenario_id": "hk-cha-chaan-teng",
            "settings": {
                "target": "yue",
                "support": "en",
                "level": "beginner",
                "script": "Hant",
                "accent": "en-GB",
                "pinyin_tone": "mark",
            },
            "history": [],
        },
    )
    assert turn.status_code == 200


def test_secure_cookie_when_https_proxy_mode(monkeypatch):
    """Behind Caddy, deploy sets LINGOCOACH_HTTPS=1; cookie must be Secure."""
    _enable(monkeypatch)
    monkeypatch.setenv("LINGOCOACH_HTTPS", "1")
    client = TestClient(app)
    code = pyotp.TOTP(TEST_SECRET).now()
    response = client.post(
        "/api/totp/verify",
        json={"code": code},
        headers={"X-Forwarded-Proto": "https"},
    )
    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie") or ""
    assert "Secure" in set_cookie
    assert "HttpOnly" in set_cookie


def test_secure_cookie_with_https_flag_without_forwarded_header(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv("LINGOCOACH_HTTPS", "1")
    client = TestClient(app)
    code = pyotp.TOTP(TEST_SECRET).now()
    response = client.post("/api/totp/verify", json={"code": code})
    assert response.status_code == 200
    assert "Secure" in (response.headers.get("set-cookie") or "")


def test_no_secure_cookie_when_forwarded_proto_spoofed_without_flag(monkeypatch):
    """Ignore X-Forwarded-Proto unless LINGOCOACH_HTTPS is opted in."""
    _enable(monkeypatch)
    monkeypatch.delenv("LINGOCOACH_HTTPS", raising=False)
    client = TestClient(app)
    code = pyotp.TOTP(TEST_SECRET).now()
    response = client.post(
        "/api/totp/verify",
        json={"code": code},
        headers={"X-Forwarded-Proto": "https"},
    )
    assert response.status_code == 200
    assert "Secure" not in (response.headers.get("set-cookie") or "")


def test_login_page_is_public(monkeypatch):
    _enable(monkeypatch)
    client = TestClient(app)
    response = client.get("/login")
    assert response.status_code == 200
    assert "LingoCoach" in response.text
    assert "one-time" in response.text.lower() or "Unlock" in response.text


def test_setup_unavailable_without_just_created(monkeypatch):
    _enable(monkeypatch)
    client = TestClient(app)
    response = client.get("/api/totp/setup")
    assert response.status_code == 404


def test_setup_once_after_mark(monkeypatch):
    _enable(monkeypatch)
    totp_gate.mark_just_created()
    client = TestClient(app)
    first = client.get("/api/totp/setup")
    assert first.status_code == 200
    body = first.json()
    assert body["otpauth_uri"].startswith("otpauth://totp/")
    assert body["secret_length"] == len(TEST_SECRET)
    second = client.get("/api/totp/setup")
    assert second.status_code == 404


def test_gate_skipped_when_unset(monkeypatch):
    _disable(monkeypatch)
    client = TestClient(app)
    response = client.get("/api/catalogue")
    assert response.status_code == 200


def test_totp_secret_alias_enables_gate(monkeypatch):
    totp_gate.reset_for_tests()
    monkeypatch.delenv("LINGOCOACH_TOTP_SECRET", raising=False)
    monkeypatch.setenv("TOTP_SECRET", TEST_SECRET)
    monkeypatch.setattr(totp_gate, "_SECRET_FILE", totp_gate._SECRET_FILE.with_name(".totp_secret_test_missing"))
    totp_gate.ensure_configured()
    assert totp_gate.is_enabled()
    client = TestClient(app)
    assert client.get("/api/catalogue").status_code == 401
    code = pyotp.TOTP(TEST_SECRET).now()
    assert client.post("/api/totp/verify", json={"code": code}).status_code == 200
    assert client.get("/api/catalogue").status_code == 200


def test_static_assets_gated_when_enabled(monkeypatch):
    _enable(monkeypatch)
    client = TestClient(app)
    response = client.get("/static/styles.css")
    assert response.status_code == 401
