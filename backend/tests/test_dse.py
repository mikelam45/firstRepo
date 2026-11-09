import json

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
    assert 'id="dse-explain-level"' in home.text
    assert 'id="dse-explain-topic"' in home.text
    assert 'id="dse-explain-picked-list"' in home.text
    assert "addExplainTopicFromSelect" in home.text
    assert "formatCreatedQuestionText" in home.text
    assert "teaching scenario" in home.text
    assert "labelled diagram you can click" in home.text
    assert "/api/dse/topics" in home.text
    assert "edb.gov.hk/en/curriculum-development/kla/ma/curr/index2.html" in home.text
    assert 'id="dse-mode-guided_no_answer"' in home.text
    assert 'id="dse-mode-guided_with_answer"' in home.text
    assert "Hints by steps" in home.text
    assert "Immediate answer" in home.text
    assert "ABC, 50°" in home.text
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
    assert "Any topic" in home.text
    assert "loadDseCurriculum" in home.text
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
    assert payload["reply"].startswith("dedicated ask")
    assert "```figure" in payload["reply"]
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
    assert "```figure" in system
    assert "You MUST include labelled" in system
    assert "100% of named givens" in system
    payload = response.json()
    assert payload["mode"] == "guided_no_answer"
    assert payload["session_id"]
    assert "expected_answer" not in payload
    assert "```figure" in payload["reply"]
    assert "What have you tried with the quadratic?" in payload["reply"]


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
    assert "```figure" in system
    assert "100% of named givens" in system
    payload = response.json()
    assert payload["mode"] == "guided_with_answer"
    assert payload["session_id"]
    assert "```figure" in payload["reply"]
    assert "x = 2 or x = 3" in payload["reply"]


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
    assert "Solve 2x + 1 = 5." in payload["reply"]
    assert "```figure" in payload["reply"]
    assert payload.get("figure")
    assert payload["mode"] == "create_and_mark"
    assert payload["level"] == "S3"
    assert "expected_answer" not in payload
    assert "official_answer" not in payload
    assert "mark_scheme" not in payload
    assert "x = 2" not in payload.get("question", "")
    session_id = payload["session_id"]
    create_system = seen["jsons"][0]["messages"][0]["content"]
    assert "Generate exactly ONE original mathematics question" in create_system
    assert "teaching scenario" in create_system
    assert "figure" in create_system
    assert "100% of named vertices" in create_system
    assert "繁體" in create_system
    assert payload.get("scenario") == ""
    assert payload.get("figure")
    assert payload["figure"]["type"] in {"geometry", "coordinate", "number_line", "chart", "bar"}
    assert "```figure" in payload["display"]

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


def test_create_question_returns_scenario_and_figure(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    created_reply = json.dumps(
        {
            "question": "Find the area of triangle ABC.",
            "scenario": "A sports-day banner is cut as triangle ABC.",
            "figure": {
                "type": "geometry",
                "title": "Triangle ABC",
                "caption": "Not to scale",
                "elements": [
                    {
                        "kind": "polygon",
                        "points": [[20, 80], [80, 80], [50, 20]],
                        "labels": ["A", "B", "C"],
                    },
                    {
                        "kind": "segment",
                        "from": [20, 80],
                        "to": [80, 80],
                        "label": "6 cm",
                    },
                ],
            },
            "expected_answer": "12 cm^2",
            "mark_scheme": "M1 area formula; A1 12",
            "outline": "base times height over 2",
        }
    )
    seen = _mock_chat(monkeypatch, reply=created_reply)
    client = _client(monkeypatch, tmp_path)
    created = client.post(
        "/api/dse/question",
        json={
            "level": "S2",
            "topic": "s2_comp_congruence_and_similarity_of_triangles",
            "grounding": "mixed",
        },
    )
    assert created.status_code == 200, created.text
    payload = created.json()
    assert payload["question"] == "Find the area of triangle ABC."
    assert payload["scenario"] == "A sports-day banner is cut as triangle ABC."
    assert payload["figure"]["type"] == "geometry"
    assert payload["figure"]["elements"][0]["labels"] == ["A", "B", "C"]
    assert "```figure" in payload["display"]
    assert "**Scenario.**" in payload["display"]
    assert "12 cm^2" not in payload["display"]
    assert "expected_answer" not in payload
    assert "12 cm^2" not in payload["reply"]
    assert payload["reply"] == payload["display"]
    system = seen["json"]["messages"][0]["content"]
    assert "scenario" in system
    assert "figure" in system
    assert "Congruence and Similarity of Triangles" in system
    assert payload["topic"] == "s2_comp_congruence_and_similarity_of_triangles"


def test_create_rejects_topic_from_another_module(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    mismatch = client.post(
        "/api/dse/question",
        json={
            "level": "S5",
            "module": "compulsory",
            "topic": "s5_m1_binomial_expansion_for_positive_integers",
        },
    )
    assert mismatch.status_code == 400
    assert "M1" in mismatch.json()["detail"] or "module" in mismatch.json()["detail"].lower()


def test_create_rejects_m1_for_junior_year(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    mismatch = client.post(
        "/api/dse/question",
        json={"level": "S2", "module": "m1"},
    )
    assert mismatch.status_code == 400
    detail = mismatch.json()["detail"]
    assert "S5" in detail and "S6" in detail


def test_create_rejects_topic_from_another_year(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    mismatch = client.post(
        "/api/dse/question",
        json={
            "level": "S2",
            "topic": "s1_comp_directed_numbers_and_the_number_line",
        },
    )
    assert mismatch.status_code == 400
    assert "S1" in mismatch.json()["detail"]


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
    assert 'id="dse-explain-level"' in home.text
    assert 'id="dse-explain-topic"' in home.text
    assert 'id="dse-explain-picked-list"' in home.text
    assert "addExplainTopicFromSelect" in home.text
    assert "catalogTopicsFor" in home.text
    assert "renderDseCreateTopics" in home.text
    assert "fillDseLevelSelect" in home.text
    assert "selectedDseModule" in home.text
    assert "pruneExplainPicked" in home.text
    assert "Any module" not in home.text
    assert "Choose a module, then a year" in home.text
    assert 'id="dse-create-cascade"' in home.text
    assert "/api/dse/topics" in home.text
    assert "edb.gov.hk/en/curriculum-development/kla/ma/curr/index2.html" in home.text
    assert 'id="dse-log-solve"' in home.text
    assert 'id="dse-log-create"' in home.text
    assert 'id="dse-log-explain"' in home.text
    assert 'id="chat-clear"' in home.text
    assert "Clear responses" in home.text
    assert 'id="dse-mode-guided_no_answer"' in home.text
    assert 'id="dse-mode-guided_with_answer"' in home.text
    assert "Hints by steps" in home.text
    assert "Immediate answer" in home.text
    assert "ABC, 50°" in home.text
    assert 'id="dse-question-count"' in home.text
    assert 'max="20"' in home.text
    for level in ("S1", "S2", "S3", "S4", "S5", "S6"):
        assert f'value="{level}"' in home.text
    assert 'value="S7"' not in home.text
    assert "/api/dse/question" in home.text
    assert "/api/dse/mark" in home.text


def test_dse_topics_catalog_is_year_specific_s1_to_s6(tmp_path, monkeypatch):
    from app.dse_topics import TOPICS_CSV_NAME, TOPICS_CSV_PATH

    assert TOPICS_CSV_PATH.is_file()
    client = _client(monkeypatch, tmp_path)
    response = client.get("/api/dse/topics")
    assert response.status_code == 200
    payload = response.json()
    assert payload["levels"] == ["S1", "S2", "S3", "S4", "S5", "S6"]
    assert payload["source"]["file"] == TOPICS_CSV_NAME
    assert payload["source"]["href"].endswith("/ma/curr/index2.html")
    counts = {level: len(payload["topics"][level]) for level in payload["levels"]}
    assert counts == {"S1": 10, "S2": 10, "S3": 10, "S4": 8, "S5": 21, "S6": 12}
    s1_ids = [row["id"] for row in payload["topics"]["S1"]]
    s2_ids = [row["id"] for row in payload["topics"]["S2"]]
    s3_ids = [row["id"] for row in payload["topics"]["S3"]]
    assert s1_ids != s2_ids
    assert s2_ids != s3_ids
    assert "s1_comp_directed_numbers_and_the_number_line" in s1_ids
    assert "s1_comp_directed_numbers_and_the_number_line" not in s2_ids
    assert "s2_comp_pythagoras_theorem_and_irrational_numbers" in s2_ids
    assert "s3_comp_properties_of_quadrilaterals_and_parallelograms" in s3_ids
    s4_labels = {row["id"]: row["label"] for row in payload["topics"]["S4"]}
    assert s4_labels["s4_comp_quadratic_equations_in_one_unknown"] == (
        "Quadratic Equations in One Unknown"
    )
    s5_modules = {row["module_key"] for row in payload["topics"]["S5"]}
    assert s5_modules == {"compulsory", "m1", "m2"}
    assert payload["levels_by_module"]["compulsory"] == ["S1", "S2", "S3", "S4", "S5", "S6"]
    assert payload["levels_by_module"]["m1"] == ["S5", "S6"]
    assert payload["levels_by_module"]["m2"] == ["S5", "S6"]
    assert {row["module_key"] for row in payload["topics"]["S2"]} == {"compulsory"}
    s5_m1 = [
        row["id"]
        for row in payload["topics"]["S5"]
        if row["module_key"] == "m1"
    ]
    s5_comp = [
        row["id"]
        for row in payload["topics"]["S5"]
        if row["module_key"] == "compulsory"
    ]
    assert s5_m1
    assert s5_comp
    assert not set(s5_m1) & set(s5_comp)


def test_dse_explain_uses_selected_year_topics(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch, reply="topic explanation")
    client = _client(monkeypatch, tmp_path)
    pythagoras = "s2_comp_pythagoras_theorem_and_irrational_numbers"
    congruence = "s2_comp_congruence_and_similarity_of_triangles"
    empty = client.post(
        "/api/chat",
        json={
            "function": "dse_math",
            "mode": "explain",
            "level": "S2",
            "topics": [pythagoras, congruence],
        },
    )
    assert empty.status_code == 200
    assert seen["calls"] == 1
    system = seen["json"]["messages"][0]["content"]
    user = seen["json"]["messages"][1]["content"]
    assert "School level: S2" in system
    assert "Pythagoras" in system
    assert "Congruence" in system
    assert "Hong Kong secondary mathematics topics to explain" in system
    assert "S2 Pythagoras" in user
    assert "real-life scenario" in user
    assert "labelled interactive diagram" in user
    assert "```figure" in system
    assert "You MUST include at least one labelled diagram" in system
    assert "100% of named givens" in system
    assert "teaching scenario" in system
    payload = empty.json()
    assert payload["topics"] == [pythagoras, congruence]
    assert payload["level"] == "S2"
    assert "```figure" in payload["reply"]
    assert payload["reply"].count("```figure") >= 2
    assert len(payload.get("figures") or []) == 2

    bad = client.post(
        "/api/dse/ask",
        json={"mode": "explain", "topics": ["not_a_unit"]},
    )
    assert bad.status_code == 400
    assert "S1–S6" in bad.json()["detail"] or "catalog" in bad.json()["detail"]

    junior_m1 = client.post(
        "/api/chat",
        json={
            "function": "dse_math",
            "mode": "explain",
            "level": "S2",
            "module": "m1",
            "topics": ["s5_m1_binomial_expansion_for_positive_integers"],
        },
    )
    assert junior_m1.status_code == 400
    assert "S5" in junior_m1.json()["detail"]


def test_solve_figure_follows_question_not_topic():
    from app.dse_figures import default_solve_figure, ensure_solve_figures, session_has_figure

    triangle = default_solve_figure(
        topic="algebra",
        question="Prove triangles ABC and DEF are congruent.",
    )
    assert triangle["type"] == "geometry"
    assert "Triangle" in triangle["title"]

    sector = default_solve_figure(
        question="Find the arc length of a sector of radius 7 cm."
    )
    assert sector["type"] == "geometry"
    assert {el.get("kind") for el in sector["elements"]} & {"sector", "arc"}

    injected = ensure_solve_figures("Look at the given sides.", question="triangle ABC")
    assert "Look at the given sides." in injected
    assert injected.count("```figure") == 1

    later = ensure_solve_figures("Now mark the equal angles.", already_has_figure=True)
    assert "```figure" not in later

    session = {"messages": [{"role": "assistant", "content": injected}]}
    assert session_has_figure(session) is True
    assert session_has_figure({"messages": [{"role": "user", "content": "hi"}]}) is False


FOUNTAIN_QUESTION = (
    "Scenario. A student is planning a community project and needs to calculate "
    "the area of a circular fountain.\n\nCircular Fountain\nCircle with diameter 10m.\n"
    "A circular fountain has a diameter of $10$ meters. Find the area of the fountain."
)


def test_fountain_circle_figure_is_complete_and_labelled():
    from app.dse_figures import (
        CIRCLE_FIGURE,
        ensure_created_figure,
        figure_from_question,
        given_labels_from_text,
    )

    labels = given_labels_from_text(FOUNTAIN_QUESTION)
    assert "10 m" in labels

    fig = figure_from_question(FOUNTAIN_QUESTION, stage="question")
    assert fig is not None
    circle = next(el for el in fig["elements"] if el.get("kind") == "circle")
    assert circle["cy"] - circle["r"] > 5
    assert circle["cy"] + circle["r"] < 95
    blob = json.dumps(fig, ensure_ascii=False)
    assert "10 m" in blob
    assert any(el.get("id") == "diameter" for el in fig["elements"])

    clipped = {
        "type": "geometry",
        "title": "Circular Fountain",
        "elements": [
            {"kind": "circle", "cx": 50, "cy": 50, "r": 50, "id": "circle"},
        ],
    }
    enforced = ensure_created_figure(clipped, question=FOUNTAIN_QUESTION)
    assert "10 m" in json.dumps(enforced, ensure_ascii=False)
    drawn = next(el for el in enforced["elements"] if el.get("kind") == "circle")
    assert drawn["r"] < 50

    template = CIRCLE_FIGURE
    assert template["elements"][0]["kind"] == "circle"
    assert template["elements"][0]["cy"] - template["elements"][0]["r"] > 0
    assert template["elements"][0]["cy"] + template["elements"][0]["r"] < 100


INCIRCLE_TANGENT_QUESTION = (
    "In a triangle $ABC$, the angle at vertex $A$ measures $50^\\circ$, "
    "and the angle at vertex $B$ measures $70^\\circ$. A circle is inscribed "
    "in the triangle, touching all three sides. Calculate the measure of the "
    "angle formed by the two tangents drawn from point $C$ to the circle."
)


def test_incircle_question_figure_marks_abc_and_given_angles():
    from app.dse_figures import (
        ensure_created_figure,
        ensure_solve_figures,
        figure_from_question,
        given_labels_from_text,
    )

    labels = given_labels_from_text(INCIRCLE_TANGENT_QUESTION)
    assert "A" in labels and "B" in labels and "C" in labels
    assert "50°" in labels and "70°" in labels

    question_fig = figure_from_question(INCIRCLE_TANGENT_QUESTION, stage="question")
    assert question_fig is not None
    blob = json.dumps(question_fig, ensure_ascii=False)
    assert "50°" in blob and "70°" in blob
    assert '"A"' in blob and '"B"' in blob and '"C"' in blob
    assert "60°" not in blob
    assert any(el.get("kind") == "circle" for el in question_fig["elements"])

    answer_fig = figure_from_question(INCIRCLE_TANGENT_QUESTION, stage="answer")
    assert answer_fig is not None
    answer_blob = json.dumps(answer_fig, ensure_ascii=False)
    assert "50°" in answer_blob and "70°" in answer_blob and "60°" in answer_blob
    assert "I" in answer_blob

    incomplete = {
        "type": "geometry",
        "elements": [
            {
                "kind": "polygon",
                "points": [[20, 80], [80, 80], [50, 20]],
                "labels": ["A", "B", "C"],
            }
        ],
    }
    enforced = ensure_created_figure(
        incomplete, topic="algebra", question=INCIRCLE_TANGENT_QUESTION
    )
    assert "50°" in json.dumps(enforced, ensure_ascii=False)

    hinted = ensure_solve_figures("What is given at A and B?", question=INCIRCLE_TANGENT_QUESTION)
    assert hinted.count("```figure") == 1
    assert "50°" in hinted and "70°" in hinted
    assert "60°" not in hinted

    solved = ensure_solve_figures(
        "The tangents from C are CA and CB.",
        question=INCIRCLE_TANGENT_QUESTION,
        reveal_answer=True,
    )
    assert solved.count("```figure") >= 2
    assert "50°" in solved and "60°" in solved

    step = ensure_solve_figures(
        "Draw the radii to the touch points.",
        question=INCIRCLE_TANGENT_QUESTION,
        already_has_figure=True,
    )
    assert "```figure" in step
    assert "I" in step or "incentre" in step.lower() or "Incentre" in step


def test_guided_later_hint_still_has_labelled_figure(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(
        monkeypatch,
        replies=["What equal sides are given?", "Now look at the included angle."],
    )
    client = _client(monkeypatch, tmp_path)
    first = client.post(
        "/api/dse/ask",
        json={
            "message": "In triangle ABC, AB = AC. Prove it is isosceles.",
            "mode": "guided_no_answer",
            "grounding": "mixed",
        },
    )
    assert first.status_code == 200
    first_reply = first.json()["reply"]
    assert first_reply.count("```figure") == 1
    assert "Triangle ABC" in first_reply
    session_id = first.json()["session_id"]

    second = client.post(
        "/api/dse/ask",
        json={
            "message": "next hint",
            "mode": "guided_no_answer",
            "session_id": session_id,
            "grounding": "mixed",
        },
    )
    assert second.status_code == 200
    second_reply = second.json()["reply"]
    assert "```figure" in second_reply
    assert "included angle" in second_reply
    assert seen["calls"] == 2


def test_solve_incircle_tangents_injects_labelled_abc_figure(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_chat(monkeypatch, reply="Look at the given angles at A and B.")
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/dse/ask",
        json={
            "message": INCIRCLE_TANGENT_QUESTION,
            "mode": "guided_no_answer",
            "grounding": "mixed",
        },
    )
    assert response.status_code == 200
    system = seen["json"]["messages"][0]["content"]
    assert "100% of named givens" in system
    reply = response.json()["reply"]
    assert "50°" in reply
    assert "70°" in reply
    assert "Look at the given angles at A and B." in reply
    assert reply.count("```figure") >= 1

    answered = client.post(
        "/api/dse/ask",
        json={
            "message": INCIRCLE_TANGENT_QUESTION,
            "mode": "guided_with_answer",
            "grounding": "mixed",
        },
    )
    assert answered.status_code == 200
    body = answered.json()["reply"]
    assert "50°" in body and "70°" in body
    assert body.count("```figure") >= 2


QUAD_ANGLE_QUESTION = (
    "A quadrilateral ABCD has angles A, B, C, and D measuring 80°, 90°, 100°, and x° "
    "respectively. Find the value of x."
)


def test_quadrilateral_abcd_is_drawn_as_four_sides_not_a_triangle():
    from app.dse_figures import (
        ensure_created_figure,
        ensure_solve_figures,
        explain_figure_for_topic,
        figure_from_question,
        given_labels_from_text,
    )

    labels = given_labels_from_text(QUAD_ANGLE_QUESTION)
    assert "A" in labels and "B" in labels and "C" in labels and "D" in labels
    assert "80°" in labels and "90°" in labels and "100°" in labels
    assert "x" not in labels and "x°" not in labels

    fig = figure_from_question(QUAD_ANGLE_QUESTION, stage="question")
    assert fig is not None
    assert "Quadrilateral" in fig["title"]
    assert "Triangle" not in fig["title"]
    polygons = [el for el in fig["elements"] if el.get("kind") == "polygon"]
    assert len(polygons) == 1
    assert len(polygons[0]["points"]) == 4
    assert polygons[0]["labels"] == ["A", "B", "C", "D"]
    assert not any(el.get("kind") == "circle" for el in fig["elements"])
    blob = json.dumps(fig, ensure_ascii=False)
    assert "80°" in blob and "90°" in blob and "100°" in blob
    angle_d = next(el for el in fig["elements"] if el.get("id") == "angle-d")
    assert not angle_d.get("label")

    answer = figure_from_question(QUAD_ANGLE_QUESTION, stage="answer")
    assert answer is not None
    answer_d = next(el for el in answer["elements"] if el.get("id") == "angle-d")
    assert answer_d.get("label") == "90°"
    assert "360" in (answer.get("caption") or "")

    triangle = {
        "type": "geometry",
        "title": "Triangle ABC",
        "elements": [
            {
                "kind": "polygon",
                "points": [[20, 80], [80, 80], [50, 20]],
                "labels": ["A", "B", "C"],
            }
        ],
    }
    enforced = ensure_created_figure(triangle, question=QUAD_ANGLE_QUESTION)
    drawn = next(el for el in enforced["elements"] if el.get("kind") == "polygon")
    assert len(drawn["points"]) == 4
    assert drawn["labels"] == ["A", "B", "C", "D"]
    assert "Triangle" not in enforced["title"]

    hinted = ensure_solve_figures("Name the given angles.", question=QUAD_ANGLE_QUESTION)
    assert "```figure" in hinted
    assert "Quadrilateral ABCD" in hinted
    assert '"id": "quad"' in hinted or '"id":"quad"' in hinted
    assert hinted.count('"kind": "polygon"') + hinted.count('"kind":"polygon"') >= 1

    topic_fig = explain_figure_for_topic(
        "s3_comp_properties_of_quadrilaterals_and_parallelograms"
    )
    topic_poly = next(el for el in topic_fig["elements"] if el.get("kind") == "polygon")
    assert len(topic_poly["points"]) == 4
    assert topic_poly["labels"] == ["A", "B", "C", "D"]
