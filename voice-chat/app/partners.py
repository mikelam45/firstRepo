"""Partners, age 27. Six scene partners, then Nora, the English teacher."""

from __future__ import annotations

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
        "manner": "Warm, clear British examiner. Short sentences. No American slang.",
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
        "id": "nora",
        "name": "Nora",
        "gender": "woman",
        "age": 27,
        "city": "London",
        "from": "London, UK",
        "region": "UK",
        "home_language": "en",
        "role": {
            "en": "English teacher",
            "cmn": "英语老师",
            "yue": "英文老師",
        },
        "manner": (
            "Patient English teacher. Speaks clear English. "
            "Corrects grammar, the wrong word, and a wrong phrase. "
            "Never comments on how a microphone heard the learner."
        ),
        "mesh": False,
        "display": "illustrated",
        "portrait": "/static/avatars/nora.svg",
        "mesh_url": None,
        "palette": {"bg": "#e7e4f4", "hair": "#4a3428", "skin": "#f4cbb3", "shirt": "#2c3f66"},
    },
]

_BY_ID = {partner["id"]: partner for partner in PARTNERS}


def all_partners() -> list[dict]:
    return list(PARTNERS)


def get_partner(partner_id: str | None) -> dict:
    if not partner_id:
        return _BY_ID["amelia"]
    partner = _BY_ID.get(partner_id)
    if partner is None:
        raise KeyError(partner_id)
    return partner


def public_partner(partner: dict) -> dict:
    return {
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
