"""Store uploaded RAG files, extract text, and build chat context.

Files live under ``$DATA_DIR/uploads/``. Extracts are ``$DATA_DIR/extracts/<id>.txt``.
The index is ``$DATA_DIR/rag-files.json``. Extraction failures are recorded; they
do not raise. Legacy ``.doc`` and ``.xls`` are accepted and marked as needing
conversion. ``.pptx`` is not accepted (no extra dependency).
"""

from __future__ import annotations

import csv
import io
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_CONTEXT_CHARS = 80_000
MAX_CSV_ROWS = 200
MAX_JSON_CHARS = 200_000
MAX_XLSX_ROWS_PER_SHEET = 200
SOURCE_EXCERPT_CHARS = 160
SOURCE_MARKER = re.compile(r"\[source:\s*([^\]]+?)\s*\]", re.IGNORECASE)

INDEX_NAME = "rag-files.json"
UPLOADS_DIRNAME = "uploads"
EXTRACTS_DIRNAME = "extracts"

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".doc",
    ".txt",
    ".md",
    ".xlsx",
    ".xls",
    ".csv",
    ".json",
}

DOC_CONVERSION_NOTE = (
    "This .doc file needs conversion to .docx or .txt before text can be extracted."
)
XLS_CONVERSION_NOTE = (
    "This .xls file needs conversion to .xlsx before text can be extracted."
)
NO_DOCUMENTS_SYSTEM = (
    "You have no uploaded documents. Tell the user you have no uploaded documents. "
    "Do not invent file contents."
)
GROUNDED_SYSTEM = (
    "Rely on the uploaded document extracts when answering. "
    "Do not invent file contents. If the extracts do not contain the answer, say so. "
    "After claims that come from an extract, cite the file as [source: <filename>]."
)


class RagError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def uploads_dir(data_dir: Path) -> Path:
    path = Path(data_dir) / UPLOADS_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def extracts_dir(data_dir: Path) -> Path:
    path = Path(data_dir) / EXTRACTS_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def index_path(data_dir: Path) -> Path:
    return Path(data_dir) / INDEX_NAME


def extract_path(data_dir: Path, file_id: str) -> Path:
    return extracts_dir(data_dir) / f"{file_id}.txt"


def content_href(file_id: str) -> str:
    return f"/api/rag/files/{file_id}/content"


def excerpt_of(text: str, limit: int = SOURCE_EXCERPT_CHARS) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip()


def parse_source_markers(reply: str) -> list[str]:
    return [match.group(1).strip() for match in SOURCE_MARKER.finditer(reply or "")]


def order_sources(sources: list[dict[str, str]], reply: str) -> list[dict[str, str]]:
    """Keep every context file; put model-cited names first when markers are present."""
    cited = parse_source_markers(reply)
    if not cited:
        return list(sources)
    by_name = {row["name"]: row for row in sources}
    seen: set[str] = set()
    ordered: list[dict[str, str]] = []
    for name in cited:
        row = by_name.get(name)
        if row and row["id"] not in seen:
            ordered.append(row)
            seen.add(row["id"])
    for row in sources:
        if row["id"] not in seen:
            ordered.append(row)
            seen.add(row["id"])
    return ordered


def get_stored_file(data_dir: Path, file_id: str) -> tuple[Path, str]:
    chosen = file_id.strip()
    if not chosen or "/" in chosen or "\\" in chosen:
        raise RagError(404, "File not found.")
    match = next((row for row in load_index(data_dir) if row.get("id") == chosen), None)
    if match is None:
        raise RagError(404, "File not found.")
    root = Path(data_dir).resolve()
    stored = (root / str(match.get("stored_path") or "")).resolve()
    if root not in stored.parents:
        raise RagError(404, "File not found.")
    if not stored.is_file():
        raise RagError(404, "File not found.")
    name = Path(str(match.get("name") or stored.name)).name or stored.name
    return stored, name


def extension_of(filename: str) -> str:
    return Path(filename).suffix.lower()


def public_record(row: dict[str, Any]) -> dict[str, Any]:
    record = {
        "id": row["id"],
        "name": row["name"],
        "size": row["size"],
        "type": row["type"],
        "stored_path": row["stored_path"],
        "extracted_chars": row["extracted_chars"],
        "created_at": row["created_at"],
    }
    if row.get("extract_error"):
        record["extract_error"] = row["extract_error"]
    return record


def load_index(data_dir: Path) -> list[dict[str, Any]]:
    path = index_path(data_dir)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    files = raw.get("files") if isinstance(raw, dict) else None
    if not isinstance(files, list):
        return []
    return [row for row in files if isinstance(row, dict) and row.get("id")]


def save_index(data_dir: Path, files: list[dict[str, Any]]) -> None:
    path = index_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"files": files}
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _decode_text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _extract_csv(data: bytes) -> str:
    text = _decode_text(data)
    reader = csv.reader(io.StringIO(text))
    rows: list[list[str]] = []
    truncated = False
    for index, row in enumerate(reader):
        if index >= MAX_CSV_ROWS:
            truncated = True
            break
        rows.append([str(cell) for cell in row])
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    header = normalized[0]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in normalized[1:]:
        lines.append("| " + " | ".join(row) + " |")
    if truncated:
        lines.append(f"| ... | truncated after {MAX_CSV_ROWS} rows |")
    return "\n".join(lines)


def _extract_json(data: bytes) -> str:
    text = _decode_text(data)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text[:MAX_JSON_CHARS]
    pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
    if len(pretty) > MAX_JSON_CHARS:
        return pretty[:MAX_JSON_CHARS] + "\n... truncated ..."
    return pretty


def _extract_xlsx(data: bytes) -> str:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    blocks: list[str] = []
    try:
        for sheet in workbook.worksheets:
            lines = [f"# {sheet.title}"]
            for index, row in enumerate(sheet.iter_rows(values_only=True)):
                if index >= MAX_XLSX_ROWS_PER_SHEET:
                    lines.append(f"... truncated after {MAX_XLSX_ROWS_PER_SHEET} rows")
                    break
                cells = ["" if cell is None else str(cell) for cell in row]
                lines.append(" | ".join(cells))
            blocks.append("\n".join(lines))
    finally:
        workbook.close()
    return "\n\n".join(blocks)


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append(f"## Page {index}\n{text}".rstrip())
    return "\n\n".join(pages)


def _extract_docx(data: bytes) -> str:
    from docx import Document

    document = Document(io.BytesIO(data))
    parts: list[str] = [paragraph.text for paragraph in document.paragraphs if paragraph.text]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            parts.append(" | ".join(cells))
    return "\n".join(parts)


def extract_text(suffix: str, data: bytes) -> tuple[str, str | None]:
    """Return ``(text, error)``. ``error`` is set when extraction fails or is skipped."""
    try:
        if suffix in {".txt", ".md"}:
            return _decode_text(data), None
        if suffix == ".csv":
            return _extract_csv(data), None
        if suffix == ".json":
            return _extract_json(data), None
        if suffix == ".xlsx":
            return _extract_xlsx(data), None
        if suffix == ".xls":
            return "", XLS_CONVERSION_NOTE
        if suffix == ".pdf":
            return _extract_pdf(data), None
        if suffix == ".docx":
            return _extract_docx(data), None
        if suffix == ".doc":
            return "", DOC_CONVERSION_NOTE
    except Exception as exc:
        kind = suffix.lstrip(".") or "file"
        return "", f"Could not extract text from this {kind} file ({type(exc).__name__})."
    return "", f"No extractor for {suffix}."


def list_files(data_dir: Path) -> list[dict[str, Any]]:
    return [public_record(row) for row in load_index(data_dir)]


def save_upload(data_dir: Path, *, filename: str, data: bytes) -> dict[str, Any]:
    name = Path(filename or "").name.strip()
    if not name:
        raise RagError(400, "Upload must include a filename.")
    suffix = extension_of(name)
    if suffix not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise RagError(400, f"Unsupported file type. Accepted extensions: {allowed}.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise RagError(400, "File exceeds the 10 MB limit.")

    file_id = uuid.uuid4().hex
    stored_name = f"{file_id}{suffix}"
    stored_rel = f"{UPLOADS_DIRNAME}/{stored_name}"
    stored_abs = uploads_dir(data_dir) / stored_name
    stored_abs.write_bytes(data)

    text, extract_error = extract_text(suffix, data)
    extract_abs = extract_path(data_dir, file_id)
    extract_abs.write_text(text, encoding="utf-8")

    row: dict[str, Any] = {
        "id": file_id,
        "name": name,
        "size": len(data),
        "type": suffix.lstrip("."),
        "stored_path": stored_rel,
        "extracted_chars": len(text),
        "created_at": _utc_now(),
    }
    if extract_error:
        row["extract_error"] = extract_error

    files = load_index(data_dir)
    files.append(row)
    save_index(data_dir, files)
    return public_record(row)


def delete_file(data_dir: Path, file_id: str) -> dict[str, Any]:
    chosen = file_id.strip()
    files = load_index(data_dir)
    match = next((row for row in files if row.get("id") == chosen), None)
    if match is None:
        raise RagError(404, "File not found.")
    stored = Path(data_dir) / str(match.get("stored_path") or "")
    if stored.is_file():
        stored.unlink()
    extracted = extract_path(data_dir, chosen)
    if extracted.is_file():
        extracted.unlink()
    save_index(data_dir, [row for row in files if row.get("id") != chosen])
    return {"ok": True, "id": chosen}


def load_extracts(data_dir: Path) -> list[dict[str, str]]:
    extracts: list[dict[str, str]] = []
    for row in load_index(data_dir):
        file_id = str(row["id"])
        name = str(row.get("name") or file_id)
        path = extract_path(data_dir, file_id)
        text = ""
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                text = ""
        error = row.get("extract_error")
        if not text and error:
            text = f"[extract unavailable: {error}]"
        extracts.append({"id": file_id, "name": name, "text": text})
    return extracts


def _source_record(extract: dict[str, str]) -> dict[str, str]:
    return {
        "id": extract["id"],
        "name": extract["name"],
        "href": content_href(extract["id"]),
        "excerpt": excerpt_of(extract["text"]),
    }


def build_rag_context(
    data_dir: Path, message: str
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return chat messages and the files actually stuffed into the prompt."""
    extracts = load_extracts(data_dir)
    if not extracts:
        return (
            [
                {"role": "system", "content": NO_DOCUMENTS_SYSTEM},
                {"role": "user", "content": message},
            ],
            [],
        )

    remaining = MAX_CONTEXT_CHARS
    parts: list[str] = []
    sources: list[dict[str, str]] = []
    for extract in extracts:
        name = extract["name"]
        text = extract["text"]
        header = f"\n\n----- {name} -----\n"
        if remaining <= len(header):
            break
        budget = remaining - len(header)
        chunk = text[:budget]
        parts.append(header + chunk)
        remaining -= len(header) + len(chunk)
        sources.append(_source_record(extract))
        if remaining <= 0:
            break

    system = GROUNDED_SYSTEM + "\n\nUploaded extracts:" + "".join(parts)
    return (
        [
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ],
        sources,
    )


def build_rag_messages(data_dir: Path, message: str) -> list[dict[str, str]]:
    messages, _sources = build_rag_context(data_dir, message)
    return messages
