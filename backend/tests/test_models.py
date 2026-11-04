import json

import pytest
from fastapi.testclient import TestClient

from app.catalog import (
    DEFAULT_SELECTION,
    FUNCTION_IDS,
    RECOMMENDED_HK_IMAGE_MODEL,
    RECOMMENDED_HK_TEXT_MODEL,
    hidden_catalog_ids,
    models_for,
)
from app.main import PAGE, SETUP_PAGE, app
from app.region import reset_probe_cache

LABELS = (
    "RAG and document analysis",
    "Standard translation",
    "Cantonese script writing",
    "DSE Math assistant",
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


def _public_option_ids(payload):
    return {
        option["id"]
        for item in payload["functions"]
        for option in item["options"]
    }


def _assert_gemini_absent(payload):
    option_ids = _public_option_ids(payload)
    assert "google/gemini-2.5-flash" not in option_ids
    assert "google/gemini-3.1-flash-image" not in option_ids
    assert "google/gemini-2.5-flash" not in payload["selection"].values()
    assert "google/gemini-3.1-flash-image" not in payload["selection"].values()
    assert "gemini" not in json.dumps(payload["functions"]).lower()
    for item in payload["functions"]:
        assert item["selected_model_id"] != "google/gemini-2.5-flash"
        assert all("region_note" not in option for option in item["options"])


def test_packaged_index_html_exists():
    assert PAGE.is_file()
    assert PAGE.name == "index.html"
    assert SETUP_PAGE.is_file()
    home = PAGE.read_text(encoding="utf-8")
    setup = SETUP_PAGE.read_text(encoding="utf-8")
    assert "Document upload" in home
    assert "OpenRouter connection" in setup
    assert "LLM setup" in setup
    assert "Only models available in Hong Kong are listed" in setup
    assert "google/gemini-2.5-flash" not in setup
    assert "region_note" not in setup


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
    assert payload["recommended_hk_text_model"] == RECOMMENDED_HK_TEXT_MODEL
    assert payload["selection"]["rag_qa"] == "deepseek/deepseek-chat"
    assert payload["selection"]["translation"] == "deepseek/deepseek-chat"
    assert payload["selection"]["cantonese_script"] == "deepseek/deepseek-chat"
    assert payload["selection"]["dse_math"] == "deepseek/deepseek-chat"
    assert payload["selection"]["image_gen"] == RECOMMENDED_HK_IMAGE_MODEL
    assert payload["prices_recorded_on"] == "2026-11-03"
    _assert_gemini_absent(payload)

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


def test_gemini_text_is_omitted_from_public_rag_options(client):
    payload = client.get("/api/models").json()
    rag = next(item for item in payload["functions"] if item["id"] == "rag_qa")
    ids = {option["id"] for option in rag["options"]}
    assert "google/gemini-2.5-flash" not in ids
    assert "deepseek/deepseek-chat" in ids
    assert all("region_note" not in option for option in rag["options"])


def test_put_rejects_hidden_hong_kong_model(client, tmp_path):
    leftover = dict(DEFAULT_SELECTION)
    leftover["rag_qa"] = "google/gemini-2.5-flash"
    leftover["translation"] = "openai/gpt-4o"
    rejected = client.put("/api/models", json=leftover)
    assert rejected.status_code == 400
    assert "not available in Hong Kong" in rejected.json()["detail"]
    assert not (tmp_path / "model-selection.json").exists()
    assert client.get("/api/models").json()["selection"] == DEFAULT_SELECTION


def test_gemini_is_not_in_public_options(client):
    payload = client.get("/api/models").json()
    _assert_gemini_absent(payload)
    rag = next(item for item in payload["functions"] if item["id"] == "rag_qa")
    assert [option["id"] for option in rag["options"]] == [
        str(model["id"]) for model in models_for("rag_qa")
    ]
    assert "google/gemini-2.5-flash" in hidden_catalog_ids()
    assert DEFAULT_SELECTION["rag_qa"] == "deepseek/deepseek-chat"
    assert DEFAULT_SELECTION["image_gen"] == "black-forest-labs/flux.2-pro"


def test_defaults_are_hong_kong_safe(client):
    for model_id in DEFAULT_SELECTION.values():
        assert "gemini" not in model_id
    payload = client.get("/api/models").json()
    assert payload["selection"] == DEFAULT_SELECTION
    _assert_gemini_absent(payload)


def test_saved_hidden_model_is_coerced(client, tmp_path):
    leftover = {
        "rag_qa": "google/gemini-2.5-flash",
        "translation": "openai/gpt-4o",
        "cantonese_script": "google/gemini-2.5-flash",
        "dse_math": "google/gemini-2.5-flash",
        "image_gen": "google/gemini-3.1-flash-image",
        "video_gen": "minimax/hailuo-2.3",
    }
    (tmp_path / "model-selection.json").write_text(
        json.dumps({"selection": leftover}, indent=2) + "\n",
        encoding="utf-8",
    )
    payload = client.get("/api/models").json()
    assert payload["selection"]["rag_qa"] == "deepseek/deepseek-chat"
    assert payload["selection"]["translation"] == "openai/gpt-4o"
    assert payload["selection"]["cantonese_script"] == "deepseek/deepseek-chat"
    assert payload["selection"]["dse_math"] == "deepseek/deepseek-chat"
    assert payload["selection"]["image_gen"] == "black-forest-labs/flux.2-pro"
    _assert_gemini_absent(payload)


def test_probe_hides_region_403_without_printing_key(tmp_path, monkeypatch):
    secret = "test-openrouter-key-not-a-secret"
    env_file = tmp_path / "openrouter.env"
    env_file.write_text(f"OPENROUTER_API_KEY={secret}\n", encoding="utf-8")
    monkeypatch.setenv("OPENROUTER_ENV_FILE", str(env_file))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    reset_probe_cache()

    def fake_hidden(*, force: bool = False):
        return frozenset({"openai/gpt-4o", "google/gemini-2.5-flash"})

    monkeypatch.setattr("app.region.extra_hidden_ids", fake_hidden)
    monkeypatch.setattr("app.main.extra_hidden_ids", fake_hidden)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("PORTAL_API_TOKEN", raising=False)
    client = TestClient(app)

    payload = client.get("/api/models").json()
    option_ids = _public_option_ids(payload)
    assert "openai/gpt-4o" not in option_ids
    assert "google/gemini-2.5-flash" not in option_ids
    assert "deepseek/deepseek-chat" in option_ids
    assert secret not in client.get("/api/models").text
    assert secret[:18] not in json.dumps(payload)
    _assert_gemini_absent(payload)
