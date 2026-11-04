import base64

from fastapi.testclient import TestClient

from app.chat import (
    MISSING_KEY_DETAIL,
    OPENROUTER_CHAT_URL,
    OPENROUTER_VISION_TIMEOUT_SECONDS,
)
from app.main import PAGE, app
from app.ocr import (
    DEFAULT_OCR_MODEL,
    MAX_OCR_BYTES,
    OCR_MODEL_CANDIDATES,
    OCR_SYSTEM,
    OVERSIZE_DETAIL,
    UNSUPPORTED_TYPE_DETAIL,
)

SECRET = "test-openrouter-key-not-a-secret"
MOCK_OCR_TEXT = "Solve x^2 - 5x + 6 = 0."
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _assert_secret_absent(text: str) -> None:
    assert SECRET not in text
    assert SECRET[:18] not in text


def _client(monkeypatch, tmp_path, *, env="development", token=None):
    monkeypatch.setenv("APP_ENV", env)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    if token:
        monkeypatch.setenv("PORTAL_API_TOKEN", token)
    else:
        monkeypatch.delenv("PORTAL_API_TOKEN", raising=False)
    return TestClient(app)


def _install_key(tmp_path, monkeypatch):
    env_file = tmp_path / "openrouter.env"
    env_file.write_text(f'OPENROUTER_API_KEY="{SECRET}"\n', encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_ENV_FILE", str(env_file))
    return env_file


def _mock_vision(monkeypatch, *, reply=MOCK_OCR_TEXT, status_code=200, body=None, replies=None):
    seen = {"calls": 0, "models": []}

    def fake_post(url, json=None, headers=None, timeout=None, follow_redirects=None):
        seen["calls"] += 1
        seen["url"] = url
        seen["json"] = json
        seen["headers"] = headers
        seen["timeout"] = timeout
        seen["follow_redirects"] = follow_redirects
        model_id = (json or {}).get("model")
        seen["models"].append(model_id)
        chosen_status = status_code
        payload = body
        if replies is not None:
            entry = replies[min(seen["calls"] - 1, len(replies) - 1)]
            chosen_status = entry.get("status_code", 200)
            payload = entry.get("body")
            reply_text = entry.get("reply", reply)
        else:
            reply_text = reply
        if payload is None:
            payload = {
                "choices": [{"message": {"role": "assistant", "content": reply_text}}]
            }

        class Response:
            def json(self_inner):
                return payload

            text = f"provider echoed {SECRET}"

        Response.status_code = chosen_status
        return Response()

    monkeypatch.setattr("app.chat.httpx.post", fake_post)
    return seen


def _upload(client, name, data, content_type="image/png", headers=None):
    return client.post(
        "/api/dse/ocr",
        files={"file": (name, data, content_type)},
        headers=headers or {},
    )


def test_ocr_candidates_are_non_gemini_qwen_first():
    assert DEFAULT_OCR_MODEL == "qwen/qwen2.5-vl-72b-instruct"
    assert OCR_MODEL_CANDIDATES[0] == DEFAULT_OCR_MODEL
    assert all(not model_id.startswith("google/gemini") for model_id in OCR_MODEL_CANDIDATES)


def test_functions_page_contains_dse_photo_ocr_control(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    home = client.get("/")
    assert home.status_code == 200
    assert "Read question from photo" in home.text
    assert 'id="dse-ocr-file"' in home.text
    assert 'id="dse-ocr-read"' in home.text
    assert 'id="dse-ocr-preview"' in home.text
    assert 'id="dse-ocr-state"' in home.text
    assert "/api/dse/ocr" in home.text
    assert "image/jpeg" in home.text
    assert "image/heic" in home.text
    assert PAGE.is_file()


def test_tiny_png_ocr_returns_text(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_vision(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    response = _upload(client, "question.png", TINY_PNG)
    assert response.status_code == 200
    payload = response.json()
    assert payload["text"] == MOCK_OCR_TEXT
    assert payload["model_id"] == DEFAULT_OCR_MODEL
    assert "confidence" not in payload
    assert set(payload) == {"text", "model_id"}
    assert seen["calls"] == 1
    assert seen["url"] == OPENROUTER_CHAT_URL
    assert "/api/v1/images" not in seen["url"]
    assert seen["json"]["model"] == DEFAULT_OCR_MODEL
    assert seen["timeout"] == OPENROUTER_VISION_TIMEOUT_SECONDS
    assert seen["follow_redirects"] is False
    assert seen["headers"]["Authorization"] == f"Bearer {SECRET}"
    messages = seen["json"]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == OCR_SYSTEM
    user_content = messages[1]["content"]
    assert user_content[0]["type"] == "text"
    image_part = user_content[1]
    assert image_part["type"] == "image_url"
    url = image_part["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    encoded = url.split(",", 1)[1]
    assert base64.b64decode(encoded) == TINY_PNG
    stored = list((tmp_path / "data" / "dse-ocr").glob("*.png"))
    assert len(stored) == 1
    assert stored[0].read_bytes() == TINY_PNG
    assert client.get("/api/dse/files").json() == []
    assert client.get("/api/rag/files").json() == []
    _assert_secret_absent(response.text)


def test_exe_upload_is_400(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_vision(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    response = _upload(
        client, "malware.exe", b"MZ" + b"\x00" * 20, "application/octet-stream"
    )
    assert response.status_code == 400
    assert response.json()["detail"] == UNSUPPORTED_TYPE_DETAIL
    assert seen["calls"] == 0
    assert not (tmp_path / "data" / "dse-ocr").exists() or not list(
        (tmp_path / "data" / "dse-ocr").iterdir()
    )
    _assert_secret_absent(response.text)


def test_oversize_upload_is_400(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_vision(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    huge = TINY_PNG + b"\x00" * (MAX_OCR_BYTES - len(TINY_PNG) + 1)
    response = _upload(client, "huge.png", huge)
    assert response.status_code == 400
    assert response.json()["detail"] == OVERSIZE_DETAIL
    assert seen["calls"] == 0
    _assert_secret_absent(response.text)


def test_missing_key_returns_503(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_ENV_FILE", str(tmp_path / "no-such.env"))
    seen = _mock_vision(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    response = _upload(client, "question.png", TINY_PNG)
    assert response.status_code == 503
    assert response.json()["detail"] == MISSING_KEY_DETAIL
    assert seen["calls"] == 0
    _assert_secret_absent(response.text)
    _assert_secret_absent(MISSING_KEY_DETAIL)


def test_production_ocr_requires_token(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_vision(monkeypatch)
    client = _client(monkeypatch, tmp_path, env="production", token="test-token")

    rejected = _upload(client, "question.png", TINY_PNG)
    assert rejected.status_code == 401
    assert seen["calls"] == 0

    accepted = _upload(
        client,
        "question.png",
        TINY_PNG,
        headers={"Authorization": "Bearer test-token"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["text"] == MOCK_OCR_TEXT
    assert accepted.json()["model_id"] == DEFAULT_OCR_MODEL
    assert seen["calls"] == 1
    _assert_secret_absent(accepted.text)
    _assert_secret_absent(rejected.text)


def test_ocr_falls_back_when_qwen_is_region_blocked(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    fallback = OCR_MODEL_CANDIDATES[1]
    seen = _mock_vision(
        monkeypatch,
        replies=[
            {
                "status_code": 403,
                "body": {"error": {"message": "This model is not available in your region"}},
            },
            {"status_code": 200, "reply": "Fallback question text"},
        ],
    )
    client = _client(monkeypatch, tmp_path)
    response = _upload(client, "question.png", TINY_PNG)
    assert response.status_code == 200
    payload = response.json()
    assert payload["text"] == "Fallback question text"
    assert payload["model_id"] == fallback
    assert seen["models"] == [DEFAULT_OCR_MODEL, fallback]
    assert seen["url"] == OPENROUTER_CHAT_URL
    _assert_secret_absent(response.text)
