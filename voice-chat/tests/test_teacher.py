"""Nora corrects grammar, a wrong word, and a wrong phrase from the text alone."""

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


def _turn(text, support="en"):
    settings = dict(SETTINGS)
    settings["support"] = support
    history = [] if text is None else [{"role": "learner", "text": text}]
    response = client.post(
        "/api/turn",
        json={
            "session_id": "teacher",
            "scenario_id": "english-teacher",
            "partner_id": "nora",
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
    assert body["partner_id"] == "nora"
    assert "Nora" in body["character"]["text"]
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


def test_teacher_page_offers_nora():
    page = client.get("/").text
    script = client.get("/static/app.js").text
    assert "english-teacher" in script
    assert 'data-act="teacher"' in script
    assert "Nora" in script or "teacher" in script
    assert "app.js" in page
