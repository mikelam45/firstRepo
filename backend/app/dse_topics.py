"""Hong Kong secondary mathematics topics (S1–S6) loaded from the attached CSV."""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .chat import ChatError

TOPICS_CSV_NAME = "HK_Secondary_Maths_S1_to_S6_Topics-v2.csv"
TOPICS_CSV_PATH = Path(__file__).resolve().parent / "curriculum" / TOPICS_CSV_NAME
EDB_CURRICULUM_HREF = (
    "https://www.edb.gov.hk/en/curriculum-development/kla/ma/curr/index2.html"
)

ALLOWED_LEVELS = ("S1", "S2", "S3", "S4", "S5", "S6")
JUNIOR_LEVELS = ("S1", "S2", "S3")
SENIOR_LEVELS = ("S4", "S5", "S6")
MAX_EXPLAIN_TOPICS = 8

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

EXPLAIN_STRANDS = {
    "number_algebra": "Number and Algebra",
    "measures_shape_space": "Measures, Shape and Space",
    "data_handling": "Data Handling",
    "calculus": "Calculus",
    "algebra": "Algebra",
    "trig": "Trigonometry",
    "further": "Further Learning Unit",
    "m1": "Module 1 (Calculus and Statistics)",
    "m2": "Module 2 (Algebra and Calculus)",
}

MODULE_KEYS = {
    "compulsory": "Compulsory Mathematics",
    "m1": "Module 1 (M1): Calculus & Statistics",
    "m2": "Module 2 (M2): Algebra & Calculus",
}

_CATEGORY_STRAND = {
    "number and algebra": "number_algebra",
    "measures, shape and space": "measures_shape_space",
    "data handling": "data_handling",
    "calculus": "calculus",
    "statistics": "data_handling",
    "algebra": "algebra",
    "trigonometry": "trig",
    "revision & integration": "further",
}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str, limit: int = 52) -> str:
    folded = (
        (text or "")
        .lower()
        .replace("'", "")
        .replace("'", "")
        .replace("&", " and ")
    )
    return _SLUG_RE.sub("_", folded).strip("_")[:limit]


def _module_key(module: str) -> str:
    raw = (module or "").strip()
    lowered = raw.lower()
    if lowered.startswith("m1"):
        return "m1"
    if lowered.startswith("m2"):
        return "m2"
    return "compulsory"


def _module_short(module_key: str) -> str:
    if module_key == "m1":
        return "M1"
    if module_key == "m2":
        return "M2"
    return "Compulsory"


def _strand_for_category(category: str) -> str:
    return _CATEGORY_STRAND.get((category or "").strip().lower(), "number_algebra")


def _figure_key_from_row(row: dict[str, str]) -> str:
    blob = " ".join(
        part for part in (row.get("label"), row.get("category"), row.get("strand")) if part
    ).lower()
    if (
        "congruent" in blob
        or "congruence" in blob
        or "similar triangle" in blob
        or "similarity of triangle" in blob
    ):
        return "congruent"
    if "quadrilateral" in blob or "parallelogram" in blob:
        return "quadrilateral"
    if any(word in blob for word in ("circle", "sector", "arc length")):
        return "mensuration"
    if any(
        word in blob
        for word in (
            "coordinate",
            "locus",
            "loci",
            "straight line",
            "quadratic",
            "function",
            "graph",
            "calculus",
            "derivative",
            "differentiation",
            "integration",
            "limit",
        )
    ):
        return "functions"
    if any(
        word in blob
        for word in (
            "statistic",
            "data",
            "histogram",
            "bar chart",
            "probability",
            "permutation",
            "combination",
            "binomial distribution",
            "poisson",
            "normal distribution",
        )
    ):
        return "data_handling"
    if any(
        word in blob
        for word in (
            "triangle",
            "pythagoras",
            "trigonometr",
            "polygon",
            "parallel",
            "angle",
            "3-d",
            "3d",
            "mensuration",
            "geometry",
            "vector",
        )
    ):
        return "geometry"
    strand = row.get("strand") or "number_algebra"
    if strand in {"calculus", "trig", "algebra", "number_algebra", "measures_shape_space", "data_handling"}:
        if strand == "trig":
            return "trig"
        if strand == "calculus":
            return "calculus"
        if strand == "measures_shape_space":
            return "geometry"
        return strand
    return "number_algebra"


def _read_csv_rows() -> list[dict[str, str]]:
    if not TOPICS_CSV_PATH.is_file():
        raise FileNotFoundError(f"Missing mathematics topics CSV: {TOPICS_CSV_PATH}")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    with TOPICS_CSV_PATH.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            form = (raw.get("Form") or "").strip()
            module = (raw.get("Module/Part") or "").strip()
            category = (raw.get("Category") or "").strip()
            topic = (raw.get("Topic") or "").strip()
            if form not in ALLOWED_LEVELS or not topic:
                continue
            module_key = _module_key(module)
            topic_id = f"{form.lower()}_{module_key[:4]}_{_slug(topic)}"
            if topic_id in seen:
                topic_id = f"{topic_id}_{len(seen) + 1}"
            seen.add(topic_id)
            strand = _strand_for_category(category)
            if module_key in {"m1", "m2"} and strand in {"number_algebra", "further"}:
                strand = module_key
            item = {
                "id": topic_id,
                "label": topic,
                "form": form,
                "module": module or MODULE_KEYS[module_key],
                "module_key": module_key,
                "module_short": _module_short(module_key),
                "category": category,
                "strand": strand,
                "stage": "junior" if form in JUNIOR_LEVELS else "senior",
                "group": (
                    category
                    if module_key == "compulsory"
                    else f"{_module_short(module_key)} · {category}"
                ),
            }
            item["figure"] = _figure_key_from_row(item)
            rows.append(item)
    if not rows:
        raise ValueError(f"No topics loaded from {TOPICS_CSV_PATH}")
    return rows


@lru_cache(maxsize=1)
def load_topic_rows() -> tuple[dict[str, str], ...]:
    return tuple(_read_csv_rows())


def topic_by_id() -> dict[str, dict[str, str]]:
    return {row["id"]: dict(row) for row in load_topic_rows()}


TOPIC_BY_ID = topic_by_id()


def levels_by_module() -> dict[str, list[str]]:
    found: dict[str, set[str]] = {key: set() for key in MODULE_KEYS}
    for row in load_topic_rows():
        key = row["module_key"]
        if key in found:
            found[key].add(row["form"])
    return {
        key: [level for level in ALLOWED_LEVELS if level in found[key]]
        for key in MODULE_KEYS
    }


def topics_catalog() -> dict[str, Any]:
    by_level: dict[str, list[dict[str, str]]] = {level: [] for level in ALLOWED_LEVELS}
    for row in load_topic_rows():
        by_level[row["form"]].append(dict(row))
    return {
        "levels": list(ALLOWED_LEVELS),
        "strands": dict(EXPLAIN_STRANDS),
        "modules": dict(MODULE_KEYS),
        "levels_by_module": levels_by_module(),
        "topics": by_level,
        "source": {
            "label": "HK secondary mathematics topics (S1–S6)",
            "href": EDB_CURRICULUM_HREF,
            "file": TOPICS_CSV_NAME,
        },
    }


def figure_topic_key(topic_id: str | None) -> str | None:
    if not topic_id:
        return None
    if topic_id in ALLOWED_TOPICS:
        return topic_id
    row = TOPIC_BY_ID.get(topic_id)
    if not row:
        return topic_id
    return row.get("figure") or row.get("strand") or "number_algebra"


def topic_prompt_label(topic_id: str | None) -> str | None:
    if not topic_id:
        return None
    if topic_id in ALLOWED_TOPICS:
        return ALLOWED_TOPICS[topic_id]
    row = TOPIC_BY_ID.get(topic_id)
    if not row:
        return topic_id
    return (
        f"{row['form']} {row['label']} "
        f"({row['module_short']}, {row['category']})"
    )


def resolve_topic_id(value: str | None) -> str | None:
    if value is None:
        return None
    item = str(value).strip()
    if not item:
        return None
    if item in ALLOWED_TOPICS or item in TOPIC_BY_ID:
        return item
    raise ChatError(
        400,
        "topic must be a strand name or an S1–S6 topic from the attached catalog.",
    )
