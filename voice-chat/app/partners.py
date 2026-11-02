"""Partners, age 27. Four choosable photo coaches; others stay for old session ids."""

from __future__ import annotations

CHOOSABLE_IDS = ("amelia", "mei", "chloe", "celine")
HIDDEN_REMAP = {
    "wing": "celine",
    "lok": "celine",
    "oliver": "amelia",
    "hao": "mei",
    "nora": "chloe",
}

PARTNERS = [
    {
        "id": "amelia",
        "name": "Amelia",
        "gender": "woman",
        "age": 27,
        "city": "London",
        "from": "London, UK",
        "region": "UK",
        "home_language": "en",
        "role": {
            "en": "London partner",
            "cmn": "伦敦伙伴",
            "yue": "倫敦夥伴",
        },
        "manner": "Warm, clear British partner. Short sentences. No American slang.",
        "mesh": True,
        "display": "mesh",
        "portrait": "/static/avatars/amelia.jpg",
        "mesh_url": "/static/avatars/amelia.json",
        "palette": {"bg": "#d7dee8", "hair": "#3a2a22", "skin": "#f0c7b0"},
    },
    {
        "id": "mei",
        "name": "Mei",
        "gender": "woman",
        "age": 27,
        "city": "Beijing",
        "from": "Beijing, China",
        "region": "China",
        "home_language": "cmn",
        "role": {
            "en": "Beijing partner",
            "cmn": "北京伙伴",
            "yue": "北京夥伴",
        },
        "manner": "Friendly Beijing host. Mainland service Mandarin when the line is Putonghua: 您好 and 请问. No extra 儿化.",
        "mesh": True,
        "display": "mesh",
        "portrait": "/static/avatars/mei.jpg",
        "mesh_url": "/static/avatars/mei.json",
        "palette": {"bg": "#e6e2dc", "hair": "#1c1c1c", "skin": "#f3d0b8"},
    },
    {
        "id": "wing",
        "name": "Wing",
        "gender": "woman",
        "age": 27,
        "city": "Hong Kong",
        "from": "Hong Kong",
        "region": "HK",
        "home_language": "yue",
        "manner": "Practical Hong Kong voice. Colloquial Cantonese, particles kept, 唔該 for requests.",
        "mesh": False,
        "display": "illustrated",
        "portrait": "/static/avatars/wing.svg",
        "mesh_url": None,
        "palette": {"bg": "#f3d6cf", "hair": "#241816", "skin": "#efc2a4", "shirt": "#8f3d4b"},
    },
    {
        "id": "oliver",
        "name": "Oliver",
        "gender": "man",
        "age": 27,
        "city": "Manchester",
        "from": "Manchester, UK",
        "region": "UK",
        "home_language": "en",
        "manner": "Calm Manchester manner. British English: lift, queue, and pavement in a London scene.",
        "mesh": False,
        "display": "illustrated",
        "portrait": "/static/avatars/oliver.svg",
        "mesh_url": None,
        "palette": {"bg": "#d5e2f2", "hair": "#5a3a24", "skin": "#f0c8a8", "shirt": "#2f4f73"},
    },
    {
        "id": "hao",
        "name": "Hao",
        "gender": "man",
        "age": 27,
        "city": "Shanghai",
        "from": "Shanghai, China",
        "region": "China",
        "home_language": "cmn",
        "manner": "Straightforward Shanghai clerk. Mainland service Mandarin. No extra 儿化 on 房间 or 早餐.",
        "mesh": False,
        "display": "illustrated",
        "portrait": "/static/avatars/hao.svg",
        "mesh_url": None,
        "palette": {"bg": "#efe2cc", "hair": "#1a1a1a", "skin": "#e8be9e", "shirt": "#3d5c4a"},
    },
    {
        "id": "lok",
        "name": "Lok",
        "gender": "man",
        "age": 27,
        "city": "Hong Kong",
        "from": "Hong Kong",
        "region": "HK",
        "home_language": "yue",
        "manner": "Easy Hong Kong tone. Colloquial Cantonese, particles kept, 唔該 for requests.",
        "mesh": False,
        "display": "illustrated",
        "portrait": "/static/avatars/lok.svg",
        "mesh_url": None,
        "palette": {"bg": "#d7ebe4", "hair": "#201814", "skin": "#e7b898", "shirt": "#1f6f78"},
    },
    {
        "id": "chloe",
        "name": "Chloe",
        "gender": "woman",
        "age": 27,
        "city": "London",
        "from": "London, UK",
        "region": "UK",
        "home_language": "en",
        "role": {
            "en": "English partner",
            "cmn": "英语伙伴",
            "yue": "英文夥伴",
        },
        "manner": (
            "Patient London English partner. Speaks clear English. "
            "In correction mode she fixes grammar, the wrong word, and a wrong phrase. "
            "Never comments on how a microphone heard the learner."
        ),
        "mesh": True,
        "display": "mesh",
        "portrait": "/static/avatars/chloe.jpg",
        "mesh_url": "/static/avatars/chloe.json",
        "palette": {"bg": "#e4d5d0", "hair": "#3a2a22", "skin": "#f3d0c0", "shirt": "#f3efe6"},
    },
    {
        "id": "celine",
        "name": "Celine",
        "gender": "woman",
        "age": 27,
        "city": "Hong Kong",
        "from": "Hong Kong",
        "region": "HK",
        "home_language": "yue",
        "role": {
            "en": "Hong Kong partner",
            "cmn": "香港伙伴",
            "yue": "香港夥伴",
        },
        "manner": (
            "Warm Hong Kong partner. Colloquial Cantonese when the line is Cantonese, "
            "唔該 for requests. In correction mode she still chats in character while "
            "fixing grammar, words, and phrases."
        ),
        "mesh": True,
        "display": "mesh",
        "portrait": "/static/avatars/celine.jpg",
        "mesh_url": "/static/avatars/celine.json",
        "palette": {"bg": "#1c2430", "hair": "#2a211c", "skin": "#e7c2a8", "shirt": "#f4f1ea"},
    },
]

_BY_ID = {partner["id"]: partner for partner in PARTNERS}


def all_partners() -> list[dict]:
    """Choosable coaches for the home picker and catalogue."""
    return [partner for partner in PARTNERS if partner["id"] in CHOOSABLE_IDS]


def choose_partner(partner_id: str | None) -> str:
    """Map a request onto a choosable coach. Hidden ids stay import-safe."""
    if not partner_id:
        return "amelia"
    if partner_id in CHOOSABLE_IDS:
        return partner_id
    return HIDDEN_REMAP.get(partner_id, "amelia")


def get_partner(partner_id: str | None) -> dict:
    if not partner_id:
        return _BY_ID["amelia"]
    partner = _BY_ID.get(partner_id)
    if partner is None:
        raise KeyError(partner_id)
    return partner


def get_choosable_partner(partner_id: str | None) -> dict:
    return _BY_ID[choose_partner(partner_id)]


EXPR_FILES = {
    "mouth_open": "mouth-open",
    "smile": "smile",
    "eyes_open": "eyes-open",
    "eyes_semi": "eyes-semi",
    "brow": "brow",
}


def expression_urls(partner_id: str) -> dict:
    return {key: f"/static/avatars/{partner_id}-{stem}.jpg" for key, stem in EXPR_FILES.items()}


def public_partner(partner: dict) -> dict:
    row = {
        "id": partner["id"],
        "name": partner["name"],
        "gender": partner["gender"],
        "age": partner["age"],
        "city": partner["city"],
        "from": partner["from"],
        "region": partner["region"],
        "home_language": partner["home_language"],
        "mesh": partner["mesh"],
        "display": partner["display"],
        "portrait": partner["portrait"],
        "mesh_url": partner["mesh_url"],
        "palette": partner["palette"],
        "role": partner.get("role"),
    }
    if partner.get("mesh"):
        row["expressions"] = expression_urls(partner["id"])
    return row
