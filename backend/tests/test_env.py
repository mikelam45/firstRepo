from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("PORTAL_API_TOKEN", raising=False)
    return TestClient(app)


def test_development_health_and_note(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "env": "development",
        "openrouter_configured": False,
    }

    created = client.post("/api/notes", json={"body": "Mac dev note"})
    assert created.status_code == 201
    assert created.json()["body"] == "Mac dev note"

    listed = client.get("/api/notes")
    assert listed.status_code == 200
    assert listed.json() == [{"id": 1, "body": "Mac dev note"}]


def test_production_requires_token(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PORTAL_API_TOKEN", "test-token")
    client = TestClient(app)

    assert client.get("/health").json()["env"] == "production"
    rejected = client.post("/api/notes", json={"body": "should fail"})
    assert rejected.status_code == 401

    accepted = client.post(
        "/api/notes",
        json={"body": "vps note"},
        headers={"Authorization": "Bearer test-token"},
    )
    assert accepted.status_code == 201
    assert accepted.json()["body"] == "vps note"


def test_production_refuses_to_boot_without_token(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PORTAL_API_TOKEN", "")
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health")
    assert response.status_code == 500


def test_unknown_env_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/health").status_code == 500


def test_dev_port_default_is_8099():
    example = (REPO_ROOT / ".env.development.example").read_text(encoding="utf-8")
    dev = (REPO_ROOT / "scripts" / "dev.sh").read_text(encoding="utf-8")
    assert "PORT=8099" in example
    assert "${PORT:-8099}" in dev


def test_cloud_install_prefers_312_then_313_and_pins_cp314_wheels():
    script = (REPO_ROOT / "scripts" / "cloud-install.sh").read_text(encoding="utf-8")
    assert script.index("python3.12") < script.index("python3.13")
    assert "--only-binary=pydantic-core" in script
    assert "brew install python@3.12" in script
    req = (REPO_ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
    assert "pydantic==2.12.5" in req
    assert "pydantic-core==2.41.5" in req
    assert "fastapi==0.118.3" in req
