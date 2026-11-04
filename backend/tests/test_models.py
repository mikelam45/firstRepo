import json

import pytest
from fastapi.testclient import TestClient

from app.catalog import DEFAULT_SELECTION, FUNCTION_IDS
from app.main import PAGE, SETUP_PAGE, app

LABELS = (
    "RAG and document analysis",
    "Standard translation",
    "Cantonese script writing",
    "Image and storyboard",
    "Video generation",
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("PORTAL_API_TOKEN", raising=False)
    return TestClient(app)


def _prices(payload):
    found = []
    for row in payload["summary"]:
        for price in row["prices"]:
            found.append(price)
    return found


def test_packaged_index_html_exists():
    assert PAGE.is_file()
    assert PAGE.name == "index.html"
    assert SETUP_PAGE.is_file()
    home = PAGE.read_text(encoding="utf-8")
    setup = SETUP_PAGE.read_text(encoding="utf-8")
    assert "Document upload" in home
    assert "OpenRouter connection" in setup
    assert "LLM setup" in setup


def test_page_lists_every_function(client):
    home = client.get("/")
    assert home.status_code == 200
    assert home.status_code != 404
    assert "text/html" in home.headers["content-type"]
    for label in LABELS:
        assert label in home.text
    assert "Chat" in home.text
    assert "not sent as chat completions" in home.text
    assert 'id="chat-send"' in home.text
    assert 'id="rag-upload"' in home.text
    assert "OpenRouter connection" not in home.text

    setup = client.get("/setup")
    assert setup.status_code == 200
    assert "text/html" in setup.headers["content-type"]
    for label in LABELS:
        assert label in setup.text
    assert "A single total is not shown" in setup.text
    assert "OpenRouter connection" in setup.text
    assert 'id="openrouter-save"' in setup.text
    assert 'id="openrouter-test"' in setup.text
    assert "openrouter_configured" in setup.text
    assert 'id="rag-upload"' not in setup.text
    assert 'id="chat-send"' not in setup.text

    settings = client.get("/settings")
    assert settings.status_code == 200
    assert "OpenRouter connection" in settings.text


def test_get_returns_defaults_and_a_priced_unit(client):
    response = client.get("/api/models")
    assert response.status_code == 200
    payload = response.json()

    assert [item["id"] for item in payload["functions"]] == list(FUNCTION_IDS)
    assert [item["label"] for item in payload["functions"]] == list(LABELS)
    assert payload["selection"] == DEFAULT_SELECTION
    assert payload["prices_recorded_on"] == "2026-11-03"

    prices = _prices(payload)
    assert prices
    for price in prices:
        assert price["unit"].startswith("USD per ")
        assert price["amount_usd"]
        assert price["price_status"] in {"confirmed", "estimate"}
    assert all(price["price_status"] == "confirmed" for price in prices)
    assert "not shown" in payload["cost_note"].lower() or "not mean anything" in payload["cost_note"]


def test_put_swaps_a_model_and_get_shows_it(client, tmp_path):
    updated = dict(DEFAULT_SELECTION)
    updated["rag_qa"] = "anthropic/claude-sonnet-5.5"
    updated["image_gen"] = "black-forest-labs/flux.2-pro"
    updated["video_gen"] = "minimax/hailuo-3"

    saved = client.put("/api/models", json=updated)
    assert saved.status_code == 200
    assert saved.json()["selection"] == updated
    rag = next(row for row in saved.json()["summary"] if row["function_id"] == "rag_qa")
    assert rag["model_id"] == "anthropic/claude-sonnet-5.5"
    assert rag["provider"] == "Anthropic"
    assert any(price["unit"] == "USD per 1M tokens" for price in rag["prices"])

    again = client.get("/api/models")
    assert again.json()["selection"] == updated

    on_disk = json.loads((tmp_path / "model-selection.json").read_text(encoding="utf-8"))
    assert on_disk["selection"] == updated


def test_put_rejects_unknown_and_disallowed_models(client, tmp_path):
    unknown = dict(DEFAULT_SELECTION)
    unknown["translation"] = "anthropic/claude-3.5-sonnet"
    rejected = client.put("/api/models", json=unknown)
    assert rejected.status_code == 400
    assert "Unknown model id" in rejected.json()["detail"]

    wrong_function = dict(DEFAULT_SELECTION)
    wrong_function["rag_qa"] = "minimax/hailuo-2.3"
    rejected = client.put("/api/models", json=wrong_function)
    assert rejected.status_code == 400
    assert "not allowed for rag_qa" in rejected.json()["detail"]

    assert not (tmp_path / "model-selection.json").exists()
    assert client.get("/api/models").json()["selection"] == DEFAULT_SELECTION


def test_production_put_requires_token_and_get_stays_open(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PORTAL_API_TOKEN", "test-token")
    client = TestClient(app)

    opened = client.get("/api/models")
    assert opened.status_code == 200
    assert opened.json()["selection"] == DEFAULT_SELECTION

    body = dict(DEFAULT_SELECTION)
    body["translation"] = "openai/gpt-4o"
    rejected = client.put("/api/models", json=body)
    assert rejected.status_code == 401

    accepted = client.put(
        "/api/models",
        json=body,
        headers={"Authorization": "Bearer test-token"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["selection"]["translation"] == "openai/gpt-4o"
    assert client.get("/api/models").json()["selection"]["translation"] == "openai/gpt-4o"
