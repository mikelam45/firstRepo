"""Mandatory diagrams for DSE Create and Explain.

The tutor is told to emit a figure. If it skips one, these templates are attached
so the student still gets a labelled, clickable diagram.
"""

from __future__ import annotations

import json
from typing import Any

from .chat_format import parse_figure_spec

FIGURE_FENCE_MARK = "```figure"

CONGRUENT_TRIANGLES_FIGURE: dict[str, Any] = {
    "type": "geometry",
    "interactive": True,
    "title": "Congruent triangles ABC and DEF",
    "caption": "Click a side or angle. The matching part on the other triangle lights up.",
    "hint": "Use the buttons to test SSS, SAS, ASA, and RHS.",
    "actions": [
        {
            "id": "sss",
            "label": "SSS",
            "highlight": ["ab", "de", "bc", "ef", "ac", "df"],
            "caption": "SSS: AB=DE, BC=EF, AC=DF. All three sides match, so △ABC ≅ △DEF.",
        },
        {
            "id": "sas",
            "label": "SAS",
            "highlight": ["ab", "de", "angle-a", "angle-d", "ac", "df"],
            "caption": "SAS: two sides and the included angle. SSA is not a rule.",
        },
        {
            "id": "asa",
            "label": "ASA",
            "highlight": ["angle-a", "angle-d", "ab", "de", "angle-b", "angle-e"],
            "caption": "ASA: two angles and the included side.",
        },
        {
            "id": "rhs",
            "label": "RHS",
            "highlight": ["angle-c", "angle-f", "ac", "df", "ab", "de"],
            "caption": "RHS: right angle, hypotenuse, and one other side (right-angled triangles only).",
        },
    ],
    "elements": [
        {
            "kind": "polygon",
            "points": [[14, 78], [46, 78], [24, 28]],
            "labels": ["A", "B", "C"],
            "id": "tri-abc",
        },
        {
            "kind": "segment",
            "from": [14, 78],
            "to": [46, 78],
            "label": "7 cm",
            "id": "ab",
            "match": "de",
            "caption": "AB = DE = 7 cm (corresponding sides).",
        },
        {
            "kind": "segment",
            "from": [46, 78],
            "to": [24, 28],
            "label": "5 cm",
            "id": "bc",
            "match": "ef",
            "caption": "BC = EF = 5 cm (corresponding sides).",
        },
        {
            "kind": "segment",
            "from": [24, 28],
            "to": [14, 78],
            "label": "6 cm",
            "id": "ac",
            "match": "df",
            "caption": "AC = DF = 6 cm (corresponding sides).",
        },
        {
            "kind": "angle",
            "at": [14, 78],
            "from": [46, 78],
            "to": [24, 28],
            "id": "angle-a",
            "match": "angle-d",
            "caption": "Angle A corresponds to angle D.",
        },
        {
            "kind": "angle",
            "at": [46, 78],
            "from": [14, 78],
            "to": [24, 28],
            "id": "angle-b",
            "match": "angle-e",
            "caption": "Angle B corresponds to angle E.",
        },
        {
            "kind": "angle",
            "at": [24, 28],
            "from": [14, 78],
            "to": [46, 78],
            "id": "angle-c",
            "match": "angle-f",
            "caption": "Angle C corresponds to angle F.",
        },
        {
            "kind": "polygon",
            "points": [[56, 78], [88, 78], [66, 28]],
            "labels": ["D", "E", "F"],
            "id": "tri-def",
        },
        {
            "kind": "segment",
            "from": [56, 78],
            "to": [88, 78],
            "label": "7 cm",
            "id": "de",
            "match": "ab",
            "caption": "DE = AB = 7 cm (corresponding sides).",
        },
        {
            "kind": "segment",
            "from": [88, 78],
            "to": [66, 28],
            "label": "5 cm",
            "id": "ef",
            "match": "bc",
            "caption": "EF = BC = 5 cm (corresponding sides).",
        },
        {
            "kind": "segment",
            "from": [66, 28],
            "to": [56, 78],
            "label": "6 cm",
            "id": "df",
            "match": "ac",
            "caption": "DF = AC = 6 cm (corresponding sides).",
        },
        {
            "kind": "angle",
            "at": [56, 78],
            "from": [88, 78],
            "to": [66, 28],
            "id": "angle-d",
            "match": "angle-a",
            "caption": "Angle D corresponds to angle A.",
        },
        {
            "kind": "angle",
            "at": [88, 78],
            "from": [56, 78],
            "to": [66, 28],
            "id": "angle-e",
            "match": "angle-b",
            "caption": "Angle E corresponds to angle B.",
        },
        {
            "kind": "angle",
            "at": [66, 28],
            "from": [56, 78],
            "to": [88, 78],
            "id": "angle-f",
            "match": "angle-c",
            "caption": "Angle F corresponds to angle C.",
        },
        {"kind": "label", "x": 30, "y": 92, "text": "△ABC"},
        {"kind": "label", "x": 72, "y": 92, "text": "△DEF"},
    ],
}

ARC_SECTOR_FIGURE: dict[str, Any] = {
    "type": "geometry",
    "interactive": True,
    "title": "Arc length and sector area",
    "caption": "Click the slice, the crust, or a radius. Buttons show the formulae.",
    "hint": "The sector is the pizza slice; the arc is the crust.",
    "actions": [
        {
            "id": "radius",
            "label": "Radius",
            "highlight": ["radius1", "radius2", "centre"],
            "caption": "Radius r = 10 cm. Both radii of the sector are equal.",
        },
        {
            "id": "angle",
            "label": "Angle",
            "highlight": ["slice", "angle-o"],
            "caption": "Central angle θ = 60°. Use θ/360 in both formulae.",
        },
        {
            "id": "arc",
            "label": "Arc length",
            "highlight": ["crust"],
            "caption": "Arc length ℓ = (θ/360) × 2πr.",
        },
        {
            "id": "area",
            "label": "Sector area",
            "highlight": ["slice"],
            "caption": "Sector area A = (θ/360) × πr².",
        },
    ],
    "elements": [
        {
            "kind": "sector",
            "cx": 48,
            "cy": 52,
            "r": 30,
            "start": -40,
            "end": 20,
            "id": "slice",
            "caption": "Sector area A = (θ/360) × πr². This is the pizza slice.",
        },
        {
            "kind": "circle",
            "cx": 48,
            "cy": 52,
            "r": 30,
            "id": "circle",
            "caption": "The whole circle. The sector is a fraction θ/360 of it.",
        },
        {
            "kind": "arc",
            "cx": 48,
            "cy": 52,
            "r": 30,
            "start": -40,
            "end": 20,
            "id": "crust",
            "caption": "Arc length ℓ = (θ/360) × 2πr. This is the crust.",
        },
        {
            "kind": "segment",
            "from": [48, 52],
            "to": [71, 33],
            "label": "r = 10 cm",
            "id": "radius1",
            "match": "radius2",
            "caption": "A radius of the sector, r = 10 cm.",
        },
        {
            "kind": "segment",
            "from": [48, 52],
            "to": [76, 62],
            "id": "radius2",
            "match": "radius1",
            "caption": "The other radius of the sector.",
        },
        {
            "kind": "point",
            "x": 48,
            "y": 52,
            "label": "O",
            "id": "centre",
            "caption": "Centre O. The central angle is at O.",
        },
        {
            "kind": "angle",
            "at": [48, 52],
            "from": [71, 33],
            "to": [76, 62],
            "label": "60°",
            "id": "angle-o",
            "caption": "Central angle θ = 60°.",
        },
        {"kind": "label", "x": 86, "y": 44, "text": "arc ℓ"},
    ],
}

TRIANGLE_FIGURE: dict[str, Any] = {
    "type": "geometry",
    "interactive": True,
    "title": "Triangle ABC",
    "caption": "Click a side or vertex. The matching label stays selected.",
    "elements": [
        {
            "kind": "polygon",
            "points": [[18, 82], [82, 82], [48, 18]],
            "labels": ["A", "B", "C"],
            "id": "tri",
        },
        {
            "kind": "segment",
            "from": [18, 82],
            "to": [82, 82],
            "label": "c",
            "id": "ab",
            "caption": "Side AB (c).",
        },
        {
            "kind": "segment",
            "from": [82, 82],
            "to": [48, 18],
            "label": "a",
            "id": "bc",
            "caption": "Side BC (a).",
        },
        {
            "kind": "segment",
            "from": [48, 18],
            "to": [18, 82],
            "label": "b",
            "id": "ca",
            "caption": "Side CA (b).",
        },
        {
            "kind": "angle",
            "at": [18, 82],
            "from": [82, 82],
            "to": [48, 18],
            "id": "angle-a",
            "caption": "Angle at A.",
        },
        {
            "kind": "angle",
            "at": [82, 82],
            "from": [18, 82],
            "to": [48, 18],
            "right": True,
            "id": "angle-b",
            "caption": "Angle at B.",
        },
    ],
}

NUMBER_LINE_FIGURE: dict[str, Any] = {
    "type": "number_line",
    "title": "Number line",
    "caption": "Use the marks to place the given values.",
    "min": -4,
    "max": 8,
    "marks": [-4, -2, 0, 2, 4, 6, 8],
    "points": [{"value": 0, "label": "0"}],
}

COORDINATE_FIGURE: dict[str, Any] = {
    "type": "coordinate",
    "title": "Coordinate plane",
    "caption": "Read the given points from the axes.",
    "axes": {"xmin": -2, "xmax": 6, "ymin": -2, "ymax": 6},
    "elements": [
        {"kind": "point", "x": 1, "y": 2, "label": "A", "id": "a", "caption": "Point A."},
        {"kind": "point", "x": 4, "y": 3, "label": "B", "id": "b", "caption": "Point B."},
        {
            "kind": "segment",
            "from": [1, 2],
            "to": [4, 3],
            "id": "ab",
            "caption": "Segment AB.",
        },
    ],
}

BAR_CHART_FIGURE: dict[str, Any] = {
    "type": "chart",
    "title": "Bar chart",
    "caption": "Read the heights from the chart.",
    "labels": ["A", "B", "C"],
    "series": [{"name": "Value", "values": [4, 7, 5]}],
}

CIRCLE_FIGURE: dict[str, Any] = {
    "type": "geometry",
    "interactive": True,
    "title": "Circle with centre O",
    "caption": "Click the radius or the circumference.",
    "elements": [
        {
            "kind": "circle",
            "cx": 50,
            "cy": 50,
            "r": 28,
            "id": "circle",
            "caption": "Circumference of the circle.",
        },
        {
            "kind": "segment",
            "from": [50, 50],
            "to": [78, 50],
            "label": "r",
            "id": "radius",
            "caption": "Radius r.",
        },
        {
            "kind": "point",
            "x": 50,
            "y": 50,
            "label": "O",
            "id": "centre",
            "caption": "Centre O.",
        },
    ],
}

EXPLAIN_FIGURES: dict[str, dict[str, Any]] = {
    "ks3_16_arc_sectors": ARC_SECTOR_FIGURE,
    "ks3_21_congruent_triangles": CONGRUENT_TRIANGLES_FIGURE,
    "ks3_22_similar_triangles": CONGRUENT_TRIANGLES_FIGURE,
    "ks3_17_3d_figures": TRIANGLE_FIGURE,
    "ks3_18_mensuration": CIRCLE_FIGURE,
    "ks3_19_angles_parallel": TRIANGLE_FIGURE,
    "ks3_20_polygons": TRIANGLE_FIGURE,
    "ks3_23_quadrilaterals": TRIANGLE_FIGURE,
    "ks3_24_centres_triangles": TRIANGLE_FIGURE,
    "ks3_25_pythagoras": TRIANGLE_FIGURE,
    "ks3_26_rectangular_coords": COORDINATE_FIGURE,
    "ks3_27_trigonometry": TRIANGLE_FIGURE,
    "ks3_08_linear_eq_one": NUMBER_LINE_FIGURE,
    "ks3_09_linear_eq_two": COORDINATE_FIGURE,
    "ks3_01_basic_computation": NUMBER_LINE_FIGURE,
    "ks3_28_organisation_data": BAR_CHART_FIGURE,
    "ks3_29_presentation_data": BAR_CHART_FIGURE,
    "cp_01_quadratic_equations": COORDINATE_FIGURE,
    "cp_02_functions_graphs": COORDINATE_FIGURE,
    "cp_11_basic_circles": CIRCLE_FIGURE,
}

CREATE_FIGURES: dict[str, dict[str, Any]] = {
    "geometry": TRIANGLE_FIGURE,
    "measures_shape_space": TRIANGLE_FIGURE,
    "trig": TRIANGLE_FIGURE,
    "mensuration": CIRCLE_FIGURE,
    "data": BAR_CHART_FIGURE,
    "data_handling": BAR_CHART_FIGURE,
    "calculus": COORDINATE_FIGURE,
    "functions": COORDINATE_FIGURE,
    "algebra": NUMBER_LINE_FIGURE,
    "numbers": NUMBER_LINE_FIGURE,
    "number_algebra": NUMBER_LINE_FIGURE,
}


def _validated(spec: dict[str, Any] | None) -> dict[str, Any] | None:
    if not spec:
        return None
    return parse_figure_spec(spec)


def default_create_figure(topic: str | None = None) -> dict[str, Any]:
    raw = CREATE_FIGURES.get(topic or "") or NUMBER_LINE_FIGURE
    parsed = _validated(raw)
    if parsed:
        return parsed
    fallback = _validated(NUMBER_LINE_FIGURE)
    assert fallback is not None
    return fallback


def explain_figure_for_topic(topic_id: str) -> dict[str, Any]:
    parsed = _validated(EXPLAIN_FIGURES.get(topic_id))
    if parsed:
        return parsed
    return default_create_figure(None)


def explain_figures_for_topics(topic_ids: list[str] | None) -> list[dict[str, Any]]:
    figures: list[dict[str, Any]] = []
    seen: set[str] = set()
    for topic_id in topic_ids or []:
        if topic_id in seen:
            continue
        seen.add(topic_id)
        figures.append(explain_figure_for_topic(topic_id))
    return figures


def figure_fence(spec: dict[str, Any]) -> str:
    return FIGURE_FENCE_MARK + "\n" + json.dumps(spec, ensure_ascii=False) + "\n```"


def ensure_created_figure(
    figure: dict[str, Any] | None,
    *,
    topic: str | None = None,
) -> dict[str, Any]:
    parsed = parse_figure_spec(figure) if figure else None
    if parsed:
        return parsed
    return default_create_figure(topic)


def default_solve_figure(
    topic: str | None = None,
    question: str | None = None,
) -> dict[str, Any]:
    text = (question or "").lower()
    if any(word in text for word in ("sector", "arc length", "arc ")):
        return _validated(ARC_SECTOR_FIGURE) or default_create_figure(None)
    if "circle" in text:
        return _validated(CIRCLE_FIGURE) or default_create_figure(None)
    if any(word in text for word in ("triangle", "congruent", "similar", "pythag")):
        return _validated(TRIANGLE_FIGURE) or default_create_figure(None)
    if any(word in text for word in ("graph", "coordinate", "quadratic", "function")):
        return _validated(COORDINATE_FIGURE) or default_create_figure(None)
    if topic:
        return default_create_figure(topic)
    return default_create_figure(None)


def ensure_solve_figures(
    reply: str,
    *,
    topic: str | None = None,
    question: str | None = None,
    already_has_figure: bool = False,
) -> str:
    text = reply or ""
    if FIGURE_FENCE_MARK in text or already_has_figure:
        return text
    return text.rstrip() + "\n\n" + figure_fence(default_solve_figure(topic, question))


def session_has_figure(session: dict[str, Any] | None) -> bool:
    if not session:
        return False
    for item in session.get("messages") or []:
        if item.get("role") == "assistant" and FIGURE_FENCE_MARK in str(item.get("content") or ""):
            return True
    return False


def ensure_explain_figures(reply: str, topic_ids: list[str] | None) -> str:
    text = reply or ""
    figures = explain_figures_for_topics(topic_ids)
    if not figures:
        if FIGURE_FENCE_MARK in text:
            return text
        return text.rstrip() + "\n\n" + figure_fence(default_create_figure(None))
    missing = [spec for spec in figures if spec.get("title") not in text]
    if FIGURE_FENCE_MARK not in text:
        missing = figures
    if not missing:
        return text
    blocks = "\n\n".join(figure_fence(spec) for spec in missing)
    return text.rstrip() + "\n\n" + blocks
