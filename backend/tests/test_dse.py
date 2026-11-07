from fastapi.testclient import TestClient

from app.catalog import DEFAULT_SELECTION
from app.dse import (
    DEFAULT_DSE_PRACTICE_MESSAGE,
    NO_DSE_DOCUMENTS_STRICT_REPLY,
)
from app.main import PAGE, SETUP_PAGE, app
from app.rag import SOURCE_EXCERPT_CHARS

SYLLABUS_SNIPPET = "HKDSE_SYLLABUS_QUADRATIC_EXTRACT"


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
    env_file.write_text(
        "OPENROUTER_API_KEY=test-openrouter-key-not-a-secret\n", encoding="utf-8"
    )
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_ENV_FILE", str(env_file))


def _mock_chat(monkeypatch, reply="mock dse reply", replies=None):
    seen = {"calls": 0, "jsons": []}

    def fake_post(url, json=None, headers=None, timeout=None, follow_redirects=None):
        seen["calls"] += 1
        seen["json"] = json
        seen["jsons"].append(json)
        text = reply
        if replies is not None:
            text = replies[min(seen["calls"] - 1, len(replies) - 1)]

        class Response:
            status_code = 200

            def json(self_inner):
                return {
                    "choices": [{"message": {"role": "assistant", "content": text}}]
                }

        return Response()

    monkeypatch.setattr("app.chat.httpx.post", fake_post)
    return seen


def test_functions_page_contains_dse_math(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    home = client.get("/")
    setup = client.get("/setup")
    assert home.status_code == 200
    assert "DSE Math" in home.text
    assert "DSE Math assistant" in home.text
    assert 'data-function="dse_math"' in home.text
    assert 'id="tab-dse_math"' in home.text
    assert 'id="dse-controls"' in home.text
    assert 'id="dse-option-solve"' in home.text
    assert 'id="dse-option-create"' in home.text
    assert 'id="dse-option-explain"' in home.text
    assert 'id="dse-solve-workspace"' in home.text
    assert 'id="dse-create-workspace"' in home.text
    assert 'id="dse-explain-workspace"' in home.text
    assert 'id="dse-log-solve"' in home.text
    assert 'id="dse-log-create"' in home.text
    assert 'id="dse-log-explain"' in home.text
    assert 'id="chat-clear"' in home.text
    assert "Clear responses" in home.text
    assert "clearActiveDseResponses" in home.text
    assert "dseBuckets" in home.text
    assert 'id="dse-mode-guided_no_answer"' in home.text
    assert 'id="dse-mode-guided_with_answer"' in home.text
    assert "Hints by steps" in home.text
    assert "Immediate answer" in home.text
    assert 'id="dse-question-count"' in home.text
    assert 'max="20"' in home.text
    assert "syncChatChrome" in home.text
    assert 'id="dse-level"' in home.text
    assert 'value="S1"' in home.text
    assert 'value="S6"' in home.text
    assert 'value="S7"' not in home.text
    assert 'id="dse-create-question"' in home.text
    assert 'id="dse-next-hint"' in home.text
    assert 'id="dse-show-answer"' in home.text
    assert 'id="dse-check"' in home.text
    assert 'id="dse-language"' in home.text
    assert "/api/dse/files" in home.text
    assert "/api/dse/ocr" in home.text
    assert "Read question from photo" in home.text
    assert 'id="dse-ocr-file"' in home.text
    assert 'id="dse-ocr-read"' in home.text
    assert "/api/dse/ask" in home.text or 'function: state.functionId' in home.text
    assert "Number &amp; Algebra" in home.text or "Number & Algebra" in home.text
    assert "Paper 1" in home.text
    assert "Paper 2" in home.text
    assert PAGE.is_file()

    assert setup.status_code == 200
    assert "DSE Math assistant" in setup.text
    assert 'data-options="dse_math"' in setup.text
    assert SETUP_PAGE.is_file()


def test_dse_upload_is_isolated_from_rag(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    dse_uploaded = client.post(
        "/api/dse/files",
        files={"file": ("syllabus.txt", f"{SYLLABUS_SNIPPET}\n".encode(), "text/plain")},
    )
    assert dse_uploaded.status_code == 201
    payload = dse_uploaded.json()
    assert payload["name"] == "syllabus.txt"
    assert payload["collection"] == "dse_math"
    assert payload["extracted_chars"] > 0

    assert client.get("/api/rag/files").json() == []
    assert client.get("/api/translation/files").json() == []
    dse_list = client.get("/api/dse/files")
    assert {row["name"] for row in dse_list.json()} == {"syllabus.txt"}
    via_query = client.get("/api/rag/files?collection=dse_math")
    assert {row["name"] for row in via_query.json()} == {"syllabus.txt"}

    rag_txt = client.post(
        "/api/rag/files",
        files={"file": ("notes.txt", b"RAG_ONLY_NOTE\n", "text/plain")},
    )
    assert rag_txt.status_code == 201
    via_rag_query = client.post(
        "/api/rag/files?collection=dse_math",
        files={"file": ("formula.md", b"DSE_MD_NOTE\n", "text/markdown")},
    )
    assert via_rag_query.status_code == 201
    assert via_rag_query.json()["collection"] == "dse_math"
    assert {row["name"] for row in client.get("/api/rag/files").json()} == {"notes.txt"}
    assert {row["name"] for row in client.get("/api/dse/files").json()} == {
        "syllabus.txt",
        "formula.md",
    }
    assert client.get("/api/translation/files").json() == []

    file_id = dse_uploaded.json()["id"]
    deleted = client.delete(f"/api/dse/files/{file_id}")
    assert deleted.status_code == 200
    assert {row["name"] for row in client.get("/api/dse/files").json()} == {"formula.md"}


def test_dse_chat_includes_hkdse_prompt_and_sources(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    uploaded = client.post(
        "/api/dse/files",
        files={"file": ("syllabus.txt", f"{SYLLABUS_SNIPPET}\n".encode(), "text/plain")},
    )
    assert uploaded.status_code == 201
    file_id = uploaded.json()["id"]

    chat = client.post(
        "/api/chat",
        json={
            "message": "Solve x^2 - 5x + 6 = 0",
            "function": "dse_math",
            "grounding": "mixed",
            "target_language": "zh_hk",
            "mode": "practice",
            "topic": "number_algebra",
            "difficulty": "mid",
            "paper": "paper_1",
            "module": "compulsory",
        },
    )
    assert chat.status_code == 200
    assert seen["calls"] == 1
    system = seen["json"]["messages"][0]["content"]
    assert "HKDSE" in system
    assert "繁體" in system
    assert "not 简体" in system
    assert "Final answer" in system
    assert "step-by-step" in system
    assert SYLLABUS_SNIPPET in system
    assert "syllabus.txt" in system
    assert "Number & Algebra" in system
    assert "Paper 1" in system
    assert seen["json"]["model"] == DEFAULT_SELECTION["dse_math"]
    assert "google/gemini" not in seen["json"]["model"]

    payload = chat.json()
    assert payload["function"] == "dse_math"
    assert payload["mode"] == "practice"
    assert payload["grounding"] == "mixed"
    assert payload["model_id"] == "deepseek/deepseek-chat"
    sources = payload["sources"]
    assert len(sources) == 1
    assert sources[0]["id"] == file_id
    assert sources[0]["name"] == "syllabus.txt"
    assert sources[0]["href"] == f"/api/rag/files/{file_id}/content"
    assert SYLLABUS_SNIPPET in sources[0]["excerpt"]
    assert len(sources[0]["excerpt"]) <= SOURCE_EXCERPT_CHARS

    downloaded = client.get(sources[0]["href"])
    assert downloaded.status_code == 200
    assert SYLLABUS_SNIPPET.encode() in downloaded.content


def test_dse_ask_wraps_the_same_chat_helper(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch, reply="dedicated ask")
    client = _client(monkeypatch, tmp_path)
    uploaded = client.post(
        "/api/dse/files",
        files={"file": ("notes.txt", b"EXPLAIN_EXTRACT\n", "text/plain")},
    )
    assert uploaded.status_code == 201
    response = client.post(
        "/api/dse/ask",
        json={
            "message": "Explain the remainder theorem",
            "mode": "explain",
            "target_language": "en",
            "grounding": "strict",
        },
    )
    assert response.status_code == 200
    assert seen["calls"] == 1
    system = seen["json"]["messages"][0]["content"]
    assert "HKDSE" in system
    assert "Explain" in system
    assert "EXPLAIN_EXTRACT" in system
    payload = response.json()
    assert payload["function"] == "dse_math"
    assert payload["mode"] == "explain"
    assert payload["reply"] == "dedicated ask"
    assert payload["sources"][0]["name"] == "notes.txt"


def test_dse_strict_without_files_skips_openrouter(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/chat",
        json={
            "message": "Solve 2x + 1 = 0",
            "function": "dse_math",
            "grounding": "strict",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"] == NO_DSE_DOCUMENTS_STRICT_REPLY
    assert payload["grounding"] == "strict"
    assert payload["sources"] == []
    assert payload["function"] == "dse_math"
    assert seen["calls"] == 0

    via_ask = client.post(
        "/api/dse/ask",
        json={"message": "Generate a question", "grounding": "strict"},
    )
    assert via_ask.status_code == 200
    assert via_ask.json()["reply"] == NO_DSE_DOCUMENTS_STRICT_REPLY
    assert seen["calls"] == 0


def test_dse_practice_empty_message_generates_default(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/chat",
        json={"function": "dse_math", "mode": "practice", "grounding": "mixed"},
    )
    assert response.status_code == 200
    assert seen["calls"] == 1
    assert seen["json"]["messages"][-1]["content"] == DEFAULT_DSE_PRACTICE_MESSAGE
    assert "HKDSE" in seen["json"]["messages"][0]["content"]


def test_dse_does_not_mix_rag_extracts(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    rag = client.post(
        "/api/rag/files",
        files={"file": ("notes.txt", b"RAG_MUST_NOT_APPEAR\n", "text/plain")},
    )
    assert rag.status_code == 201
    translation = client.post(
        "/api/translation/files",
        files={"file": ("brief.txt", b"TRANSLATION_MUST_NOT_APPEAR\n", "text/plain")},
    )
    assert translation.status_code == 201
    dse = client.post(
        "/api/dse/files",
        files={"file": ("syllabus.txt", b"DSE_ONLY_EXTRACT\n", "text/plain")},
    )
    assert dse.status_code == 201

    chat = client.post(
        "/api/chat",
        json={"message": "What is on the syllabus?", "function": "dse_math"},
    )
    assert chat.status_code == 200
    outbound = str(seen["json"]["messages"])
    assert "DSE_ONLY_EXTRACT" in outbound
    assert "RAG_MUST_NOT_APPEAR" not in outbound
    assert "TRANSLATION_MUST_NOT_APPEAR" not in outbound
    assert {row["name"] for row in chat.json()["sources"]} == {"syllabus.txt"}


CREATED_QUESTION = (
    '{"question":"Solve 2x + 1 = 5.","expected_answer":"x = 2",'
    '"mark_scheme":"M1 isolate x; A1 x = 2","outline":"subtract 1, divide by 2"}'
)
MARK_FAIL_REPLY = (
    '{"verdict":"wrong","reason":"The constant term was not moved correctly."}'
)


def test_guided_no_answer_system_prompt_forbids_final_answer(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch, reply="What have you tried with the quadratic?")
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/dse/ask",
        json={
            "message": "Solve x^2 - 5x + 6 = 0",
            "dse_mode": "guided_no_answer",
            "grounding": "mixed",
        },
    )
    assert response.status_code == 200
    system = seen["json"]["messages"][0]["content"]
    assert "Never state the boxed final answer" in system
    assert "Do not write 'Final answer:'." in system
    assert "Socratic" in system
    assert "Ask what the student has already tried" in system
    payload = response.json()
    assert payload["mode"] == "guided_no_answer"
    assert payload["session_id"]
    assert "expected_answer" not in payload


def test_guided_with_answer_includes_final_answer_instruction(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch, reply="Final answer: x = 2 or x = 3")
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/chat",
        json={
            "message": "Solve x^2 - 5x + 6 = 0",
            "function": "dse_math",
            "mode": "guided_with_answer",
            "grounding": "mixed",
        },
    )
    assert response.status_code == 200
    system = seen["json"]["messages"][0]["content"]
    assert "include the final answer immediately" in system
    assert "Final answer:" in system
    assert response.json()["mode"] == "guided_with_answer"
    assert response.json()["session_id"]


def test_create_question_returns_session_id_and_mark_fail_hides_official_answer(
    tmp_path, monkeypatch
):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch, replies=[CREATED_QUESTION, MARK_FAIL_REPLY])
    client = _client(monkeypatch, tmp_path)

    created = client.post(
        "/api/dse/question",
        json={
            "level": "S3",
            "topic": "algebra",
            "target_language": "zh_hk",
            "grounding": "mixed",
        },
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["session_id"]
    assert payload["question_id"]
    assert payload["question"] == "Solve 2x + 1 = 5."
    assert payload["reply"] == "Solve 2x + 1 = 5."
    assert payload["mode"] == "create_and_mark"
    assert payload["level"] == "S3"
    assert "expected_answer" not in payload
    assert "official_answer" not in payload
    assert "mark_scheme" not in payload
    assert "x = 2" not in payload.get("question", "")
    session_id = payload["session_id"]
    create_system = seen["jsons"][0]["messages"][0]["content"]
    assert "Generate exactly ONE original mathematics question" in create_system
    assert "繁體" in create_system

    marked = client.post(
        "/api/dse/mark",
        json={"session_id": session_id, "attempt_text": "x = 9"},
    )
    assert marked.status_code == 200
    fail = marked.json()
    assert fail["correct"] is False
    assert fail["next_options"] == ["hints", "retry"]
    assert "official_answer" not in fail
    assert "expected_answer" not in fail
    assert "answer" not in fail
    assert "mark_scheme" not in fail
    assert fail["session_id"] == session_id
    assert fail["verdict"] == "wrong"
    mark_system = seen["jsons"][1]["messages"][0]["content"]
    assert "Do not restate the official answer" in mark_system


def test_s7_or_bad_mode_returns_400(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    s7 = client.post(
        "/api/dse/question",
        json={"level": "S7", "topic": "algebra"},
    )
    assert s7.status_code == 400
    assert "S1" in s7.json()["detail"]

    bad_mode = client.post(
        "/api/chat",
        json={
            "message": "Solve 1 + 1",
            "function": "dse_math",
            "mode": "telepathy",
        },
    )
    assert bad_mode.status_code == 400
    assert "mode must be one of" in bad_mode.json()["detail"]

    via_dse_mode = client.post(
        "/api/dse/ask",
        json={"message": "Solve 1 + 1", "dse_mode": "not_a_mode"},
    )
    assert via_dse_mode.status_code == 400

    calculus_s1 = client.post(
        "/api/dse/question",
        json={"level": "S1", "topic": "calculus"},
    )
    assert calculus_s1.status_code == 400


def test_create_question_batch_up_to_twenty(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    batch = (
        '{"questions":['
        '{"question":"Q1: solve x=1.","expected_answer":"1","mark_scheme":"A1","outline":"one"},'
        '{"question":"Q2: solve x=2.","expected_answer":"2","mark_scheme":"A1","outline":"two"}'
        "]}"
    )
    seen = _mock_chat(monkeypatch, reply=batch)
    client = _client(monkeypatch, tmp_path)
    created = client.post(
        "/api/dse/question",
        json={
            "level": "S4",
            "topic": "algebra",
            "difficulty": "mid",
            "count": 2,
            "grounding": "mixed",
        },
    )
    assert created.status_code == 200, created.text
    payload = created.json()
    assert payload["question_count"] == 2
    assert len(payload["questions"]) == 2
    assert payload["questions"][0]["question"] == "Q1: solve x=1."
    assert payload["questions"][1]["question"] == "Q2: solve x=2."
    assert payload["question"] == "Q1: solve x=1."
    assert "expected_answer" not in payload
    assert "expected_answer" not in payload["questions"][0]
    system = seen["json"]["messages"][0]["content"]
    assert "exactly 2 original mathematics questions" in system
    assert "Difficulty: mid" in system

    too_many = client.post(
        "/api/dse/question",
        json={"level": "S4", "count": 21},
    )
    assert too_many.status_code == 400
    assert "1 to 20" in too_many.json()["detail"]

    zero = client.post("/api/dse/question", json={"level": "S4", "count": 0})
    assert zero.status_code == 400


def test_page_has_three_mode_controls_and_s1_s6(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    home = client.get("/")
    assert home.status_code == 200
    assert 'id="dse-option-solve"' in home.text
    assert 'id="dse-option-create"' in home.text
    assert 'id="dse-option-explain"' in home.text
    assert 'id="dse-solve-workspace"' in home.text
    assert 'id="dse-create-workspace"' in home.text
    assert 'id="dse-explain-workspace"' in home.text
    assert 'id="dse-log-solve"' in home.text
    assert 'id="dse-log-create"' in home.text
    assert 'id="dse-log-explain"' in home.text
    assert 'id="chat-clear"' in home.text
    assert "Clear responses" in home.text
    assert 'id="dse-mode-guided_no_answer"' in home.text
    assert 'id="dse-mode-guided_with_answer"' in home.text
    assert "Hints by steps" in home.text
    assert "Immediate answer" in home.text
    assert 'id="dse-question-count"' in home.text
    assert 'max="20"' in home.text
    for level in ("S1", "S2", "S3", "S4", "S5", "S6"):
        assert f'value="{level}"' in home.text
    assert 'value="S7"' not in home.text
    assert "/api/dse/question" in home.text
    assert "/api/dse/mark" in home.text
