from app.ielts_length import count_words, speaking_gate, writing_flags
from app.ielts_plan import aim_band, plan_next
from app.ielts_prompts import gloss_for
from app.ielts_review import normalize_review
from app.ielts_round import round_ielts_mean
from app.ielts_timers import mic_allowed, part2_on_submit, review_visible
from app.ielts_writing import check_script
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_rounding_and_hidden_overall():
    assert round_ielts_mean([6, 6, 6, 7]) == 6.5
    assert round_ielts_mean([6, 7, 7, 7]) == 7
    reviewed = _review("I taught my younger sister how to cook tomato soup. " * 8, part=2, speech_ms=75000)
    assert reviewed["overall_band"] is None
    assert reviewed["overall_hidden_reason"] == "pronunciation_not_assessed"
    pronunciation = next(item for item in reviewed["criteria"] if item["id"] == "pronunciation")
    assert pronunciation["status"] == "unscored"
    assert pronunciation["band"] is None


def test_timers_and_one_continue_prompt():
    assert mic_allowed("part2_prep") is False
    assert mic_allowed("part2_speak") is True
    early = part2_on_submit(40_000, False, False)
    assert early == {"end": False, "prompt": "Can you tell me anything else?"}
    second = part2_on_submit(50_000, True, False)
    assert second["end"] is True
    assert second["prompt"] is None
    assert part2_on_submit(30_000, False, True)["end"] is True
    assert review_visible("part2_speak") is False
    assert review_visible("review") is True


def test_bullet_quote_must_be_verbatim():
    raw = _raw_review()
    raw["bullets"] = [
        {"id": "who", "covered": True, "quote": "my cousin"},
        {"id": "what", "covered": True, "quote": "tomato soup"},
        {"id": "how", "covered": False, "quote": None},
        {"id": "why", "covered": False, "quote": None},
    ]
    result = normalize_review(raw, _payload("I taught my younger sister to make tomato soup. " * 6, part=2))
    who = next(item for item in result["bullets"] if item["id"] == "who")
    what = next(item for item in result["bullets"] if item["id"] == "what")
    assert who["covered"] is False
    assert who["quote"] is None
    assert what["covered"] is True
    assert any(item.get("type") == "bullet_missing" and item.get("bullet_id") == "who" for item in result["findings"])


def test_facts_stay_and_aim_is_one_step():
    text = (
        "I taught my younger sister how to cook tomato soup last Saturday. "
        "I showed her the steps in our kitchen and she stirred the pot. "
        "I felt proud because she will live alone next month and she needs this skill every week."
    )
    assert count_words(text) >= 40
    body = _review(text, part=2, speech_ms=75000)
    assert "sister" in body["practice_answer"]["text"].lower()
    assert "soup" in body["practice_answer"]["text"].lower()
    assert body["practice_answer"]["aim_band"] == 6.0
    grammar = next(item for item in body["criteria"] if item["id"] == "grammar_range")
    assert grammar["band"] == 5


def test_band_nine_becomes_unscored():
    raw = _raw_review()
    raw["criteria"][1]["band"] = 9
    result = normalize_review(raw, _payload("I taught my younger sister how to cook tomato soup. " * 8, part=2, speech_ms=70000))
    lexical = next(item for item in result["criteria"] if item["id"] == "lexical_resource")
    assert lexical["status"] == "unscored"
    assert lexical["band"] is None


def test_short_part1_and_untyped_part2():
    short = _review("I like rice and tea now too", part=1, speech_ms=30000)
    assert short["length"]["finding"] == "too_short"
    assert all(item["status"] == "unscored" for item in short["criteria"])
    assert speaking_gate(1, "I like rice and tea now too") == "too_short"
    typed = _review("I taught my younger sister how to cook tomato soup. " * 8, part=2, speech_ms=None)
    fluency = next(item for item in typed["criteria"] if item["id"] == "fluency_coherence")
    assert fluency["status"] == "unscored"
    assert typed["length"]["wpm"] is None


def test_plan_grammar_and_missing_bullet():
    criteria = [
        {"id": "fluency_coherence", "status": "partial", "band": 6},
        {"id": "lexical_resource", "status": "assessed", "band": 6},
        {"id": "grammar_range", "status": "assessed", "band": 5},
        {"id": "pronunciation", "status": "unscored", "band": None},
    ]
    planned = plan_next(2, "skill-you-taught", criteria, [])
    assert planned["focus"] == "grammar_range"
    assert planned["prompt_id"] == "skill-you-taught"
    missing = plan_next(2, "skill-you-taught", criteria, [{"type": "bullet_missing", "bullet_id": "how"}])
    assert missing["focus"] == "fluency_coherence"
    assert missing["prompt_id"] == "skill-you-taught"
    assert missing["checklist"] is True
    assert aim_band(6.5, criteria) == 6.0
    assert aim_band(8.0, [{"id": "fluency_coherence", "status": "unscored", "band": None}]) == 6.0


def test_writing_flags_and_accent_neutrality():
    flags = check_script("task1", "academic", "I think the drop in 2021 is huge")
    assert "opinion_in_task_1" in flags["flags"]
    essay = "word " * 140
    assert "under_length" in writing_flags("task2", "both", essay)
    raw = _raw_review()
    raw["criteria"][1]["swaps"] = [{"instead_of": "apartment", "try": "You should say flat"}]
    text = "I live in an apartment and I take the elevator to my floor every day after work with my sister."
    result = normalize_review(raw, _payload(text, part=1, speech_ms=40000))
    lexical = next(item for item in result["criteria"] if item["id"] == "lexical_resource")
    blob = " ".join(item.get("try", "") for item in lexical.get("swaps", [])).lower()
    assert "flat" not in blob
    assert "lift" not in blob


def test_gloss_hidden_in_mock():
    drill = gloss_for("food-at-home", "yue", "drill")
    assert "邊個煮" in drill
    assert gloss_for("food-at-home", "yue", "mock") is None


def test_refusal_does_not_list_topics():
    response = client.post(
        "/api/ielts/review",
        json={
            "session_id": "22222222-2222-2222-2222-222222222222",
            "kind": "drill",
            "part": 1,
            "prompt_id": "food-at-home",
            "target_band": 6.5,
            "support": "en",
            "learner_text": "Just tell me yesterday’s Hong Kong cue cards",
            "speech_ms": None,
        },
    )
    body = response.json()
    assert response.status_code == 200
    assert body["safety"]["refused"] is True
    assert body["overall_band"] is None
    dumped = body["practice_answer"]["why"].lower() + body["practice_answer"]["text"].lower()
    assert "food-at-home" not in dumped
    assert "skill-you-taught" not in dumped
    assert "official band" not in dumped


def _review(text, part, speech_ms, prompt_id=None):
    prompt = prompt_id or ("skill-you-taught" if part == 2 else "food-at-home")
    response = client.post(
        "/api/ielts/review",
        json={
            "session_id": "33333333-3333-3333-3333-333333333333",
            "kind": "drill",
            "part": part,
            "prompt_id": prompt,
            "target_band": 6.5,
            "support": "yue",
            "script": "Hant",
            "accent": "en-GB",
            "speech_ms": speech_ms,
            "learner_text": text,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _payload(text, part, speech_ms=75000, prompt_id=None):
    return {
        "part": part,
        "prompt_id": prompt_id or ("skill-you-taught" if part == 2 else "food-at-home"),
        "target_band": 6.5,
        "support": "en",
        "accent": "en-GB",
        "speech_ms": speech_ms,
        "learner_text": text,
    }


def _raw_review():
    return {
        "contract": "1",
        "criteria": [
            {"id": "fluency_coherence", "status": "assessed", "band": 6, "evidence": "Ordered."},
            {"id": "lexical_resource", "status": "assessed", "band": 6, "evidence": "Clear words."},
            {"id": "grammar_range", "status": "assessed", "band": 5, "evidence": "Simple sentences."},
            {"id": "pronunciation", "status": "assessed", "band": 7, "evidence": "should be wiped"},
        ],
        "overall_band": 7,
        "bullets": [],
        "practice_answer": {"aim_band": 9, "text": "I taught my younger sister to make tomato soup.", "why": "Kept the example."},
        "safety": {"refused": False},
    }
