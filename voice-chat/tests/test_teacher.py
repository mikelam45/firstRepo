"""Chloe corrects grammar, a wrong word, and a wrong phrase from the text alone."""

import json

from fastapi.testclient import TestClient

from app.fixtures import DAILY_DENY
from app.main import app

client = TestClient(app)

SETTINGS = {
    "target": "yue",
    "support": "en",
    "level": "beginner",
    "script": "Hant",
    "accent": "en-GB",
    "pinyin_tone": "mark",
}


def _turn(text, support="en", mode="correction"):
    settings = dict(SETTINGS)
    settings["support"] = support
    settings["mode"] = mode
    history = [] if text is None else [{"role": "learner", "text": text}]
    response = client.post(
        "/api/turn",
        json={
            "session_id": "teacher",
            "scenario_id": "english-teacher",
            "partner_id": "chloe",
            "settings": settings,
            "history": history,
            "fired_signals": [],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _clean(body):
    blob = json.dumps(body, ensure_ascii=False).lower()
    for phrase in DAILY_DENY:
        assert phrase.lower() not in blob


def test_teacher_opening_is_english():
    body = _turn(None)
    assert body["coaching"] is None
    assert body["partner_id"] == "chloe"
    assert "Chloe" in body["character"]["text"]
    assert body["character"]["phonetic_system"] == "ipa-rp"
    assert body["meta"]["route"] == "roleplay"
    _clean(body)


def test_teacher_fixes_past_grammar_and_bored():
    grammar = _turn("I want go to school yesterday")
    correction = grammar["coaching"]["corrections"][0]
    assert correction["type"] == "grammar"
    assert correction["quote"] in "I want go to school yesterday"
    assert "wanted" in grammar["coaching"]["suggested_reply"].lower()
    assert "school" in grammar["coaching"]["suggested_reply"].lower()
    assert grammar["character"]["phonetic_system"] == "ipa-rp"
    assert "shared_sentence" in grammar["session"]["fired_signals"]
    _clean(grammar)
    assert grammar["coaching"]["reading_hints"]
    for hint in grammar["coaching"]["reading_hints"]:
        assert hint["term"]
        assert "read" in hint["note"].lower() or "/" in hint["note"]

    word = _turn("I am very boring in the class")
    wrong = word["coaching"]["corrections"][0]
    assert wrong["type"] == "vocabulary"
    assert wrong["quote"].lower() == "boring"
    assert "bored" in word["coaching"]["suggested_reply"].lower()
    assert any(hint["term"].lower() == "the" for hint in word["coaching"]["reading_hints"])
    _clean(word)


def test_teacher_fixes_a_wrong_phrase_and_translates_the_explanation():
    body = _turn("Please discuss about this.", support="cmn")
    correction = body["coaching"]["corrections"][0]
    assert correction["type"] == "phrase"
    assert correction["quote"].lower() == "discuss about"
    assert "discuss about" not in body["coaching"]["suggested_reply"].lower()
    assert body["character"]["translation"]
    assert body["character"]["text"]
    _clean(body)


def test_offline_teacher_does_not_pretend_the_sentence_was_checked():
    body = _turn("I went to the market yesterday.")
    blob = json.dumps(body, ensure_ascii=False).lower()
    assert body["meta"]["provider"] == "fixture"
    assert "that sentence works" not in blob
    assert "model" in body["character"]["text"].lower()
    assert body["coaching"]["corrections"] == []
    assert "openrouter" in body["coaching"]["praise"].lower()
    _clean(body)


def test_teacher_page_offers_chloe_and_celine():
    page = client.get("/").text
    script = client.get("/static/app.js").text
    assert "english-teacher" in script
    assert 'data-act="teacher"' in script
    assert "chloe" in script
    assert "celine" in script
    assert "hk-cha-chaan-teng" in script
    assert "app.js" in page


def test_teacher_conversation_mode_natural_reply():
    body = _turn("Hello! Nice to meet you.", mode="conversation")
    assert body["meta"]["provider"] == "fixture"
    assert body["coaching"]["praise"]
    assert body["coaching"]["corrections"] == []
    assert body["coaching"]["suggested_reply"] is None
    assert body["coaching"]["reading_hints"] == []
    text = body["character"]["text"]
    correction_phrases = {
        "Let us fix the grammar in that sentence.",
        "One word in that sentence does not match the meaning.",
        "That phrase is not the one English uses here.",
        "I have not checked that sentence with the model yet.",
        "Send that sentence in English and I will help.",
        "Let us stop here for today.",
    }
    assert text not in correction_phrases
    assert text
    _clean(body)


def test_teacher_correction_mode_keeps_corrections():
    body = _turn("I want go to school yesterday", mode="correction")
    correction = body["coaching"]["corrections"][0]
    assert correction["type"] == "grammar"
    assert "wanted" in body["coaching"]["suggested_reply"].lower()
    _clean(body)
