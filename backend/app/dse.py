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
EXPLAIN_STRANDS = {
    "number_algebra": "Number and Algebra",
    "measures_shape_space": "Measures, Shape and Space",
    "data_handling": "Data Handling",
    "further": "Further Learning Unit",
    "m1": "Module 1 (Calculus and Statistics)",
    "m2": "Module 2 (Algebra and Calculus)",
}
JUNIOR_LEVELS = ("S1", "S2", "S3")
SENIOR_LEVELS = ("S4", "S5", "S6")
MAX_EXPLAIN_TOPICS = 8
DEFAULT_EXPLAIN_MESSAGE = "Explain the selected mathematics topics."
EDB_CURRICULUM_HREF = (
    "https://www.edb.gov.hk/en/curriculum-development/kla/ma/curr/index2.html"
)
# Official EDB learning units. Junior Secondary is Key Stage 3 (S1–S3) as a whole;
# Senior Secondary Compulsory Part and Extended Part cover S4–S6.
# Source: Mathematics Education curriculum documents on edb.gov.hk.
# id, label, strand, stage ("junior" | "senior")
_EXPLAIN_TOPIC_ROWS = (
    ("ks3_01_basic_computation", "1. Basic computation", "number_algebra", "junior"),
    ("ks3_02_directed_numbers", "2. Directed numbers", "number_algebra", "junior"),
    ("ks3_03_approximate_values", "3. Approximate values and numerical estimation", "number_algebra", "junior"),
    ("ks3_04_rational_irrational", "4. Rational and irrational numbers", "number_algebra", "junior"),
    ("ks3_05_using_percentages", "5. Using percentages", "number_algebra", "junior"),
    ("ks3_06_rates_ratios", "6. Rates, ratios and proportions", "number_algebra", "junior"),
    ("ks3_07_algebraic_expressions", "7. Algebraic expressions", "number_algebra", "junior"),
    ("ks3_08_linear_eq_one", "8. Linear equations in one unknown", "number_algebra", "junior"),
    ("ks3_09_linear_eq_two", "9. Linear equations in two unknowns", "number_algebra", "junior"),
    ("ks3_10_laws_indices", "10. Laws of integral indices", "number_algebra", "junior"),
    ("ks3_11_polynomials", "11. Polynomials", "number_algebra", "junior"),
    ("ks3_12_identities", "12. Identities", "number_algebra", "junior"),
    ("ks3_13_formulae", "13. Formulae", "number_algebra", "junior"),
    ("ks3_14_linear_inequalities", "14. Linear inequalities in one unknown", "number_algebra", "junior"),
    ("ks3_15_errors_measurement", "15. Errors in measurement", "measures_shape_space", "junior"),
    ("ks3_16_arc_sectors", "16. Arc lengths and areas of sectors", "measures_shape_space", "junior"),
    ("ks3_17_3d_figures", "17. 3-D figures", "measures_shape_space", "junior"),
    ("ks3_18_mensuration", "18. Mensuration", "measures_shape_space", "junior"),
    ("ks3_19_angles_parallel", "19. Angles and parallel lines", "measures_shape_space", "junior"),
    ("ks3_20_polygons", "20. Polygons", "measures_shape_space", "junior"),
    ("ks3_21_congruent_triangles", "21. Congruent triangles", "measures_shape_space", "junior"),
    ("ks3_22_similar_triangles", "22. Similar triangles", "measures_shape_space", "junior"),
    ("ks3_23_quadrilaterals", "23. Quadrilaterals", "measures_shape_space", "junior"),
    ("ks3_24_centres_triangles", "24. Centres of triangles", "measures_shape_space", "junior"),
    ("ks3_25_pythagoras", "25. Pythagoras’ theorem", "measures_shape_space", "junior"),
    ("ks3_26_rectangular_coords", "26. Rectangular coordinate system", "measures_shape_space", "junior"),
    ("ks3_27_trigonometry", "27. Trigonometry", "measures_shape_space", "junior"),
    ("ks3_28_organisation_data", "28. Organisation of data", "data_handling", "junior"),
    ("ks3_29_presentation_data", "29. Presentation of data", "data_handling", "junior"),
    ("ks3_30_central_tendency", "30. Measures of central tendency", "data_handling", "junior"),
    ("ks3_31_probability", "31. Probability", "data_handling", "junior"),
    ("ks3_32_inquiry", "32. Inquiry and investigation", "further", "junior"),
    ("cp_01_quadratic_equations", "1. Quadratic equations in one unknown", "number_algebra", "senior"),
    ("cp_02_functions_graphs", "2. Functions and graphs", "number_algebra", "senior"),
    ("cp_03_exponential_log", "3. Exponential and logarithmic functions", "number_algebra", "senior"),
    ("cp_04_more_polynomials", "4. More about polynomials", "number_algebra", "senior"),
    ("cp_05_more_equations", "5. More about equations", "number_algebra", "senior"),
    ("cp_06_variations", "6. Variations", "number_algebra", "senior"),
    ("cp_07_sequences", "7. Arithmetic and geometric sequences and their summations", "number_algebra", "senior"),
    ("cp_08_inequalities_lp", "8. Inequalities and linear programming", "number_algebra", "senior"),
    ("cp_09_more_function_graphs", "9. More about graphs of functions", "number_algebra", "senior"),
    ("cp_10_equations_straight_lines", "10. Equations of straight lines", "measures_shape_space", "senior"),
    ("cp_11_basic_circles", "11. Basic properties of circles", "measures_shape_space", "senior"),
    ("cp_12_loci", "12. Loci", "measures_shape_space", "senior"),
    ("cp_13_equations_circles", "13. Equations of circles", "measures_shape_space", "senior"),
    ("cp_14_more_trigonometry", "14. More about trigonometry", "measures_shape_space", "senior"),
    ("cp_15_permutations_combinations", "15. Permutations and combinations", "data_handling", "senior"),
    ("cp_16_more_probability", "16. More about probability", "data_handling", "senior"),
    ("cp_17_measures_dispersion", "17. Measures of dispersion", "data_handling", "senior"),
    ("cp_18_uses_abuses_statistics", "18. Uses and abuses of statistics", "data_handling", "senior"),
    ("cp_19_further_applications", "19. Further applications", "further", "senior"),
    ("cp_20_inquiry", "20. Inquiry and investigation", "further", "senior"),
    ("m1_01_binomial_expansion", "1. Binomial expansion", "m1", "senior"),
    ("m1_02_exponential_log", "2. Exponential and logarithmic functions", "m1", "senior"),
    ("m1_03_derivative", "3. Derivative of a function", "m1", "senior"),
    ("m1_04_differentiation", "4. Differentiation of a function", "m1", "senior"),
    ("m1_05_second_derivative", "5. Second derivative", "m1", "senior"),
    ("m1_06_applications_diff", "6. Applications of differentiation", "m1", "senior"),
    ("m1_07_indefinite_integration", "7. Indefinite integration and its applications", "m1", "senior"),
    ("m1_08_definite_integration", "8. Definite integration and its applications", "m1", "senior"),
    ("m1_09_trapezoidal_rule", "9. Approximation of definite integrals using the trapezoidal rule", "m1", "senior"),
    ("m1_10_conditional_probability", "10. Conditional probability and Bayes’ theorem", "m1", "senior"),
    ("m1_11_discrete_rv", "11. Discrete random variables", "m1", "senior"),
    ("m1_12_probability_distribution", "12. Probability distribution, expectation and variance", "m1", "senior"),
    ("m1_13_binomial_distribution", "13. The binomial distribution", "m1", "senior"),
    ("m1_14_poisson_distribution", "14. The Poisson distribution", "m1", "senior"),
    ("m1_15_binomial_poisson_apps", "15. Applications of the binomial and the Poisson distributions", "m1", "senior"),
    ("m1_16_normal_definition", "16. Basic definition and properties of normal distribution", "m1", "senior"),
    ("m1_17_normal_standardisation", "17. Standardisation of a normal variable and use of the standard normal table", "m1", "senior"),
    ("m1_18_normal_applications", "18. Applications of the normal distribution", "m1", "senior"),
    ("m1_19_sampling_point_estimates", "19. Sampling distribution and point estimates", "m1", "senior"),
    ("m1_20_confidence_interval", "20. Confidence interval for a population mean", "m1", "senior"),
    ("m1_21_inquiry", "21. Inquiry and investigation", "m1", "senior"),
    ("m2_01_odd_even", "1. Odd and even functions", "m2", "senior"),
    ("m2_02_mathematical_induction", "2. Mathematical induction", "m2", "senior"),
    ("m2_03_binomial_theorem", "3. The binomial theorem", "m2", "senior"),
    ("m2_04_trig_functions", "4. More about trigonometric functions", "m2", "senior"),
    ("m2_05_introduction_to_e", "5. Introduction to e", "m2", "senior"),
    ("m2_06_limits", "6. Limits", "m2", "senior"),
    ("m2_07_differentiation", "7. Differentiation", "m2", "senior"),
    ("m2_08_applications_diff", "8. Applications of differentiation", "m2", "senior"),
    ("m2_09_indefinite_integration", "9. Indefinite integration and its applications", "m2", "senior"),
    ("m2_10_definite_integration", "10. Definite integration", "m2", "senior"),
    ("m2_11_applications_definite", "11. Applications of definite integration", "m2", "senior"),
    ("m2_12_determinants", "12. Determinants", "m2", "senior"),
    ("m2_13_matrices", "13. Matrices", "m2", "senior"),
    ("m2_14_linear_systems", "14. Systems of linear equations", "m2", "senior"),
    ("m2_15_introduction_vectors", "15. Introduction to vectors", "m2", "senior"),
    ("m2_16_scalar_vector_product", "16. Scalar product and vector product", "m2", "senior"),
    ("m2_17_applications_vectors", "17. Applications of vectors", "m2", "senior"),
    ("m2_18_inquiry", "18. Inquiry and investigation", "m2", "senior"),
)


def _levels_for_stage(stage: str) -> tuple[str, ...]:
    if stage == "junior":
        return JUNIOR_LEVELS
    return SENIOR_LEVELS


EXPLAIN_TOPIC_BY_ID = {
    row[0]: {
        "id": row[0],
        "label": row[1],
        "strand": row[2],
        "stage": row[3],
        "levels": _levels_for_stage(row[3]),
    }
    for row in _EXPLAIN_TOPIC_ROWS
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
DSE_FIGURE_INSTRUCTION = (
    "Use diagrams and figures, not only prose. Invent a short teaching scenario "
    "a Hong Kong secondary student would recognise (for example MTR fares, a wet "
    "market, sports day, a shopping receipt, a floor plan, or a slope on a hill) "
    "and keep the mathematics at the stated level. "
    "When a sketch, geometric figure, number line, coordinate graph, or statistical "
    "chart helps, emit one fenced JSON block:\n"
    "```figure\n"
    '{"type":"geometry|coordinate|number_line|chart","title":"...","caption":"...",'
    '"elements":[{"kind":"polygon","points":[[20,80],[80,80],[50,20]],"labels":["A","B","C"]},'
    '{"kind":"segment","from":[20,80],"to":[80,80],"label":"6 cm"}]}\n'
    "```\n"
    "geometry uses a 0–100 canvas, x right, y down. coordinate uses data units and "
    'optional "axes":{"xmin":-2,"xmax":6,"ymin":-2,"ymax":6} with y up. '
    "number_line uses min, max, marks, and points. chart uses labels and series "
    "(bar, line, or pie). "
    "Label given lengths and angles. Do not draw the hidden answer, the completed "
    "construction, or worked numbers that give the result away."
)
DSE_EXPLAIN_INSTRUCTION = (
    "Mode is Explain. Teach the selected school-level topics step by step, "
    "grounded on uploaded syllabus and notes when they are present. Cite those "
    "files. For each topic give: a short real-life scenario, the idea, a labelled "
    "diagram or figure in a ```figure fence, the method, one worked example, and "
    "common mistakes. Stay at the stated form (S1–S6); do not jump ahead unless "
    "asked. Show working; mark the final answer when you reach one. "
    + DSE_FIGURE_INSTRUCTION
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
DSE_CREATE_JSON_KEYS = (
    "question, scenario, figure, expected_answer, mark_scheme, outline"
)
DSE_CREATE_FIGURE_JSON = (
    "figure is a JSON object or null. Use the same contract as a ```figure fence: "
    '{"type":"geometry|coordinate|number_line|chart","title":"...","caption":"...",'
    '"elements":[{"kind":"polygon","points":[[20,80],[80,80],[50,20]],'
    '"labels":["A","B","C"]}]}. '
    "geometry uses a 0–100 canvas, x right, y down. Include a diagram whenever the "
    "question has a triangle, circle, graph, chart, number line, 3-D figure, or "
    "measurement. If the item is pure algebra with no geometric meaning, set "
    "figure to null. The figure must show given information only, never the answer. "
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
    return _optional_choice(value, ALLOWED_TOPICS, "topic")


def explain_topics_catalog() -> dict[str, object]:
    by_level: dict[str, list[dict[str, str]]] = {level: [] for level in ALLOWED_LEVELS}
    for row in _EXPLAIN_TOPIC_ROWS:
        item = {"id": row[0], "label": row[1], "strand": row[2], "stage": row[3]}
        for level in _levels_for_stage(row[3]):
            by_level[level].append(item)
    return {
        "levels": list(ALLOWED_LEVELS),
        "strands": dict(EXPLAIN_STRANDS),
        "topics": by_level,
        "source": {
            "label": "EDB Mathematics curriculum documents",
            "href": EDB_CURRICULUM_HREF,
        },
    }


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
        stage = "S1–S3" if row.get("stage") == "junior" else "S4–S6"
        labels.append(f"{stage} {row['label']}".strip())
    return labels


def explain_user_message(topic_ids: list[str], extra: str = "") -> str:
    labels = explain_topic_labels(topic_ids)
    if not labels:
        return extra.strip() or DEFAULT_EXPLAIN_MESSAGE
    head = "Explain these topics: " + "; ".join(labels) + "."
    extra = extra.strip()
    if extra:
        return extra + "\n\n" + head
    return (
        head
        + " Teach each one at that school level with a real-life scenario, "
        "a labelled diagram or figure, and a worked example."
    )


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


def _mode_instruction(mode: str, question_count: int = DEFAULT_QUESTION_COUNT) -> str:
    if mode == MODE_GUIDED_NO_ANSWER:
        return DSE_GUIDED_NO_ANSWER_INSTRUCTION
    if mode == MODE_GUIDED_WITH_ANSWER:
        return DSE_GUIDED_WITH_ANSWER_INSTRUCTION
    if mode == MODE_CREATE_AND_MARK:
        return create_question_instruction(question_count)
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
    topics: list[str] | None = None,
    question: str | None = None,
    has_extracts: bool = False,
    reveal_mark_scheme: str | None = None,
    question_count: int = DEFAULT_QUESTION_COUNT,
) -> str:
    if mode == MODE_GUIDED_NO_ANSWER:
        parts = [DSE_TUTOR_IDENTITY]
    else:
        parts = [DSE_TUTOR_BASE]
    parts.extend(_language_instructions(target_language))
    parts.append(_mode_instruction(mode, question_count))
    if level:
        parts.append(f"School level: {level} (Hong Kong secondary).")
    if module:
        parts.append(f"Curriculum module: {ALLOWED_MODULES[module]}.")
    if topic:
        parts.append(f"Topic: {ALLOWED_TOPICS[topic]}.")
    if topics:
        labeled = []
        for topic_id in topics:
            row = EXPLAIN_TOPIC_BY_ID.get(topic_id)
            if not row:
                continue
            strand = EXPLAIN_STRANDS.get(row["strand"], row["strand"])
            labeled.append(f"{row['label']} ({strand})")
        if labeled:
            parts.append(
                "EDB Mathematics learning units to explain: " + "; ".join(labeled) + "."
            )
            parts.append(
                "Follow the Education Bureau Mathematics curriculum learning objectives "
                "for these units. Pitch the explanation at the stated school level."
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
        "figure": parse_figure_spec(parsed.get("figure")),
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
