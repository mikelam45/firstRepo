from fastapi.testclient import TestClient

from app.main import app
from app.partners import PARTNERS
from app.phonetics.pipeline import annotate
from app.visemes import english_visemes, pinyin_visemes

client = TestClient(app)

SETTINGS = {
    "target": "yue",
    "support": "en",
    "level": "beginner",
    "script": "Hant",
    "accent": "en-GB",
    "pinyin_tone": "mark",
}


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_catalogue_includes_english_teacher():
    women = [row for row in PARTNERS if row["gender"] == "woman"]
    men = [row for row in PARTNERS if row["gender"] == "man"]
    assert [row["name"] for row in women] == ["Amelia", "Mei", "Wing", "Chloe", "Celine"]
    assert [row["name"] for row in men] == ["Oliver", "Hao", "Lok"]
    assert all(row["age"] == 27 for row in PARTNERS)
    catalogue = client.get("/api/catalogue").json()
    assert len(catalogue["partners"]) == 8
    chloe = next(row for row in catalogue["partners"] if row["id"] == "chloe")
    assert chloe["name"] == "Chloe"
    assert chloe["age"] == 27
    assert chloe["role"]["en"] == "English teacher"
    assert chloe["mesh"] is True
    celine = next(row for row in catalogue["partners"] if row["id"] == "celine")
    assert celine["name"] == "Celine"
    assert celine["role"]["yue"] == "茶餐廳侍應"
    assert celine["mesh"] is True
    teacher = next(row for row in catalogue["scenarios"] if row["id"] == "english-teacher")
    assert teacher["role_ai"]["en"] == "English teacher"
    assert "examiner" not in teacher["role_ai"]["en"].lower()


def test_cantonese_register_fixture():
    response = client.post("/api/turn", json={
        "session_id": "s",
        "scenario_id": "hk-cha-chaan-teng",
        "partner_id": "wing",
        "settings": SETTINGS,
        "history": [{"role": "learner", "text": "我要咖啡"}],
        "fired_signals": [],
    })
    assert response.status_code == 200
    body = response.json()
    assert body["contract"] == "1"
    assert "唔該" in body["coaching"]["suggested_reply"]
    assert body["coaching"]["corrections"][0]["type"] == "register"
    assert body["coaching"]["suggested_reply_phonetic"].startswith("m4 goi1")


def test_opening_has_no_coaching():
    response = client.post("/api/turn", json={
        "session_id": "s",
        "scenario_id": "hk-cha-chaan-teng",
        "settings": SETTINGS,
        "history": [],
    })
    body = response.json()
    assert response.status_code == 200
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
        "script": "Hant",
        "accent": "en-GB",
        "speech_ms": 45000,
        "learner_text": text,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["overall_band"] is None
    pronunciation = next(row for row in body["criteria"] if row["id"] == "pronunciation")
    assert pronunciation["status"] == "unscored"
    assert pronunciation["band"] is None


def test_golden_jyutping_and_visemes():
    assert annotate("唔該，一杯熱啡，走甜。", "yue")["phonetic"] == "m4 goi1 jat1 bui1 jit6 fe1 zau2 tim4"
    assert annotate("埋單", "yue")["phonetic"] == "maai4 daan1"
    visemes = english_visemes("Do you usually cook at home?")
    assert len(visemes) > 1
    assert "DD" in visemes or "TH" in visemes
    pu = pinyin_visemes("pu tong hua")
    assert pu[0] in {"PP", "U"}
    assert "aa" in pu
    goi = pinyin_visemes("m4 goi1")
    assert goi[0] == "PP"
    assert any(name in {"aa", "E", "I", "O", "U"} for name in goi)
