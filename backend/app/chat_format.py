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
MAX_SCENARIO_CHARS = 600
ALLOWED_FIGURE_TYPES = frozenset({"geometry", "coordinate", "number_line", "chart"})
ALLOWED_FIGURE_KINDS = frozenset(
    {"point", "segment", "line", "polygon", "circle", "angle", "label", "text", "arrow"}
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
        return item
    if kind in {"segment", "arrow"}:
        start = _point(row.get("from") or row.get("start"))
        end = _point(row.get("to") or row.get("end"))
        if not start or not end:
            return None
        item["from"] = start
        item["to"] = end
        item["label"] = _clip_label(row.get("label"))
        return item
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
        return item
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
        return item
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
        return item
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
        return item
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
                value = _finite_number(row.get("value") or row.get("x"))
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
    caption = _clip_label(data.get("caption"))
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
    return spec


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
