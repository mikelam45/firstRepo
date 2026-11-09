"""Mandatory diagrams for DSE Create, Explain, and Solve.

The tutor is told to emit a figure. If it skips one, or if the figure omits named
givens (triangle ABC, 50°, 70°), these builders attach a labelled clickable diagram.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from .chat_format import parse_figure_spec, tex_to_plain

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

QUADRILATERAL_FIGURE: dict[str, Any] = {
    "type": "geometry",
    "interactive": True,
    "title": "Quadrilateral ABCD",
    "caption": "Click a vertex or side. Named givens stay labelled on the figure.",
    "actions": [
        {
            "id": "givens",
            "label": "Givens",
            "highlight": ["angle-a", "angle-b", "angle-c", "angle-d", "ab", "bc", "cd", "da"],
            "caption": "Click a vertex or side. Named givens stay labelled on the figure.",
        }
    ],
    "elements": [
        {
            "kind": "polygon",
            "points": [[16, 84], [86, 84], [78, 16], [22, 28]],
            "labels": ["A", "B", "C", "D"],
            "id": "quad",
        },
        {
            "kind": "segment",
            "from": [16, 84],
            "to": [86, 84],
            "id": "ab",
            "caption": "Side AB.",
        },
        {
            "kind": "segment",
            "from": [86, 84],
            "to": [78, 16],
            "id": "bc",
            "caption": "Side BC.",
        },
        {
            "kind": "segment",
            "from": [78, 16],
            "to": [22, 28],
            "id": "cd",
            "caption": "Side CD.",
        },
        {
            "kind": "segment",
            "from": [22, 28],
            "to": [16, 84],
            "id": "da",
            "caption": "Side DA.",
        },
        {
            "kind": "angle",
            "at": [16, 84],
            "from": [86, 84],
            "to": [22, 28],
            "id": "angle-a",
            "caption": "Angle at A.",
        },
        {
            "kind": "angle",
            "at": [86, 84],
            "from": [16, 84],
            "to": [78, 16],
            "right": True,
            "id": "angle-b",
            "caption": "Angle at B.",
        },
        {
            "kind": "angle",
            "at": [78, 16],
            "from": [86, 84],
            "to": [22, 28],
            "id": "angle-c",
            "caption": "Angle at C.",
        },
        {
            "kind": "angle",
            "at": [22, 28],
            "from": [78, 16],
            "to": [16, 84],
            "id": "angle-d",
            "caption": "Angle at D.",
        },
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
    "ks3_23_quadrilaterals": QUADRILATERAL_FIGURE,
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
    "congruent": CONGRUENT_TRIANGLES_FIGURE,
    "quadrilateral": QUADRILATERAL_FIGURE,
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


_FENCE_BODY_RE = re.compile(r"```figure[^\n]*\n(.*?)```", re.S)
_TRIANGLE_RE = re.compile(
    r"(?:triangle|△|∆)\s*([A-Za-z])\s*([A-Za-z])\s*([A-Za-z])",
    re.I,
)
_QUAD_RE = re.compile(
    r"(?:quadrilateral|parallelogram|rectangle|rhombus|trapez(?:ium|oid)|kite)\s*"
    r"([A-Za-z])\s*([A-Za-z])\s*([A-Za-z])\s*([A-Za-z])",
    re.I,
)
_CIRCLE_WORD_RE = re.compile(
    r"\b(circles?|circular|incircle|in-circle|fountain)\b",
    re.I,
)
_RESPECTIVE_ANGLES_RE = re.compile(
    r"angles?\s+([A-Za-z](?:\s*,\s*[A-Za-z])*(?:\s*,?\s*and\s+[A-Za-z])?)\s+"
    r"(?:measuring|are)\s+(.+?)(?:\s+respectively)?\s*(?:\.|$)",
    re.I | re.S,
)
_MEASURE_TOKEN_RE = re.compile(
    r"(\d+(?:\.\d+)?|[A-Za-z])\s*(?:°|degrees|deg)",
    re.I,
)
_DEGREE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:°|degrees|deg)",
    re.I,
)
_VERTEX_ANGLE_RES = (
    re.compile(
        r"angle\s+at(?:\s+vertex)?\s+([A-Za-z])\s+(?:measures?|is|=|:)?\s*(\d+(?:\.\d+)?)",
        re.I,
    ),
    re.compile(
        r"∠\s*([A-Za-z]{1,3})\s*(?:=|measures?|is|:)?\s*(\d+(?:\.\d+)?)",
        re.I,
    ),
    re.compile(
        r"angle\s+([A-Za-z])\s*(?:=|measures?|is|:)\s*(\d+(?:\.\d+)?)",
        re.I,
    ),
    re.compile(
        r"\b([A-Za-z])\s*=\s*(\d+(?:\.\d+)?)\s*°",
        re.I,
    ),
    re.compile(
        r"(\d+(?:\.\d+)?)\s*°\s+at\s+(?:vertex\s+)?([A-Za-z])",
        re.I,
    ),
)
_LENGTH_RE = re.compile(
    r"\b([A-Za-z]{2})\s*=\s*(\d+(?:\.\d+)?)\s*(cm|mm|m|km)?",
    re.I,
)
_DIAMETER_RE = re.compile(
    r"diameter(?:\s+of)?\s*(?:\$)?(\d+(?:\.\d+)?)(?:\s*\$)?\s*(meters?|metres?|cm|mm|km|m\b)?",
    re.I,
)


def _plain_math_text(text: str | None) -> str:
    return tex_to_plain(text or "")


def format_degree(value: Any) -> str:
    number = float(value)
    if number.is_integer():
        return f"{int(number)}°"
    return f"{number}°"


def _length_label(amount: Any, unit: str | None) -> str:
    number = float(amount)
    shown = str(int(number)) if number.is_integer() else str(number)
    raw_unit = (unit or "").strip().lower()
    if raw_unit in {"meter", "meters", "metre", "metres"}:
        raw_unit = "m"
    return f"{shown} {raw_unit}".strip() if raw_unit else shown


def given_labels_from_text(text: str | None) -> list[str]:
    plain = _plain_math_text(text)
    labels: list[str] = []
    seen: set[str] = set()

    def add(token: str) -> None:
        item = str(token).strip()
        if not item or item in seen:
            return
        seen.add(item)
        labels.append(item)

    match = _QUAD_RE.search(plain)
    if match:
        for group in match.groups():
            add(group.upper())
    match = _TRIANGLE_RE.search(plain)
    if match:
        for group in match.groups():
            add(group.upper())
    for names, measures in _respective_angle_pairs(plain):
        for name in names:
            add(name)
        for token in measures:
            if not _is_unknown_measure(token):
                add(format_degree(token))
    for pattern in _VERTEX_ANGLE_RES:
        for row in pattern.findall(plain):
            if pattern is _VERTEX_ANGLE_RES[-1]:
                add(format_degree(row[0]))
                add(row[1][0].upper())
            else:
                add(row[0][0].upper())
                add(format_degree(row[1]))
    for match in _DEGREE_RE.finditer(plain):
        add(format_degree(match.group(1)))
    for row in _LENGTH_RE.findall(plain):
        letters, amount, unit = row[0].upper(), row[1], row[2]
        add(letters)
        add(f"{amount} {unit}".strip() if unit else amount)
    for match in _DIAMETER_RE.finditer(plain):
        add(_length_label(match.group(1), match.group(2)))
    return labels


def _split_vertex_names(chunk: str) -> list[str]:
    names: list[str] = []
    for part in re.split(r",|\band\b", chunk or ""):
        token = part.strip().upper()
        if len(token) == 1 and token.isalpha():
            names.append(token)
    return names


def _is_unknown_measure(token: str) -> bool:
    text = str(token).strip()
    if not text:
        return True
    if text.lower() in {"x", "y", "z", "n", "k", "m", "t"}:
        return True
    try:
        float(text)
    except ValueError:
        return True
    return False


def _respective_angle_pairs(plain: str) -> list[tuple[list[str], list[str]]]:
    pairs: list[tuple[list[str], list[str]]] = []
    for match in _RESPECTIVE_ANGLES_RE.finditer(plain):
        names = _split_vertex_names(match.group(1))
        measures = [token for token in _MEASURE_TOKEN_RE.findall(match.group(2) or "")]
        if names and measures:
            pairs.append((names, measures))
    return pairs


def _given_facts(text: str | None) -> dict[str, Any]:
    plain = _plain_math_text(text)
    vertices: tuple[str, ...] = ()
    shape = ""
    quad = _QUAD_RE.search(plain)
    tri = _TRIANGLE_RE.search(plain)
    if quad:
        vertices = tuple(group.upper() for group in quad.groups())
        shape = "quadrilateral"
    elif tri:
        vertices = tuple(group.upper() for group in tri.groups())
        shape = "triangle"
    angles: dict[str, float] = {}
    unknowns: list[str] = []
    for names, measures in _respective_angle_pairs(plain):
        if not vertices:
            vertices = tuple(names)
            if len(names) >= 4:
                shape = "quadrilateral"
            elif len(names) == 3:
                shape = "triangle"
        for name, token in zip(names, measures):
            if _is_unknown_measure(token):
                if name not in unknowns:
                    unknowns.append(name)
                continue
            if name not in angles:
                angles[name] = float(token)
    for pattern in _VERTEX_ANGLE_RES:
        for row in pattern.findall(plain):
            if pattern is _VERTEX_ANGLE_RES[-1]:
                vertex, amount = row[1][0].upper(), float(row[0])
            else:
                vertex, amount = row[0][0].upper(), float(row[1])
            key = vertex if len(vertex) == 1 else vertex[0]
            if key not in angles:
                angles[key] = amount
    assigned = {format_degree(value) for value in angles.values()}
    unused = [
        float(match.group(1))
        for match in _DEGREE_RE.finditer(plain)
        if format_degree(match.group(1)) not in assigned
    ]
    if vertices:
        for vertex in vertices:
            if vertex not in angles and vertex not in unknowns and unused:
                angles[vertex] = unused.pop(0)
    lengths: dict[str, str] = {}
    for letters, amount, unit in _LENGTH_RE.findall(plain):
        key = "".join(sorted(letters.upper()))
        label = f"{amount} {unit}".strip() if unit else amount
        lengths[key] = label
    lowered = plain.lower()
    incircle = any(
        word in lowered
        for word in ("inscribed", "incircle", "in-circle", "touches all three", "tangent")
    )
    return {
        "vertices": vertices,
        "shape": shape,
        "angles": angles,
        "unknowns": unknowns,
        "lengths": lengths,
        "incircle": incircle,
        "labels": given_labels_from_text(text),
    }


def _figure_tokens(spec: dict[str, Any] | None) -> set[str]:
    tokens: set[str] = set()

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if not text:
            return
        tokens.add(text)
        tokens.add(text.upper())
        for match in _DEGREE_RE.finditer(_plain_math_text(text)):
            tokens.add(format_degree(match.group(1)))

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in {"label", "labels", "title", "caption", "text", "hint"}:
                    if isinstance(value, list):
                        for item in value:
                            add(item)
                    else:
                        add(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(spec)
    return tokens


def figure_spec_has_labels(spec: dict[str, Any] | None, required: list[str] | None) -> bool:
    if not required:
        return spec is not None
    if not spec:
        return False
    tokens = _figure_tokens(spec)
    for item in required:
        if item in tokens or item.upper() in tokens:
            continue
        return False
    return True


def figure_text_has_labels(text: str | None, required: list[str] | None) -> bool:
    if not required:
        return FIGURE_FENCE_MARK in (text or "")
    for body in _FENCE_BODY_RE.findall(text or ""):
        spec = parse_figure_spec(body)
        if spec and figure_spec_has_labels(spec, required):
            return True
    return False


def _intersect(
    origin: tuple[float, float],
    direction: tuple[float, float],
    other: tuple[float, float],
    other_dir: tuple[float, float],
) -> tuple[float, float] | None:
    det = direction[0] * other_dir[1] - direction[1] * other_dir[0]
    if abs(det) < 1e-9:
        return None
    t = (
        (other[0] - origin[0]) * other_dir[1] - (other[1] - origin[1]) * other_dir[0]
    ) / det
    return (origin[0] + t * direction[0], origin[1] + t * direction[1])


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _xy(point: tuple[float, float]) -> list[float]:
    return [round(point[0], 2), round(point[1], 2)]


def labelled_quadrilateral_figure(
    facts: dict[str, Any],
    *,
    stage: str = "question",
) -> dict[str, Any]:
    verts = tuple(facts.get("vertices") or ())
    if len(verts) < 4:
        verts = ("A", "B", "C", "D")
    a_name, b_name, c_name, d_name = verts[:4]
    given_angles: dict[str, float] = dict(facts.get("angles") or {})
    angles: dict[str, float] = dict(given_angles)
    lengths: dict[str, str] = dict(facts.get("lengths") or {})
    points = {
        a_name: (16.0, 84.0),
        b_name: (86.0, 84.0),
        c_name: (78.0, 16.0),
        d_name: (22.0, 28.0),
    }
    missing = [name for name in (a_name, b_name, c_name, d_name) if name not in given_angles]
    if stage == "answer" and len(missing) == 1:
        leftover = 360.0 - sum(
            given_angles[name]
            for name in (a_name, b_name, c_name, d_name)
            if name in given_angles
        )
        if leftover > 0:
            angles[missing[0]] = leftover
    side_pairs = (
        (a_name, b_name, "ab"),
        (b_name, c_name, "bc"),
        (c_name, d_name, "cd"),
        (d_name, a_name, "da"),
    )
    elements: list[dict[str, Any]] = [
        {
            "kind": "polygon",
            "points": [
                _xy(points[a_name]),
                _xy(points[b_name]),
                _xy(points[c_name]),
                _xy(points[d_name]),
            ],
            "labels": [a_name, b_name, c_name, d_name],
            "id": "quad",
        }
    ]
    for start, end, part_id in side_pairs:
        key = "".join(sorted((start, end)))
        elements.append(
            {
                "kind": "segment",
                "from": _xy(points[start]),
                "to": _xy(points[end]),
                "label": lengths.get(key, ""),
                "id": part_id,
                "caption": f"Side {start}{end}.",
            }
        )
    for vertex, start, end, part_id in (
        (a_name, b_name, d_name, "angle-a"),
        (b_name, a_name, c_name, "angle-b"),
        (c_name, b_name, d_name, "angle-c"),
        (d_name, c_name, a_name, "angle-d"),
    ):
        labelled = vertex in given_angles or (stage == "answer" and vertex in angles)
        label = format_degree(angles[vertex]) if labelled and vertex in angles else ""
        item: dict[str, Any] = {
            "kind": "angle",
            "at": _xy(points[vertex]),
            "from": _xy(points[start]),
            "to": _xy(points[end]),
            "label": label,
            "id": part_id,
            "caption": f"Angle at {vertex}" + (f" = {label}." if label else "."),
        }
        if labelled and vertex in angles and abs(angles[vertex] - 90.0) < 0.51:
            item["right"] = True
        elements.append(item)
    actions = [
        {
            "id": "givens",
            "label": "Givens",
            "highlight": ["angle-a", "angle-b", "angle-c", "angle-d", "ab", "bc", "cd", "da"],
            "caption": "Click a vertex or side. Named givens stay labelled on the figure.",
        }
    ]
    title = f"Quadrilateral {a_name}{b_name}{c_name}{d_name}"
    caption = "Given vertices and angles are marked. Click a part to highlight it."
    if stage == "answer" and missing and missing[0] in angles:
        found = format_degree(angles[missing[0]])
        caption = (
            f"{missing[0]} = {found} because the interior angles of a quadrilateral "
            "sum to 360°."
        )
        actions.append(
            {
                "id": "sum",
                "label": "Angle sum",
                "highlight": ["angle-a", "angle-b", "angle-c", "angle-d"],
                "caption": caption,
            }
        )
    spec = {
        "type": "geometry",
        "interactive": True,
        "title": title if stage == "question" else f"{title} ({stage})",
        "caption": caption,
        "actions": actions,
        "elements": elements,
    }
    parsed = _validated(spec)
    return parsed or spec


def labelled_triangle_figure(
    facts: dict[str, Any],
    *,
    stage: str = "question",
) -> dict[str, Any]:
    verts = tuple(facts.get("vertices") or ())
    if len(verts) < 3:
        verts = ("A", "B", "C")
    a_name, b_name, c_name = verts[:3]
    given_angles: dict[str, float] = dict(facts.get("angles") or {})
    angles: dict[str, float] = dict(given_angles)
    lengths: dict[str, str] = dict(facts.get("lengths") or {})
    point_a = (16.0, 86.0)
    point_b = (84.0, 86.0)
    ang_a = angles.get(a_name)
    ang_b = angles.get(b_name)
    point_c = (50.0, 18.0)
    if ang_a and ang_b:
        rad_a = math.radians(ang_a)
        rad_b = math.radians(ang_b)
        hit = _intersect(
            point_a,
            (math.cos(rad_a), -math.sin(rad_a)),
            point_b,
            (math.cos(math.pi - rad_b), -math.sin(math.pi - rad_b)),
        )
        if hit and 6 <= hit[0] <= 94 and 6 <= hit[1] <= 90:
            point_c = hit
    if c_name in given_angles and a_name in given_angles and b_name not in given_angles:
        angles[b_name] = 180.0 - angles[a_name] - angles[c_name]
    if (
        stage == "answer"
        and a_name in given_angles
        and b_name in given_angles
        and c_name not in given_angles
    ):
        leftover = 180.0 - angles[a_name] - angles[b_name]
        if leftover > 0:
            angles[c_name] = leftover
    points = {a_name: point_a, b_name: point_b, c_name: point_c}
    side_pairs = (
        (a_name, b_name, "ab"),
        (b_name, c_name, "bc"),
        (c_name, a_name, "ca"),
    )
    elements: list[dict[str, Any]] = [
        {
            "kind": "polygon",
            "points": [_xy(point_a), _xy(point_b), _xy(point_c)],
            "labels": [a_name, b_name, c_name],
            "id": "tri",
        }
    ]
    for start, end, part_id in side_pairs:
        key = "".join(sorted((start, end)))
        elements.append(
            {
                "kind": "segment",
                "from": _xy(points[start]),
                "to": _xy(points[end]),
                "label": lengths.get(key, ""),
                "id": part_id,
                "caption": f"Side {start}{end}.",
            }
        )
    for vertex, start, end, part_id in (
        (a_name, b_name, c_name, "angle-a"),
        (b_name, a_name, c_name, "angle-b"),
        (c_name, a_name, b_name, "angle-c"),
    ):
        label = ""
        if vertex in given_angles or (stage == "answer" and vertex in angles):
            label = format_degree(angles[vertex]) if vertex in angles else ""
        elements.append(
            {
                "kind": "angle",
                "at": _xy(points[vertex]),
                "from": _xy(points[start]),
                "to": _xy(points[end]),
                "label": label,
                "id": part_id,
                "caption": f"Angle at {vertex}" + (f" = {label}." if label else "."),
            }
        )
    actions = [
        {
            "id": "givens",
            "label": "Givens",
            "highlight": ["angle-a", "angle-b", "ab", "bc", "ca"],
            "caption": "Click a vertex or side. Named givens stay labelled on the figure.",
        }
    ]
    title = f"Triangle {a_name}{b_name}{c_name}"
    caption = "Given vertices and angles are marked. Click a part to highlight it."
    if facts.get("incircle"):
        side_a = _dist(point_b, point_c)
        side_b = _dist(point_a, point_c)
        side_c = _dist(point_a, point_b)
        perimeter = side_a + side_b + side_c
        incenter = (
            (side_a * point_a[0] + side_b * point_b[0] + side_c * point_c[0]) / perimeter,
            (side_a * point_a[1] + side_b * point_b[1] + side_c * point_c[1]) / perimeter,
        )
        semi = perimeter / 2
        area_sq = max(semi * (semi - side_a) * (semi - side_b) * (semi - side_c), 0)
        radius = (math.sqrt(area_sq) / semi) if semi else 8
        radius = round(max(6.0, min(radius, 18.0)), 2)
        in_xy = _xy(incenter)
        elements.append(
            {
                "kind": "circle",
                "cx": in_xy[0],
                "cy": in_xy[1],
                "r": radius,
                "id": "incircle",
                "caption": "Incircle touching AB, BC, and CA.",
            }
        )
        def foot(p: tuple[float, float], q: tuple[float, float]) -> tuple[float, float]:
            qx, qy = q[0] - p[0], q[1] - p[1]
            length = _dist(p, q) or 1
            t = ((incenter[0] - p[0]) * qx + (incenter[1] - p[1]) * qy) / (length * length)
            t = max(0.0, min(1.0, t))
            return (p[0] + t * qx, p[1] + t * qy)

        touch = {
            "x": foot(point_a, point_b),
            "y": foot(point_b, point_c),
            "z": foot(point_c, point_a),
        }
        if stage in {"steps", "answer"}:
            elements.append(
                {
                    "kind": "point",
                    "x": in_xy[0],
                    "y": in_xy[1],
                    "label": "I",
                    "id": "incentre",
                    "caption": "Incentre I.",
                }
            )
            for point, label, part_id in (
                (touch["x"], "X", "ix"),
                (touch["y"], "Y", "iy"),
                (touch["z"], "Z", "iz"),
            ):
                pt = _xy(point)
                elements.append(
                    {
                        "kind": "point",
                        "x": pt[0],
                        "y": pt[1],
                        "label": label,
                        "id": part_id.replace("i", "").lower(),
                        "caption": f"Touch point {label}.",
                    }
                )
                elements.append(
                    {
                        "kind": "segment",
                        "from": in_xy,
                        "to": pt,
                        "id": part_id,
                        "caption": f"Radius to {label} (perpendicular to the tangent).",
                    }
                )
            actions.append(
                {
                    "id": "tangents",
                    "label": "Tangents at C",
                    "highlight": ["ca", "bc", "iz", "iy", "angle-c"],
                    "caption": f"The tangents from {c_name} are {c_name}{a_name} and {c_name}{b_name}.",
                }
            )
            caption = (
                f"Incentre I and radii to the touch points. The tangents from {c_name} "
                f"are sides {c_name}{a_name} and {c_name}{b_name}."
            )
            if stage == "answer" and c_name in angles:
                caption = (
                    f"The angle of the tangents from {c_name} is angle {c_name} = "
                    f"{format_degree(angles[c_name])}."
                )
        else:
            caption = (
                f"Incircle of triangle {a_name}{b_name}{c_name}. Given angles stay labelled."
            )
            actions.append(
                {
                    "id": "circle",
                    "label": "Incircle",
                    "highlight": ["incircle", "ab", "bc", "ca"],
                    "caption": "The circle touches all three sides.",
                }
            )
    spec = {
        "type": "geometry",
        "interactive": True,
        "title": title if stage == "question" else f"{title} ({stage})",
        "caption": caption,
        "actions": actions,
        "elements": elements,
    }
    parsed = _validated(spec)
    return parsed or spec


def labelled_circle_figure(
    question: str | None,
    *,
    stage: str = "question",
) -> dict[str, Any]:
    plain = _plain_math_text(question)
    match = _DIAMETER_RE.search(plain)
    diameter_label = _length_label(match.group(1), match.group(2)) if match else ""
    radius = 32.0
    centre = (50.0, 50.0)
    left = (centre[0] - radius, centre[1])
    right = (centre[0] + radius, centre[1])
    elements: list[dict[str, Any]] = [
        {
            "kind": "circle",
            "cx": centre[0],
            "cy": centre[1],
            "r": radius,
            "id": "circle",
            "caption": "The full circumference. Nothing is cut off.",
        },
        {
            "kind": "segment",
            "from": list(left),
            "to": list(right),
            "label": diameter_label or "d",
            "id": "diameter",
            "caption": f"Diameter {diameter_label}.".strip() if diameter_label else "Diameter.",
        },
        {
            "kind": "point",
            "x": centre[0],
            "y": centre[1],
            "label": "O",
            "id": "centre",
            "caption": "Centre O.",
        },
    ]
    title = "Circular fountain" if "fountain" in plain.lower() else "Circle"
    if diameter_label:
        title = f"{title} (diameter {diameter_label})"
    caption = "The complete circle is shown. Click the diameter or the centre."
    if stage == "answer" and match:
        diameter = float(match.group(1))
        rad = diameter / 2.0
        area = math.pi * rad * rad
        unit = (match.group(2) or "m").strip()
        if unit.lower() in {"meter", "meters", "metre", "metres"}:
            unit = "m"
        caption = f"Area = πr² with r = {rad:g} {unit}. A = {area:.2f} {unit}²."
        title = f"{title} (answer)" if "answer" not in title else title
    spec = {
        "type": "geometry",
        "interactive": True,
        "title": title,
        "caption": caption,
        "actions": [
            {
                "id": "diameter",
                "label": "Diameter",
                "highlight": ["diameter", "centre", "circle"],
                "caption": caption,
            }
        ],
        "elements": elements,
    }
    parsed = _validated(spec)
    return parsed or spec


def _mentions_quadrilateral(question: str | None, facts: dict[str, Any]) -> bool:
    if facts.get("shape") == "quadrilateral":
        return True
    if len(facts.get("vertices") or ()) >= 4:
        return True
    plain = _plain_math_text(question)
    if _QUAD_RE.search(plain):
        return True
    lowered = plain.lower()
    return any(
        word in lowered
        for word in (
            "quadrilateral",
            "parallelogram",
            "rhombus",
            "trapezium",
            "trapezoid",
        )
    )


def figure_from_question(
    question: str | None,
    *,
    stage: str = "question",
    topic: str | None = None,
) -> dict[str, Any] | None:
    facts = _given_facts(question)
    plain = _plain_math_text(question)
    lowered = plain.lower()
    if _mentions_quadrilateral(question, facts):
        return labelled_quadrilateral_figure(facts, stage=stage)
    if facts["labels"] or facts["incircle"] or _TRIANGLE_RE.search(plain):
        if (
            "triangle" in lowered
            or "△" in (question or "")
            or facts["incircle"]
            or (facts["angles"] and len(facts.get("vertices") or ()) <= 3)
        ):
            return labelled_triangle_figure(facts, stage=stage)
    if _CIRCLE_WORD_RE.search(plain) or _DIAMETER_RE.search(plain):
        return labelled_circle_figure(question, stage=stage)
    return None


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
    from .dse_topics import figure_topic_key

    return default_create_figure(figure_topic_key(topic_id))


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
    question: str | None = None,
) -> dict[str, Any]:
    required = given_labels_from_text(question)
    parsed = parse_figure_spec(figure) if figure else None
    if parsed and figure_spec_has_labels(parsed, required):
        return parsed
    built = figure_from_question(question, stage="question", topic=topic)
    if built:
        return built
    if parsed:
        return parsed
    return default_create_figure(topic)


def default_solve_figure(
    topic: str | None = None,
    question: str | None = None,
    *,
    stage: str = "question",
) -> dict[str, Any]:
    built = figure_from_question(question, stage=stage, topic=topic)
    if built:
        return built
    text = (question or "").lower()
    if any(word in text for word in ("sector", "arc length", "arc ")):
        return _validated(ARC_SECTOR_FIGURE) or default_create_figure(None)
    if _mentions_quadrilateral(question, _given_facts(question)):
        return labelled_quadrilateral_figure(_given_facts(question), stage=stage)
    if _CIRCLE_WORD_RE.search(question or "") or _DIAMETER_RE.search(_plain_math_text(question)):
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
    reveal_answer: bool = False,
) -> str:
    text = reply or ""
    required = given_labels_from_text(question)
    has_fence = FIGURE_FENCE_MARK in text
    covering = (not required and (has_fence or already_has_figure)) or (
        has_fence and figure_text_has_labels(text, required)
    )
    extras: list[dict[str, Any]] = []
    answer_fig = (
        figure_from_question(question, stage="answer", topic=topic) if reveal_answer else None
    )
    if not covering:
        if already_has_figure and not reveal_answer:
            extras.append(default_solve_figure(topic, question, stage="steps"))
        else:
            extras.append(default_solve_figure(topic, question, stage="question"))
        if answer_fig:
            extras.append(answer_fig)
    elif answer_fig:
        extras.append(answer_fig)
    if not extras:
        return text
    blocks = "\n\n".join(figure_fence(spec) for spec in extras)
    return text.rstrip() + "\n\n" + blocks


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
