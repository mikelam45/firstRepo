from fastapi.testclient import TestClient

from app.chat_format import escape_html, markdown_table_to_html, parse_chart_fence
from app.catalog import DEFAULT_SELECTION
from app.main import CHAT_FORMAT_JS, PAGE, app
from app.rag import FORMAT_REPLY_INSTRUCTION, MIXED_SYSTEM, STRICT_SYSTEM


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


def _mock_chat(monkeypatch, reply="mock"):
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


def test_escape_html_escapes_markup():
    assert escape_html('<script>alert("x")</script>') == (
        "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;"
    )
    assert escape_html("a&b") == "a&amp;b"
    assert escape_html("it's") == "it&#39;s"


def test_parse_chart_fence_accepts_bar_default_and_rejects_invalid():
    spec = parse_chart_fence(
        '{"labels":["A","B"],"series":[{"name":"Sales","values":[1,2]}]}'
    )
    assert spec == {
        "type": "bar",
        "title": "",
        "labels": ["A", "B"],
        "series": [{"name": "Sales", "values": [1.0, 2.0]}],
    }

    pie = parse_chart_fence(
        '{"type":"pie","title":"Share","labels":["A","B"],'
        '"series":[{"name":"One","values":[3,1]},{"name":"Two","values":[9,1]}]}'
    )
    assert pie["type"] == "pie"
    assert pie["title"] == "Share"
    assert len(pie["series"]) == 1
    assert pie["series"][0]["name"] == "One"

    line = parse_chart_fence(
        '{"type":"line","labels":["A","B"],"series":[{"values":["4","5"]}]}'
    )
    assert line["type"] == "line"
    assert line["series"][0]["name"] == "Series"
    assert line["series"][0]["values"] == [4.0, 5.0]

    assert parse_chart_fence("not json") is None
    assert parse_chart_fence('{"type":"radar","labels":["A"],"series":[{"values":[1]}]}') is None
    assert parse_chart_fence('{"labels":["A"],"series":[{"values":[1,2]}]}') is None
    assert parse_chart_fence("") is None


def test_markdown_table_to_html_builds_escaped_table():
    html = markdown_table_to_html(
        "| Name | Qty |\n| --- | --- |\n| <b>x</b> | 2 |\n| B | 3 |"
    )
    assert html is not None
    assert html.startswith("<table>")
    assert "<th>Name</th>" in html
    assert "<th>Qty</th>" in html
    assert "<td>&lt;b&gt;x&lt;/b&gt;</td>" in html
    assert "<td>2</td>" in html
    assert "<script>" not in html
    assert markdown_table_to_html("not a table") is None


def test_format_instruction_avoids_only_and_documents_the_chart_fence():
    assert "ONLY" not in FORMAT_REPLY_INSTRUCTION
    assert "```chart" in FORMAT_REPLY_INSTRUCTION
    assert '"type":"bar|line|pie"' in FORMAT_REPLY_INSTRUCTION
    assert "Markdown table" in FORMAT_REPLY_INSTRUCTION
    assert "[source: filename]" in FORMAT_REPLY_INSTRUCTION
    assert FORMAT_REPLY_INSTRUCTION in MIXED_SYSTEM
    assert FORMAT_REPLY_INSTRUCTION in STRICT_SYSTEM
    assert "ONLY" not in MIXED_SYSTEM


def test_functions_page_includes_table_chart_renderer(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    home = client.get("/")
    script = client.get("/static/chat_format.js")
    setup = client.get("/setup")

    assert home.status_code == 200
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]
    assert 'src="/static/chat_format.js"' in home.text
    assert "parseChartFence" in home.text
    assert "parseChartFence" in script.text
    assert "markdownTableToHtml" in script.text
    assert "escapeHtml" in script.text
    assert "renderAssistantReply" in script.text
    assert "drawChartSvg" in script.text
    assert "createElementNS" in script.text
    assert ".innerHTML" not in script.text
    assert "body.innerHTML" not in home.text
    assert "renderAssistantReply(text)" in home.text
    assert "chat-reply-plain" in home.text
    assert 'data-options="rag_qa"' not in home.text
    assert "parseChartFence" not in setup.text
    assert PAGE.is_file()
    assert CHAT_FORMAT_JS.is_file()


def test_rag_and_translation_prompts_include_format_contract(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    table_reply = (
        "Totals from the sheet [source: notes.csv]\n\n"
        "| Item | Qty |\n| --- | --- |\n| Widget | 2 |\n\n"
        "```chart\n"
        '{"type":"bar","title":"Qty","labels":["Widget"],"series":[{"name":"Qty","values":[2]}]}'
        "\n```"
    )
    seen = _mock_chat(monkeypatch, reply=table_reply)
    client = _client(monkeypatch, tmp_path)
    uploaded = client.post(
        "/api/rag/files",
        files={"file": ("notes.csv", b"item,qty\nwidget,2\n", "text/csv")},
    )
    assert uploaded.status_code == 201

    rag = client.post("/api/chat", json={"message": "Compare the rows", "function": "rag_qa"})
    assert rag.status_code == 200
    assert rag.json()["reply"] == table_reply
    assert "<table>" not in rag.json()["reply"]
    system = seen["json"]["messages"][0]["content"]
    assert "```chart" in system
    assert "Markdown table" in system
    assert "[source: <filename>]" in system
    assert rag.json()["sources"][0]["name"] == "notes.csv"

    translation = client.post(
        "/api/chat",
        json={"message": "hello", "function": "translation", "target_language": "en"},
    )
    assert translation.status_code == 200
    assert translation.json()["reply"] == table_reply
    messages = seen["json"]["messages"]
    assert FORMAT_REPLY_INSTRUCTION in messages[0]["content"]
    assert "professional translator" in messages[0]["content"]
    assert "natural" in messages[0]["content"]
    assert messages[1] == {"role": "user", "content": "hello"}
    assert "sources" not in translation.json()
    assert seen["json"]["model"] == DEFAULT_SELECTION["translation"]
