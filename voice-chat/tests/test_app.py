import logging
from pathlib import Path

import httpx
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


STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


class _StatusClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, headers=None):
        assert url == "https://openrouter.ai/api/v1/key"
        assert headers["Authorization"].startswith("Bearer ")
        token = headers["Authorization"].split(" ", 1)[1]
        assert token not in url
        if self.mode == "timeout":
            raise httpx.TimeoutException("timed out")
        if self.mode == "network":
            raise httpx.ConnectError("network down")
        return httpx.Response(
            self.code,
            json={"data": {"label": "secret-account", "limit_remaining": 3}},
        )


def _install_status_client(monkeypatch, mode, code=200):
    class Client(_StatusClient):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.mode = mode
            self.code = code

    monkeypatch.setattr("app.main.httpx.Client", Client)


def test_openrouter_status_without_key_skips_the_network(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("LINGOCOACH_ENV_FILE", raising=False)

    def forbid(*args, **kwargs):
        raise AssertionError("OpenRouter must not be contacted without a key")

    monkeypatch.setattr("app.main.httpx.Client", forbid)
    response = client.get("/api/openrouter/status")
    assert response.status_code == 200
    assert response.json() == {"connected": False, "reason": "no_key"}
    assert "OPENROUTER_API_KEY=" not in response.text
    assert "sk-or-" not in response.text
    blob = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in STATIC.rglob("*")
        if path.is_file() and path.suffix in {".html", ".js", ".css", ".svg"}
    )
    assert "OPENROUTER_API_KEY=" not in blob
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'src="/static/app.js?v=20261023-modes"' in page
    assert "OpenRouter LLM connectivity check" in script
    assert "Not connected. No OpenRouter key. Put it in /Users/mikelam/firstRepo/openrouter_key/.env_voice_chat and restart ./run-local.sh from voice-chat." in script
    assert "Not connected. Wrong key. OpenRouter rejected it. The key is not shown." in script
    assert "Not connected. Connection error. This server cannot reach OpenRouter. Check the network, then press Check again." in script
    nokeys = [line for line in script.splitlines() if line.strip().startswith("orNoKey:")]
    assert len(nokeys) == 3
    for line in nokeys:
        assert "Connection error" not in line
        assert "连接错误" not in line
        assert "連線錯誤" not in line
    assert 'data-act="or-status"' in script
    assert "/api/openrouter/status" in script


def test_openrouter_status_maps_auth_timeout_and_ok(monkeypatch, caplog):
    secret = "unit-test-key"
    monkeypatch.setenv("OPENROUTER_API_KEY", secret)
    cases = [
        ("ok", 200, {"connected": True}),
        ("auth", 401, {"connected": False, "reason": "auth"}),
        ("auth", 403, {"connected": False, "reason": "auth"}),
        ("timeout", 0, {"connected": False, "reason": "unreachable"}),
        ("network", 500, {"connected": False, "reason": "unreachable"}),
        ("other", 500, {"connected": False, "reason": "unreachable"}),
    ]
    for mode, code, expected in cases:
        _install_status_client(monkeypatch, mode, code)
        with caplog.at_level(logging.INFO, logger="lingocoach"):
            response = client.get("/api/openrouter/status")
        assert response.status_code == 200
        assert response.json() == expected
        assert secret not in response.text
        assert "secret-account" not in response.text
        assert secret not in caplog.text
        assert "Bearer" not in caplog.text
        assert "secret-account" not in caplog.text
        caplog.clear()
