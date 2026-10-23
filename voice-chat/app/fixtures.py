"""Recorded fixture provider for daily turns when OPENROUTER_API_KEY is empty.

These replies follow the §10.4 behaviours. Wording can vary. The structure cannot.
Nothing here claims the microphone was heard.
"""

from __future__ import annotations

import re

from app.phonetics.segment import is_han
from app.scenarios import signal_ids
from app.session import learner_count, turns_remaining_including_this, union_signals

DAILY_DENY = (
    "pronunciation was",
    "you pronounced",
    "your tone",
    "口音很",
    "你讀錯",
    "你读错",
)

_STATIONS = (
    "oxford",
    "paddington",
    "waterloo",
    "piccadilly",
    "victoria",
    "euston",
    "holborn",
    "angel",
    "bank",
    "king's cross",
    "kings cross",
)


def build_fixture(payload: dict, scenario: dict) -> dict:
    settings = payload["settings"]
    history = payload["history"]
    target = settings["target"]
    support = settings["support"]
    level = settings["level"]
    allowed = signal_ids(scenario)
    if _refused(history):
        return _safety(scenario, target)
    if scenario["id"] == "english-teacher" and settings.get("mode") == "conversation":
        return _teacher_conversation(payload, scenario)
    if not history:
        text = _opening(scenario["id"], target, level)
        return _pack(text, None, target, support, [], "open")
    fired = _signals_in_history(scenario["id"], history)
    fired = union_signals(payload.get("fired_signals") or [], fired, allowed)
    status = "met" if set(allowed).issubset(fired) else "open"
    learner = _last_learner(history)
    coaching = _coach(scenario["id"], learner, target, support, level, fired)
    text = _character(scenario["id"], target, level, fired, learner, status)
    including = turns_remaining_including_this(level, history)
    if learner_count(history) > 0 and including <= 1 and status != "met":
        text = "Let us stop here for today." if scenario["id"] == "english-teacher" else _wrap(target)
    return _pack(text, coaching, target, support, fired, status)


def _pack(text, coaching, target, support, fired, status) -> dict:
    translation = None if support == target else _translate(text, support)
    return {
        "contract": "1",
        "character": {"text": text, "translation": translation},
        "coaching": coaching,
        "goal": {"status": status, "fired": fired},
        "safety": {"refused": False},
    }


def _last_learner(history: list[dict]) -> str:
    for item in reversed(history):
        if item.get("role") == "learner":
            return str(item.get("text") or "")
    return ""


def _teacher_conversation(payload: dict, scenario: dict) -> dict:
    settings = payload["settings"]
    history = payload["history"]
    target = settings["target"]
    support = settings["support"]
    level = settings["level"]
    allowed = signal_ids(scenario)
    if _refused(history):
        return _safety(scenario, target)
    if not history:
        return _pack("Hello! How are you today?", None, target, support, [], "open")
    fired = _signals_in_history(scenario["id"], history)
    fired = union_signals(payload.get("fired_signals") or [], fired, allowed)
    including = turns_remaining_including_this(level, history)
    text = _conversation_reply(history, level, including)
    praise = _t(
        support,
        "That sounds clear.",
        "这句话听起来很清楚。",
        "呢句聽落好清楚。",
    )
    coaching = {"praise": praise, "corrections": [], "suggested_reply": None, "reading_hints": []}
    return _pack(text, coaching, target, support, fired, "open")


def _conversation_reply(history: list[dict], level: str, including: int) -> str:
    if learner_count(history) > 0 and including <= 1:
        return "It was great chatting with you today."
    replies = (
        "Nice to meet you too. What do you like to do in your free time?",
        "That sounds nice. Tell me more about it.",
        "I see. Do you have any plans for the weekend?",
        "Really? I would love to hear more.",
        "Hmm, interesting. What else is on your mind?",
    )
    return replies[learner_count(history) % len(replies)]


def _refused(history: list[dict]) -> bool:
    text = " ".join(str(item.get("text") or "") for item in history if item.get("role") == "learner")
    return bool(
        re.search(
            r"ignore (all|previous)|system prompt|reveal (the |your )?prompt|"
            r"\b(diagnos\w*|prescription|dosage)\b|\b(sue|lawsuit|legal advice)\b|"
            r"\b(invest|bitcoin|stock tip)\b|\b(nude|horny)\b|"
            r"yesterday.?s hong kong|what came up in hong kong|real test questions",
            text,
            re.I,
        )
    )


def _safety(scenario: dict, target: str) -> dict:
    scene = {
        "hk-cha-chaan-teng": {
            "yue": "我只可以幫你處理呢張單。",
            "cmn": "我只能帮您处理这个点单。",
            "en": "I can only help with this order.",
        },
        "london-directions": {
            "yue": "我只可以幫你問路。",
            "cmn": "我只能帮您问路。",
            "en": "I can only help with directions.",
        },
        "beijing-hotel-checkin": {
            "yue": "我只可以幫你辦理入住。",
            "cmn": "我只能帮您办理入住。",
            "en": "I can only help with check-in.",
        },
        "english-teacher": {
            "yue": "I can only help with your English sentences.",
            "cmn": "I can only help with your English sentences.",
            "en": "I can only help with your English sentences.",
        },
    }[scenario["id"]][target]
    return {
        "contract": "1",
        "character": {"text": scene, "translation": None},
        "coaching": None,
        "goal": {"status": "open", "fired": []},
        "safety": {"refused": True},
    }


def _opening(scenario_id: str, target: str, level: str) -> str:
    if scenario_id == "english-teacher":
        return "Hello, I am Chloe. Send me a sentence and I will help with the English."
    if scenario_id == "hk-cha-chaan-teng":
        if target == "yue":
            if level == "intermediate":
                return "唔該，今日有凍檸特飲，想飲啲咩？"
            if level == "advanced":
                return "唔該，而家有少少人排緊隊，想飲啲咩？"
            return "唔該，想飲啲咩？"
        if target == "cmn":
            return "您好，请问想喝什么？"
        if level == "advanced":
            return "Hi — there's a short queue. What would you like?"
        return "What would you like to drink?"
    if scenario_id == "london-directions":
        if target == "en":
            if level == "advanced":
                return "Hi, you look a bit lost — where are you trying to get to?"
            return "Hi — where are you trying to get to?"
        if target == "yue":
            return "你好，你想去邊度？"
        return "您好，请问您想去哪里？"
    if target == "cmn":
        if level == "beginner":
            return "您好，请问您有预订吗？"
        return "您好，请问预订姓名和日期？"
    if target == "yue":
        return "你好，請問有冇預訂？"
    return "Hello, do you have a reservation?"


def _wrap(target: str) -> str:
    if target == "yue":
        return "我哋今日先到呢度。唔該。"
    if target == "cmn":
        return "我们先到这里。"
    return "Let's wrap up here."


def _signals_in_history(scenario_id: str, history: list[dict]) -> list[str]:
    fired: list[str] = []
    for item in history:
        if item.get("role") != "learner":
            continue
        for signal in _signals_in_text(scenario_id, str(item.get("text") or "")):
            if signal not in fired:
                fired.append(signal)
    return fired


def _signals_in_text(scenario_id: str, text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    if scenario_id == "hk-cha-chaan-teng":
        if any(word in text for word in ("啡", "茶", "咖啡", "奶", "檸")) or any(
            word in lowered for word in ("coffee", "tea", "milk", "latte", "lemon")
        ):
            found.append("ordered_drink")
        if any(word in text for word in ("熱", "冻", "凍", "甜", "冰", "糖")) or any(
            word in lowered for word in ("hot", "iced", "ice", "sugar", "sweet", "cold", "warm")
        ):
            found.append("confirmed_detail")
        if any(word in text for word in ("埋單", "買單", "結帳", "结账")) or "bill" in lowered:
            found.append("asked_for_bill")
    elif scenario_id == "london-directions":
        if any(name in lowered for name in _STATIONS) or ("站" in text and "the station" not in lowered):
            found.append("named_destination")
        if any(word in lowered for word in ("roundel", "landmark", "bridge", "crossing", "lights")) or any(
            word in text for word in ("地標", "地标", "圓標", "桥", "橋")
        ):
            found.append("checked_a_landmark")
        if any(word in lowered for word in ("turn left", "turn right", "on the left", "on the right", "left", "right")) or any(
            word in text for word in ("轉左", "轉右", "向左", "向右", "左边", "右边")
        ):
            found.append("confirmed_the_turn")
    elif scenario_id == "english-teacher":
        return _teacher_signals(text)
    else:
        if any(word in text for word in ("我叫", "姓名", "名字")) or bool(
            re.search(r"\bmy name is\b|\bi'm\b|\bi am\b", lowered)
        ):
            found.append("gave_name")
        if any(word in text for word in ("月", "號", "号", "日", "晚")) or any(
            word in lowered for word in ("night", "until", "from", "october", "monday", "date")
        ):
            found.append("confirmed_dates")
        if any(word in lowered for word in ("wifi", "wi-fi", "breakfast", "checkout")) or any(
            word in text for word in ("早餐", "退房", "无线", "無線", "密碼", "密码")
        ):
            found.append("asked_extra")
    return found


def _wrong_language(text: str, target: str) -> bool:
    han = sum(1 for char in text if is_han(char))
    latin = sum(1 for char in text if char.isascii() and char.isalpha())
    if han + latin < 3:
        return False
    if target == "en":
        return han > latin
    # A single borrowed English word inside a Chinese line is normal.
    return latin > han and latin >= 8


def _coach(scenario_id: str, learner: str, target: str, support: str, level: str, fired: list[str]) -> dict:
    if scenario_id == "english-teacher":
        return _teacher_coaching(learner, support)
    if _wrong_language(learner, target):
        return _mismatch(scenario_id, learner, target, support)
    special = _special(scenario_id, learner, target, support)
    if special is not None:
        return special
    if _already_fine(scenario_id, learner, target, fired):
        return {
            "praise": _praise_fine(scenario_id, learner, support),
            "corrections": [],
            "suggested_reply": None,
            "reading_hints": [],
        }
    return _nudge(scenario_id, learner, target, support, fired)


def _special(scenario_id: str, learner: str, target: str, support: str):
    compact = re.sub(r"\s+", "", learner)
    if scenario_id == "hk-cha-chaan-teng" and target == "yue" and compact in {"我要咖啡", "我要一杯咖啡"}:
        return {
            "praise": _t(support, "You named the drink clearly.", "你讲清了饮料。", "你講清楚想飲咩。"),
            "corrections": [
                {
                    "type": "register",
                    "quote": "我要",
                    "why": _t(
                        support,
                        "In a Hong Kong café, 唔該 is the natural way to make a request. 我要 sounds like a translation from Mandarin.",
                        "在茶餐厅点单，用唔该才自然。我要像从普通话直译过来。",
                        "喺茶餐廳叫嘢，用唔該先自然。我要聽落似由普通話譯過嚟。",
                    ),
                }
            ],
            "suggested_reply": "唔該，一杯熱啡。",
            "reading_hints": [
                {
                    "term": "啡",
                    "note": _t(
                        support,
                        "Spoken Cantonese often shortens 咖啡 to 啡 in this setting.",
                        "口语里常把咖啡说成啡。",
                        "口語入面，咖啡通常會講成啡。",
                    ),
                }
            ],
        }
    if scenario_id == "hk-cha-chaan-teng" and target == "yue" and "走甜" in learner and "唔該" in learner:
        return {
            "praise": _t(
                support,
                "You used 唔該 for the request, and 走甜 is clear.",
                "你用了唔该来点单，走甜也说清楚了。",
                "你用咗唔該嚟叫嘢，走甜都講得清楚。",
            ),
            "corrections": [],
            "suggested_reply": None,
            "reading_hints": [],
        }
    if scenario_id == "london-directions" and target == "en" and learner.strip().lower() in {
        "i want the station.",
        "i want the station",
    }:
        return {
            "praise": None,
            "corrections": [
                {
                    "type": "completeness",
                    "quote": "the station",
                    "why": _t(
                        support,
                        "The person needs the station's name before they can point. A request can wait until that is clear.",
                        "对方要先知道站名才指得了路。站名清楚之前，不必先改礼貌说法。",
                        "人哋要知係邊個站先指到路。站名未清楚，唔使先改禮貌講法。",
                    ),
                }
            ],
            "suggested_reply": "Could you tell me the way to the station I need?",
            "reading_hints": [],
        }
    if scenario_id == "beijing-hotel-checkin" and target == "cmn" and compact in {"我要入住", "我要办理入住"}:
        return {
            "praise": _t(support, "You said you want to check in.", "你说了要入住。", "你講咗想入住。"),
            "corrections": [
                {
                    "type": "completeness",
                    "quote": "我要入住",
                    "why": _t(
                        support,
                        "The clerk still needs a booking name or the dates. 您好 or 麻烦您 fits the front desk.",
                        "前台还需要预订姓名或日期。用您好或麻烦您更像前台。",
                        "前台仲要預訂姓名或者日期。用您好或者麻烦您先似前台。",
                    ),
                }
            ],
            "suggested_reply": "您好，麻烦您，我想办理入住。",
            "reading_hints": [],
        }
    return None


def _mismatch(scenario_id: str, learner: str, target: str, support: str) -> dict:
    suggestion = {
        ("hk-cha-chaan-teng", "yue"): "唔該，一杯熱啡。",
        ("hk-cha-chaan-teng", "cmn"): "您好，我要一杯热咖啡。",
        ("hk-cha-chaan-teng", "en"): "Could I get a hot coffee, please?",
        ("london-directions", "en"): "Could you tell me the way to Paddington station?",
        ("london-directions", "yue"): "唔該，去 Paddington 站點行？",
        ("london-directions", "cmn"): "请问，去 Paddington 站怎么走？",
        ("beijing-hotel-checkin", "cmn"): "您好，我有预订。",
        ("beijing-hotel-checkin", "yue"): "您好，我有預訂。",
        ("beijing-hotel-checkin", "en"): "Hello, I have a reservation.",
    }[(scenario_id, target)]
    quote = learner.strip()[:80]
    return {
        "praise": None,
        "corrections": [
            {
                "type": "mismatch",
                "quote": quote,
                "why": _t(
                    support,
                    "That line is not in the language of this scene. Here is the same request in the target language.",
                    "这句不是这个场景的语言。下面是同一件事的目标语说法。",
                    "呢句唔係呢個場景嘅語言。下面係同一件事嘅目標語講法。",
                ),
            }
        ],
        "suggested_reply": suggestion,
        "reading_hints": [],
    }


def _already_fine(scenario_id: str, learner: str, target: str, fired: list[str]) -> bool:
    if _wrong_language(learner, target):
        return False
    if scenario_id == "hk-cha-chaan-teng" and target == "yue":
        return "唔該" in learner and ("ordered_drink" in fired) and (
            "confirmed_detail" in fired or "asked_for_bill" in fired
        )
    if scenario_id == "london-directions" and target == "en":
        lowered = learner.lower()
        return lowered.startswith("could you") or lowered.startswith("excuse me")
    if scenario_id == "beijing-hotel-checkin" and target == "cmn":
        return "您好" in learner or "麻烦" in learner
    return False


def _praise_fine(scenario_id: str, learner: str, support: str) -> str:
    if "走甜" in learner or "唔該" in learner:
        return _t(
            support,
            "You used 唔該 for the request, and the detail is clear.",
            "你用了唔该，细节也清楚。",
            "你用咗唔該，細節都清楚。",
        )
    return _t(support, "That works for this step.", "这一步这样说就可以。", "呢一步咁講得。")


def _nudge(scenario_id: str, learner: str, target: str, support: str, fired: list[str]) -> dict:
    suggestion = _suggest_missing(scenario_id, target, fired)
    if suggestion is None:
        return {
            "praise": _praise_fine(scenario_id, learner, support),
            "corrections": [],
            "suggested_reply": None,
            "reading_hints": [],
        }
    quote = learner.strip()[:80] or learner
    return {
        "praise": None,
        "corrections": [
            {
                "type": "completeness",
                "quote": quote,
                "why": _t(
                    support,
                    "The scene still needs one more piece before it can move on.",
                    "这个场景还缺一样信息，对方才好继续。",
                    "呢個場景仲缺一樣資料，對方先繼續到。",
                ),
            }
        ],
        "suggested_reply": suggestion,
        "reading_hints": [],
    }


def _suggest_missing(scenario_id: str, target: str, fired: list[str]) -> str | None:
    if scenario_id == "hk-cha-chaan-teng":
        if "ordered_drink" not in fired:
            return {"yue": "唔該，一杯熱啡。", "cmn": "您好，一杯热咖啡。", "en": "Could I get a hot coffee, please?"}[target]
        if "confirmed_detail" not in fired:
            return {"yue": "唔該，一杯熱啡，走甜。", "cmn": "请给我一杯热的，不要糖。", "en": "Could I get it hot, with no sugar, please?"}[target]
        if "asked_for_bill" not in fired:
            return {"yue": "唔該，埋單。", "cmn": "请买单。", "en": "Could I have the bill, please?"}[target]
        return None
    if scenario_id == "london-directions":
        if "named_destination" not in fired:
            return {
                "en": "Could you tell me the way to Paddington station?",
                "cmn": "请问去 Paddington 站怎么走？",
                "yue": "唔該，去 Paddington 站點行？",
            }[target]
        if "checked_a_landmark" not in fired:
            return {
                "en": "Will I see the roundel?",
                "cmn": "我会看到圆标吗？",
                "yue": "我會唔會見到個圓標？",
            }[target]
        if "confirmed_the_turn" not in fired:
            return {"en": "So I turn left?", "cmn": "所以我向左转？", "yue": "即係我轉左？"}[target]
        return None
    if "gave_name" not in fired:
        return {"cmn": "您好，预订姓名是林。", "yue": "您好，預訂姓名係林。", "en": "Hello, the booking name is Lin."}[target]
    if "confirmed_dates" not in fired:
        return {"cmn": "入住是周五，住两晚。", "yue": "星期五入住，住兩晚。", "en": "I arrive on Friday and stay two nights."}[target]
    if "asked_extra" not in fired:
        return {"cmn": "请问早餐怎么安排？", "yue": "請問早餐點安排？", "en": "Could you tell me about breakfast?"}[target]
    return None


def _character(scenario_id: str, target: str, level: str, fired: list[str], learner: str, status: str) -> str:
    if scenario_id == "english-teacher":
        return _teacher_line(learner)
    if status == "met":
        return {
            "hk-cha-chaan-teng": {"yue": "好，埋單。一共廿八蚊。", "cmn": "好的，我来买单。一共二十八块。", "en": "Sure, here is the bill. That's twenty-eight dollars."},
            "london-directions": {"en": "Yes — turn left, and you'll see the roundel.", "cmn": "对，向左转，你会看到圆标。", "yue": "係，轉左，你會見到個圓標。"},
            "beijing-hotel-checkin": {"cmn": "好的，早餐在一楼。这是您的房卡。", "yue": "好，早餐喺一樓。呢張係房卡。", "en": "Breakfast is on the first floor. Here is your key."},
        }[scenario_id][target]
    if scenario_id == "hk-cha-chaan-teng":
        if "ordered_drink" not in fired:
            return _opening(scenario_id, target, level)
        if "confirmed_detail" not in fired:
            return {"yue": "熱定凍？甜度呢？", "cmn": "热的还是冰的？甜度呢？", "en": "Hot or iced? And how sweet?"}[target]
        if "asked_for_bill" not in fired:
            return {"yue": "好，喺度飲定打包？", "cmn": "好的，在这儿喝还是带走？", "en": "For here, or to take away?"}[target]
    if scenario_id == "london-directions":
        if "named_destination" not in fired:
            return {"en": "Which station is that?", "cmn": "请问是哪一站？", "yue": "係邊個站？"}[target]
        if "checked_a_landmark" not in fired:
            return {"en": "You'll see the roundel by the entrance.", "cmn": "入口那儿你会看到圆标。", "yue": "入口度你會見到個圓標。"}[target]
        return {"en": "Then turn left at the lights.", "cmn": "然后在红绿灯向左转。", "yue": "跟住喺紅綠燈轉左。"}[target]
    if "gave_name" not in fired:
        return {"cmn": "请问预订姓名是什么？", "yue": "請問預訂姓名係咩？", "en": "What name is the booking under?"}[target]
    if "confirmed_dates" not in fired:
        return {"cmn": "请问入住和离店的日期？", "yue": "請問邊日入住、邊日走？", "en": "What are the arrival and departure dates?"}[target]
    return {"cmn": "好的。还需要早餐或者延迟退房吗？", "yue": "好。仲使唔使問早餐或者遲退房？", "en": "Certainly. Do you need breakfast or a late checkout?"}[target]


def _translate(text: str, support: str) -> str:
    table = {
        "唔該，想飲啲咩？": ("What would you like to drink?", "请问想喝什么？", "唔該，想飲啲咩？"),
        "熱定凍？甜度呢？": ("Hot or iced? And how sweet?", "热的还是冰的？甜度呢？", "熱定凍？甜度呢？"),
        "好，喺度飲定打包？": ("For here, or to take away?", "在这儿喝还是带走？", "喺度飲定打包？"),
        "好，埋單。一共廿八蚊。": ("Sure, here is the bill. That's twenty-eight dollars.", "好的，买单。一共二十八块。", "好，埋單。一共廿八蚊。"),
        "Hi — where are you trying to get to?": ("Hi — where are you trying to get to?", "你好，你想去哪里？", "你好，你想去邊度？"),
        "Which station is that?": ("Which station is that?", "请问是哪一站？", "係邊個站？"),
        "您好，请问您有预订吗？": ("Hello, do you have a reservation?", "您好，请问您有预订吗？", "你好，請問有冇預訂？"),
        "请问预订姓名是什么？": ("What name is the booking under?", "请问预订姓名是什么？", "請問預訂姓名係咩？"),
        "我哋今日先到呢度。唔該。": ("Let's wrap up here.", "我们先到这里。", "我哋今日先到呢度。唔該。"),
        "Let's wrap up here.": ("Let's wrap up here.", "我们先到这里。", "我哋今日先到呢度。"),
        "我们先到这里。": ("Let's wrap up here.", "我们先到这里。", "我哋今日先到呢度。"),
        "Hello, I am Chloe. Send me a sentence and I will help with the English.": (
            "Hello, I am Chloe. Send me a sentence and I will help with the English.",
            "你好，我是 Chloe。发我一句英语，我来帮你改。",
            "你好，我係 Chloe。傳一句英文畀我，我幫你改。",
        ),
        "Let us fix the grammar in that sentence.": (
            "Let us fix the grammar in that sentence.",
            "我们来改这句的语法。",
            "我哋嚟改呢句嘅文法。",
        ),
        "One word in that sentence does not match the meaning.": (
            "One word in that sentence does not match the meaning.",
            "这句里有一个词和意思不相符。",
            "呢句有個字同意思唔夾。",
        ),
        "That phrase is not the one English uses here.": (
            "That phrase is not the one English uses here.",
            "这个短语不是英语这里的说法。",
            "呢個短語唔係英文呢度嘅講法。",
        ),
        "I have not checked that sentence with the model yet.": (
            "I have not checked that sentence with the model yet.",
            "我还没有把这句发给模型。",
            "我未將呢句交俾模型。",
        ),
        "Send that sentence in English and I will help.": (
            "Send that sentence in English and I will help.",
            "请用英语把那句发给我，我来帮你。",
            "請用英文傳嗰句，我嚟幫你。",
        ),
        "Let us stop here for today.": (
            "Let us stop here for today.",
            "今天先到这里。",
            "今日先到呢度。",
        ),
        "Hello! How are you today?": (
            "Hello! How are you today?",
            "你好！今天怎么样？",
            "你好！今日點呀？",
        ),
        "Nice to meet you too. What do you like to do in your free time?": (
            "Nice to meet you too. What do you like to do in your free time?",
            "我也很高兴认识你。你空闲时喜欢做什么？",
            "我都好高興認識你。你空閒嗰陣鍾意做咩？",
        ),
        "That sounds nice. Tell me more about it.": (
            "That sounds nice. Tell me more about it.",
            "听起来不错。再多告诉我一点。",
            "聽落唔錯。再講多啲嚟聽下。",
        ),
        "I see. Do you have any plans for the weekend?": (
            "I see. Do you have any plans for the weekend?",
            "原来如此。你周末有什么安排吗？",
            "我明白。你週末有咩安排？",
        ),
        "Really? I would love to hear more.": (
            "Really? I would love to hear more.",
            "真的吗？我很想再听多点。",
            "真係？我想再聽多啲。",
        ),
        "Hmm, interesting. What else is on your mind?": (
            "Hmm, interesting. What else is on your mind?",
            "嗯，有意思。你还在想什么？",
            "嗯，幾得意。你仲有咩諗緊？",
        ),
        "It was great chatting with you today.": (
            "It was great chatting with you today.",
            "今天聊得很开心。",
            "今日傾得好開心。",
        ),
    }
    if text in table:
        return table[text][{"en": 0, "cmn": 1, "yue": 2}[support]]
    if support == "en":
        return "Reply in the scene."
    if support == "cmn":
        return "这是场景里的下一句。"
    return "呢句係場景入面嘅下一句。"


def _t(support: str, en: str, cmn: str, yue: str) -> str:
    return {"en": en, "cmn": cmn, "yue": yue}[support]


_TEACHER_VERBS = {
    "go", "eat", "drink", "see", "buy", "make", "do", "study", "learn", "play",
    "come", "take", "have", "get", "walk", "read", "write", "speak", "say",
    "visit", "meet", "watch", "cook", "work", "sleep", "leave", "start",
}

_TEACHER_PAST = {
    "go": "went",
    "eat": "ate",
    "see": "saw",
    "come": "came",
    "buy": "bought",
    "drink": "drank",
    "walk": "walked",
}

_TEACHER_SAY = {
    "grammar": "Let us fix the grammar in that sentence.",
    "vocabulary": "One word in that sentence does not match the meaning.",
    "phrase": "That phrase is not the one English uses here.",
    "mismatch": "Send that sentence in English and I will help.",
    "fine": "I have not checked that sentence with the model yet.",
}

_PHRASE_FIXES = (
    (
        re.compile(r"\bdiscuss about\b", re.I),
        "discuss",
        (
            "English uses discuss plus the topic. About is an extra word.",
            "英语里 discuss 直接接话题，about 是多出来的。",
            "英文 discuss 直接接話題，about 係多出嚟嘅。",
        ),
    ),
    (
        re.compile(r"\breturn back\b", re.I),
        "return",
        (
            "Return already means go back. Back is an extra word.",
            "return 已经是回去。back 是多出来的。",
            "return 已經係返去。back 係多出嚟嘅。",
        ),
    ),
    (
        re.compile(r"\bmore better\b", re.I),
        "better",
        (
            "Better is already the comparative. More is an extra word.",
            "better 已经是比较级。more 是多出来的。",
            "better 已經係比較級。more 係多出嚟嘅。",
        ),
    ),
    (
        re.compile(r"\bexplain me\b", re.I),
        "explain to me",
        (
            "Explain needs to before the person: explain to me.",
            "explain 后面说到人要用 to：explain to me。",
            "explain 後面講到人要用 to：explain to me。",
        ),
    ),
)


def _teacher_signals(text: str) -> list[str]:
    if re.search(r"[A-Za-z]", text):
        return ["shared_sentence"]
    return []


def _teacher_line(learner: str) -> str:
    kind = _teacher_coaching(learner, "en")["corrections"]
    if not kind:
        return _TEACHER_SAY["fine"]
    return _TEACHER_SAY.get(kind[0]["type"], _TEACHER_SAY["fine"])


def _tidy_sentence(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip())
    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def _sentence_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower().rstrip(".!?")


def _teacher_pack(support: str, ctype: str, quote: str, why: tuple[str, str, str], suggestion: str) -> dict:
    return {
        "praise": None,
        "corrections": [{"type": ctype, "quote": quote, "why": _t(support, *why)}],
        "suggested_reply": suggestion,
        "reading_hints": [],
    }


def _teacher_coaching(learner: str, support: str) -> dict:
    original = learner.strip()
    text = re.sub(r"\s+", " ", original)
    if _wrong_language(original, "en"):
        return _teacher_pack(
            support,
            "mismatch",
            original[:80],
            (
                "Send the sentence in English and I will correct it.",
                "请用英语写这句，我再帮你改。",
                "請用英文寫呢句，我再幫你改。",
            ),
            "I wanted to go to school yesterday.",
        )
    key = _sentence_key(original)
    if key == "i want go to school yesterday":
        match = re.search(r"want\s+go", original, re.I)
        quote = original[match.start():match.end()] if match else "want go"
        return _teacher_pack(
            support,
            "grammar",
            quote,
            (
                "After want, use to before the verb. Yesterday needs the past: wanted.",
                "want 后面要加 to 再接动词。yesterday 要用过去式 wanted。",
                "want 後面要加 to 先接動詞。yesterday 要用過去式 wanted。",
            ),
            "I wanted to go to school yesterday.",
        )
    if key == "i am very boring in the class":
        match = re.search(r"boring", original, re.I)
        quote = original[match.start():match.end()] if match else "boring"
        return _teacher_pack(
            support,
            "vocabulary",
            quote,
            (
                "Boring describes something that makes you feel dull. You feel bored.",
                "boring 用来形容让人觉得闷的事物。你自己的感觉要用 bored。",
                "boring 係形容令人覺得悶嘅事物。你自己嘅感覺要用 bored。",
            ),
            "I am very bored in the class.",
        )
    patterned = _teacher_patterns(original, support)
    if patterned is not None:
        return patterned
    return {
        "praise": _t(
            support,
            "Offline examples did not send this sentence to the model. Restart with the OpenRouter key and send it again.",
            "离线例句没有把这句发给模型。用 OpenRouter 密钥重新启动后再发一次。",
            "離線例句冇將呢句交俾模型。用 OpenRouter 金鑰重新開一次再傳。",
        ),
        "corrections": [],
        "suggested_reply": None,
        "reading_hints": [],
    }


def _teacher_patterns(text: str, support: str) -> dict | None:
    feeling = re.search(
        r"\b(?:i am|i'm|i feel|i felt|he is|she is|we are|they are|you are)\b(?:\s+\w+){0,4}\s+(boring)\b",
        text,
        re.I,
    )
    if feeling:
        quote = text[feeling.start(1):feeling.end(1)]
        suggestion = _tidy_sentence(text[:feeling.start(1)] + "bored" + text[feeling.end(1):])
        return _teacher_pack(
            support,
            "vocabulary",
            quote,
            (
                "Boring describes something that makes you feel dull. You feel bored.",
                "boring 用来形容让人觉得闷的事物。你自己的感觉要用 bored。",
                "boring 係形容令人覺得悶嘅事物。你自己嘅感覺要用 bored。",
            ),
            suggestion,
        )
    want = re.search(r"\b(want|need|needs|needed)\s+(?!to\b)([A-Za-z]+)\b", text, re.I)
    if want and want.group(2).lower() in _TEACHER_VERBS:
        quote = text[want.start():want.end()]
        helper = want.group(1)
        verb = want.group(2)
        past = bool(re.search(r"\byesterday\b|\blast night\b|\blast week\b", text, re.I))
        if helper.lower() in {"want", "need"} and past:
            replacement = f"{helper.lower()}ed to {verb}"
            why = (
                "After want or need, use to before the verb. A past time needs the past form.",
                "want 或 need 后面要加 to。说到过去要用过去式。",
                "want 或者 need 後面要加 to。講到過去要用過去式。",
            )
        else:
            replacement = f"{helper} to {verb}"
            why = (
                "After want or need, use to before the verb.",
                "want 或 need 后面要加 to 再接动词。",
                "want 或者 need 後面要加 to 先接動詞。",
            )
        suggestion = _tidy_sentence(text[:want.start()] + replacement + text[want.end():])
        return _teacher_pack(support, "grammar", quote, why, suggestion)
    if re.search(r"\byesterday\b", text, re.I) and not re.search(
        r"\b(went|ate|saw|came|bought|drank|walked|wanted|needed|was|were)\b", text, re.I
    ):
        bare = re.search(r"\b(go|eat|see|come|buy|drink|walk)\b", text, re.I)
        if bare:
            verb = bare.group(1).lower()
            quote = text[bare.start():bare.end()]
            suggestion = _tidy_sentence(text[:bare.start()] + _TEACHER_PAST[verb] + text[bare.end():])
            return _teacher_pack(
                support,
                "grammar",
                quote,
                (
                    "Yesterday needs a past verb.",
                    "yesterday 后面要用过去式动词。",
                    "yesterday 後面要用過去式動詞。",
                ),
                suggestion,
            )
    for pattern, replacement, why in _PHRASE_FIXES:
        match = pattern.search(text)
        if not match:
            continue
        quote = text[match.start():match.end()]
        suggestion = _tidy_sentence(text[:match.start()] + replacement + text[match.end():])
        return _teacher_pack(support, "phrase", quote, why, suggestion)
    return None
