"""Choosable roster, four scenes, and correction/conversation on every coach."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.partners import CHOOSABLE_IDS, all_partners
from app.scenarios import ENGLISH_FOCUS_IDS, MENU_IDS, enabled_scenarios, get_scenario

client = TestClient(app)
STATIC = Path(__file__).resolve().parents[1] / "app" / "static"

SETTINGS = {
    "target": "en",
    "support": "en",
    "level": "beginner",
    "script": "Hant",
    "accent": "en-GB",
    "pinyin_tone": "mark",
}


def test_catalogue_roster_and_scenes():
    catalogue = client.get("/api/catalogue").json()
    ids = [row["id"] for row in catalogue["partners"]]
    names = [row["name"] for row in catalogue["partners"]]
    assert ids == list(CHOOSABLE_IDS)
    assert names == ["Amelia", "Mei", "Chloe", "Celine"]
    assert "Wing" not in names
    assert "Oliver" not in names
    assert "Hao" not in names
    assert "Lok" not in names
    for row in catalogue["partners"]:
        assert row["mesh"] is True
        assert row["portrait"].endswith(".jpg")
        assert row["mesh_url"].endswith(".json")
        photo = STATIC / "avatars" / f"{row['id']}.jpg"
        mesh = STATIC / "avatars" / f"{row['id']}.json"
        assert photo.is_file()
        assert mesh.is_file()
        exprs = row["expressions"]
        assert set(exprs) == {"mouth_open", "smile", "eyes_open", "eyes_semi", "brow"}
        for key, url in exprs.items():
            stem = url.rsplit("/", 1)[-1]
            assert (STATIC / "avatars" / stem).is_file()
            assert stem.startswith(row["id"] + "-")
    scene_ids = [row["id"] for row in catalogue["scenarios"]]
    assert scene_ids == list(MENU_IDS)
    titles = {row["id"]: row["title"]["en"] for row in catalogue["scenarios"]}
    assert titles["hk-cha-chaan-teng"] == "Restaurant"
    assert titles["london-directions"] == "Asking for directions"
    assert titles["english-teacher"] == "Casual chat"
    assert titles["london-chat"] == "London-focus chat"
    assert "beijing-hotel-checkin" not in scene_ids


def test_enabled_menu_matches_catalogue():
    assert [row["id"] for row in enabled_scenarios()] == list(MENU_IDS)
    assert [partner["id"] for partner in all_partners()] == list(CHOOSABLE_IDS)
    hotel = get_scenario("beijing-hotel-checkin")
    assert hotel["enabled"] is False


def test_modes_on_all_four_coaches_and_scenes():
    scenes = list(MENU_IDS)
    for partner_id in CHOOSABLE_IDS:
        for scenario_id in scenes:
            for mode in ("correction", "conversation", "teacher"):
                settings = dict(SETTINGS)
                settings["mode"] = mode
                settings["partner"] = partner_id
                if scenario_id == "hk-cha-chaan-teng":
                    settings["target"] = "yue"
                response = client.post(
                    "/api/turn",
                    headers={"X-Client-Id": f"{partner_id}-{scenario_id}-{mode}"},
                    json={
                        "session_id": f"{partner_id}-{scenario_id}-{mode}",
                        "scenario_id": scenario_id,
                        "partner_id": partner_id,
                        "settings": settings,
                        "history": [{"role": "learner", "text": "Hello there"}],
                        "fired_signals": [],
                    },
                )
                assert response.status_code == 200, response.text
                body = response.json()
                assert body["partner_id"] == partner_id
                assert body["character"]["text"]
                if mode == "conversation":
                    assert body["coaching"]["corrections"] == []
                    assert body["coaching"]["suggested_reply"] is None
                    assert body["coaching"]["praise"]
                if mode == "teacher":
                    assert body["character"]["phonetic_system"] == "ipa-rp"
                    assert not any("\u4e00" <= ch <= "\u9fff" for ch in body["character"]["text"])


def test_hidden_partner_is_remapped_on_turn():
    response = client.post(
        "/api/turn",
        headers={"X-Client-Id": "hidden-wing"},
        json={
            "session_id": "hidden-wing",
            "scenario_id": "hk-cha-chaan-teng",
            "partner_id": "wing",
            "settings": {**SETTINGS, "target": "yue", "mode": "correction"},
            "history": [{"role": "learner", "text": "我要咖啡"}],
            "fired_signals": [],
        },
    )
    assert response.status_code == 200
    assert response.json()["partner_id"] == "celine"


def test_picker_script_hides_retired_coaches():
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "pickCoach" in script
    assert "home-scene" in script
    assert "teacher-mode" in script
    assert "london-chat" in script
    for hidden in ("data-id=\"wing\"", "data-id=\"oliver\"", "data-id=\"hao\"", "data-id=\"lok\""):
        assert hidden not in script
    assert "CHOOSABLE_IDS" in script
    assert "amelia" in script and "mei" in script and "chloe" in script and "celine" in script
    assert "app.js?v=20261102-expr" in page


def test_face_mesh_stays_mouth_only_with_sharp_brows():
    src = (STATIC / "face.js").read_text(encoding="utf-8")
    assert "Speak mode is mouth-only" in src
    assert "never move points above the upper-lip" in src
    assert "brow: speaking ? 0" in src
    assert "lip landmarks are deformed" in src
    assert "chin, cheeks, brows, and head stay still" in src
    assert "Photo frames (mouth-open / smile / eyes-semi / brow) blend" in src
    assert "load(imageUrl, meshUrl, expressions)" in src
    assert "u_smileAmt" in src
    assert ENGLISH_FOCUS_IDS == {"english-teacher", "london-chat"}


def test_casual_and_london_force_english():
    for scenario_id, partner_id in (("english-teacher", "mei"), ("london-chat", "celine")):
        body = client.post(
            "/api/turn",
            headers={"X-Client-Id": f"en-focus-{scenario_id}"},
            json={
                "session_id": f"en-focus-{scenario_id}",
                "scenario_id": scenario_id,
                "partner_id": partner_id,
                "settings": {**SETTINGS, "target": "yue", "support": "yue", "mode": "correction"},
                "history": [],
                "fired_signals": [],
            },
        ).json()
        assert body["partner_id"] == partner_id
        assert body["character"]["phonetic_system"] == "ipa-rp"
        assert not any("\u4e00" <= ch <= "\u9fff" for ch in body["character"]["text"])


def test_english_teacher_mode_in_restaurant_stays_in_scene():
    body = client.post(
        "/api/turn",
        headers={"X-Client-Id": "amelia-restaurant-teacher"},
        json={
            "session_id": "amelia-restaurant-teacher",
            "scenario_id": "hk-cha-chaan-teng",
            "partner_id": "amelia",
            "settings": {**SETTINGS, "target": "yue", "support": "en", "mode": "teacher"},
            "history": [{"role": "learner", "text": "I want go to school yesterday"}],
            "fired_signals": [],
        },
    ).json()
    assert body["partner_id"] == "amelia"
    assert body["character"]["phonetic_system"] == "ipa-rp"
    assert "Amelia" in body["character"]["text"] or body["coaching"]["corrections"]
    correction = body["coaching"]["corrections"][0]
    assert correction["type"] == "grammar"
    assert "wanted" in body["coaching"]["suggested_reply"].lower()
    assert body["coaching"]["reading_hints"]
    blob = str(body).lower()
    assert "you pronounced" not in blob
    assert "pronunciation was" not in blob


def test_home_offers_three_modes():
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "englishTeacherMode" in script
    assert 'data-mode="correction"' in script
    assert 'data-mode="conversation"' in script
    assert 'data-mode="teacher"' in script


def test_expression_photos_are_photographic_and_distinct():
    kinds = ("mouth-open", "smile", "eyes-open", "eyes-semi", "brow")
    for partner_id in CHOOSABLE_IDS:
        rest = (STATIC / "avatars" / f"{partner_id}.jpg").read_bytes()
        assert rest[:3] == b"\xff\xd8\xff"
        for kind in kinds:
            path = STATIC / "avatars" / f"{partner_id}-{kind}.jpg"
            data = path.read_bytes()
            assert data[:3] == b"\xff\xd8\xff"
            if kind == "eyes-open":
                assert data == rest
            else:
                assert data != rest
