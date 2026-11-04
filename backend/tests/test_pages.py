from fastapi.testclient import TestClient

from app.main import PAGE, SETUP_PAGE, app


def test_home_and_setup_are_distinct_html_pages(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("PORTAL_API_TOKEN", raising=False)
    client = TestClient(app)

    home = client.get("/")
    setup = client.get("/setup")
    settings = client.get("/settings")
    css = client.get("/static/portal.css")

    assert home.status_code == 200
    assert setup.status_code == 200
    assert settings.status_code == 200
    assert css.status_code == 200
    assert "text/html" in home.headers["content-type"]
    assert "text/html" in setup.headers["content-type"]
    assert "text/css" in css.headers["content-type"]

    assert "OpenRouter connection" in setup.text
    assert 'id="openrouter-save"' in setup.text
    assert 'data-options="rag_qa"' in setup.text
    assert "Save selection" in setup.text
    assert 'id="rag-upload"' not in setup.text
    assert 'id="chat-send"' not in setup.text

    assert 'id="rag-upload"' in home.text
    assert 'id="chat-send"' in home.text
    assert "Document upload" in home.text
    assert "Chat" in home.text
    assert "OpenRouter connection" not in home.text
    assert 'data-options="rag_qa"' not in home.text

    assert "OpenRouter connection" in settings.text
    assert PAGE.is_file()
    assert SETUP_PAGE.is_file()
