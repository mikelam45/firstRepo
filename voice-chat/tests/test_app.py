from fastapi.testclient import TestClient

from app.main import app
from app.partners import PARTNERS
from app.phonetics import transcribe
from app.visemes import english_visemes, has_open_vowel, syllable_visemes

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_partners_are_six_people_aged_27():
    women = [row for row in PARTNERS if row["gender"] == "woman"]
    men = [row for row in PARTNERS if row["gender"] == "man"]
    assert len(women) == 3
    assert len(men) == 3
    assert all(row["age"] == 27 for row in PARTNERS)


def test_cantonese_register_fixture():
    response = client.post("/api/turn", json={
        "session_id": "s",
        "scenario_id": "hk-cha-chaan-teng",
        "partner_id": "wing",
        "settings": {"target": "yue", "support": "en", "level": "beginner", "script": "Hant", "accent": "en-GB"},
        "history": [{"role": "learner", "text": "我要咖啡"}],
        "fired_signals": [],
    })
    assert response.status_code == 200
    body = response.json()
    assert body["contract"] == "1"
    assert "唔該" in body["coaching"]["suggested_reply"]
    assert body["coaching"]["corrections"][0]["type"] == "register"
    assert body["coaching"]["suggested_reply_phonetic"].startswith("m4 goi1")
    assert body["provider"] == "fixture"


def test_opening_has_no_coaching():
    response = client.post("/api/turn", json={
        "session_id": "s",
        "scenario_id": "hk-cha-chaan-teng",
        "settings": {"target": "yue", "support": "en", "level": "beginner"},
        "history": [],
    })
    body = response.json()
    assert body["coaching"] is None
    assert body["character"]["text"]
    assert body["character"]["phonetic"]


def test_ielts_hides_overall_and_pronunciation():
    text = "I usually cook at home and yesterday I ate noodles with my sister there."
    response = client.post("/api/ielts/review", json={
        "session_id": "s",
        "kind": "drill",
        "part": 1,
        "prompt_id": "food-at-home",
        "target_band": 6.5,
        "support": "en",
        "speech_ms": 45000,
        "learner_text": text,
    })
    body = response.json()
    assert body["overall_band"] is None
    pronunciation = next(row for row in body["criteria"] if row["id"] == "pronunciation")
    assert pronunciation["status"] == "unscored"
    assert pronunciation["band"] is None


def test_golden_jyutping_and_visemes():
    assert transcribe("唔該，一杯熱啡，走甜。", "yue")["phonetic"] == "m4 goi1 jat1 bui1 jit6 fe1 zau2 tim4"
    assert transcribe("埋單", "yue")["phonetic"] == "maai4 daan1"
    gb = transcribe("Could I get a coffee, please?", "en", "en-GB")["phonetic"]
    us = transcribe("Could I get a coffee, please?", "en", "en-US")["phonetic"]
    assert "kɒfi" in gb
    assert "kɔːfi" in us
    assert gb != us
    visemes = english_visemes("Do you usually cook at home?")
    assert len(visemes) > 1
    assert "DD" in visemes or "TH" in visemes
    assert has_open_vowel(visemes)
    pu = syllable_visemes("pu tong hua")
    assert pu[0] in {"PP", "U"}
    assert "aa" in pu
    goi = syllable_visemes("m4 goi1")
    assert goi[0] == "PP"
    assert has_open_vowel(goi)
