import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.coach import normalize_turn, resolve_provider
from app.fixtures import DAILY_DENY
from app.main import app
from app.models import ROUTES
from app.scenarios import get_scenario

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def _settings(**overrides):
    base = {
        "target": "yue",
        "support": "en",
        "level": "beginner",
        "script": "Hant",
        "accent": "en-GB",
        "pinyin_tone": "mark",
        "partner": "amelia",
    }
    base.update(overrides)
    return base


def _turn(history, scenario="hk-cha-chaan-teng", settings=None, fired=None, client_id="test"):
    response = client.post(
        "/api/turn",
        headers={"X-Client-Id": client_id},
        json={
            "session_id": "11111111-1111-1111-1111-111111111111",
            "scenario_id": scenario,
            "partner_id": (settings or _settings()).get("partner", "amelia"),
            "settings": settings or _settings(),
            "history": history,
            "fired_signals": fired or [],
        },
    )
    return response


def test_health_does_not_call_the_model(monkeypatch):
    def boom():
        raise AssertionError("model called")

    monkeypatch.setattr("app.coach.resolve_provider", boom)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_routes_are_the_pinned_openrouter_ids():
    assert ROUTES["roleplay"]["model"] == "deepseek/deepseek-v4-flash"
    assert ROUTES["roleplay"]["fallback"] == "google/gemini-2.5-flash-lite"
    assert ROUTES["yue"]["model"] == "qwen/qwen3.7-flash"
    assert ROUTES["yue"]["fallback"] == "qwen/qwen3.8-flash"
    assert ROUTES["review"]["model"] == "anthropic/claude-haiku-5.5"
    assert ROUTES["review"]["fallback"] == "deepseek/deepseek-v4-flash"


def test_empty_key_uses_fixture():
    assert resolve_provider().name == "fixture"


def test_opening_has_no_coaching():
    response = _turn([])
    body = response.json()
    assert response.status_code == 200
    assert body["coaching"] is None
    assert body["goal"]["status"] == "open"
    assert body["goal"]["fired"] == []
    assert body["character"]["text"]
    assert body["character"]["phonetic"]
    assert body["meta"]["provider"] == "fixture"
    assert body["session"]["turns_remaining"] == 8


def test_cantonese_register_fixture():
    response = _turn([{"role": "learner", "text": "我要咖啡"}])
    body = response.json()
    assert response.status_code == 200
    suggestion = body["coaching"]["suggested_reply"]
    assert "唔該" in suggestion
    assert body["coaching"]["corrections"][0]["type"] == "register"
    assert any(token in body["character"]["text"] for token in ("熱", "凍", "？"))
    assert body["coaching"]["suggested_reply_phonetic"].startswith("m4 goi1")
    assert body["session"]["turns_remaining"] == 7
    _assert_clean(body)


def test_already_good_line():
    response = _turn([{"role": "learner", "text": "唔該，一杯熱啡，走甜。"}])
    coaching = response.json()["coaching"]
    assert coaching["corrections"] == []
    assert coaching["suggested_reply"] is None
    assert "唔該" in coaching["praise"] or "走甜" in coaching["praise"]
    _assert_clean(response.json())


def test_wrong_language_mismatch():
    response = _turn([{"role": "learner", "text": "Can I have a hot coffee?"}])
    body = response.json()
    assert body["coaching"]["corrections"][0]["type"] == "mismatch"
    assert any("\u4e00" <= ch <= "\u9fff" for ch in body["coaching"]["suggested_reply"])
    assert any("\u4e00" <= ch <= "\u9fff" for ch in body["character"]["text"])
    _assert_clean(body)


def test_london_completeness_beats_register():
    response = _turn(
        [{"role": "learner", "text": "I want the station."}],
        scenario="london-directions",
        settings=_settings(target="en", support="en"),
    )
    coaching = response.json()["coaching"]
    assert [item["type"] for item in coaching["corrections"]] == ["completeness"]
    assert "Could you tell me" in coaching["suggested_reply"]
    assert "Oxford" not in coaching["suggested_reply"]
    _assert_clean(response.json())


def test_putonghua_checkin_prompt():
    response = _turn(
        [{"role": "learner", "text": "我要入住"}],
        scenario="beijing-hotel-checkin",
        settings=_settings(target="cmn", support="en", script="Hans"),
    )
    body = response.json()
    suggestion = body["coaching"]["suggested_reply"]
    assert "您好" in suggestion or "麻烦" in suggestion
    assert "姓名" in body["character"]["text"] or "名字" in body["character"]["text"]
    _assert_clean(body)


def test_goal_met_when_all_signals_fire():
    response = _turn(
        [
            {"role": "learner", "text": "唔該，一杯熱啡，走甜。"},
            {"role": "character", "text": "好。"},
            {"role": "learner", "text": "唔該，埋單。"},
        ]
    )
    body = response.json()
    assert body["session"]["goal_status"] == "met"
    assert set(body["session"]["fired_signals"]) == {"ordered_drink", "confirmed_detail", "asked_for_bill"}


def test_eighth_beginner_turn_closes():
    history = [{"role": "learner", "text": "我要咖啡"} for _ in range(8)]
    body = _turn(history).json()
    assert body["session"]["turns_remaining"] == 0
    assert body["session"]["turns_remaining_including_this"] == 1
    assert body["session"]["cap_reached"] is True
    assert "到呢度" in body["character"]["text"] or "wrap up" in body["character"]["text"].lower()


def test_bad_quote_and_same_suggestion_are_dropped():
    scenario = get_scenario("hk-cha-chaan-teng")
    raw = {
        "contract": "1",
        "character": {"text": "熱定凍？", "translation": "Hot or iced?", "phonetic": "FAKE"},
        "coaching": {
            "praise": "Fine.",
            "corrections": [{"type": "register", "quote": "not-in-text", "why": "no"}],
            "suggested_reply": "我要咖啡",
            "reading_hints": [{"term": "ghost", "note": "no"}],
        },
        "goal": {"status": "met", "fired": ["not-a-signal", "ordered_drink"]},
        "safety": {"refused": False},
    }
    payload = {
        "scenario_id": "hk-cha-chaan-teng",
        "settings": _settings(),
        "history": [{"role": "learner", "text": "我要咖啡"}],
        "fired_signals": [],
    }
    result = normalize_turn(raw, payload, scenario)
    assert result["coaching"]["corrections"] == []
    assert result["coaching"]["suggested_reply"] is None
    assert result["coaching"]["reading_hints"] == []
    assert result["character"]["phonetic"] != "FAKE"
    assert "m4" in result["character"]["phonetic"] or result["character"]["phonetic"]
    assert result["goal"]["fired"] == ["ordered_drink"]
    assert result["goal"]["status"] == "open"


def test_repair_then_success(monkeypatch):
    good = {
        "contract": "1",
        "character": {"text": "熱定凍？", "translation": "Hot or iced?"},
        "coaching": {"praise": None, "corrections": [], "suggested_reply": None, "reading_hints": []},
        "goal": {"status": "open", "fired": []},
        "safety": {"refused": False},
    }
    provider = _Scripted(["nope", json.dumps(good)])
    monkeypatch.setattr("app.coach.resolve_provider", lambda: provider)
    response = _turn([{"role": "learner", "text": "我要咖啡"}], client_id="repair")
    assert response.status_code == 200
    assert provider.calls == 2
    assert response.json()["character"]["text"]


def test_repair_failure_is_502(monkeypatch):
    provider = _Scripted(["nope", "still nope"])
    monkeypatch.setattr("app.coach.resolve_provider", lambda: provider)
    response = _turn([{"role": "learner", "text": "我要咖啡"}], client_id="repair-fail")
    assert response.status_code == 502
    assert response.json()["error"] == "coach_unavailable"
    assert provider.calls == 2


def test_english_teacher_grammar_fixture():
    learner = "I want go to school yesterday"
    response = _turn(
        [{"role": "learner", "text": learner}],
        scenario="english-teacher",
        settings=_settings(target="yue", support="en", partner="chloe"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["provider"] == "fixture"
    assert body["meta"]["route"] == "roleplay"
    assert body["meta"]["model"] is None
    assert body["partner_id"] == "chloe"
    correction = body["coaching"]["corrections"][0]
    assert correction["type"] == "grammar"
    assert correction["quote"] in learner
    assert "wanted" in body["coaching"]["suggested_reply"]
    assert "to go" in body["coaching"]["suggested_reply"]
    assert body["character"]["text"]
    assert not any("\u4e00" <= ch <= "\u9fff" for ch in body["character"]["text"])
    assert body["goal"]["status"] == "open"
    _assert_reading_hints(body, learner)
    _assert_clean(body)


def test_english_teacher_wrong_word_fixture():
    learner = "I am very boring in the class"
    response = _turn(
        [{"role": "learner", "text": learner}],
        scenario="english-teacher",
        settings=_settings(target="en", support="cmn", partner="chloe", script="Hans"),
    )
    assert response.status_code == 200
    body = response.json()
    correction = body["coaching"]["corrections"][0]
    assert correction["type"] == "vocabulary"
    assert correction["quote"] == "boring"
    assert correction["quote"] in learner
    assert "bored" in body["coaching"]["suggested_reply"]
    assert "boring" not in body["coaching"]["suggested_reply"].lower()
    assert any("\u4e00" <= ch <= "\u9fff" for ch in correction["why"])
    assert not any("\u4e00" <= ch <= "\u9fff" for ch in body["character"]["text"])
    assert all(hint["term"].lower() != "boring" for hint in body["coaching"]["reading_hints"])
    assert any(hint["term"].lower() == "the" for hint in body["coaching"]["reading_hints"])
    _assert_reading_hints(body, learner)
    _assert_clean(body)


def test_english_teacher_support_cantonese_keeps_english_line():
    response = _turn(
        [{"role": "learner", "text": "I want go to school yesterday"}],
        scenario="english-teacher",
        settings=_settings(target="cmn", support="yue", partner="chloe"),
    )
    body = response.json()
    assert response.status_code == 200
    assert body["meta"]["route"] == "roleplay"
    assert "wanted" in body["coaching"]["suggested_reply"]
    assert not any("\u4e00" <= ch <= "\u9fff" for ch in body["character"]["text"])
    assert any("\u4e00" <= ch <= "\u9fff" for ch in (body["character"]["translation"] or ""))
    assert any("\u4e00" <= ch <= "\u9fff" for ch in body["coaching"]["corrections"][0]["why"])
    _assert_clean(body)


def test_english_teacher_denylist_rejects_pronunciation_praise(monkeypatch):
    for praise in ("you pronounced that clearly", "pronunciation was good"):
        bad = {
            "contract": "1",
            "character": {"text": "Let us look at that sentence.", "translation": None},
            "coaching": {
                "praise": praise,
                "corrections": [],
                "suggested_reply": None,
                "reading_hints": [],
            },
            "goal": {"status": "open", "fired": []},
            "safety": {"refused": False},
        }
        monkeypatch.setattr("app.coach.resolve_provider", lambda bad=bad: _Scripted([json.dumps(bad)]))
        response = _turn(
            [{"role": "learner", "text": "I want go to school yesterday"}],
            scenario="english-teacher",
            settings=_settings(target="en", support="en", partner="chloe"),
            client_id=f"deny-teacher-{praise.split()[0]}",
        )
        assert response.status_code == 502


def test_denylist_is_rejected(monkeypatch):
    bad = {
        "contract": "1",
        "character": {"text": "熱定凍？", "translation": "Hot or iced?"},
        "coaching": {
            "praise": "you pronounced that clearly",
            "corrections": [],
            "suggested_reply": None,
            "reading_hints": [],
        },
        "goal": {"status": "open", "fired": []},
        "safety": {"refused": False},
    }
    monkeypatch.setattr("app.coach.resolve_provider", lambda: _Scripted([json.dumps(bad)]))
    response = _turn([{"role": "learner", "text": "我要咖啡"}], client_id="deny")
    assert response.status_code == 502


def test_missing_character_reading_still_200(monkeypatch):
    raw = {
        "contract": "1",
        "character": {"text": "𠮷", "translation": "missing"},
        "coaching": {"praise": None, "corrections": [], "suggested_reply": None, "reading_hints": []},
        "goal": {"status": "open", "fired": []},
        "safety": {"refused": False},
    }
    monkeypatch.setattr("app.coach.resolve_provider", lambda: _Scripted([json.dumps(raw)]))
    response = _turn([{"role": "learner", "text": "我要咖啡"}], client_id="missing")
    assert response.status_code == 200
    assert response.json()["character"]["phonetic_complete"] is False
    assert "·" in response.json()["character"]["phonetic"]


def test_invalid_request_and_rate_limit():
    response = client.post("/api/turn", json={"session_id": "x"})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"
    for index in range(30):
        ok = _turn([{"role": "learner", "text": "我要咖啡"}], client_id="burst")
        assert ok.status_code == 200, index
    limited = _turn([{"role": "learner", "text": "我要咖啡"}], client_id="burst")
    assert limited.status_code == 429
    assert limited.json()["error"] == "slow_down"
    assert limited.headers.get("retry-after")


def test_static_bundle_has_no_provider_key():
    blob = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in (ROOT / "app" / "static").rglob("*") if path.is_file() and path.suffix in {".html", ".js", ".css", ".svg"})
    assert "OPENROUTER_API_KEY=" not in blob
    assert "sk-or-" not in blob


def _assert_clean(body: dict):
    blob = json.dumps(body, ensure_ascii=False).lower()
    for phrase in DAILY_DENY:
        assert phrase.lower() not in blob


def _assert_reading_hints(body: dict, learner: str):
    suggestion = body["coaching"].get("suggested_reply") or ""
    blob = f"{learner}\n{suggestion}"
    hints = body["coaching"]["reading_hints"]
    assert hints
    for hint in hints:
        assert hint["term"] in blob
        note = hint["note"].lower()
        assert "you pronounced" not in note
        assert "pronunciation was" not in note
        assert "your tone" not in note
        assert "/" in hint["note"]
        assert any(token in hint["note"].lower() for token in ("read", "读", "讀"))


class _Scripted:
    name = "scripted"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def complete(self, messages, model, fallback):
        self.calls += 1
        return self.replies.pop(0) if self.replies else "nope"
