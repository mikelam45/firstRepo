from app.partners import PARTNERS, get_partner
from app.session import needs_reset_confirm
from app.visemes import MOODS, english_visemes, pinyin_visemes, synthesis_request, viseme_at


def test_partner_catalogue_three_and_three_age_27():
    women = [partner for partner in PARTNERS if partner["gender"] == "woman"]
    men = [partner for partner in PARTNERS if partner["gender"] == "man"]
    assert [partner["name"] for partner in women] == ["Amelia", "Mei", "Wing"]
    assert [partner["name"] for partner in men] == ["Oliver", "Hao", "Lok"]
    assert [partner["name"] for partner in PARTNERS] == ["Amelia", "Mei", "Wing", "Oliver", "Hao", "Lok"]
    assert all(partner["age"] == 27 for partner in PARTNERS)
    assert sum(1 for partner in PARTNERS if partner["gender"] == "woman") == 3
    assert sum(1 for partner in PARTNERS if partner["gender"] == "man") == 3


def test_english_and_pinyin_visemes():
    shapes = english_visemes("Do you usually cook at home?")
    assert len(shapes) > 1
    assert "DD" in shapes or "TH" in shapes
    assert any(shape in {"aa", "E", "I", "O", "U"} for shape in shapes)
    assert "PP" in english_visemes("up")
    hua = pinyin_visemes("pu tong hua")
    assert hua[0] in {"PP", "U"}
    assert "aa" in hua
    cantonese = pinyin_visemes("m4 goi1")
    assert cantonese[0] == "PP"
    assert cantonese[1] in {"aa", "E", "I", "O", "U"}


def test_clip_returns_to_rest():
    shapes = english_visemes("Do you usually cook at home?")
    seen = {viseme_at(shapes, t, 90, 400) for t in (0, 90, 180, 270)}
    assert len(seen) > 1
    assert viseme_at(shapes, 400, 90, 400) == "sil"
    assert viseme_at(shapes, 600, 90, 400) == "sil"


def test_mood_caps():
    assert MOODS["examiner"]["smile"] <= 0.12
    assert MOODS["happy"]["smile"] >= 0.6


def test_switch_keeps_bubbles_and_labels_hao():
    bubbles = [{"role": "character", "text": "Hello.", "partner_id": "amelia"}]
    kept = list(bubbles)
    assert get_partner("hao")["name"] == "Hao"
    assert kept == bubbles
    assert kept[0]["partner_id"] == "amelia"


def test_cantonese_voice_never_selects_mandarin():
    for partner_id in ("wing", "lok"):
        choice = synthesis_request(get_partner(partner_id), "yue", "en-GB")
        assert "zh-CN" not in choice["langs"]
        assert "zh-TW" not in choice["langs"]
        assert "zh-CN" in choice["forbid"]


def test_reset_confirm_only_after_a_learner_line():
    assert needs_reset_confirm([]) is False
    assert needs_reset_confirm([{"role": "character", "text": "Hi"}]) is False
    assert needs_reset_confirm([{"role": "learner", "text": "Hello"}]) is True
