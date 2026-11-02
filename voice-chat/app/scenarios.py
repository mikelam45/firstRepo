"""Daily scenarios. The chip row only lists records that are fully specified."""

from __future__ import annotations

SCENARIOS = {
    "hk-cha-chaan-teng": {
        "id": "hk-cha-chaan-teng",
        "locale": "HK",
        "enabled": True,
        "icon": "🍴",
        "title": {
            "en": "Restaurant",
            "cmn": "餐厅点餐",
            "yue": "餐廳叫餐",
        },
        "role_ai": {
            "en": "Counter staff",
            "cmn": "柜台店员",
            "yue": "櫃檯伙計",
        },
        "role_learner": {
            "en": "Customer",
            "cmn": "顾客",
            "yue": "客",
        },
        "goal": {
            "en": "Order a drink or dish, change or confirm one detail (ice, sugar, temperature), and ask for the bill",
            "cmn": "点一杯饮料或一道菜，确认或改一个细节（冰、甜度或冷热），然后买单",
            "yue": "叫一杯嘢飲或一碟餸，改或者確認一樣（冰、甜度、冷熱），再埋單",
        },
        "success_signals": [
            {"id": "ordered_drink", "description": "The learner ordered a drink."},
            {
                "id": "confirmed_detail",
                "description": "The learner confirmed or changed ice, sugar, or temperature.",
            },
            {"id": "asked_for_bill", "description": "The learner asked for the bill."},
        ],
        "vocab": [
            {"id": "please", "say": {"en": "please", "cmn": "请问", "yue": "唔該"}, "gloss": {"en": "request word", "cmn": "请求", "yue": "請求"}},
            {"id": "hot-coffee", "say": {"en": "a hot coffee", "cmn": "一杯热咖啡", "yue": "一杯熱啡"}, "gloss": {"en": "hot coffee", "cmn": "热咖啡", "yue": "熱咖啡"}},
            {"id": "iced-lemon", "say": {"en": "an iced lemon tea", "cmn": "一杯冻柠茶", "yue": "一杯凍檸茶"}, "gloss": {"en": "iced lemon tea", "cmn": "冻柠茶", "yue": "凍檸茶"}},
            {"id": "less-sweet", "say": {"en": "less sugar", "cmn": "少糖", "yue": "少甜"}, "gloss": {"en": "less sweet", "cmn": "少糖", "yue": "少甜"}},
            {"id": "no-sugar", "say": {"en": "no sugar", "cmn": "不要糖", "yue": "走甜"}, "gloss": {"en": "no sugar", "cmn": "不要糖", "yue": "走甜"}},
            {"id": "less-ice", "say": {"en": "less ice", "cmn": "少冰", "yue": "少冰"}, "gloss": {"en": "less ice", "cmn": "少冰", "yue": "少冰"}},
            {"id": "bill", "say": {"en": "the bill, please", "cmn": "买单", "yue": "埋單"}, "gloss": {"en": "the bill", "cmn": "买单", "yue": "埋單"}},
        ],
        "cultural_notes": [
            "Restaurant or café. Staff take the order; they do not lecture about the menu.",
            "Cantonese: requests use 唔該. Thanks for the drink once it is handed over can be 多謝. 咖啡 in speech is often 啡.",
            "Mandarin: 您好 / 请问. English: Could I / please. Drinks are often hot or iced, with or without sugar.",
            "Prices, if mentioned, match the locale (HKD in a Hong Kong café). No tipping ritual.",
        ],
        "opening_hint": {
            "beginner": "Staff greet and ask what they would like, in one short line.",
            "intermediate": "Greet and offer the day's iced special in one extra clause.",
            "advanced": "Greet, note the queue briefly, ask the order.",
        },
        # Surname Sin. Longer dictionary matches such as 埋單 stay on the default reading.
        "jyutping_overrides": {"單先生": "sin6 sin1 saang1"},
        "pinyin_phrases": {},
    },
    "london-directions": {
        "id": "london-directions",
        "locale": "London",
        "enabled": True,
        "icon": "🚇",
        "title": {
            "en": "Asking for directions",
            "cmn": "问路",
            "yue": "問路",
        },
        "role_ai": {
            "en": "A person on the pavement near a Tube entrance",
            "cmn": "地铁口一位路人",
            "yue": "地鐵口一個路人",
        },
        "role_learner": {
            "en": "A visitor",
            "cmn": "访客",
            "yue": "訪客",
        },
        "goal": {
            "en": "Ask the way to a named station entrance, understand one landmark, and confirm the turn",
            "cmn": "问到一个指名车站入口的路，听懂一个地标，并确认转弯",
            "yue": "問到一個指名車站入口點去，聽明一個地標，再確認轉彎",
        },
        "success_signals": [
            {"id": "named_destination", "description": "The learner named a station."},
            {"id": "checked_a_landmark", "description": "The learner checked a landmark."},
            {"id": "confirmed_the_turn", "description": "The learner confirmed the turn."},
        ],
        "vocab": [
            {"id": "excuse", "say": {"en": "Excuse me", "cmn": "打扰一下", "yue": "唔該"}, "gloss": {"en": "polite opener", "cmn": "礼貌开头", "yue": "有禮開頭"}},
            {"id": "way", "say": {"en": "Could you tell me the way to…", "cmn": "请问去……怎么走", "yue": "請問去……點行"}, "gloss": {"en": "ask the way", "cmn": "问路", "yue": "問路"}},
            {"id": "tube", "say": {"en": "the Tube", "cmn": "地铁", "yue": "地鐵"}, "gloss": {"en": "London underground", "cmn": "地铁", "yue": "地鐵"}},
            {"id": "roundel", "say": {"en": "the roundel", "cmn": "圆标", "yue": "圓標"}, "gloss": {"en": "Tube sign", "cmn": "地铁标志", "yue": "地鐵標誌"}},
            {"id": "left", "say": {"en": "turn left", "cmn": "向左转", "yue": "轉左"}, "gloss": {"en": "left turn", "cmn": "左转", "yue": "轉左"}},
        ],
        "cultural_notes": [
            "British English: lift, queue, way out, Tube, pavement. The polite frame is “Excuse me” and “Could you tell me…”.",
            "The character gives at most two steps, then a landmark (“you’ll see the roundel”). They do not list five turns.",
            "They do not ask for money.",
        ],
        "opening_hint": {
            "beginner": "The first bubble is the character offering help in one line: “Hi — where are you trying to get to?”",
            "intermediate": "The first bubble is the character offering help in one line: “Hi — where are you trying to get to?”",
            "advanced": "The character is mid-stride and may say they look a bit lost, then ask where they are trying to get to.",
        },
        "jyutping_overrides": {},
        "pinyin_phrases": {},
    },
    "beijing-hotel-checkin": {
        "id": "beijing-hotel-checkin",
        "locale": "Beijing",
        "enabled": False,
        "icon": "🏨",
        "title": {
            "en": "Hotel check-in",
            "cmn": "酒店入住",
            "yue": "酒店入住",
        },
        "role_ai": {
            "en": "Front-desk clerk",
            "cmn": "前台",
            "yue": "前台",
        },
        "role_learner": {
            "en": "Guest with a reservation",
            "cmn": "有预订的客人",
            "yue": "有預訂嘅客人",
        },
        "goal": {
            "en": "Give a name, confirm dates, and ask one practical question (wifi, breakfast, or late checkout)",
            "cmn": "说出姓名，确认日期，并问一个实际问题（无线网、早餐或延迟退房）",
            "yue": "講個名，確認日期，再問一樣實際嘅嘢（wifi、早餐或者遲退房）",
        },
        "success_signals": [
            {"id": "gave_name", "description": "The learner gave a booking name."},
            {"id": "confirmed_dates", "description": "The learner confirmed the dates."},
            {"id": "asked_extra", "description": "The learner asked about wifi, breakfast, or late checkout."},
        ],
        "vocab": [
            {"id": "hello", "say": {"en": "Hello", "cmn": "您好", "yue": "您好"}, "gloss": {"en": "service hello", "cmn": "您好", "yue": "您好"}},
            {"id": "booking", "say": {"en": "I have a reservation", "cmn": "我有预订", "yue": "我有預訂"}, "gloss": {"en": "reservation", "cmn": "预订", "yue": "預訂"}},
            {"id": "name", "say": {"en": "The booking name is…", "cmn": "预订姓名是……", "yue": "預訂姓名係……"}, "gloss": {"en": "booking name", "cmn": "姓名", "yue": "姓名"}},
            {"id": "wifi", "say": {"en": "What is the wifi password?", "cmn": "请问无线网密码是什么？", "yue": "請問 wifi 密碼係咩？"}, "gloss": {"en": "wifi", "cmn": "无线网", "yue": "wifi"}},
            {"id": "breakfast", "say": {"en": "Is breakfast included?", "cmn": "含早餐吗？", "yue": "包唔包早餐？"}, "gloss": {"en": "breakfast", "cmn": "早餐", "yue": "早餐"}},
        ],
        "cultural_notes": [
            "Mainland service Mandarin, 您好 / 请问 / 麻烦您.",
            "The clerk asks for the passport or booking name and the dates. They do not roleplay handing over a real ID number; if the learner starts to dictate a long number, the clerk says a booking name is enough.",
            "儿化 only in natural spots (这儿, 一点儿), not on 房间 or 早餐.",
        ],
        "opening_hint": {
            "beginner": "您好，请问您有预订吗？",
            "intermediate": "您好，请问您有预订吗？可以告诉我姓名和日期。",
            "advanced": "您好，欢迎光临。请问预订姓名和入住日期？",
        },
        "jyutping_overrides": {},
        # Surname Shan (单 shàn), not the default dān. Loaded for this scenario only.
        "pinyin_phrases": {"单先生": [["shàn"], ["xiān"], ["shēng"]]},
    },
    "english-teacher": {
        "id": "english-teacher",
        "locale": "London",
        "enabled": True,
        "icon": "💬",
        "title": {
            "en": "Casual chat",
            "cmn": "闲聊",
            "yue": "傾偈",
        },
        "role_ai": {
            "en": "Chat partner",
            "cmn": "闲聊伙伴",
            "yue": "傾偈夥伴",
        },
        "role_learner": {
            "en": "Learner",
            "cmn": "学习者",
            "yue": "學習者",
        },
        "goal": {
            "en": "Everyday small talk. In correction mode the coach fixes grammar, a wrong word, or a wrong phrase. In conversation mode they chat naturally with a short correctness note.",
            "cmn": "日常闲聊。纠错模式改正语法、用错的词或短语。对话模式自然聊天，并给一句简短对错提示。",
            "yue": "日常傾偈。糾錯模式改文法、用錯嘅字或者短語。對話模式自然傾，再加一句短短對錯提示。",
        },
        "success_signals": [
            {"id": "shared_sentence", "description": "The learner sent a sentence to correct."},
            {"id": "revised_sentence", "description": "The learner tried a revised sentence after a correction."},
        ],
        "vocab": [
            {"id": "past-want", "say": {"en": "I wanted to go", "cmn": "I wanted to go", "yue": "I wanted to go"}, "gloss": {"en": "past of want to", "cmn": "want 的过去式", "yue": "want 嘅過去式"}},
            {"id": "bored", "say": {"en": "I am bored", "cmn": "I am bored", "yue": "I am bored"}, "gloss": {"en": "how you feel", "cmn": "你的感觉", "yue": "你嘅感覺"}},
        ],
        "cultural_notes": [
            "Everyday small talk: weekend plans, food, weather, work, hobbies. Not a café clerk, hotel clerk, or IELTS examiner.",
            "character.text is English only. Explanations stay in the support language.",
            "Correction mode: grammar, a wrong word, or a wrong phrase. quote must be an exact substring of the learner line.",
            "Conversation mode: answer the learner naturally and put one short correctness or encouragement note in coaching.praise.",
            "Do not score pronunciation and do not say what a microphone heard. Leave reading_hints empty; the server adds how a word is read from the spelling.",
            "Never write “you pronounced”, “pronunciation was”, or “your tone”.",
        ],
        "opening_hint": {
            "beginner": "Hello, I am {name}. Shall we have a chat?",
            "intermediate": "Hello, I am {name}. Shall we have a chat?",
            "advanced": "Hello, I am {name}. Shall we have a chat?",
        },
        "jyutping_overrides": {},
        "pinyin_phrases": {},
    },
    "london-chat": {
        "id": "london-chat",
        "locale": "London",
        "enabled": True,
        "icon": "🇬🇧",
        "title": {
            "en": "London-focus chat",
            "cmn": "伦敦英语闲聊",
            "yue": "倫敦英語傾偈",
        },
        "role_ai": {
            "en": "London local",
            "cmn": "伦敦本地人",
            "yue": "倫敦本地人",
        },
        "role_learner": {
            "en": "Visitor or newcomer",
            "cmn": "访客或新来者",
            "yue": "訪客或新來者",
        },
        "goal": {
            "en": "Chat in UK/London English: a place, the Tube, and a polite local phrase.",
            "cmn": "用英国/伦敦英语闲聊：一个地方、地铁，以及一句礼貌的本地说法。",
            "yue": "用英國／倫敦英語傾偈：一個地方、地鐵，同一句有禮嘅本地講法。",
        },
        "success_signals": [
            {"id": "named_place", "description": "The learner named a London place."},
            {"id": "mentioned_tube", "description": "The learner mentioned the Tube or a line."},
            {"id": "used_polite_phrase", "description": "The learner used a polite British phrase."},
        ],
        "vocab": [
            {"id": "tube", "say": {"en": "the Tube", "cmn": "the Tube", "yue": "the Tube"}, "gloss": {"en": "London underground", "cmn": "伦敦地铁", "yue": "倫敦地鐵"}},
            {"id": "queue", "say": {"en": "join the queue", "cmn": "join the queue", "yue": "join the queue"}, "gloss": {"en": "British for line", "cmn": "排队", "yue": "排隊"}},
            {"id": "cheers", "say": {"en": "Cheers", "cmn": "Cheers", "yue": "Cheers"}, "gloss": {"en": "thanks / bye", "cmn": "谢谢或再见", "yue": "多謝或再見"}},
            {"id": "excuse", "say": {"en": "Excuse me", "cmn": "Excuse me", "yue": "Excuse me"}, "gloss": {"en": "polite opener", "cmn": "礼貌开头", "yue": "有禮開頭"}},
            {"id": "gap", "say": {"en": "mind the gap", "cmn": "mind the gap", "yue": "mind the gap"}, "gloss": {"en": "platform warning", "cmn": "月台空隙提醒", "yue": "月台空隙提醒"}},
        ],
        "cultural_notes": [
            "UK/London English: Tube, queue, pavement, lift, way out, cheers, mind the gap. No American subway/line/sidewalk unless correcting it.",
            "Talk about places (Soho, Covent Garden, Camden, Westminster, Hyde Park), the Tube, and politeness.",
            "character.text is English only. Explanations stay in the support language.",
            "Correction mode: grammar, a wrong word, a wrong phrase, or a more London wording. quote must be an exact substring of the learner line.",
            "Conversation mode: answer naturally about London and put one short correctness note in coaching.praise.",
            "Never write “you pronounced”, “pronunciation was”, or “your tone”.",
        ],
        "opening_hint": {
            "beginner": "Hi, I am {name}. Fancy a chat about London?",
            "intermediate": "Hi, I am {name}. Fancy a chat about London?",
            "advanced": "Hi, I am {name} — fancy a natter about London?",
        },
        "jyutping_overrides": {},
        "pinyin_phrases": {},
    },
}

MENU_IDS = (
    "hk-cha-chaan-teng",
    "london-directions",
    "english-teacher",
    "london-chat",
)

ENGLISH_FOCUS_IDS = {"english-teacher", "london-chat"}


def enabled_scenarios() -> list[dict]:
    rows = []
    for scenario_id in MENU_IDS:
        scenario = SCENARIOS.get(scenario_id)
        if scenario and scenario["enabled"]:
            rows.append(scenario)
    for scenario in SCENARIOS.values():
        if scenario["enabled"] and scenario["id"] not in MENU_IDS:
            rows.append(scenario)
    return rows


def get_scenario(scenario_id: str) -> dict:
    scenario = SCENARIOS.get(scenario_id)
    if scenario is None:
        raise KeyError(scenario_id)
    return scenario


def is_english_focus(scenario_id: str) -> bool:
    return scenario_id in ENGLISH_FOCUS_IDS


def signal_ids(scenario: dict) -> list[str]:
    return [item["id"] for item in scenario["success_signals"]]


def public_scenario(scenario: dict) -> dict:
    return {
        "id": scenario["id"],
        "locale": scenario["locale"],
        "icon": scenario["icon"],
        "title": scenario["title"],
        "role_ai": scenario["role_ai"],
        "role_learner": scenario["role_learner"],
        "goal": scenario["goal"],
        "success_signals": scenario["success_signals"],
        "vocab": scenario["vocab"],
    }
