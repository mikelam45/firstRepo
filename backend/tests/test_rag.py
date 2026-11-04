from pathlib import Path

from fastapi.testclient import TestClient

from app.main import PAGE, app
from app.rag import MAX_UPLOAD_BYTES, SOURCE_EXCERPT_CHARS

CSV_SNIPPET = "ALPHA_SNIPPET_42"
TXT_SNIPPET = "TXT_GROUNDING_NOTE"
JSON_SNIPPET = "JSON_WIDGET_NAME"


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
    env_file.write_text("OPENROUTER_API_KEY=test-openrouter-key-not-a-secret\n", encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_ENV_FILE", str(env_file))


def _mock_chat(monkeypatch):
    seen = {"calls": 0}

    def fake_post(url, json=None, headers=None, timeout=None, follow_redirects=None):
        seen["calls"] += 1
        seen["json"] = json

        class Response:
            status_code = 200

            def json(self_inner):
                return {"choices": [{"message": {"role": "assistant", "content": "mock"}}]}

        return Response()

    monkeypatch.setattr("app.chat.httpx.post", fake_post)
    return seen


def test_upload_list_and_rag_chat_includes_extracts(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    data_dir = tmp_path / "data"

    csv_body = f"item,code\nwidget,{CSV_SNIPPET}\n".encode("utf-8")
    txt_body = f"Note: {TXT_SNIPPET}\n".encode("utf-8")
    json_body = f'{{"name": "{JSON_SNIPPET}"}}\n'.encode("utf-8")

    csv_resp = client.post("/api/rag/files", files={"file": ("notes.csv", csv_body, "text/csv")})
    txt_resp = client.post("/api/rag/files", files={"file": ("memo.txt", txt_body, "text/plain")})
    json_resp = client.post("/api/rag/files", files={"file": ("meta.json", json_body, "application/json")})
    assert csv_resp.status_code == 201
    assert txt_resp.status_code == 201
    assert json_resp.status_code == 201
    assert csv_resp.json()["name"] == "notes.csv"
    assert csv_resp.json()["type"] == "csv"
    assert csv_resp.json()["extracted_chars"] > 0
    assert "stored_path" in csv_resp.json()

    listed = client.get("/api/rag/files")
    assert listed.status_code == 200
    names = {row["name"] for row in listed.json()}
    assert names == {"notes.csv", "memo.txt", "meta.json"}
    for row in listed.json():
        assert "content" not in row
        assert row["size"] > 0
        extract = data_dir / "extracts" / f"{row['id']}.txt"
        assert extract.is_file()
        stored = data_dir / row["stored_path"]
        assert stored.is_file()

    chat = client.post("/api/chat", json={"message": "What is in the files?", "function": "rag_qa"})
    assert chat.status_code == 200
    assert seen["calls"] == 1
    outbound = str(seen["json"]["messages"])
    assert CSV_SNIPPET in outbound
    assert TXT_SNIPPET in outbound
    assert JSON_SNIPPET in outbound
    assert "notes.csv" in outbound
    assert "Do not invent file contents" in outbound
    assert "[source: <filename>]" in outbound
    assert "general knowledge" in outbound
    assert chat.json()["grounding"] == "mixed"

    sources = chat.json()["sources"]
    assert {row["name"] for row in sources} == {"notes.csv", "memo.txt", "meta.json"}
    by_name = {row["name"]: row for row in sources}
    assert by_name["memo.txt"]["id"] == txt_resp.json()["id"]
    assert by_name["memo.txt"]["href"] == f"/api/rag/files/{txt_resp.json()['id']}/content"
    assert txt_resp.json()["id"] in by_name["memo.txt"]["href"]
    assert TXT_SNIPPET in by_name["memo.txt"]["excerpt"]
    assert len(by_name["memo.txt"]["excerpt"]) <= SOURCE_EXCERPT_CHARS

    downloaded = client.get(by_name["memo.txt"]["href"])
    assert downloaded.status_code == 200
    assert downloaded.content == txt_body
    disposition = downloaded.headers["content-disposition"]
    assert "attachment" in disposition
    assert "memo.txt" in disposition

    file_id = csv_resp.json()["id"]
    deleted = client.delete(f"/api/rag/files/{file_id}")
    assert deleted.status_code == 200
    remaining = {row["name"] for row in client.get("/api/rag/files").json()}
    assert remaining == {"memo.txt", "meta.json"}
    assert not (data_dir / "extracts" / f"{file_id}.txt").exists()


def test_reject_exe_and_oversized_upload(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    rejected = client.post(
        "/api/rag/files",
        files={"file": ("malware.exe", b"MZ", "application/octet-stream")},
    )
    assert rejected.status_code == 400
    assert "Unsupported file type" in rejected.json()["detail"]
    assert client.get("/api/rag/files").json() == []

    oversized = client.post(
        "/api/rag/files",
        files={"file": ("huge.txt", b"x" * (MAX_UPLOAD_BYTES + 1), "text/plain")},
    )
    assert oversized.status_code == 400
    assert "10 MB" in oversized.json()["detail"]
    assert client.get("/api/rag/files").json() == []
    data_dir = tmp_path / "data"
    uploads = data_dir / "uploads"
    if uploads.is_dir():
        assert list(uploads.iterdir()) == []


def test_production_upload_requires_token(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path, env="production", token="test-token")
    body = b"hello\n"
    rejected = client.post("/api/rag/files", files={"file": ("note.txt", body, "text/plain")})
    assert rejected.status_code == 401
    assert client.get("/api/rag/files").json() == []

    accepted = client.post(
        "/api/rag/files",
        files={"file": ("note.txt", body, "text/plain")},
        headers={"Authorization": "Bearer test-token"},
    )
    assert accepted.status_code == 201
    file_id = accepted.json()["id"]
    assert client.get("/api/rag/files").json()[0]["name"] == "note.txt"

    delete_rejected = client.delete(f"/api/rag/files/{file_id}")
    assert delete_rejected.status_code == 401
    deleted = client.delete(
        f"/api/rag/files/{file_id}",
        headers={"Authorization": "Bearer test-token"},
    )
    assert deleted.status_code == 200


def test_doc_is_accepted_with_conversion_note(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/rag/files",
        files={"file": ("legacy.doc", b"not a real word file", "application/msword")},
    )
    assert response.status_code == 201
    assert response.json()["type"] == "doc"
    assert "needs conversion" in response.json()["extract_error"]


def test_corrupt_pdf_stores_extract_error(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/rag/files",
        files={"file": ("broken.pdf", b"%PDF-not-valid", "application/pdf")},
    )
    assert response.status_code == 201
    assert response.json()["type"] == "pdf"
    assert response.json().get("extract_error")
    extract = Path(tmp_path / "data" / "extracts" / f"{response.json()['id']}.txt")
    assert extract.is_file()


def test_rag_chat_sources_include_uploaded_txt(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    _mock_chat(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    body = b"Alpha grounding sentence about widgets.\n"
    uploaded = client.post("/api/rag/files", files={"file": ("notes.txt", body, "text/plain")})
    assert uploaded.status_code == 201
    file_id = uploaded.json()["id"]

    chat = client.post("/api/chat", json={"message": "What is in notes.txt?", "function": "rag_qa"})
    assert chat.status_code == 200
    sources = chat.json()["sources"]
    assert len(sources) == 1
    source = sources[0]
    assert source["id"] == file_id
    assert source["name"] == "notes.txt"
    assert file_id in source["href"]
    assert source["href"] == f"/api/rag/files/{file_id}/content"
    assert source["excerpt"].startswith("Alpha grounding sentence")

    downloaded = client.get(source["href"])
    assert downloaded.status_code == 200
    assert downloaded.content == body
    assert "notes.txt" in downloaded.headers["content-disposition"]


def test_rag_chat_without_files_has_empty_sources(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    _mock_chat(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    chat = client.post("/api/chat", json={"message": "Any documents?", "function": "rag_qa"})
    assert chat.status_code == 200
    payload = chat.json()
    assert payload.get("sources", []) == []


def test_translation_does_not_invent_sources(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    _mock_chat(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    uploaded = client.post(
        "/api/rag/files",
        files={"file": ("notes.txt", b"should not become a translation citation\n", "text/plain")},
    )
    assert uploaded.status_code == 201
    chat = client.post("/api/chat", json={"message": "hello", "function": "translation"})
    assert chat.status_code == 200
    assert "sources" not in chat.json()


def test_missing_file_content_is_404(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    missing = client.get("/api/rag/files/does-not-exist/content")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "File not found."


def test_production_content_download_requires_token(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path, env="production", token="test-token")
    body = b"secret memo\n"
    uploaded = client.post(
        "/api/rag/files",
        files={"file": ("note.txt", body, "text/plain")},
        headers={"Authorization": "Bearer test-token"},
    )
    assert uploaded.status_code == 201
    href = f"/api/rag/files/{uploaded.json()['id']}/content"

    rejected = client.get(href)
    assert rejected.status_code == 401

    accepted = client.get(href, headers={"Authorization": "Bearer test-token"})
    assert accepted.status_code == 200
    assert accepted.content == body
    assert "note.txt" in accepted.headers["content-disposition"]


def test_functions_page_renders_source_links(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    home = client.get("/")
    assert home.status_code == 200
    assert 'id="chat-log"' in home.text
    assert "appendSources" in home.text
    assert "chat-sources" in home.text
    assert "source.href" in home.text
    assert "Sources" in home.text
    assert 'id="grounding-control"' in home.text
    assert 'id="grounding-strict"' in home.text
    assert 'id="grounding-mixed"' in home.text
    assert "rag-grounding" in home.text
    assert "chat-grounding" in home.text
    assert PAGE.is_file()


def test_strict_grounding_with_file_uses_only_extract_language(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    uploaded = client.post(
        "/api/rag/files",
        files={"file": ("memo.txt", b"ONLY_FROM_THIS_EXTRACT\n", "text/plain")},
    )
    assert uploaded.status_code == 201
    file_id = uploaded.json()["id"]

    chat = client.post(
        "/api/chat",
        json={"message": "What is in memo.txt?", "function": "rag_qa", "grounding": "strict"},
    )
    assert chat.status_code == 200
    assert seen["calls"] == 1
    system = seen["json"]["messages"][0]["content"]
    assert "ONLY" in system
    assert "uploaded document extracts" in system
    assert "Do not use outside knowledge" in system
    assert "ONLY_FROM_THIS_EXTRACT" in system
    assert "[source: <filename>]" in system
    payload = chat.json()
    assert payload["grounding"] == "strict"
    assert payload["sources"][0]["id"] == file_id
    assert payload["sources"][0]["name"] == "memo.txt"
    downloaded = client.get(payload["sources"][0]["href"])
    assert downloaded.status_code == 200
    assert downloaded.content == b"ONLY_FROM_THIS_EXTRACT\n"


def test_mixed_grounding_with_file_allows_general_knowledge(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    uploaded = client.post(
        "/api/rag/files",
        files={"file": ("memo.txt", b"MIXED_EXTRACT_NOTE\n", "text/plain")},
    )
    assert uploaded.status_code == 201

    chat = client.post(
        "/api/chat",
        json={"message": "What is in memo.txt?", "function": "rag_qa", "grounding": "mixed"},
    )
    assert chat.status_code == 200
    assert seen["calls"] == 1
    system = seen["json"]["messages"][0]["content"]
    assert "general knowledge" in system
    assert "Prefer the uploaded extracts" in system
    assert "MIXED_EXTRACT_NOTE" in system
    assert "ONLY" not in system.split("Uploaded extracts:")[0]
    assert chat.json()["grounding"] == "mixed"
    assert chat.json()["sources"][0]["name"] == "memo.txt"
