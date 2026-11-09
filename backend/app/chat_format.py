"""Parse rules mirrored by ``static/chat_format.js``.

The functions page renders assistant replies in the browser. This module is
the same contract for tests. The HTML page cannot import it.
"""

from __future__ import annotations

import json
import re
from typing import Any

TABLE_SEP_RE = re.compile(r"^\s*\|?(?:\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$")
SAFE_HREF_RE = re.compile(r"^(https?://|/api/rag/)", re.IGNORECASE)
MAX_FIGURE_ELEMENTS = 48
MAX_POLYGON_POINTS = 16
MAX_LABEL_CHARS = 48
MAX_CAPTION_CHARS = 180
MAX_SCENARIO_CHARS = 600
ALLOWED_FIGURE_TYPES = frozenset({"geometry", "coordinate", "number_line", "chart"})
ALLOWED_FIGURE_KINDS = frozenset(
    {
        "point",
        "segment",
        "line",
        "polygon",
        "circle",
        "angle",
        "label",
        "text",
        "arrow",
        "arc",
        "sector",
    }
)


def escape_html(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def is_safe_href(href: str) -> bool:
    return bool(SAFE_HREF_RE.match((href or "").strip()))


def parse_chart_fence(body: str | None) -> dict[str, Any] | None:
    text = (body or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    raw_type = data.get("type")
    chart_type = "bar" if raw_type in (None, "") else str(raw_type).lower()
    if chart_type not in {"bar", "line", "pie"}:
        return None

    labels_raw = data.get("labels")
    if not isinstance(labels_raw, list) or not labels_raw:
        return None
    labels = [str(item) for item in labels_raw]

    series_raw = data.get("series")
    if not isinstance(series_raw, list) or not series_raw:
        return None
    series: list[dict[str, Any]] = []
    for row in series_raw:
        if not isinstance(row, dict) or not isinstance(row.get("values"), list):
            return None
        values_raw = row["values"]
        if len(values_raw) != len(labels):
            return None
        values: list[float] = []
        for item in values_raw:
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                try:
                    number = float(item)
                except (TypeError, ValueError):
                    return None
            else:
                number = float(item)
            if number != number or number in {float("inf"), float("-inf")}:
                return None
            values.append(number)
        name = "Series" if row.get("name") is None else str(row.get("name"))
        series.append({"name": name, "values": values})

    if chart_type == "pie":
        series = [series[0]]

    title = "" if data.get("title") is None else str(data.get("title"))
    return {"type": chart_type, "title": title, "labels": labels, "series": series}


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
    else:
        number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        return None
    return number


def _clip_label(value: Any) -> str:
    return str(value or "").strip()[:MAX_LABEL_CHARS]


def _clip_caption(value: Any) -> str:
    return str(value or "").strip()[:MAX_CAPTION_CHARS]


def _attach_part(item: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    part = _clip_label(row.get("id") or row.get("part"))
    if part:
        item["id"] = part
    match = _clip_label(row.get("match"))
    if match:
        item["match"] = match
    caption = _clip_caption(row.get("caption") or row.get("hint"))
    if caption:
        item["caption"] = caption
    return item


def _point(value: Any) -> list[float] | None:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        x = _finite_number(value[0])
        y = _finite_number(value[1])
        if x is None or y is None:
            return None
        return [x, y]
    if isinstance(value, dict):
        x = _finite_number(value.get("x"))
        y = _finite_number(value.get("y"))
        if x is None or y is None:
            return None
        return [x, y]
    return None


def _parse_figure_element(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    kind = str(row.get("kind") or row.get("type") or "").strip().lower()
    if kind == "text":
        kind = "label"
    if kind == "line":
        kind = "segment"
    if kind not in ALLOWED_FIGURE_KINDS:
        return None
    item: dict[str, Any] = {"kind": kind}
    if kind == "point":
        x = _finite_number(row.get("x"))
        y = _finite_number(row.get("y"))
        if x is None or y is None:
            point = _point(row.get("at") or row.get("point"))
            if not point:
                return None
            x, y = point
        item["x"] = x
        item["y"] = y
        item["label"] = _clip_label(row.get("label"))
        return _attach_part(item, row)
    if kind in {"segment", "arrow"}:
        start = _point(row.get("from") or row.get("start"))
        end = _point(row.get("to") or row.get("end"))
        if not start or not end:
            return None
        item["from"] = start
        item["to"] = end
        item["label"] = _clip_label(row.get("label"))
        return _attach_part(item, row)
    if kind == "polygon":
        raw_points = row.get("points")
        if not isinstance(raw_points, list) or len(raw_points) < 3:
            return None
        points: list[list[float]] = []
        for raw in raw_points[:MAX_POLYGON_POINTS]:
            point = _point(raw)
            if not point:
                return None
            points.append(point)
        if len(points) < 3:
            return None
        labels_raw = row.get("labels")
        labels = (
            [_clip_label(label) for label in labels_raw[: len(points)]]
            if isinstance(labels_raw, list)
            else []
        )
        item["points"] = points
        item["labels"] = labels
        item["fill"] = bool(row.get("fill", True))
        return _attach_part(item, row)
    if kind == "circle":
        cx = _finite_number(row.get("cx"))
        cy = _finite_number(row.get("cy"))
        radius = _finite_number(row.get("r") or row.get("radius"))
        if cx is None or cy is None or radius is None or radius <= 0:
            centre = _point(row.get("center") or row.get("centre") or row.get("at"))
            if centre is None or radius is None or radius <= 0:
                return None
            cx, cy = centre
        item["cx"] = cx
        item["cy"] = cy
        item["r"] = radius
        item["label"] = _clip_label(row.get("label"))
        return _attach_part(item, row)
    if kind == "arc" or kind == "sector":
        cx = _finite_number(row.get("cx"))
        cy = _finite_number(row.get("cy"))
        radius = _finite_number(row.get("r") or row.get("radius"))
        start = _finite_number(row.get("start") if row.get("start") is not None else row.get("start_deg"))
        end = _finite_number(row.get("end") if row.get("end") is not None else row.get("end_deg"))
        if cx is None or cy is None or radius is None or radius <= 0 or start is None or end is None:
            centre = _point(row.get("center") or row.get("centre") or row.get("at"))
            if centre is None or radius is None or radius <= 0 or start is None or end is None:
                return None
            cx, cy = centre
        item["cx"] = cx
        item["cy"] = cy
        item["r"] = radius
        item["start"] = start
        item["end"] = end
        item["label"] = _clip_label(row.get("label"))
        if kind == "sector":
            item["fill"] = bool(row.get("fill", True))
        return _attach_part(item, row)
    if kind == "angle":
        at = _point(row.get("at") or row.get("vertex"))
        start = _point(row.get("from") or row.get("start"))
        end = _point(row.get("to") or row.get("end"))
        if not at or not start or not end:
            return None
        item["at"] = at
        item["from"] = start
        item["to"] = end
        item["label"] = _clip_label(row.get("label"))
        item["right"] = bool(row.get("right") or row.get("right_angle"))
        return _attach_part(item, row)
    if kind == "label":
        x = _finite_number(row.get("x"))
        y = _finite_number(row.get("y"))
        if x is None or y is None:
            point = _point(row.get("at"))
            if not point:
                return None
            x, y = point
        text = _clip_label(row.get("text") or row.get("label"))
        if not text:
            return None
        item["x"] = x
        item["y"] = y
        item["text"] = text
        return _attach_part(item, row)
    return None


def _parse_number_line(data: dict[str, Any], title: str, caption: str) -> dict[str, Any] | None:
    low = _finite_number(data.get("min"))
    high = _finite_number(data.get("max"))
    if low is None or high is None or high == low:
        return None
    if low > high:
        low, high = high, low
    marks_raw = data.get("marks") or data.get("ticks")
    marks: list[float] = []
    if isinstance(marks_raw, list):
        for item in marks_raw[:24]:
            number = _finite_number(item)
            if number is not None:
                marks.append(number)
    points: list[dict[str, Any]] = []
    raw_points = data.get("points")
    if isinstance(raw_points, list):
        for row in raw_points[:16]:
            if isinstance(row, dict):
                if row.get("value") is not None:
                    value = _finite_number(row.get("value"))
                else:
                    value = _finite_number(row.get("x"))
                if value is None:
                    continue
                points.append({"value": value, "label": _clip_label(row.get("label"))})
            else:
                value = _finite_number(row)
                if value is not None:
                    points.append({"value": value, "label": ""})
    return {
        "type": "number_line",
        "title": title,
        "caption": caption,
        "min": low,
        "max": high,
        "marks": marks,
        "points": points,
    }


def _parse_axes(data: dict[str, Any]) -> dict[str, float] | None:
    raw = data.get("axes") if isinstance(data.get("axes"), dict) else data
    xmin = _finite_number(raw.get("xmin"))
    xmax = _finite_number(raw.get("xmax"))
    ymin = _finite_number(raw.get("ymin"))
    ymax = _finite_number(raw.get("ymax"))
    if xmin is None or xmax is None or ymin is None or ymax is None:
        return None
    if xmin == xmax or ymin == ymax:
        return None
    if xmin > xmax:
        xmin, xmax = xmax, xmin
    if ymin > ymax:
        ymin, ymax = ymax, ymin
    return {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax}


def parse_figure_spec(body: Any) -> dict[str, Any] | None:
    data: Any = body
    if isinstance(body, str):
        text = body.strip()
        if not text:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    raw_type = data.get("type")
    figure_type = "geometry" if raw_type in (None, "") else str(raw_type).lower()
    if figure_type not in ALLOWED_FIGURE_TYPES:
        return None
    title = _clip_label(data.get("title"))
    caption = _clip_caption(data.get("caption"))
    if figure_type == "chart":
        payload = dict(data)
        if str(payload.get("type") or "").lower() == "chart":
            payload["type"] = "bar"
        chart = parse_chart_fence(json.dumps(payload))
        if chart is None:
            return None
        chart["caption"] = caption
        return chart
    if figure_type == "number_line":
        return _parse_number_line(data, title, caption)
    elements_raw = data.get("elements")
    elements: list[dict[str, Any]] = []
    if isinstance(elements_raw, list):
        for row in elements_raw[:MAX_FIGURE_ELEMENTS]:
            item = _parse_figure_element(row)
            if item:
                elements.append(item)
    if not elements:
        return None
    spec: dict[str, Any] = {
        "type": figure_type,
        "title": title,
        "caption": caption,
        "elements": elements,
    }
    axes = _parse_axes(data)
    if axes:
        spec["axes"] = axes
    hint = _clip_caption(data.get("hint"))
    if hint:
        spec["hint"] = hint
    actions = _parse_actions(data.get("actions"))
    if actions:
        spec["actions"] = actions
    if data.get("interactive") or actions or any(el.get("id") for el in elements):
        spec["interactive"] = True
    return spec


def _parse_actions(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for row in raw[:8]:
        if not isinstance(row, dict):
            continue
        label = _clip_label(row.get("label") or row.get("id"))
        if not label:
            continue
        highlight: list[str] = []
        parts = row.get("highlight") or row.get("parts")
        if isinstance(parts, list):
            for item in parts[:16]:
                token = _clip_label(item)
                if token:
                    highlight.append(token)
        out.append(
            {
                "id": _clip_label(row.get("id") or label),
                "label": label,
                "highlight": highlight,
                "caption": _clip_caption(row.get("caption")),
            }
        )
    return out


def clip_scenario(value: Any) -> str:
    return str(value or "").strip()[:MAX_SCENARIO_CHARS]


def _split_table_row(line: str) -> list[str]:
    trimmed = line.strip()
    if trimmed.startswith("|"):
        trimmed = trimmed[1:]
    if trimmed.endswith("|"):
        trimmed = trimmed[:-1]
    return [cell.strip() for cell in trimmed.split("|")]


def markdown_table_to_html(markdown: str) -> str | None:
    lines = [line for line in (markdown or "").replace("\r\n", "\n").split("\n") if line.strip()]
    if len(lines) < 2 or not TABLE_SEP_RE.match(lines[1]):
        return None
    headers = _split_table_row(lines[0])
    if not headers:
        return None
    parts = ["<table>", "<thead>", "<tr>"]
    for header in headers:
        parts.append(f"<th>{escape_html(header)}</th>")
    parts.extend(["</tr>", "</thead>", "<tbody>"])
    for line in lines[2:]:
        if TABLE_SEP_RE.match(line):
            continue
        cells = _split_table_row(line)
        parts.append("<tr>")
        for index in range(len(headers)):
            cell = cells[index] if index < len(cells) else ""
            parts.append(f"<td>{escape_html(cell)}</td>")
        parts.append("</tr>")
        parts.extend(["</tbody>", "</table>"])
    return "".join(parts)


MATH_GREEK = {
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "delta": "δ",
    "Delta": "Δ",
    "epsilon": "ε",
    "varepsilon": "ε",
    "zeta": "ζ",
    "eta": "η",
    "theta": "θ",
    "Theta": "Θ",
    "vartheta": "ϑ",
    "iota": "ι",
    "kappa": "κ",
    "lambda": "λ",
    "mu": "μ",
    "nu": "ν",
    "xi": "ξ",
    "pi": "π",
    "Pi": "Π",
    "rho": "ρ",
    "sigma": "σ",
    "Sigma": "Σ",
    "tau": "τ",
    "upsilon": "υ",
    "phi": "φ",
    "Phi": "Φ",
    "varphi": "φ",
    "chi": "χ",
    "psi": "ψ",
    "omega": "ω",
    "Omega": "Ω",
    "ell": "ℓ",
    "infty": "∞",
    "partial": "∂",
    "nabla": "∇",
    "hbar": "ℏ",
}
MATH_SYMBOLS = {
    "times": "×",
    "div": "÷",
    "cdot": "·",
    "pm": "±",
    "mp": "∓",
    "leq": "≤",
    "geq": "≥",
    "le": "≤",
    "ge": "≥",
    "neq": "≠",
    "ne": "≠",
    "approx": "≈",
    "equiv": "≡",
    "sim": "∼",
    "propto": "∝",
    "circ": "°",
    "degree": "°",
    "angle": "∠",
    "triangle": "△",
    "perp": "⊥",
    "parallel": "∥",
    "in": "∈",
    "to": "→",
    "rightarrow": "→",
    "leftarrow": "←",
    "ldots": "…",
    "cdots": "⋯",
    "dots": "…",
    "therefore": "∴",
    "because": "∵",
    "int": "∫",
    "sum": "∑",
    "prod": "∏",
    "infty": "∞",
}
MATH_FUNCTIONS = frozenset(
    {
        "sin",
        "cos",
        "tan",
        "cot",
        "sec",
        "csc",
        "arcsin",
        "arccos",
        "arctan",
        "sinh",
        "cosh",
        "tanh",
        "log",
        "ln",
        "lg",
        "exp",
        "lim",
        "max",
        "min",
        "det",
        "gcd",
        "arg",
        "deg",
        "dim",
    }
)
MATH_REL = frozenset("=<>≤≥≠≈≡∼∝→←∈")
MATH_BIN = frozenset("+-×÷·±∓")


def _span(cls: str, inner: str, tag: str = "span") -> str:
    if cls:
        return f'<{tag} class="{cls}">{inner}</{tag}>'
    return f"<{tag}>{inner}</{tag}>"


class _MathCursor:
    def __init__(self, src: str) -> None:
        self.src = src or ""
        self.i = 0

    def peek(self) -> str:
        return self.src[self.i] if self.i < len(self.src) else ""

    def skip_space(self) -> None:
        while self.peek() and self.peek().isspace():
            self.i += 1


def _read_command_name(cur: _MathCursor) -> str:
    cur.i += 1
    ch = cur.peek()
    if ch.isalpha():
        name = []
        while cur.peek().isalpha():
            name.append(cur.peek())
            cur.i += 1
        cur.skip_space()
        return "".join(name)
    if ch:
        cur.i += 1
        return ch
    return ""


def _read_math_atom(cur: _MathCursor) -> str | None:
    cur.skip_space()
    ch = cur.peek()
    if not ch:
        return None
    if ch == "}":
        return None
    if ch == "{":
        cur.i += 1
        inner = _parse_math_list(cur, "}")
        return _span("math-group", inner)
    if ch == "\\":
        return _read_math_command(cur)
    if ch in "^_":
        return None
    if ch.isdigit() or (ch == "." and cur.i + 1 < len(cur.src) and cur.src[cur.i + 1].isdigit()):
        start = cur.i
        cur.i += 1
        while cur.peek().isdigit() or cur.peek() == ".":
            cur.i += 1
        return _span("math-numeral", escape_html(cur.src[start : cur.i]))
    if ch.isalpha():
        cur.i += 1
        return _span("math-letter", escape_html(ch))
    cur.i += 1
    glyph = "−" if ch == "-" else ch
    cls = "math-rel" if glyph in MATH_REL else "math-bin" if glyph in MATH_BIN else "math-sym"
    if ch in "()[]|.":
        cls = "math-delim"
    return _span(cls, escape_html(glyph))


def _read_math_command(cur: _MathCursor) -> str:
    name = _read_command_name(cur)
    if name in {"frac", "dfrac", "tfrac"}:
        num = _read_math_atom(cur) or ""
        den = _read_math_atom(cur) or ""
        return _span(
            "math-frac",
            _span("math-num", num) + _span("math-den", den),
        )
    if name == "sqrt":
        body = _read_math_atom(cur) or ""
        return _span(
            "math-sqrt",
            _span("math-radic", "√") + _span("math-radicand", body),
        )
    if name in {"text", "mathrm", "mathbf", "operatorname"}:
        body = _read_math_atom(cur) or ""
        plain = re.sub(r"<[^>]+>", "", body)
        return _span("math-text", plain)
    if name in {"left", "right"}:
        delim = cur.peek()
        if delim == "\\":
            inner = _read_command_name(cur)
            delim = inner or delim
        elif delim:
            cur.i += 1
        if not delim or delim == ".":
            return ""
        return _span("math-delim", escape_html(delim))
    if name in {"quad", "qquad", ",", ";", "!", " "}:
        return _span("math-space", "\u00a0")
    if name in MATH_GREEK:
        return _span("math-sym", MATH_GREEK[name])
    if name in MATH_SYMBOLS:
        glyph = MATH_SYMBOLS[name]
        cls = "math-rel" if glyph in MATH_REL else "math-bin" if glyph in MATH_BIN else "math-sym"
        return _span(cls, glyph)
    if name in MATH_FUNCTIONS:
        return _span("math-fn", escape_html(name))
    if name in {"{", "}", "%", "$", "_", "&", "#"}:
        return _span("math-sym", escape_html(name))
    if name == "\\":
        return "<br>"
    if re.fullmatch(r"[A-Za-z]+", name or ""):
        return _span("math-fn", escape_html(name))
    return _span("math-sym", escape_html(name))


def _attach_script(base: str, kind: str, script: str) -> str:
    tag = "sup" if kind == "sup" else "sub"
    cls = "math-sup" if kind == "sup" else "math-sub"
    return _span("math-scripted", base + f'<{tag} class="{cls}">{script}</{tag}>')


def _parse_math_list(cur: _MathCursor, stop: str | None = None) -> str:
    parts: list[str] = []
    while cur.i < len(cur.src):
        if stop and cur.peek() == stop:
            cur.i += 1
            break
        atom = _read_math_atom(cur)
        if atom is None:
            if stop and cur.peek() == stop:
                cur.i += 1
            break
        while cur.peek() in {"^", "_"}:
            kind = "sup" if cur.peek() == "^" else "sub"
            cur.i += 1
            script = _read_math_atom(cur) or ""
            atom = _attach_script(atom, kind, script)
        parts.append(atom)
    return "".join(parts)


def render_math_html(tex: str, display: bool = False) -> str:
    inner = _parse_math_list(_MathCursor(tex or ""))
    cls = "math-display" if display else "math-inline"
    tag = "div" if display else "span"
    return f'<{tag} class="{cls}" role="math">{inner}</{tag}>'


def split_math_segments(text: str) -> list[tuple[str, str]]:
    src = text or ""
    out: list[tuple[str, str]] = []
    i = 0
    n = len(src)
    while i < n:
        start, opener = _next_math(src, i)
        if start is None:
            out.append(("text", src[i:]))
            break
        if start > i:
            out.append(("text", src[i:start]))
        if opener == "$$":
            end = src.find("$$", start + 2)
            if end < 0:
                out.append(("display", src[start + 2 :]))
                break
            out.append(("display", src[start + 2 : end]))
            i = end + 2
        elif opener == "\\[":
            end = src.find("\\]", start + 2)
            if end < 0:
                out.append(("display", src[start + 2 :]))
                break
            out.append(("display", src[start + 2 : end]))
            i = end + 2
        elif opener == "\\(":
            end = src.find("\\)", start + 2)
            if end < 0:
                out.append(("inline", src[start + 2 :]))
                break
            out.append(("inline", src[start + 2 : end]))
            i = end + 2
        else:
            end = _next_unescaped_dollar(src, start + 1)
            if end < 0:
                out.append(("inline", src[start + 1 :]))
                break
            out.append(("inline", src[start + 1 : end]))
            i = end + 1
    return out


def _next_math(src: str, start: int) -> tuple[int | None, str | None]:
    j = start
    n = len(src)
    while j < n:
        if src.startswith("$$", j):
            return j, "$$"
        if src.startswith("\\[", j):
            return j, "\\["
        if src.startswith("\\(", j):
            return j, "\\("
        if src[j] == "$" and (j == 0 or src[j - 1] != "\\"):
            return j, "$"
        j += 1
    return None, None


def _next_unescaped_dollar(src: str, start: int) -> int:
    j = start
    while j < len(src):
        if src.startswith("$$", j):
            j += 2
            continue
        if src[j] == "$" and src[j - 1] != "\\":
            return j
        j += 1
    return -1


def tex_to_plain(text: str) -> str:
    raw = text or ""
    raw = raw.replace("$$", "").replace("\\[", "").replace("\\]", "")
    raw = raw.replace("\\(", "").replace("\\)", "")
    raw = raw.replace("^\\circ", "°").replace("\\circ", "°")
    frac_re = re.compile(r"\\(?:dfrac|tfrac|frac)\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
    while frac_re.search(raw):
        raw = frac_re.sub(lambda match: f"{match.group(1)}/{match.group(2)}", raw)
    for name, glyph in sorted(MATH_GREEK.items(), key=lambda item: -len(item[0])):
        raw = raw.replace("\\" + name, glyph)
    for name, glyph in sorted(MATH_SYMBOLS.items(), key=lambda item: -len(item[0])):
        raw = raw.replace("\\" + name, glyph)
    for name in sorted(MATH_FUNCTIONS, key=len, reverse=True):
        raw = re.sub(r"\\" + name + r"(?![A-Za-z])", name, raw)
    raw = raw.replace("$", "")
    raw = re.sub(r"\\([A-Za-z]+)", r"\1", raw)
    raw = raw.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", raw).strip()
