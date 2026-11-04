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
