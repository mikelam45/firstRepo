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
    assert 'data-options="dse_math"' in setup.text
    assert "Save selection" in setup.text
    assert "Hong Kong" in setup.text
    assert 'id="rag-upload"' not in setup.text
    assert 'id="chat-send"' not in setup.text

    assert 'id="rag-upload"' in home.text
    assert 'id="chat-send"' in home.text
    assert "Background" in home.text
    assert "Objects" in home.text
    assert "Attributes of background" in home.text
    assert "Attributes of objects" in home.text
    assert "Assembled prompt" in home.text
    assert "Nationality" in home.text
    assert "Height" in home.text
    assert "Hair" in home.text
    assert "Eyes" in home.text
    assert "Nose" in home.text
    assert "Mouth" in home.text
    assert "Dress" in home.text
    assert "Top" in home.text
    assert "Bottom" in home.text
    assert "Shoes" in home.text
    assert "expression" in home.text
    assert "Action on objects" in home.text
    assert "1 photo" in home.text
    assert "10 photos" in home.text
    assert "11 photos" not in home.text
    assert "slight smile" in home.text
    assert "walking" in home.text
    assert "Facial change" in home.text
    assert "Motion change" in home.text
    assert "Maintain 100% across photos" in home.text
    assert 'id="image-maintain-background"' in home.text
    assert 'id="image-maintain-dressing"' in home.text
    assert 'id="image-maintain-face"' in home.text
    assert 'id="image-variance-steps"' in home.text
    assert "Batch variance steps" in home.text
    assert "Apply intensity to all steps" in home.text
    assert "MAX_VARIANCE_STEPS = 10" in home.text
    assert "variance_steps" in home.text
    assert 'id="image-output-resolution"' in home.text
    assert "1K" in home.text
    assert "2K" in home.text
    assert "4K" in home.text
    assert "2048x2048" in home.text
    assert 'id="image-panel"' in home.text
    assert "People in this image" in home.text
    assert "1 person" in home.text
    assert "2 persons" in home.text
    assert 'id="image-person-2"' in home.text
    assert 'id="image-sex"' in home.text
    assert 'id="image-sex-2"' in home.text
    assert "Body figure" in home.text
    assert 'id="image-people-relation"' in home.text
    assert "Past projects" in home.text
    assert "Add new project" in home.text
    assert "Blank studio" in home.text
    assert 'id="image-project-select"' in home.text
    assert 'id="image-project-add"' in home.text
    assert 'id="image-project-save"' in home.text
    assert "/api/images/projects" in home.text
    assert 'id="ref-slots"' in home.text
    assert "Reference photos" in home.text
    assert "0/5" in home.text
    assert 'id="image-subject"' in home.text
    assert 'id="image-setting"' in home.text
    assert 'id="image-style"' in home.text
    assert "cinematic still" in home.text
    assert "product photo" in home.text
    assert "storyboard frame" in home.text
    assert "ink wash" in home.text
    assert "documentary" in home.text
    assert 'id="image-camera"' in home.text
    assert 'id="image-lighting"' in home.text
    assert 'id="image-preset"' in home.text
    assert "1024x1024" in home.text
    assert "1024x768" in home.text
    assert "768x1024" in home.text
    assert "1344x768" in home.text
    assert "1920x1080" in home.text
    assert 'id="image-format"' in home.text
    assert 'id="image-generate"' in home.text
    assert 'id="image-enhance"' in home.text
    assert "google/gemini-3.1-flash-image" not in home.text
    assert 'id="grounding-control"' in home.text
    assert 'id="translation-languages"' in home.text
    assert 'id="source-language"' in home.text
    assert 'id="target-language"' in home.text
    assert "Auto detect" in home.text
    assert "Simplified Chinese (简体)" in home.text
    assert "Traditional Chinese (繁體)" in home.text
    assert "/api/translation/files" in home.text
    assert "/api/dse/files" in home.text
    assert "/api/dse/ocr" in home.text
    assert "DSE Math assistant" in home.text
    assert 'data-function="dse_math"' in home.text
    assert 'id="dse-controls"' in home.text
    assert 'id="dse-option-solve"' in home.text
    assert 'id="dse-option-create"' in home.text
    assert 'id="dse-option-explain"' in home.text
    assert 'id="dse-solve-workspace"' in home.text
    assert 'id="dse-create-workspace"' in home.text
    assert 'id="dse-explain-workspace"' in home.text
    assert 'id="dse-explain-level"' in home.text
    assert 'id="dse-explain-topic-scroll"' in home.text
    assert "/api/dse/topics" in home.text
    assert "edb.gov.hk/en/curriculum-development/kla/ma/curr/index2.html" in home.text
    assert 'id="chat-lede"' in home.text
    assert "syncChatChrome" in home.text
    assert 'id="dse-log-solve"' in home.text
    assert 'id="dse-log-create"' in home.text
    assert 'id="dse-log-explain"' in home.text
    assert 'id="chat-clear"' in home.text
    assert "Clear responses" in home.text
    assert 'id="dse-mode-guided_no_answer"' in home.text
    assert 'id="dse-mode-guided_with_answer"' in home.text
    assert 'id="dse-question-count"' in home.text
    assert 'value="S1"' in home.text
    assert 'value="S6"' in home.text
    assert "Read question from photo" in home.text
    assert 'id="dse-ocr-file"' in home.text
    assert 'id="dse-ocr-read"' in home.text
    assert 'id="dse-ocr-preview"' in home.text
    assert "Document upload" in home.text
    assert "Chat" in home.text
    assert "OpenRouter connection" not in home.text
    assert 'data-options="rag_qa"' not in home.text
    assert 'id="grounding-control"' not in setup.text

    assert "OpenRouter connection" in settings.text
    assert PAGE.is_file()
    assert SETUP_PAGE.is_file()
