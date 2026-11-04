from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.rag import MAX_UPLOAD_BYTES

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
