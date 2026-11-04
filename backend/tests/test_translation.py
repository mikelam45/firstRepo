import io

from fastapi.testclient import TestClient

from app.main import PAGE, app
from app.rag import (
    DEFAULT_TRANSLATION_MESSAGE,
    PPT_CONVERSION_NOTE,
    extract_text,
)


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("PORTAL_API_TOKEN", raising=False)
    return TestClient(app)


def _install_key(tmp_path, monkeypatch):
    env_file = tmp_path / "openrouter.env"
    env_file.write_text("OPENROUTER_API_KEY=test-openrouter-key-not-a-secret\n", encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_ENV_FILE", str(env_file))


def _mock_chat(monkeypatch, reply="translated"):
    seen = {"calls": 0}

    def fake_post(url, json=None, headers=None, timeout=None, follow_redirects=None):
        seen["calls"] += 1
        seen["json"] = json

        class Response:
            status_code = 200

            def json(self_inner):
                return {"choices": [{"message": {"role": "assistant", "content": reply}}]}

        return Response()

    monkeypatch.setattr("app.chat.httpx.post", fake_post)
    return seen


def _docx_bytes(text: str) -> bytes:
    from docx import Document

    document = Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _pptx_bytes(text: str) -> bytes:
    from pptx import Presentation

    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[0])
    slide.shapes.title.text = text
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def test_translation_upload_is_filtered_from_rag_list(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    pptx_body = _pptx_bytes("SLIDE_ONLY_FOR_TRANSLATION")
    uploaded = client.post(
        "/api/translation/files",
        files={
            "file": (
                "deck.pptx",
                pptx_body,
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        },
    )
    assert uploaded.status_code == 201
    payload = uploaded.json()
    assert payload["name"] == "deck.pptx"
    assert payload["collection"] == "translation"
    assert payload["extracted_chars"] > 0

    rag_list = client.get("/api/rag/files")
    assert rag_list.status_code == 200
    assert rag_list.json() == []

    query_list = client.get("/api/rag/files?collection=translation")
    assert {row["name"] for row in query_list.json()} == {"deck.pptx"}
    translation_list = client.get("/api/translation/files")
    assert {row["name"] for row in translation_list.json()} == {"deck.pptx"}

    rag_txt = client.post(
        "/api/rag/files",
        files={"file": ("notes.txt", b"RAG_ONLY_NOTE\n", "text/plain")},
    )
    assert rag_txt.status_code == 201
    via_query = client.post(
        "/api/rag/files?collection=translation",
        files={
            "file": (
                "brief.docx",
                _docx_bytes("QUERY_COLLECTION_DOC"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert via_query.status_code == 201
    assert via_query.json()["collection"] == "translation"
    assert {row["name"] for row in client.get("/api/rag/files").json()} == {"notes.txt"}
    assert {row["name"] for row in client.get("/api/translation/files").json()} == {
        "deck.pptx",
        "brief.docx",
    }


def test_translation_chat_includes_traditional_instruction_and_extract(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    snippet = "BOARD_MINUTES_EXTRACT_77"
    uploaded = client.post(
        "/api/translation/files",
        files={
            "file": (
                "minutes.docx",
                _docx_bytes(snippet),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert uploaded.status_code == 201
    file_id = uploaded.json()["id"]

    rag_chat = client.post(
        "/api/chat",
        json={"message": "What is in the notes?", "function": "rag_qa"},
    )
    assert rag_chat.status_code == 200
    rag_outbound = str(seen["json"]["messages"])
    assert snippet not in rag_outbound
    assert rag_chat.json()["sources"] == []

    chat = client.post(
        "/api/chat",
        json={
            "message": "Translate this deck",
            "function": "translation",
            "target_language": "zh_hk",
            "source_language": "en",
        },
    )
    assert chat.status_code == 200
    outbound = str(seen["json"]["messages"])
    system = seen["json"]["messages"][0]["content"]
    assert "professional translator" in system
    assert "Traditional" in system
    assert "繁體" in system
    assert "简体" in system
    assert snippet in system
    assert "minutes.docx" in system
    assert "Source documents:" in system
    assert outbound.count(snippet) >= 1

    sources = chat.json()["sources"]
    assert len(sources) == 1
    assert sources[0]["name"] == "minutes.docx"
    assert sources[0]["id"] == file_id
    assert sources[0]["href"] == f"/api/rag/files/{file_id}/content"
    assert snippet in sources[0]["excerpt"]
    downloaded = client.get(sources[0]["href"])
    assert downloaded.status_code == 200
    assert "minutes.docx" in downloaded.headers["content-disposition"]


def test_translation_missing_or_invalid_target_is_400(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch)
    client = _client(monkeypatch, tmp_path)

    missing = client.post("/api/chat", json={"message": "hello", "function": "translation"})
    assert missing.status_code == 400
    assert "target_language" in missing.json()["detail"]

    invalid = client.post(
        "/api/chat",
        json={"message": "hello", "function": "translation", "target_language": "zh_tw"},
    )
    assert invalid.status_code == 400
    assert "target_language" in invalid.json()["detail"]
    assert "zh_hk" in invalid.json()["detail"]

    bad_source = client.post(
        "/api/chat",
        json={
            "message": "hello",
            "function": "translation",
            "target_language": "en",
            "source_language": "fr",
        },
    )
    assert bad_source.status_code == 400
    assert "source_language" in bad_source.json()["detail"]
    assert seen["calls"] == 0


def test_translation_empty_message_defaults_when_docs_exist(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    uploaded = client.post(
        "/api/translation/files",
        files={"file": ("memo.txt", b"Please translate this memo.\n", "text/plain")},
    )
    assert uploaded.status_code == 201
    chat = client.post(
        "/api/chat",
        json={"function": "translation", "target_language": "zh_cn"},
    )
    assert chat.status_code == 200
    assert seen["json"]["messages"][-1]["content"] == DEFAULT_TRANSLATION_MESSAGE
    assert "Simplified Chinese" in seen["json"]["messages"][0]["content"]
    assert "简体" in seen["json"]["messages"][0]["content"]
    assert "Please translate this memo." in seen["json"]["messages"][0]["content"]

    empty = client.post(
        "/api/chat",
        json={"function": "translation", "target_language": "en", "message": ""},
    )
    assert empty.status_code == 200

    deleted = client.delete(f"/api/translation/files/{uploaded.json()['id']}")
    assert deleted.status_code == 200
    rejected = client.post(
        "/api/chat",
        json={"function": "translation", "target_language": "en"},
    )
    assert rejected.status_code == 400
    assert "message" in rejected.json()["detail"]


def test_pptx_extractor_reads_slide_text():
    body = _pptx_bytes("SLIDE_TEXT_UNIQUE_99")
    text, error = extract_text(".pptx", body)
    assert error is None
    assert "SLIDE_TEXT_UNIQUE_99" in text
    assert "Slide" in text


def test_ppt_is_accepted_with_conversion_note(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/translation/files",
        files={"file": ("legacy.ppt", b"not a real powerpoint file", "application/vnd.ms-powerpoint")},
    )
    assert response.status_code == 201
    assert response.json()["type"] == "ppt"
    assert response.json()["extract_error"] == PPT_CONVERSION_NOTE


def test_invalid_collection_is_400(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    listed = client.get("/api/rag/files?collection=other")
    assert listed.status_code == 400
    assert "collection" in listed.json()["detail"]


def test_functions_page_has_translation_language_and_upload(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    home = client.get("/")
    assert home.status_code == 200
    assert 'id="translation-languages"' in home.text
    assert 'id="source-language"' in home.text
    assert 'id="target-language"' in home.text
    assert 'id="rag-upload"' in home.text
    assert "translation-target-language" in home.text
    assert "Translate the uploaded documents." in home.text
    assert PAGE.is_file()
