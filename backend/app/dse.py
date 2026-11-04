"""HKDSE Math assistant: practice/explain chat grounded on syllabus uploads.

This is the first portal slice, not the full 3-tier Socratic product. It reuses
the RAG file store (collection ``dse_math``), strict/mixed grounding, and the
OpenRouter chat helper. Image and video APIs are never used here.
"""

from __future__ import annotations

from pathlib import Path

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
ALLOWED_MODES = frozenset({MODE_PRACTICE, MODE_EXPLAIN})
DEFAULT_MODE = MODE_PRACTICE
DEFAULT_DSE_LANGUAGE = TARGET_EN
DEFAULT_DSE_PRACTICE_MESSAGE = "Generate a HKDSE Mathematics practice question."

ALLOWED_TOPICS = {
    "number_algebra": "Number & Algebra",
    "measures_shape_space": "Measures, Shape & Space",
    "data_handling": "Data Handling",
    "calculus": "Calculus",
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

DSE_TUTOR_BASE = (
    "You are a senior HKDSE Mathematics tutor specializing in Compulsory "
    "Mathematics, Module 1 (M1): Calculus & Statistics, and Module 2 (M2): "
    "Algebra & Calculus. "
    "Show numbered step-by-step working. Mark the final answer on its own line "
    "as 'Final answer:'. "
    "When a mark scheme helps, use HKDSE M-marks (method) and A-marks (accuracy) "
    "in a Markdown table. "
    "Use precise HKDSE terminology (for example Alternate Segment Theorem, "
    "Integration by Parts, Mathematical Induction). "
    "Write mathematics in LaTeX ($ ... $ inline, $$ ... $$ display)."
)
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
NO_DSE_DOCUMENTS_MIXED = (
    "You have no uploaded syllabus or notes. You may use general HKDSE knowledge. "
    "Say when a claim is not from uploaded documents. Do not invent file contents."
)


def resolve_dse_mode(value: str | None) -> str:
    if value is None:
        return DEFAULT_MODE
    chosen = value.strip() if isinstance(value, str) else ""
    if not chosen:
        return DEFAULT_MODE
    if chosen not in ALLOWED_MODES:
        raise ChatError(400, "mode must be 'practice' or 'explain'.")
    return chosen


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


def dse_system_prompt(
    *,
    grounding: str,
    target_language: str,
    mode: str,
    topic: str | None = None,
    difficulty: str | None = None,
    paper: str | None = None,
    module: str | None = None,
    has_extracts: bool = False,
) -> str:
    parts = [DSE_TUTOR_BASE]
    if target_language == TARGET_ZH_HK:
        parts.append(TRANSLATION_TRADITIONAL)
        parts.append(
            "Write the explanation in Traditional Chinese (繁體), not 简体."
        )
    elif target_language == TARGET_ZH_CN:
        parts.append(TRANSLATION_SIMPLIFIED)
        parts.append("Write the explanation in Simplified Chinese (简体).")
    else:
        parts.append(TRANSLATION_ENGLISH)
        parts.append("Write the explanation in English.")
    parts.append(
        DSE_PRACTICE_INSTRUCTION if mode == MODE_PRACTICE else DSE_EXPLAIN_INSTRUCTION
    )
    if module:
        parts.append(f"Curriculum module: {ALLOWED_MODULES[module]}.")
    if topic:
        parts.append(f"Topic: {ALLOWED_TOPICS[topic]}.")
    if difficulty:
        parts.append(f"Difficulty: {ALLOWED_DIFFICULTIES[difficulty]}.")
    if paper:
        parts.append(f"Paper: {ALLOWED_PAPERS[paper]}.")
    if has_extracts:
        parts.append(grounding_instructions(grounding))
    else:
        parts.append(NO_DSE_DOCUMENTS_MIXED)
        parts.append(FORMAT_REPLY_INSTRUCTION)
    return "\n".join(parts)


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
        has_extracts=bool(extracts),
    )
    if not extracts:
        return (
            [
                {"role": "system", "content": system},
                {"role": "user", "content": message},
            ],
            [],
        )

    stuffed, sources = _stuff_extracts(extracts)
    system = system + "\n\nUploaded syllabus and notes:" + stuffed
    return (
        [
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ],
        sources,
    )
