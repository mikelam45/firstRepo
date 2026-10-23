"""Assemble a daily turn, validate the contract, and call OpenRouter or a fixture."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import httpx

from app.fixtures import DAILY_DENY, build_fixture
from app.models import ROUTES, route_for_turn
from app.partners import get_partner
from app.phonetics.pipeline import annotate
from app.scenarios import get_scenario, signal_ids
from app.session import (
    CORRECTION_PRIORITY,
    LEVEL_BUDGETS,
    goal_met,
    turns_remaining,
    turns_remaining_including_this,
    union_signals,
)
from app.visemes import MOODS

logger = logging.getLogger("lingocoach.turn")

LANGS = {"en", "cmn", "yue"}
LEVELS = {"beginner", "intermediate", "advanced"}
CORRECTION_TYPES = {"register", "vocabulary", "grammar", "completeness", "mismatch"}


class ServiceError(Exception):
    def __init__(self, status: int, error: str, message: str = "", retry_after: int | None = None):
        super().__init__(error)
        self.status = status
        self.error = error
        self.message = message
        self.retry_after = retry_after


class CoachUnavailable(ServiceError):
    def __init__(self) -> None:
        super().__init__(502, "coach_unavailable")


class FixtureProvider:
    name = "fixture"

    def complete(self, messages: list[dict], model: str, fallback: str) -> str:
        raise RuntimeError("fixture provider does not call a model")


class OpenRouterProvider:
    name = "openrouter"

    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self.api_key = api_key
        self._client = client

    def complete(self, messages: list[dict], model: str, fallback: str) -> str:
        status, text = self._post(messages, model, json_mode=True)
        if status == 400:
            status, text = self._post(messages, model, json_mode=False)
        if status == 429 or (status is not None and status >= 500):
            logger.info("turn fallback model=%s status=%s", fallback, status)
            status, text = self._post(messages, fallback, json_mode=True)
            if status == 400:
                status, text = self._post(messages, fallback, json_mode=False)
        if status != 200 or not text:
            logger.info("turn provider_failed status=%s model=%s", status, model)
            raise CoachUnavailable()
        return text

    def _post(self, messages: list[dict], model: str, json_mode: bool) -> tuple[int | None, str]:
        body: dict[str, Any] = {
            "model": model,
            "temperature": 0.4,
            "messages": messages,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": "LingoCoach",
        }
        client = self._client or httpx.Client(timeout=20.0)
        close = self._client is None
        try:
            response = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=body,
            )
        except httpx.HTTPError:
            logger.info("turn provider_network model=%s", model)
            return 599, ""
        finally:
            if close:
                client.close()
        text = ""
        try:
            payload = response.json()
            text = payload["choices"][0]["message"]["content"] or ""
        except Exception:
            text = ""
        logger.info("turn provider_status=%s model=%s", response.status_code, model)
        return response.status_code, text


def resolve_provider():
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        return FixtureProvider()
    return OpenRouterProvider(key)


def handle_turn(payload: dict, provider=None) -> dict:
    scenario = get_scenario(payload["scenario_id"])
    partner = get_partner(payload.get("partner_id") or payload["settings"].get("partner"))
    provider = provider or resolve_provider()
    route = route_for_turn(payload["settings"]["target"], payload["settings"]["support"])
    model = ROUTES[route]["model"]
    fallback = ROUTES[route]["fallback"]
    if provider.name == "fixture":
        raw = build_fixture(payload, scenario)
        logger.info("turn session_id=%s provider=fixture route=%s", payload.get("session_id"), route)
    else:
        raw = _live_raw(payload, scenario, partner, provider, model, fallback)
        logger.info(
            "turn session_id=%s provider=openrouter route=%s model=%s",
            payload.get("session_id"),
            route,
            model,
        )
    result = normalize_turn(raw, payload, scenario)
    result["meta"] = {
        "provider": "fixture" if provider.name == "fixture" else "openrouter",
        "route": route,
        "model": None if provider.name == "fixture" else model,
    }
    result["partner_id"] = partner["id"]
    return result


def _live_raw(payload, scenario, partner, provider, model, fallback) -> dict:
    messages = build_messages(payload, scenario, partner)
    text = provider.complete(messages, model, fallback)
    raw = parse_json(text)
    if raw is None:
        messages = messages + [
            {"role": "assistant", "content": text},
            {"role": "user", "content": "Your previous reply was not JSON. Return only the object."},
        ]
        text = provider.complete(messages, model, fallback)
        raw = parse_json(text)
        if raw is None:
            raise CoachUnavailable()
    return raw


def build_messages(payload: dict, scenario: dict, partner: dict) -> list[dict]:
    settings = payload["settings"]
    including = turns_remaining_including_this(settings["level"], payload["history"])
    system = "\n".join(
        [
            "You are LingoCoach, running a spoken-language practice scene.",
            "You play the character described in SCENARIO. You speak only TARGET_LANG",
            "in character.text. You explain only in SUPPORT_LANG, in the coaching fields.",
            "",
            "Orthography and politeness follow the scenario cultural notes.",
            "Level behaviour: beginner lines stay short; intermediate is natural service length;",
            "advanced can include asides. Beginner: at most 1 correction. Otherwise at most 2.",
            "",
            f"Turns remaining including this reply: {including}.",
            "If this number is 1, move to a natural closing line. If the learner has",
            'already hit every success signal, set goal.status to "met" and close in',
            "character.",
            "",
            "Return a single JSON object matching the schema. No markdown fence.",
            "Do not include phonetic transcriptions; the server adds them.",
            "Do not claim the learner’s pronunciation was good or bad. You cannot hear them.",
            "If their wording already works, return an empty corrections array and",
            "suggested_reply null.",
            "",
            f"The learner is talking to {partner['name']}, 27, from {partner['city']}.",
            f"Speak the target language in character. Manner: {partner['manner']}.",
            "",
            "LANGUAGE_RULES:",
            _language_rules(settings["target"]),
            "",
            "CULTURAL_NOTES:",
            "\n".join(f"- {note}" for note in scenario["cultural_notes"]),
            "",
            "OPENING_HINT:",
            scenario["opening_hint"][settings["level"]],
        ]
    )
    user = {
        "scenario": {
            "id": scenario["id"],
            "locale": scenario["locale"],
            "goal": scenario["goal"]["en"],
            "signals": scenario["success_signals"],
        },
        "settings": {
            "target": settings["target"],
            "support": settings["support"],
            "level": settings["level"],
            "script": settings["script"],
            "accent": settings["accent"],
        },
        "history": [{"role": item["role"], "text": item["text"]} for item in payload["history"][-12:]],
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]


def _language_rules(target: str) -> str:
    if target == "yue":
        return (
            "Colloquial written Cantonese in Traditional characters. "
            "Requests use 唔該. Do not answer in Mandarin. Particles stay."
        )
    if target == "cmn":
        return "Mainland service Mandarin. 您好, 请问, 麻烦您. 儿化 only where natural (这儿, 一点儿)."
    return "British spelling in London scenes. Could you / Excuse me. Do not switch into American slang."


def parse_json(text: str | None) -> dict | None:
    if not text:
        return None
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.S)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    return value


def normalize_turn(raw: dict, payload: dict, scenario: dict) -> dict:
    if raw.get("contract") != "1":
        raise CoachUnavailable()
    character = raw.get("character")
    if not isinstance(character, dict) or "text" not in character or "translation" not in character:
        raise CoachUnavailable()
    text = str(character.get("text") or "").strip()
    if not text:
        raise CoachUnavailable()
    text = text[:280]
    settings = payload["settings"]
    opening = len(payload["history"]) == 0
    safety = raw.get("safety") if isinstance(raw.get("safety"), dict) else {}
    refused = bool(safety.get("refused"))
    translation = character.get("translation")
    if settings["support"] == settings["target"]:
        translation = None
    elif translation is not None:
        translation = str(translation)[:400]
    coaching = None if opening or refused else _coaching(raw.get("coaching"), payload)
    _scan_denied(text, translation, coaching)
    text = _script(text, settings["script"])
    if isinstance(translation, str):
        translation = _script(translation, settings["script"])
    if coaching:
        coaching = _script_coaching(coaching, settings["script"])
    allowed = signal_ids(scenario)
    model_fired = []
    goal = raw.get("goal") if isinstance(raw.get("goal"), dict) else {}
    if isinstance(goal.get("fired"), list):
        model_fired = [item for item in goal["fired"] if isinstance(item, str)]
    fired = union_signals(payload.get("fired_signals") or [], model_fired, allowed)
    status = "met" if goal_met(fired, allowed) else "open"
    annotated = annotate(
        text,
        settings["target"],
        settings.get("accent", "en-GB"),
        settings.get("pinyin_tone", "mark"),
        scenario.get("jyutping_overrides") or None,
        scenario.get("pinyin_phrases") or None,
    )
    if coaching and coaching.get("suggested_reply"):
        suggestion_phone = annotate(
            coaching["suggested_reply"],
            settings["target"],
            settings.get("accent", "en-GB"),
            settings.get("pinyin_tone", "mark"),
            scenario.get("jyutping_overrides") or None,
            scenario.get("pinyin_phrases") or None,
        )
        coaching["suggested_reply_phonetic"] = suggestion_phone["phonetic"]
        coaching["suggested_reply_phonetic_complete"] = suggestion_phone["phonetic_complete"]
        coaching["suggested_reply_visemes"] = suggestion_phone["visemes"]
        coaching["suggested_reply_syllables"] = suggestion_phone["syllables"]
    elif coaching is not None:
        coaching["suggested_reply_phonetic"] = None
    mood = _mood(text, opening, status)
    return {
        "contract": "1",
        "character": {
            "text": text,
            "translation": translation,
            "phonetic": annotated["phonetic"],
            "phonetic_complete": annotated["phonetic_complete"],
            "phonetic_system": annotated["phonetic_system"],
            "syllables": annotated["syllables"],
            "visemes": annotated["visemes"],
            "mood": mood,
        },
        "coaching": coaching,
        "goal": {"status": status, "fired": fired},
        "safety": {"refused": refused},
        "session": {
            "fired_signals": fired,
            "turns_remaining": turns_remaining(settings["level"], payload["history"]),
            "turns_remaining_including_this": turns_remaining_including_this(
                settings["level"], payload["history"]
            ),
            "goal_status": status,
            "cap_reached": (not opening)
            and turns_remaining_including_this(settings["level"], payload["history"]) <= 1,
        },
        "moods": {"active": MOODS[mood]},
    }


def _coaching(raw: Any, payload: dict) -> dict | None:
    if raw is None:
        return {
            "praise": None,
            "corrections": [],
            "suggested_reply": None,
            "reading_hints": [],
        }
    if not isinstance(raw, dict):
        raise CoachUnavailable()
    learner = ""
    for item in reversed(payload["history"]):
        if item.get("role") == "learner":
            learner = str(item.get("text") or "")
            break
    praise = raw.get("praise")
    if praise is not None:
        praise = str(praise)[:160]
    budget = LEVEL_BUDGETS[payload["settings"]["level"]]
    corrections = []
    seen_types = set()
    incoming = raw.get("corrections") if isinstance(raw.get("corrections"), list) else []
    incoming = sorted(
        incoming,
        key=lambda item: CORRECTION_PRIORITY.index(item.get("type"))
        if isinstance(item, dict) and item.get("type") in CORRECTION_PRIORITY
        else 99,
    )
    for item in incoming:
        if not isinstance(item, dict):
            continue
        ctype = item.get("type")
        quote = item.get("quote")
        why = item.get("why")
        if ctype not in CORRECTION_TYPES or ctype in seen_types:
            continue
        if not isinstance(quote, str) or not quote or quote not in learner:
            continue
        if not isinstance(why, str) or not why.strip():
            continue
        seen_types.add(ctype)
        corrections.append({"type": ctype, "quote": quote, "why": why[:240]})
        if len(corrections) >= budget:
            break
    suggestion = raw.get("suggested_reply")
    if suggestion is not None:
        suggestion = str(suggestion).strip()
        if not suggestion or _same_line(suggestion, learner):
            suggestion = None
    hints = []
    for item in raw.get("reading_hints") or []:
        if not isinstance(item, dict):
            continue
        term = item.get("term")
        note = item.get("note")
        if not isinstance(term, str) or not term:
            continue
        if not isinstance(note, str) or not note.strip():
            continue
        blob = learner + "\n" + (suggestion or "")
        if term not in blob:
            continue
        hints.append({"term": term, "note": note[:240]})
        if len(hints) >= 2:
            break
    return {
        "praise": praise,
        "corrections": corrections,
        "suggested_reply": suggestion,
        "reading_hints": hints,
    }


def _same_line(suggestion: str, learner: str) -> bool:
    def norm(value: str) -> str:
        return re.sub(r"[^\w\u3400-\u9fff]+", "", value or "", flags=re.U).lower()

    return norm(suggestion) == norm(learner)


def _scan_denied(text: str, translation: str | None, coaching: dict | None) -> None:
    chunks = [text or "", translation or ""]
    if coaching:
        chunks.append(coaching.get("praise") or "")
        for item in coaching.get("corrections") or []:
            chunks.append(item.get("why") or "")
        for item in coaching.get("reading_hints") or []:
            chunks.append(item.get("note") or "")
    blob = "\n".join(chunks).lower()
    for phrase in DAILY_DENY:
        if phrase.lower() in blob:
            raise CoachUnavailable()


def _script(text: str, script: str) -> str:
    import zhconv

    if script == "Hans":
        return zhconv.convert(text, "zh-hans")
    return zhconv.convert(text, "zh-hant")


def _script_coaching(coaching: dict, script: str) -> dict:
    if coaching.get("praise"):
        coaching["praise"] = _script(coaching["praise"], script)
    if coaching.get("suggested_reply"):
        coaching["suggested_reply"] = _script(coaching["suggested_reply"], script)
    for item in coaching.get("corrections") or []:
        item["why"] = _script(item["why"], script)
    for item in coaching.get("reading_hints") or []:
        item["note"] = _script(item["note"], script)
    return coaching


def _mood(text: str, opening: bool, status: str) -> str:
    if text.rstrip().endswith(("?", "？")):
        return "question"
    if opening or status == "met":
        return "happy"
    return "happy"


def validate_request(body: Any) -> dict:
    if not isinstance(body, dict):
        raise ServiceError(400, "invalid_request", "Body must be a JSON object.")
    session_id = body.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 80:
        raise ServiceError(400, "invalid_request", "session_id is required.")
    scenario_id = body.get("scenario_id")
    try:
        get_scenario(scenario_id)
    except (KeyError, TypeError):
        raise ServiceError(400, "invalid_request", "Unknown scenario_id.")
    settings = body.get("settings")
    if not isinstance(settings, dict):
        raise ServiceError(400, "invalid_request", "settings are required.")
    if settings.get("target") not in LANGS or settings.get("support") not in LANGS:
        raise ServiceError(400, "invalid_request", "target and support must be en, cmn, or yue.")
    if settings.get("level") not in LEVELS:
        raise ServiceError(400, "invalid_request", "level is invalid.")
    if settings.get("script") not in {"Hant", "Hans"}:
        raise ServiceError(400, "invalid_request", "script must be Hant or Hans.")
    if settings.get("accent") not in {"en-GB", "en-US"}:
        raise ServiceError(400, "invalid_request", "accent must be en-GB or en-US.")
    settings = dict(settings)
    if settings.get("pinyin_tone") not in {None, "mark", "number"}:
        raise ServiceError(400, "invalid_request", "pinyin_tone must be mark or number.")
    settings["pinyin_tone"] = settings.get("pinyin_tone") or "mark"
    partner_id = body.get("partner_id") or settings.get("partner") or "amelia"
    try:
        get_partner(partner_id)
    except KeyError:
        raise ServiceError(400, "invalid_request", "Unknown partner.")
    history = body.get("history", [])
    if not isinstance(history, list) or len(history) > 12:
        raise ServiceError(400, "invalid_request", "history must be a list of at most 12 turns.")
    clean_history = []
    for item in history:
        if not isinstance(item, dict) or item.get("role") not in {"learner", "character"}:
            raise ServiceError(400, "invalid_request", "history roles must be learner or character.")
        text = item.get("text")
        if not isinstance(text, str) or len(text) > 500:
            raise ServiceError(400, "invalid_request", "Each history text must be a string of at most 500 characters.")
        clean_history.append({"role": item["role"], "text": text})
    if clean_history and clean_history[-1]["role"] != "learner":
        raise ServiceError(400, "invalid_request", "The newest history item must be the learner line.")
    fired = body.get("fired_signals") or []
    if not isinstance(fired, list) or any(not isinstance(item, str) for item in fired):
        raise ServiceError(400, "invalid_request", "fired_signals must be a list of strings.")
    return {
        "session_id": session_id.strip(),
        "scenario_id": scenario_id,
        "partner_id": partner_id,
        "settings": settings,
        "history": clean_history,
        "fired_signals": fired,
    }
