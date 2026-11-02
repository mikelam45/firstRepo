"""Scripted IELTS speaking prompts. The model does not invent the next question."""

from __future__ import annotations

FOOD_GLOSS = {
    "en": "Questions about who cooks, a recent meal, a change in taste, and home versus restaurants.",
    "cmn": "这几题问：谁做饭、昨天吃了什么、小时候不喜欢但现在喜欢的食物，以及更想在家吃还是出去吃。",
    "yue": "呢幾題問：邊個煮、尋日食咗咩、細個唔鍾意而家鍾意嘅嘢食，同埋想喺屋企食定出面食。",
}

SKILL_GLOSS = {
    "en": "Describe a practical skill you taught someone you know: who, what, how, and how you felt.",
    "cmn": "描述一个你教给认识的人的实用技能：教了谁、教了什么、怎么教的，以及你的感受。",
    "yue": "講一個你教過俾一個你識嘅人嘅實用技能：教邊個、教咗咩、點教，同埋你教完有咩感覺。",
}

PROMPTS = [
    {
        "id": "food-at-home",
        "part": 1,
        "topic_tag": "food",
        "enabled": True,
        "questions": [
            "Do you usually cook, or does someone else cook in your home?",
            "What did you eat yesterday?",
            "Are there any foods you disliked as a child but like now?",
            "Do you prefer eating at home or eating out?",
        ],
        "gloss": FOOD_GLOSS,
    },
    {
        "id": "where-you-live",
        "part": 1,
        "topic_tag": "home",
        "enabled": True,
        "questions": [
            "Do you live in a house or a flat?",
            "What do you like about the area where you live?",
            "How long have you lived there?",
            "Would you like to move somewhere else in the future?",
        ],
        "gloss": {
            "en": "Questions about your home, the area, how long you have lived there, and moving.",
            "cmn": "这几题问：住的是房子还是公寓、喜欢这个地区的什么、住了多久，以及以后想不想搬走。",
            "yue": "呢幾題問：住屋定住樓、鍾意呢區邊樣、住咗幾耐，同埋以後想唔想搬走。",
        },
    },
    {
        "id": "free-time",
        "part": 1,
        "topic_tag": "leisure",
        "enabled": True,
        "questions": [
            "What do you usually do in the evening?",
            "Do you prefer spending free time alone or with other people?",
            "Have your hobbies changed since you were a child?",
            "Is there a hobby you would like to start this year?",
        ],
        "gloss": {
            "en": "Questions about evenings, company, old hobbies, and something new.",
            "cmn": "这几题问：晚上通常做什么、喜欢一个人还是和别人一起、爱好有没有变，以及今年想开始什么。",
            "yue": "呢幾題問：夜晚通常做咩、鍾意自己定同人一齊、興趣有冇變，同埋今年想開始咩。",
        },
    },
    {
        "id": "skill-you-taught",
        "part": 2,
        "topic_tag": "people",
        "enabled": True,
        "cue": {
            "title": "Describe a practical skill you taught someone you know.",
            "say": [
                "who you taught",
                "what skill you taught them",
                "how you taught it",
                "and explain how you felt about teaching that person",
            ],
        },
        "bullet_ids": ["who", "what", "how", "why"],
        "rounding_off": ["Do you still see that person often?"],
        "part3": [
            "Why do some people prefer to learn a skill from a friend rather than in a class?",
            "What practical skills are most useful before someone lives alone?",
            "How has the way people learn practical skills changed in recent years?",
            "Should schools spend more time teaching practical skills?",
        ],
        "gloss": SKILL_GLOSS,
    },
    {
        "id": "place-you-walk",
        "part": 2,
        "topic_tag": "places",
        "enabled": True,
        "cue": {
            "title": "Describe a place in your city where you like to walk.",
            "say": [
                "where it is",
                "how often you go there",
                "what you see there",
                "and explain why you enjoy walking there",
            ],
        },
        "bullet_ids": ["where", "often", "see", "why"],
        "rounding_off": ["Would you recommend that place to a visitor?"],
        "part3": [
            "Why do people choose to walk instead of using transport for short trips?",
            "How important are parks in a crowded city?",
            "Should city streets be safer for people who walk at night?",
            "How might walking habits change as cities get hotter?",
        ],
        "gloss": {
            "en": "Describe a walk you like: where, how often, what you see, and why you enjoy it.",
            "cmn": "描述一个你喜欢散步的地方：在哪里、多久去一次、看到什么，以及为什么喜欢。",
            "yue": "講一個你鍾意行下嘅地方：喺邊、幾耐去一次、見到咩，同埋點解鍾意。",
        },
    },
]

DIAGNOSTIC = {
    "part1": "food-at-home",
    "part2": "skill-you-taught",
    "part3_limit": 2,
}

_BY_ID = {item["id"]: item for item in PROMPTS}


def get_prompt(prompt_id: str) -> dict:
    prompt = _BY_ID.get(prompt_id)
    if prompt is None or not prompt["enabled"]:
        raise KeyError(prompt_id)
    return prompt


def prompts_for_part(part: int) -> list[dict]:
    return [item for item in PROMPTS if item["part"] == part and item["enabled"]]


def gloss_for(prompt_id: str, support: str, kind: str) -> str | None:
    if kind in {"mock", "mock_part"}:
        return None
    prompt = get_prompt(prompt_id)
    return prompt["gloss"].get(support) or prompt["gloss"]["en"]


def public_prompt(prompt: dict, kind: str = "drill") -> dict:
    data = {
        "id": prompt["id"],
        "part": prompt["part"],
        "topic_tag": prompt["topic_tag"],
        "questions": prompt.get("questions"),
        "cue": prompt.get("cue"),
        "bullet_ids": prompt.get("bullet_ids"),
        "rounding_off": prompt.get("rounding_off"),
        "part3": prompt.get("part3"),
        "gloss": None if kind in {"mock", "mock_part"} else prompt["gloss"],
    }
    return data


def public_bank(kind: str = "drill") -> list[dict]:
    return [public_prompt(item, kind) for item in PROMPTS if item["enabled"]]
