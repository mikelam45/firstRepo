"""HKDSE Math assistant: three UI options mapped onto existing tutor modes.

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
from .chat_format import clip_scenario, parse_figure_spec
from .dse_figures import (
    ensure_created_figure,
    ensure_explain_figures,
    ensure_solve_figures,
    explain_figures_for_topics,
    figure_from_question,
    session_has_figure,
)
from .dse_topics import (
    ALLOWED_LEVELS,
    EXPLAIN_STRANDS,
    MAX_EXPLAIN_TOPICS,
    TOPIC_BY_ID,
    figure_topic_key,
    levels_by_module,
    resolve_topic_id,
    topic_prompt_label,
    topics_catalog,
)
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
MAX_QUESTION_COUNT = 20
DEFAULT_QUESTION_COUNT = 1
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


def create_question_user_message(count: int = DEFAULT_QUESTION_COUNT) -> str:
    n = resolve_question_count(count)
    if n <= 1:
        return CREATE_QUESTION_USER_MESSAGE
    return f"Generate {n} original mathematics questions at the requested level and topic."
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

CALCULUS_LEVELS = frozenset({"S5", "S6"})
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
DEFAULT_EXPLAIN_MESSAGE = "Explain the selected mathematics topics."
DEFAULT_EXPLAIN_TASK_PROMPT = (
    "Explain each selected topic by 3 examples with diagrams/figures/charts "
    "and create 6 questions (2 easy, 2 mid & 2 hard) and step by step solving "
    "it until reaching the answer."
)
EXPLAIN_PROMPT_DEFAULT = "default"
EXPLAIN_PROMPT_CUSTOM = "custom"
ALLOWED_EXPLAIN_PROMPT_KINDS = frozenset({EXPLAIN_PROMPT_DEFAULT, EXPLAIN_PROMPT_CUSTOM})
EXPLAIN_TOPIC_BY_ID = TOPIC_BY_ID

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
    "Write mathematics in LaTeX so the page can typeset it like a textbook: "
    "$ ... $ or \\( ... \\) inline, $$ ... $$ or \\[ ... \\] on its own line for display. "
    "Use \\frac{a}{b} so a sits above b (never a/b as the main form, never the source markup "
    "as the student-facing answer). Use \\theta for θ, \\sin for sine, \\circ or ^\\circ for degrees."
)
DSE_WORKING_AND_FINAL = (
    "Show numbered step-by-step working. Mark the final answer on its own line "
    "as 'Final answer:'. "
    "When a mark scheme helps, use HKDSE M-marks (method) and A-marks (accuracy) "
    "in a Markdown table. "
)
DSE_TUTOR_BASE = DSE_TUTOR_IDENTITY + " " + DSE_WORKING_AND_FINAL
DSE_GIVEN_LABEL_INSTRUCTION = (
    "100% of named givens MUST appear as labels on the diagram: every vertex "
    "(for example A, B, C, D on quadrilateral ABCD) and every given angle or length "
    "(for example 80°, 90°, 50°, 6 cm). Never leave those only in prose. "
    "Match the named shape: a quadrilateral is four sides, never a triangle. "
    "Question and hint figures show given facts only. "
    "Working-step figures may add constructions (incentre, radii, touch points). "
    "The answer figure marks the found angle or length on the same diagram."
)
DSE_SOLVE_FIGURE_INSTRUCTION = (
    "You MUST include labelled ```figure blocks for the question, each working "
    "step, and the answer. "
    + DSE_GIVEN_LABEL_INSTRUCTION
    + " Draw given lengths, angles, and points. "
    "Use the figure fence contract (geometry, coordinate, number_line, or chart). "
    "Give clickable ids on corresponding parts."
)
DSE_PRACTICE_INSTRUCTION = (
    "Mode is Practice. If the student pastes a question, solve or grade it. "
    "If they ask to generate a question, write one HKDSE-style question that "
    "matches the selected module, topic, difficulty, and paper, then give the "
    "worked solution. Always show steps before the final answer. "
    + DSE_SOLVE_FIGURE_INSTRUCTION
)
DSE_FIGURE_INSTRUCTION = (
    "You MUST include at least one labelled diagram for every topic. Never reply "
    "in prose only. Invent a short teaching scenario a Hong Kong secondary student "
    "would recognise (for example MTR fares, a wet market, sports day, a shopping "
    "receipt, a pizza slice, a window, a floor plan, or a slope on a hill). "
    "For each topic emit one fenced JSON block the page can draw:\n"
    "```figure\n"
    '{"type":"geometry|coordinate|number_line|chart|bar|line","title":"...","caption":"...",'
    '"interactive":true,'
    '"elements":[{"kind":"polygon","points":[[20,80],[80,80],[50,20]],"labels":["A","B","C"],"id":"tri"},'
    '{"kind":"segment","from":[20,80],"to":[80,80],"label":"6 cm","id":"ab"}],'
    '"actions":[{"id":"sss","label":"SSS","highlight":["ab"],"caption":"..."}]}\n'
    "```\n"
    "geometry uses a 0–100 canvas, x right, y down. Also allowed: circle, arc, "
    "sector (cx, cy, r, start, end in degrees, 0 at +x, clockwise), angle, point, "
    "label. coordinate uses data units and optional "
    '"axes":{"xmin":-2,"xmax":6,"ymin":-2,"ymax":6} with y up. '
    "number_line uses min, max, marks, and points. chart, bar, and line figures "
    "draw as charts: labels + series, labels + values, or a line graph with axes "
    "and series values as [x, y] points. "
    "Give elements an id so the student can click corresponding parts. "
    "Label given lengths and angles. Do not draw the hidden answer. "
    + DSE_GIVEN_LABEL_INSTRUCTION
)
DSE_EXPLAIN_INSTRUCTION = (
    "Mode is Explain. Teach the selected school-level topics step by step, "
    "grounded on uploaded syllabus and notes when they are present. Cite those "
    "files. For each topic give: a short real-life scenario, the idea, a labelled "
    "interactive diagram in a ```figure fence (required, never skip), the method, "
    "one worked example that refers to the diagram, and common mistakes. "
    "Stay at the stated form (S1–S6); do not jump ahead unless asked. "
    "Show working; mark the final answer when you reach one. "
    + DSE_FIGURE_INSTRUCTION
)
DSE_EXPLAIN_DEFAULT_TASK_INSTRUCTION = (
    "The user chose the default Explain prompt. For EACH selected topic you MUST: "
    "(1) teach the idea with a short scenario; "
    "(2) give 3 distinct worked examples, each with its own labelled ```figure or "
    "```chart (diagrams, figures, or charts — never skip); "
    "(3) create 6 new questions on that topic: 2 easy, 2 mid, and 2 hard; "
    "(4) solve every one of those 6 questions step by step until 'Final answer:'. "
    "Do not stop after one example. Follow-up turns may answer a shorter question "
    "without repeating all 6 items."
)
DSE_EXPLAIN_CUSTOM_TASK_INSTRUCTION = (
    "The user chose a custom Explain prompt. Follow that prompt for how to teach "
    "the selected topics. Still include labelled ```figure or ```chart blocks."
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
    "If they share working, comment on that step only. "
    "Every hint or working step MUST include a labelled ```figure. "
    "On the first reply, draw the given question (vertices and given angles). "
    "Do not mark the unknown, the completed construction, or the final answer on "
    "the first figure. Later steps may add constructions on a new figure. "
    + DSE_SOLVE_FIGURE_INSTRUCTION
)
DSE_GUIDED_WITH_ANSWER_INSTRUCTION = (
    "Mode is Guided solve with answer. "
    "Give numbered step-by-step working and include the final answer immediately, "
    "marked clearly on its own line as 'Final answer: …', plus full working. "
    "When a mark scheme helps, use HKDSE M-marks (method) and A-marks (accuracy) "
    "in a Markdown table. "
    "Start with a labelled ```figure of the given question (all named vertices "
    "and given angles). In the working, add a figure for the key construction. "
    "On the answer, mark the found measure on a figure. "
    + DSE_SOLVE_FIGURE_INSTRUCTION
)
DSE_CREATE_JSON_KEYS = (
    "question, scenario, figure, expected_answer, mark_scheme, outline"
)
DSE_CREATE_FIGURE_JSON = (
    "figure is required. Never set it to null. Use the same contract as a ```figure fence: "
    '{"type":"geometry|coordinate|number_line|chart|bar|line","title":"...","caption":"...",'
    '"interactive":true,'
    '"elements":[{"kind":"polygon","points":[[20,80],[80,80],[50,20]],'
    '"labels":["A","B","C"],"id":"tri"}]}. '
    "geometry uses a 0–100 canvas, x right, y down. Also allowed: circle, arc, sector, "
    "angle, point, label. For algebra use a number_line or coordinate axes. For data "
    "use a chart. The figure must show given information only, never the answer. "
    "100% of named vertices and given angles or lengths in the question text "
    "must be labels on the figure (quadrilateral ABCD with 80° at A, not a blank sketch). "
    "Draw the named shape: quadrilateral ABCD is a four-sided polygon with vertices "
    "A, B, C, D, never a triangle. "
    "scenario is one or two sentences of teaching context, not the solution."
)
DSE_CREATE_QUESTION_INSTRUCTION = (
    "Mode is Generate + mark attempt. "
    "Generate exactly ONE original mathematics question at the requested Hong Kong "
    "secondary level and topic. Junior secondary (S1–S3) stays at that level; "
    "S4–S6 may be HKDSE style. Calculus is only for S5–S6. "
    "Wrap the item in a short teaching scenario a student can picture. "
    "Do not include the answer, working, or hints in the question text or figure. "
    "Reply with JSON only, no markdown fences, with keys: "
    + DSE_CREATE_JSON_KEYS
    + ". "
    + DSE_CREATE_FIGURE_JSON
)


def create_question_instruction(count: int = DEFAULT_QUESTION_COUNT) -> str:
    n = count if isinstance(count, int) else DEFAULT_QUESTION_COUNT
    if n <= 1:
        return DSE_CREATE_QUESTION_INSTRUCTION
    return (
        "Mode is Generate + mark attempt. "
        f"Generate exactly {n} original mathematics questions at the requested Hong Kong "
        "secondary level and topic. Junior secondary (S1–S3) stays at that level; "
        "S4–S6 may be HKDSE style. Calculus is only for S5–S6. "
        "Vary the items so they are not copies of each other. "
        "Wrap each item in a short teaching scenario a student can picture. "
        "Do not include the answer, working, or hints in the question text or figure. "
        "Reply with JSON only, no markdown fences, as "
        '{"questions":[{"question":"...","scenario":"...","figure":{},'
        '"expected_answer":"...","mark_scheme":"...","outline":"..."}]} '
        f"with exactly {n} items. "
        + DSE_CREATE_FIGURE_JSON
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


def resolve_question_count(value: object) -> int:
    if value is None or value == "":
        return DEFAULT_QUESTION_COUNT
    try:
        count = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ChatError(
            400, f"count must be an integer from 1 to {MAX_QUESTION_COUNT}."
        ) from exc
    if count < 1 or count > MAX_QUESTION_COUNT:
        raise ChatError(400, f"count must be an integer from 1 to {MAX_QUESTION_COUNT}.")
    return count


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
    return resolve_topic_id(value)


def explain_topics_catalog() -> dict[str, object]:
    return topics_catalog()


def _normalize_topic_ids(values: list[str] | str | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        parts = [part.strip() for part in values.split(",") if part.strip()]
        return parts
    items: list[str] = []
    for value in values:
        if isinstance(value, str) and value.strip():
            items.append(value.strip())
    return items


def resolve_explain_topics(values: list[str] | str | None) -> list[str]:
    items = _normalize_topic_ids(values)
    if not items:
        return []
    unknown: list[str] = []
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in EXPLAIN_TOPIC_BY_ID:
            unknown.append(item)
            continue
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    if unknown:
        sample = ", ".join(unknown[:5])
        raise ChatError(400, f"topics must be from the S1–S6 catalog; unknown: {sample}.")
    if len(out) > MAX_EXPLAIN_TOPICS:
        raise ChatError(400, f"topics must have at most {MAX_EXPLAIN_TOPICS} items.")
    return out


def explain_topic_labels(topic_ids: list[str]) -> list[str]:
    labels: list[str] = []
    for topic_id in topic_ids:
        row = EXPLAIN_TOPIC_BY_ID.get(topic_id)
        if not row:
            continue
        form = row.get("form") or ("S1–S3" if row.get("stage") == "junior" else "S4–S6")
        labels.append(f"{form} {row['label']}".strip())
    return labels


def resolve_explain_prompt_kind(value: str | None) -> str:
    chosen = (value or EXPLAIN_PROMPT_DEFAULT).strip().lower()
    if not chosen:
        return EXPLAIN_PROMPT_DEFAULT
    if chosen not in ALLOWED_EXPLAIN_PROMPT_KINDS:
        raise ChatError(400, "explain_prompt_kind must be default or custom.")
    return chosen


def explain_user_message(
    topic_ids: list[str],
    extra: str = "",
    *,
    prompt_kind: str = EXPLAIN_PROMPT_DEFAULT,
) -> str:
    labels = explain_topic_labels(topic_ids)
    head = "Explain these topics: " + "; ".join(labels) + "." if labels else ""
    extra = extra.strip()
    kind = resolve_explain_prompt_kind(prompt_kind)
    if kind == EXPLAIN_PROMPT_CUSTOM:
        task = extra or DEFAULT_EXPLAIN_MESSAGE
    else:
        task = DEFAULT_EXPLAIN_TASK_PROMPT
        if extra and extra not in {DEFAULT_EXPLAIN_TASK_PROMPT, DEFAULT_EXPLAIN_MESSAGE, head}:
            if DEFAULT_EXPLAIN_TASK_PROMPT not in extra:
                task = DEFAULT_EXPLAIN_TASK_PROMPT + "\n\n" + extra
            else:
                task = extra
    if head and head not in task:
        return f"{task}\n\n{head}" if task else head
    return task or DEFAULT_EXPLAIN_MESSAGE


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


def validate_level_topic(
    level: str | None,
    topic: str | None,
    module: str | None = None,
) -> None:
    if module and level:
        allowed = levels_by_module().get(module) or []
        if allowed and level not in allowed:
            label = ALLOWED_MODULES.get(module, module)
            raise ChatError(
                400,
                f"{label} is only offered for {' and '.join(allowed)}.",
            )
    if not topic:
        return
    row = TOPIC_BY_ID.get(topic)
    if row and level and row.get("form") and row["form"] != level:
        raise ChatError(400, f"topic belongs to {row['form']}, not {level}.")
    if row and module and row.get("module_key") and row["module_key"] != module:
        raise ChatError(
            400,
            f"topic belongs to {row.get('module_short') or row['module_key']}, not the selected module.",
        )
    figure = figure_topic_key(topic)
    if (
        (topic == "calculus" or figure == "calculus" or (row and row.get("module_key") in {"m1", "m2"}))
        and level
        and level not in CALCULUS_LEVELS
    ):
        raise ChatError(400, "Calculus and M1/M2 topics are only available for S5 and S6.")


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


def _mode_instruction(
    mode: str,
    question_count: int = DEFAULT_QUESTION_COUNT,
    explain_prompt_kind: str = EXPLAIN_PROMPT_DEFAULT,
) -> str:
    if mode == MODE_GUIDED_NO_ANSWER:
        return DSE_GUIDED_NO_ANSWER_INSTRUCTION
    if mode == MODE_GUIDED_WITH_ANSWER:
        return DSE_GUIDED_WITH_ANSWER_INSTRUCTION
    if mode == MODE_CREATE_AND_MARK:
        return create_question_instruction(question_count)
    if mode == MODE_PRACTICE:
        return DSE_PRACTICE_INSTRUCTION
    if resolve_explain_prompt_kind(explain_prompt_kind) == EXPLAIN_PROMPT_CUSTOM:
        return DSE_EXPLAIN_INSTRUCTION + " " + DSE_EXPLAIN_CUSTOM_TASK_INSTRUCTION
    return DSE_EXPLAIN_INSTRUCTION + " " + DSE_EXPLAIN_DEFAULT_TASK_INSTRUCTION


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
    topics: list[str] | None = None,
    question: str | None = None,
    has_extracts: bool = False,
    reveal_mark_scheme: str | None = None,
    question_count: int = DEFAULT_QUESTION_COUNT,
    explain_prompt_kind: str = EXPLAIN_PROMPT_DEFAULT,
) -> str:
    if mode == MODE_GUIDED_NO_ANSWER:
        parts = [DSE_TUTOR_IDENTITY]
    else:
        parts = [DSE_TUTOR_BASE]
    parts.extend(_language_instructions(target_language))
    parts.append(_mode_instruction(mode, question_count, explain_prompt_kind))
    if level:
        parts.append(f"School level: {level} (Hong Kong secondary).")
    if module:
        parts.append(f"Curriculum module: {ALLOWED_MODULES[module]}.")
    if topic:
        label = topic_prompt_label(topic) or topic
        parts.append(f"Topic: {label}.")
    if topics:
        labeled = []
        for topic_id in topics:
            row = EXPLAIN_TOPIC_BY_ID.get(topic_id)
            if not row:
                continue
            strand = EXPLAIN_STRANDS.get(row["strand"], row["strand"])
            form = row.get("form") or ""
            labeled.append(f"{form} {row['label']} ({strand})".strip())
        if labeled:
            parts.append(
                "Hong Kong secondary mathematics topics to explain: "
                + "; ".join(labeled)
                + "."
            )
            parts.append(
                "Follow the attached S1–S6 topic list and the Education Bureau "
                "Mathematics curriculum learning objectives. Pitch the explanation "
                "at the stated school year."
            )
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
    topics: list[str] | None = None,
    history: list[dict[str, str]] | None = None,
    question: str | None = None,
    reveal_mark_scheme: str | None = None,
    question_count: int = DEFAULT_QUESTION_COUNT,
    explain_prompt_kind: str = EXPLAIN_PROMPT_DEFAULT,
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
        topics=topics,
        question=question,
        has_extracts=bool(extracts),
        reveal_mark_scheme=reveal_mark_scheme,
        question_count=question_count,
        explain_prompt_kind=explain_prompt_kind,
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


def _question_from_mapping(parsed: dict[str, Any], fallback: str = "") -> dict[str, Any]:
    question = str(parsed.get("question") or "").strip()
    if not question:
        question = (fallback or "").strip()
    expected = str(
        parsed.get("expected_answer") or parsed.get("official_answer") or parsed.get("answer") or ""
    ).strip()
    figure = parse_figure_spec(parsed.get("figure"))
    return {
        "question": question,
        "scenario": clip_scenario(parsed.get("scenario")),
        "figure": figure,
        "expected_answer": expected,
        "mark_scheme": str(parsed.get("mark_scheme") or "").strip(),
        "outline": str(parsed.get("outline") or "").strip(),
    }


def student_question_text(parsed: dict[str, Any]) -> str:
    parts: list[str] = []
    scenario = clip_scenario(parsed.get("scenario"))
    if scenario:
        parts.append("**Scenario.** " + scenario)
    figure = parsed.get("figure")
    spec = parse_figure_spec(figure) if figure else None
    if spec:
        parts.append("```figure\n" + json.dumps(spec, ensure_ascii=False) + "\n```")
    question = str(parsed.get("question") or "").strip()
    if question:
        parts.append(question)
    return "\n\n".join(parts)


def parse_generated_question(text: str) -> dict[str, Any]:
    parsed = extract_json_object(text) or {}
    items = parsed.get("questions")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return _question_from_mapping(items[0], text)
    return _question_from_mapping(parsed, text)


def parse_generated_questions(text: str, count: int = DEFAULT_QUESTION_COUNT) -> list[dict[str, Any]]:
    wanted = resolve_question_count(count)
    parsed = extract_json_object(text) or {}
    raw_items = parsed.get("questions")
    rows: list[dict[str, str]] = []
    if isinstance(raw_items, list):
        for item in raw_items[:wanted]:
            if isinstance(item, dict):
                row = _question_from_mapping(item)
                if row["question"]:
                    rows.append(row)
    if not rows:
        single = parse_generated_question(text)
        if single["question"]:
            rows.append(single)
    return rows[:wanted]


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
    parsed: dict[str, Any],
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
        "scenario": clip_scenario(parsed.get("scenario")),
        "figure": ensure_created_figure(
            parsed.get("figure"),
            topic=figure_topic_key(topic),
            question=parsed.get("question"),
        ),
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
    figure = parse_figure_spec(session.get("figure"))
    payload: dict[str, Any] = {
        "session_id": session["id"],
        "question_id": session.get("question_id") or session["id"],
        "question": session.get("question") or "",
        "scenario": clip_scenario(session.get("scenario")),
        "level": session.get("level"),
        "topic": session.get("topic"),
        "mode": session.get("mode") or MODE_CREATE_AND_MARK,
        "display": student_question_text(session),
    }
    if figure:
        payload["figure"] = figure
    return payload


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
        answer_figure = figure_from_question(
            session.get("question"),
            stage="answer",
            topic=session.get("topic"),
        )
        if answer_figure:
            payload["figure"] = answer_figure
            payload["figures"] = [answer_figure]
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
    if session.get("topic"):
        label = topic_prompt_label(session["topic"])
        if label:
            parts.append(f"Topic: {label}.")
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
