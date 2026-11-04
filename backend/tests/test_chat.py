import httpx
from fastapi.testclient import TestClient

from app.catalog import DEFAULT_SELECTION, get_model
from app.chat import (
    GENERIC_COMPLETION_ERROR,
    MISSING_KEY_DETAIL,
    OPENROUTER_CHAT_TIMEOUT_SECONDS,
    OPENROUTER_CHAT_URL,
    REGION_SETUP_HINT,
)
from app.main import app
from app.openrouter_key import MAC_KEY_PATH
from app.rag import NO_DOCUMENTS_STRICT_REPLY

SECRET = "test-openrouter-key-not-a-secret"
MOCK_REPLY = "mock grounded answer"


def _assert_secret_absent(text: str) -> None:
    assert SECRET not in text
    assert SECRET[:18] not in text


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("PORTAL_API_TOKEN", raising=False)
    return TestClient(app)


def _install_key(tmp_path, monkeypatch):
    env_file = tmp_path / "openrouter.env"
    env_file.write_text(f'OPENROUTER_API_KEY="{SECRET}"\n', encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_ENV_FILE", str(env_file))
    return env_file


def _mock_chat(monkeypatch, *, reply=MOCK_REPLY, status_code=200, raise_error=None, body=None):
    seen = {"calls": 0}

    def fake_post(url, json=None, headers=None, timeout=None, follow_redirects=None):
        seen["calls"] += 1
        seen["url"] = url
        seen["json"] = json
        seen["headers"] = headers
        seen["timeout"] = timeout
        seen["follow_redirects"] = follow_redirects
        if raise_error is not None:
            raise raise_error
        payload = body if body is not None else {
            "choices": [{"message": {"role": "assistant", "content": reply}}]
        }

        class Response:
            def json(self_inner):
                return payload

            text = f"provider echoed {SECRET}"

        Response.status_code = status_code
        return Response()

    monkeypatch.setattr("app.chat.httpx.post", fake_post)
    return seen


def test_missing_key_returns_503_without_calling_openrouter(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_ENV_FILE", str(tmp_path / "no-such.env"))

    def fake_post(*args, **kwargs):
        raise AssertionError("OpenRouter should not be called")

    monkeypatch.setattr("app.chat.httpx.post", fake_post)
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/chat", json={"message": "hello", "function": "rag_qa"})
    assert response.status_code == 503
    assert response.json()["detail"] == MISSING_KEY_DETAIL
    assert str(MAC_KEY_PATH) in response.json()["detail"]
    assert "page still loads" in response.json()["detail"]
    _assert_secret_absent(response.text)
    page = client.get("/")
    assert page.status_code == 200
    assert "Chat" in page.text
    setup = client.get("/setup")
    assert setup.status_code == 200
    assert "loads without an API key" in setup.text


def test_image_and_video_are_not_chat_completions(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    for function_id in ("image_gen", "video_gen"):
        response = client.post(
            "/api/chat",
            json={"message": "draw this", "function": function_id},
        )
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "not a chat completion" in detail
        assert function_id in detail
        _assert_secret_absent(response.text)
    assert seen["calls"] == 0


def test_unknown_function_is_400(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/chat", json={"message": "hello", "function": "speech_to_text"})
    assert response.status_code == 400
    assert "Unknown function" in response.json()["detail"]
    assert seen["calls"] == 0
    _assert_secret_absent(response.text)


def test_rag_qa_uses_saved_model_and_returns_mock_text(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    updated = dict(DEFAULT_SELECTION)
    updated["rag_qa"] = "anthropic/claude-sonnet-5.5"
    assert client.put("/api/models", json=updated).status_code == 200

    response = client.post("/api/chat", json={"message": "What is in the notes?"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"] == MOCK_REPLY
    assert payload["function"] == "rag_qa"
    assert payload["model_id"] == "anthropic/claude-sonnet-5.5"
    assert payload["name"] == "Claude Sonnet 5.5"
    assert payload["prices_recorded_on"] == "2026-11-03"
    catalog_prices = list(get_model("anthropic/claude-sonnet-5.5")["prices"])
    assert payload["prices"] == catalog_prices
    assert all(price["unit"].startswith("USD per ") for price in payload["prices"])
    _assert_secret_absent(response.text)

    assert seen["calls"] == 1
    assert seen["url"] == OPENROUTER_CHAT_URL
    assert seen["timeout"] == OPENROUTER_CHAT_TIMEOUT_SECONDS
    assert seen["follow_redirects"] is False
    assert seen["headers"]["Authorization"] == f"Bearer {SECRET}"
    assert seen["json"]["model"] == "anthropic/claude-sonnet-5.5"
    assert seen["json"]["stream"] is False
    messages = seen["json"]["messages"]
    assert messages[0]["role"] == "system"
    assert "no uploaded documents" in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "What is in the notes?"}
    assert payload["grounding"] == "mixed"
    assert payload["sources"] == []


def test_translation_uses_that_function_model(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch, reply="translated")
    client = _client(monkeypatch, tmp_path)
    updated = dict(DEFAULT_SELECTION)
    updated["translation"] = "openai/gpt-4o"
    client.put("/api/models", json=updated)
    response = client.post(
        "/api/chat",
        json={"message": "hello", "function": "translation", "target_language": "en"},
    )
    assert response.status_code == 200
    assert response.json()["reply"] == "translated"
    assert response.json()["model_id"] == "openai/gpt-4o"
    assert seen["json"]["model"] == "openai/gpt-4o"


def test_openrouter_error_body_is_not_returned(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    _mock_chat(monkeypatch, status_code=401)
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 502
    assert "401" in response.json()["detail"]
    assert "provider echoed" not in response.text
    _assert_secret_absent(response.text)


def test_openrouter_error_message_is_surfaced(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    provider_message = (
        "The request is prohibited due to a violation of provider Terms Of Service."
    )
    _mock_chat(
        monkeypatch,
        status_code=403,
        body={
            "error": {"message": provider_message, "code": 403, "metadata": {"raw": SECRET}},
            "user_id": "user-should-stay-private",
        },
    )
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "403" in detail
    assert provider_message in detail
    assert "Open Setup" not in detail
    assert "user-should-stay-private" not in response.text
    assert "metadata" not in response.text
    assert "provider echoed" not in response.text
    _assert_secret_absent(response.text)


def test_openrouter_region_403_includes_setup_hint(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    provider_message = "This model is not available in your region."
    _mock_chat(
        monkeypatch,
        status_code=403,
        body={"error": {"message": provider_message, "code": 403}},
    )
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "OpenRouter returned HTTP 403: " + provider_message in detail
    assert REGION_SETUP_HINT in detail
    assert detail.index(provider_message) < detail.index("Open Setup")
    _assert_secret_absent(response.text)


def test_openrouter_http_200_error_object_is_surfaced(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    _mock_chat(
        monkeypatch,
        status_code=200,
        body={"error": {"message": "Provider returned error", "code": 502}},
    )
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 502
    assert "Provider returned error" in response.json()["detail"]
    assert "200" in response.json()["detail"]
    _assert_secret_absent(response.text)


def test_null_content_uses_reasoning_fallback(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    _mock_chat(
        monkeypatch,
        body={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "reasoning": "Grounded fallback from reasoning",
                    },
                    "finish_reason": "stop",
                }
            ]
        },
    )
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/chat", json={"message": "What is in the notes?"})
    assert response.status_code == 200
    assert response.json()["reply"] == "Grounded fallback from reasoning"
    _assert_secret_absent(response.text)


def test_content_parts_are_concatenated(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    _mock_chat(
        monkeypatch,
        body={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "Part A "},
                            {"type": "text", "text": "Part B"},
                        ],
                    }
                }
            ]
        },
    )
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 200
    assert response.json()["reply"] == "Part A Part B"
    _assert_secret_absent(response.text)


def test_empty_content_without_fallback_names_model(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    _mock_chat(
        monkeypatch,
        body={"choices": [{"message": {"role": "assistant", "content": None}}]},
    )
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 502
    assert response.json()["detail"] == f"empty reply from {DEFAULT_SELECTION['rag_qa']}"
    _assert_secret_absent(response.text)


def test_provider_error_redacts_api_key(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    _mock_chat(
        monkeypatch,
        status_code=401,
        body={"error": {"message": f"Invalid token {SECRET}"}},
    )
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "401" in detail
    assert "Invalid token" in detail
    _assert_secret_absent(response.text)


def test_openrouter_transport_error_hides_details(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    _mock_chat(monkeypatch, raise_error=httpx.ConnectError(f"boom {SECRET}"))
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 502
    assert response.json()["detail"] == GENERIC_COMPLETION_ERROR
    _assert_secret_absent(response.text)


def test_production_chat_requires_token(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PORTAL_API_TOKEN", "test-token")
    client = TestClient(app)

    rejected = client.post("/api/chat", json={"message": "hello"})
    assert rejected.status_code == 401
    assert seen["calls"] == 0

    models_rejected = client.put("/api/models", json=dict(DEFAULT_SELECTION))
    assert models_rejected.status_code == 401
    notes_rejected = client.post("/api/notes", json={"body": "should fail"})
    assert notes_rejected.status_code == 401

    accepted = client.post(
        "/api/chat",
        json={"message": "hello", "function": "rag_qa"},
        headers={"Authorization": "Bearer test-token"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["reply"] == MOCK_REPLY
    assert seen["calls"] == 1
    _assert_secret_absent(accepted.text)


def test_strict_grounding_without_files_skips_openrouter(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/chat",
        json={"message": "What is in the notes?", "function": "rag_qa", "grounding": "strict"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"] == NO_DOCUMENTS_STRICT_REPLY
    assert payload["grounding"] == "strict"
    assert payload["sources"] == []
    assert payload["function"] == "rag_qa"
    assert seen["calls"] == 0
    _assert_secret_absent(response.text)


def test_invalid_grounding_is_400(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/chat",
        json={"message": "hello", "function": "rag_qa", "grounding": "loose"},
    )
    assert response.status_code == 400
    assert "grounding" in response.json()["detail"]
    assert seen["calls"] == 0
    _assert_secret_absent(response.text)
