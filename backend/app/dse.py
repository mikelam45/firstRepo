"""HKDSE Math assistant: practice/explain chat and three guided modes.

Reuses the RAG file store (collection ``dse_math``), strict/mixed grounding, and
the OpenRouter chat helper. Photo OCR is a separate vision chat completion
(``POST /api/dse/ocr``), not the Images API and not the FLUX image_gen path.
Guided threads and generated mark schemes live in ``$DATA_DIR/dse-sessions.json``.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .chat import ChatError
from .rag import (
    COLLECTION_DSE_MATH,
    FORMAT_REPLY_INSTRUCTION,
    GROUNDING_MIXED,
    LANGUAGE_LABELS,
    TARGET_EN,
    TARGET_ZH_CN,
    TARGET_ZH_HK,
    TRANSLATION_ENGLISH,
    TRANSLATION_SIMPLIFIED,
    TRANSLATION_TRADITIONAL,
    grounding_instructions,
    load_extracts,
    _stuff_extracts,
)

MODE_PRACTICE = "practice"
MODE_EXPLAIN = "explain"
MODE_GUIDED_NO_ANSWER = "guided_no_answer"
MODE_GUIDED_WITH_ANSWER = "guided_with_answer"
MODE_CREATE_AND_MARK = "create_and_mark"
ALLOWED_MODES = frozenset(
    {
        MODE_PRACTICE,
        MODE_EXPLAIN,
        MODE_GUIDED_NO_ANSWER,
        MODE_GUIDED_WITH_ANSWER,
        MODE_CREATE_AND_MARK,
    }
)
GUIDED_MODES = frozenset({MODE_GUIDED_NO_ANSWER, MODE_GUIDED_WITH_ANSWER})
DEFAULT_MODE = MODE_PRACTICE
DEFAULT_DSE_LANGUAGE = TARGET_EN
DEFAULT_DSE_PRACTICE_MESSAGE = "Generate a HKDSE Mathematics practice question."
NEXT_HINT_USER_MESSAGE = (
    "Give the next hint or the next working step only. "
    "Ask what I have already tried. Do not reveal the final answer."
)
SHOW_ANSWER_USER_MESSAGE = (
    "Show the full working and the final answer for this question."
)
CREATE_QUESTION_USER_MESSAGE = (
    "Generate one original mathematics question at the requested level and topic."
)
SESSIONS_NAME = "dse-sessions.json"
MARK_FAIL_NEXT_OPTIONS = ["hints", "retry"]
HIDDEN_SESSION_FIELDS = (
    "expected_answer",
    "official_answer",
    "answer",
    "mark_scheme",
    "outline",
)
ALLOWED_VERDICTS = frozenset({"correct", "partial", "wrong"})

ALLOWED_LEVELS = ("S1", "S2", "S3", "S4", "S5", "S6")
CALCULUS_LEVELS = frozenset({"S5", "S6"})

ALLOWED_TOPICS = {
    "number_algebra": "Number & Algebra",
    "measures_shape_space": "Measures, Shape & Space",
    "data_handling": "Data Handling",
    "calculus": "Calculus",
    "numbers": "Numbers",
    "algebra": "Algebra",
    "geometry": "Geometry",
    "mensuration": "Mensuration",
    "data": "Data",
    "trig": "Trigonometry",
    "functions": "Functions",
}
ALLOWED_DIFFICULTIES = {
    "easy": "easy",
    "mid": "mid",
    "hard": "hard",
    "dse_1": "DSE 1",
    "dse_2": "DSE 2",
    "dse_3": "DSE 3",
    "dse_4": "DSE 4",
    "dse_5star": "DSE 5*",
}
ALLOWED_PAPERS = {
    "paper_1": "Paper 1",
    "paper_2": "Paper 2",
}
ALLOWED_MODULES = {
    "compulsory": "Compulsory Mathematics",
    "m1": "Module 1 (M1): Calculus & Statistics",
    "m2": "Module 2 (M2): Algebra & Calculus",
}

NO_DSE_DOCUMENTS_STRICT_REPLY = (
    "There are no uploaded syllabus or notes to ground on. "
    "I cannot answer from document extracts."
)

DSE_TUTOR_IDENTITY = (
    "You are a senior HKDSE Mathematics tutor specializing in Compulsory "
    "Mathematics, Module 1 (M1): Calculus & Statistics, and Module 2 (M2): "
    "Algebra & Calculus. "
    "Use precise HKDSE terminology (for example Alternate Segment Theorem, "
    "Integration by Parts, Mathematical Induction). "
    "Write mathematics in LaTeX ($ ... $ inline, $$ ... $$ display)."
)
DSE_WORKING_AND_FINAL = (
    "Show numbered step-by-step working. Mark the final answer on its own line "
    "as 'Final answer:'. "
    "When a mark scheme helps, use HKDSE M-marks (method) and A-marks (accuracy) "
    "in a Markdown table. "
)
DSE_TUTOR_BASE = DSE_TUTOR_IDENTITY + " " + DSE_WORKING_AND_FINAL
DSE_PRACTICE_INSTRUCTION = (
    "Mode is Practice. If the student pastes a question, solve or grade it. "
    "If they ask to generate a question, write one HKDSE-style question that "
    "matches the selected module, topic, difficulty, and paper, then give the "
    "worked solution. Always show steps before the final answer."
)
DSE_EXPLAIN_INSTRUCTION = (
    "Mode is Explain. Teach the concept step by step, grounded on uploaded "
    "syllabus and notes when they are present. Cite those files. Show working; "
    "mark the final answer when you reach one."
)
DSE_GUIDED_NO_ANSWER_INSTRUCTION = (
    "Mode is Guided solve (no final answer yet). "
    "You are a Socratic HKDSE tutor. "
    "Give exactly ONE hint or ONE next step in each reply. "
    "Never state the boxed final answer, the numeric result, or the closed-form "
    "symbolic answer until the user explicitly asks for the answer or the mode "
    "switches to guided_with_answer. "
    "Do not write 'Final answer:'. Do not put the complete solution in the first "
    "replies. Ask what the student has already tried. "
    "If they share working, comment on that step only."
)
DSE_GUIDED_WITH_ANSWER_INSTRUCTION = (
    "Mode is Guided solve with answer. "
    "Give numbered step-by-step working and include the final answer immediately, "
    "marked clearly on its own line as 'Final answer: …', plus full working. "
    "When a mark scheme helps, use HKDSE M-marks (method) and A-marks (accuracy) "
    "in a Markdown table."
)
DSE_CREATE_QUESTION_INSTRUCTION = (
    "Mode is Generate + mark attempt. "
    "Generate exactly ONE original mathematics question at the requested Hong Kong "
    "secondary level and topic. Junior secondary (S1–S3) stays at that level; "
    "S4–S6 may be HKDSE style. Calculus is only for S5–S6. "
    "Do not include the answer, working, or hints in the question text. "
    "Reply with JSON only, no markdown fences, with keys: "
    "question, expected_answer, mark_scheme, outline."
)
DSE_MARK_INSTRUCTION = (
    "You are an HKDSE marker. Compare the student's attempt to the hidden mark "
    "scheme. Reply with JSON only, no markdown fences, with keys: "
    "verdict (correct, partial, or wrong) and reason (one or two short sentences). "
    "Do not restate the official answer or dump the full solution when the attempt "
    "is not fully correct."
)
NO_DSE_DOCUMENTS_MIXED = (
    "You have no uploaded syllabus or notes. You may use general HKDSE knowledge. "
    "Say when a claim is not from uploaded documents. Do not invent file contents."
)

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def resolve_dse_mode(value: str | None) -> str:
    if value is None:
        return DEFAULT_MODE
    chosen = value.strip() if isinstance(value, str) else ""
    if not chosen:
        return DEFAULT_MODE
    if chosen not in ALLOWED_MODES:
        options = ", ".join(sorted(ALLOWED_MODES))
        raise ChatError(400, f"mode must be one of: {options}.")
    return chosen


def resolve_request_mode(mode: str | None, dse_mode: str | None) -> str:
    chosen = dse_mode if isinstance(dse_mode, str) and dse_mode.strip() else mode
    return resolve_dse_mode(chosen)


def resolve_dse_level(value: str | None) -> str | None:
    if value is None:
        return None
    chosen = value.strip() if isinstance(value, str) else ""
    if not chosen:
        return None
    normalized = chosen.upper()
    if normalized not in ALLOWED_LEVELS:
        raise ChatError(400, "level must be one of: S1, S2, S3, S4, S5, S6.")
    return normalized


def _optional_choice(
    value: str | None,
    allowed: dict[str, str],
    field: str,
) -> str | None:
    if value is None:
        return None
    chosen = value.strip() if isinstance(value, str) else ""
    if not chosen:
        return None
    if chosen not in allowed:
        options = ", ".join(sorted(allowed))
        raise ChatError(400, f"{field} must be one of: {options}.")
    return chosen


def resolve_dse_topic(value: str | None) -> str | None:
    return _optional_choice(value, ALLOWED_TOPICS, "topic")


def resolve_dse_difficulty(value: str | None) -> str | None:
    return _optional_choice(value, ALLOWED_DIFFICULTIES, "difficulty")


def resolve_dse_paper(value: str | None) -> str | None:
    return _optional_choice(value, ALLOWED_PAPERS, "paper")


def resolve_dse_module(value: str | None) -> str | None:
    return _optional_choice(value, ALLOWED_MODULES, "module")


def resolve_dse_language(value: str | None) -> str:
    if value is None:
        return DEFAULT_DSE_LANGUAGE
    chosen = value.strip() if isinstance(value, str) else ""
    if not chosen:
        return DEFAULT_DSE_LANGUAGE
    if chosen not in LANGUAGE_LABELS:
        raise ChatError(
            400,
            "target_language must be 'en', 'zh_cn', or 'zh_hk'.",
        )
    return chosen


def validate_level_topic(level: str | None, topic: str | None) -> None:
    if topic == "calculus" and level and level not in CALCULUS_LEVELS:
        raise ChatError(400, "topic 'calculus' is only available for S5 and S6.")


def _language_instructions(target_language: str) -> list[str]:
    if target_language == TARGET_ZH_HK:
        return [
            TRANSLATION_TRADITIONAL,
            "Write the explanation in Traditional Chinese (繁體), not 简体.",
        ]
    if target_language == TARGET_ZH_CN:
        return [
            TRANSLATION_SIMPLIFIED,
            "Write the explanation in Simplified Chinese (简体).",
        ]
    return [TRANSLATION_ENGLISH, "Write the explanation in English."]


def _mode_instruction(mode: str) -> str:
    if mode == MODE_GUIDED_NO_ANSWER:
        return DSE_GUIDED_NO_ANSWER_INSTRUCTION
    if mode == MODE_GUIDED_WITH_ANSWER:
        return DSE_GUIDED_WITH_ANSWER_INSTRUCTION
    if mode == MODE_CREATE_AND_MARK:
        return DSE_CREATE_QUESTION_INSTRUCTION
    if mode == MODE_PRACTICE:
        return DSE_PRACTICE_INSTRUCTION
    return DSE_EXPLAIN_INSTRUCTION


def dse_system_prompt(
    *,
    grounding: str,
    target_language: str,
    mode: str,
    topic: str | None = None,
    difficulty: str | None = None,
    paper: str | None = None,
    module: str | None = None,
    level: str | None = None,
    question: str | None = None,
    has_extracts: bool = False,
    reveal_mark_scheme: str | None = None,
) -> str:
    if mode == MODE_GUIDED_NO_ANSWER:
        parts = [DSE_TUTOR_IDENTITY]
    else:
        parts = [DSE_TUTOR_BASE]
    parts.extend(_language_instructions(target_language))
    parts.append(_mode_instruction(mode))
    if level:
        parts.append(f"School level: {level} (Hong Kong secondary).")
    if module:
        parts.append(f"Curriculum module: {ALLOWED_MODULES[module]}.")
    if topic:
        parts.append(f"Topic: {ALLOWED_TOPICS[topic]}.")
    if difficulty:
        parts.append(f"Difficulty: {ALLOWED_DIFFICULTIES[difficulty]}.")
    if paper:
        parts.append(f"Paper: {ALLOWED_PAPERS[paper]}.")
    if question:
        parts.append("The student's question is:\n" + question)
    if reveal_mark_scheme and mode == MODE_GUIDED_WITH_ANSWER:
        parts.append(
            "Hidden mark scheme (you may use this; present a full solution):\n"
            + reveal_mark_scheme
        )
    if has_extracts:
        parts.append(grounding_instructions(grounding))
    else:
        parts.append(NO_DSE_DOCUMENTS_MIXED)
        parts.append(FORMAT_REPLY_INSTRUCTION)
    return "\n".join(parts)


def _history_messages(
    history: list[dict[str, str]] | None,
    message: str,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if history:
        for item in history:
            role = item.get("role")
            content = item.get("content")
            if role in {"user", "assistant"} and isinstance(content, str) and content:
                messages.append({"role": role, "content": content})
        if messages and messages[-1]["role"] == "user" and messages[-1]["content"] == message:
            return messages
    messages.append({"role": "user", "content": message})
    return messages


def build_dse_context(
    data_dir: Path,
    message: str,
    *,
    grounding: str = GROUNDING_MIXED,
    target_language: str = DEFAULT_DSE_LANGUAGE,
    mode: str = DEFAULT_MODE,
    topic: str | None = None,
    difficulty: str | None = None,
    paper: str | None = None,
    module: str | None = None,
    level: str | None = None,
    history: list[dict[str, str]] | None = None,
    question: str | None = None,
    reveal_mark_scheme: str | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    extracts = load_extracts(data_dir, collection=COLLECTION_DSE_MATH)
    system = dse_system_prompt(
        grounding=grounding,
        target_language=target_language,
        mode=mode,
        topic=topic,
        difficulty=difficulty,
        paper=paper,
        module=module,
        level=level,
        question=question,
        has_extracts=bool(extracts),
        reveal_mark_scheme=reveal_mark_scheme,
    )
    sources: list[dict[str, str]] = []
    if extracts:
        stuffed, sources = _stuff_extracts(extracts)
        system = system + "\n\nUploaded syllabus and notes:" + stuffed
    messages = [{"role": "system", "content": system}]
    messages.extend(_history_messages(history, message))
    return messages, sources


def sessions_path(data_dir: Path) -> Path:
    return Path(data_dir) / SESSIONS_NAME


def load_sessions(data_dir: Path) -> dict[str, dict[str, Any]]:
    path = sessions_path(data_dir)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = raw.get("sessions") if isinstance(raw, dict) else None
    if isinstance(rows, dict):
        return {
            key: value
            for key, value in rows.items()
            if isinstance(key, str) and isinstance(value, dict)
        }
    if isinstance(rows, list):
        packed: dict[str, dict[str, Any]] = {}
        for row in rows:
            if isinstance(row, dict) and isinstance(row.get("id"), str):
                packed[row["id"]] = row
        return packed
    return {}


def save_sessions(data_dir: Path, sessions: dict[str, dict[str, Any]]) -> None:
    path = sessions_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"sessions": sessions}
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def get_session(data_dir: Path, session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return None
    chosen = session_id.strip()
    if not chosen:
        return None
    return load_sessions(data_dir).get(chosen)


def require_session(data_dir: Path, session_id: str | None) -> dict[str, Any]:
    session = get_session(data_dir, session_id)
    if session is None:
        raise ChatError(400, "Unknown session_id.")
    return session


def upsert_session(data_dir: Path, session: dict[str, Any]) -> dict[str, Any]:
    sessions = load_sessions(data_dir)
    session["updated_at"] = _now()
    sessions[str(session["id"])] = session
    save_sessions(data_dir, sessions)
    return session


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_session_id() -> str:
    return uuid.uuid4().hex


def extract_json_object(text: str) -> dict[str, Any] | None:
    cleaned = _JSON_FENCE.sub("", (text or "").strip()).strip()
    candidates = [cleaned]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        candidates.append(cleaned[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def parse_generated_question(text: str) -> dict[str, str]:
    parsed = extract_json_object(text) or {}
    question = str(parsed.get("question") or "").strip()
    if not question:
        question = (text or "").strip()
    expected = str(
        parsed.get("expected_answer") or parsed.get("official_answer") or parsed.get("answer") or ""
    ).strip()
    return {
        "question": question,
        "expected_answer": expected,
        "mark_scheme": str(parsed.get("mark_scheme") or "").strip(),
        "outline": str(parsed.get("outline") or "").strip(),
    }


def parse_mark_verdict(text: str) -> tuple[str, str]:
    parsed = extract_json_object(text) or {}
    verdict = str(parsed.get("verdict") or "").strip().lower()
    if verdict not in ALLOWED_VERDICTS:
        lowered = (text or "").lower()
        if "partial" in lowered:
            verdict = "partial"
        elif "incorrect" in lowered or "wrong" in lowered:
            verdict = "wrong"
        elif "correct" in lowered:
            verdict = "correct"
        else:
            verdict = "wrong"
    reason = str(parsed.get("reason") or "").strip()
    if not reason:
        reason = "The attempt does not match the mark scheme."
    return verdict, reason


def store_created_question(
    data_dir: Path,
    *,
    parsed: dict[str, str],
    level: str | None,
    topic: str | None,
    language: str,
    module: str | None = None,
) -> dict[str, Any]:
    session_id = new_session_id()
    session = {
        "id": session_id,
        "question_id": new_session_id(),
        "mode": MODE_CREATE_AND_MARK,
        "level": level,
        "topic": topic,
        "module": module,
        "language": language,
        "question": parsed["question"],
        "expected_answer": parsed.get("expected_answer") or "",
        "mark_scheme": parsed.get("mark_scheme") or "",
        "outline": parsed.get("outline") or "",
        "messages": [],
        "step_count": 0,
        "created_at": _now(),
    }
    return upsert_session(data_dir, session)


def record_guided_turn(
    data_dir: Path,
    *,
    session: dict[str, Any] | None,
    mode: str,
    user_message: str,
    assistant_reply: str,
    question: str | None = None,
    level: str | None = None,
    topic: str | None = None,
    language: str = DEFAULT_DSE_LANGUAGE,
) -> dict[str, Any]:
    if session is None:
        stored_question = question or user_message
        session = {
            "id": new_session_id(),
            "question_id": new_session_id(),
            "mode": mode,
            "level": level,
            "topic": topic,
            "language": language,
            "question": stored_question,
            "expected_answer": "",
            "mark_scheme": "",
            "outline": "",
            "messages": [],
            "step_count": 0,
            "created_at": _now(),
        }
    else:
        session = dict(session)
        session["mode"] = mode
        if question:
            session["question"] = question
        if level:
            session["level"] = level
        if topic:
            session["topic"] = topic
        session["language"] = language
    messages = list(session.get("messages") or [])
    messages.append({"role": "user", "content": user_message})
    messages.append({"role": "assistant", "content": assistant_reply})
    session["messages"] = messages
    session["step_count"] = int(session.get("step_count") or 0) + 1
    return upsert_session(data_dir, session)


def public_question_payload(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": session["id"],
        "question_id": session.get("question_id") or session["id"],
        "question": session.get("question") or "",
        "level": session.get("level"),
        "topic": session.get("topic"),
        "mode": session.get("mode") or MODE_CREATE_AND_MARK,
    }


def public_mark_payload(
    session: dict[str, Any],
    *,
    verdict: str,
    reason: str,
) -> dict[str, Any]:
    correct = verdict == "correct"
    payload: dict[str, Any] = {
        "correct": correct,
        "verdict": verdict,
        "reason": reason,
        "session_id": session["id"],
        "question_id": session.get("question_id") or session["id"],
    }
    if correct:
        payload["expected_answer"] = session.get("expected_answer") or ""
    else:
        payload["next_options"] = list(MARK_FAIL_NEXT_OPTIONS)
    return scrub_hidden_fields(payload, include_answer=correct)


def scrub_hidden_fields(
    payload: dict[str, Any],
    *,
    include_answer: bool = False,
) -> dict[str, Any]:
    cleaned = dict(payload)
    for key in HIDDEN_SESSION_FIELDS:
        if include_answer and key == "expected_answer":
            continue
        cleaned.pop(key, None)
    return cleaned


def build_mark_context(
    data_dir: Path,
    session: dict[str, Any],
    attempt_text: str,
    *,
    grounding: str = GROUNDING_MIXED,
    target_language: str = DEFAULT_DSE_LANGUAGE,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    extracts = load_extracts(data_dir, collection=COLLECTION_DSE_MATH)
    parts = [DSE_TUTOR_IDENTITY, DSE_MARK_INSTRUCTION]
    parts.extend(_language_instructions(target_language))
    if session.get("level"):
        parts.append(f"School level: {session['level']} (Hong Kong secondary).")
    if session.get("topic") and session["topic"] in ALLOWED_TOPICS:
        parts.append(f"Topic: {ALLOWED_TOPICS[session['topic']]}.")
    parts.append("Question:\n" + str(session.get("question") or ""))
    mark_scheme = str(session.get("mark_scheme") or "").strip()
    expected = str(session.get("expected_answer") or "").strip()
    outline = str(session.get("outline") or "").strip()
    hidden_bits = []
    if mark_scheme:
        hidden_bits.append("Mark scheme:\n" + mark_scheme)
    if outline:
        hidden_bits.append("Outline:\n" + outline)
    if expected:
        hidden_bits.append("Expected answer:\n" + expected)
    if hidden_bits:
        parts.append(
            "Hidden mark scheme (never repeat these fields in the JSON reason):\n"
            + "\n".join(hidden_bits)
        )
    sources: list[dict[str, str]] = []
    if extracts:
        stuffed, sources = _stuff_extracts(extracts)
        parts.append(grounding_instructions(grounding))
        parts.append("Uploaded syllabus and notes:" + stuffed)
    else:
        parts.append(NO_DSE_DOCUMENTS_MIXED)
    system = "\n".join(parts)
    user = "Student attempt:\n" + attempt_text.strip()
    return (
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        sources,
    )


def is_next_hint_message(message: str) -> bool:
    cleaned = message.strip().lower()
    return cleaned in {"", "next hint", "hint", "next step"}
