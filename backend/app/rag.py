"""Store uploaded RAG and translation files, extract text, and build chat context.

Files live under ``$DATA_DIR/uploads/``. Extracts are ``$DATA_DIR/extracts/<id>.txt``.
The index is ``$DATA_DIR/rag-files.json``. Extraction failures are recorded; they
do not raise. Legacy ``.doc``, ``.xls``, and ``.ppt`` are accepted and marked as
needing conversion. ``.pptx`` is extracted with python-pptx.

Each file is tagged ``collection`` ``rag`` or ``translation`` so the two
libraries do not mix. Legacy rows without a collection are treated as ``rag``.
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
    ".pptx",
    ".ppt",
    ".txt",
    ".md",
    ".xlsx",
    ".xls",
    ".csv",
    ".json",
}
TRANSLATION_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".doc",
    ".pptx",
    ".ppt",
    ".xlsx",
    ".xls",
    ".txt",
    ".md",
}

COLLECTION_RAG = "rag"
COLLECTION_TRANSLATION = "translation"
ALLOWED_COLLECTIONS = frozenset({COLLECTION_RAG, COLLECTION_TRANSLATION})

TARGET_EN = "en"
TARGET_ZH_CN = "zh_cn"
TARGET_ZH_HK = "zh_hk"
ALLOWED_TARGET_LANGUAGES = frozenset({TARGET_EN, TARGET_ZH_CN, TARGET_ZH_HK})
ALLOWED_SOURCE_LANGUAGES = ALLOWED_TARGET_LANGUAGES | {"auto"}
DEFAULT_SOURCE_LANGUAGE = "auto"
DEFAULT_TRANSLATION_MESSAGE = "Translate the uploaded documents."
LANGUAGE_LABELS = {
    TARGET_EN: "English",
    TARGET_ZH_CN: "Simplified Chinese (简体)",
    TARGET_ZH_HK: "Traditional Chinese (繁體)",
}

DOC_CONVERSION_NOTE = (
    "This .doc file needs conversion to .docx or .txt before text can be extracted."
)
XLS_CONVERSION_NOTE = (
    "This .xls file needs conversion to .xlsx before text can be extracted."
)
PPT_CONVERSION_NOTE = (
    "This .ppt file needs conversion to .pptx before text can be extracted."
)
GROUNDING_STRICT = "strict"
GROUNDING_MIXED = "mixed"
ALLOWED_GROUNDING = frozenset({GROUNDING_STRICT, GROUNDING_MIXED})
CITE_INSTRUCTION = (
    "After claims that come from an extract, cite the file as [source: <filename>]."
)
FORMAT_REPLY_INSTRUCTION = (
    "When comparing rows or columns from documents, prefer a Markdown table.\n"
    "When a chart helps, add one fenced block:\n"
    "```chart\n"
    '{"type":"bar|line|pie","title":"...","labels":["A","B"],'
    '"series":[{"name":"Series","values":[1,2]}]}\n'
    "```\n"
    "Still write a short prose answer. Still use [source: filename] when grounded."
)
NO_DOCUMENTS_SYSTEM = (
    "You have no uploaded documents. Tell the user you have no uploaded documents. "
    "Do not invent file contents.\n"
    + FORMAT_REPLY_INSTRUCTION
)
NO_DOCUMENTS_STRICT_REPLY = (
    "There are no uploaded documents to ground on. "
    "I cannot answer from document extracts."
)
STRICT_SYSTEM = (
    "Rely ONLY on the uploaded document extracts. "
    "If they are insufficient, say you cannot answer from the documents. "
    "Do not use outside knowledge. " + CITE_INSTRUCTION
    + "\n" + FORMAT_REPLY_INSTRUCTION
)
MIXED_SYSTEM = (
    "Prefer the uploaded extracts. You may add general knowledge; "
    "when you do, say it is not from the documents. "
    "Do not invent file contents. " + CITE_INSTRUCTION
    + "\n" + FORMAT_REPLY_INSTRUCTION
)
GROUNDED_SYSTEM = MIXED_SYSTEM
TRANSLATION_BASE = (
    "You are a professional translator. "
    "Output the translation in the target language only, except proper nouns "
    "that are conventionally left in their original form. "
    "Do not add commentary, preambles, or a second language unless the user asks."
)
TRANSLATION_TRADITIONAL = (
    "The target is Traditional Chinese (繁體). Write 繁體, not 简体. "
    "Do not convert to Simplified Chinese."
)
TRANSLATION_SIMPLIFIED = (
    "The target is Simplified Chinese (简体). Write 简体, not 繁體. "
    "Do not use 粵文 particles (such as 嘅, 咗, 喺, 唔) unless the user asks for Cantonese."
)
TRANSLATION_ENGLISH = "The target is English. Write natural, fluent English."
TRANSLATION_FILE_HEADINGS = (
    "If several source documents are provided, start each translation with a "
    "Markdown heading using the file name."
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


def file_collection(row: dict[str, Any]) -> str:
    value = row.get("collection")
    if value in ALLOWED_COLLECTIONS:
        return str(value)
    return COLLECTION_RAG


def resolve_collection(value: str | None) -> str:
    chosen = (value or COLLECTION_RAG).strip() or COLLECTION_RAG
    if chosen not in ALLOWED_COLLECTIONS:
        raise RagError(400, "collection must be 'rag' or 'translation'.")
    return chosen


def allowed_extensions_for(collection: str) -> set[str]:
    if collection == COLLECTION_TRANSLATION:
        return TRANSLATION_EXTENSIONS
    return ALLOWED_EXTENSIONS


def public_record(row: dict[str, Any]) -> dict[str, Any]:
    record = {
        "id": row["id"],
        "name": row["name"],
        "size": row["size"],
        "type": row["type"],
        "collection": file_collection(row),
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


def _shape_text(shape: Any) -> list[str]:
    parts: list[str] = []
    if getattr(shape, "has_text_frame", False):
        text = (shape.text_frame.text or "").strip()
        if text:
            parts.append(text)
    if getattr(shape, "has_table", False):
        for row in shape.table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            parts.append(" | ".join(cells))
    return parts


def _extract_pptx(data: bytes) -> str:
    from pptx import Presentation

    presentation = Presentation(io.BytesIO(data))
    slides: list[str] = []
    for index, slide in enumerate(presentation.slides, start=1):
        parts: list[str] = []
        for shape in slide.shapes:
            parts.extend(_shape_text(shape))
        if slide.has_notes_slide:
            notes = (slide.notes_slide.notes_text_frame.text or "").strip()
            if notes:
                parts.append(notes)
        slides.append(f"## Slide {index}\n" + "\n".join(parts) if parts else f"## Slide {index}")
    return "\n\n".join(slides)


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
        if suffix == ".pptx":
            return _extract_pptx(data), None
        if suffix == ".ppt":
            return "", PPT_CONVERSION_NOTE
    except Exception as exc:
        kind = suffix.lstrip(".") or "file"
        return "", f"Could not extract text from this {kind} file ({type(exc).__name__})."
    return "", f"No extractor for {suffix}."


def list_files(data_dir: Path, collection: str = COLLECTION_RAG) -> list[dict[str, Any]]:
    chosen = resolve_collection(collection)
    return [
        public_record(row)
        for row in load_index(data_dir)
        if file_collection(row) == chosen
    ]


def save_upload(
    data_dir: Path,
    *,
    filename: str,
    data: bytes,
    collection: str = COLLECTION_RAG,
) -> dict[str, Any]:
    name = Path(filename or "").name.strip()
    if not name:
        raise RagError(400, "Upload must include a filename.")
    chosen = resolve_collection(collection)
    suffix = extension_of(name)
    allowed = allowed_extensions_for(chosen)
    if suffix not in allowed:
        listed = ", ".join(sorted(allowed))
        raise RagError(400, f"Unsupported file type. Accepted extensions: {listed}.")
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
        "collection": chosen,
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


def load_extracts(
    data_dir: Path,
    collection: str = COLLECTION_RAG,
) -> list[dict[str, str]]:
    chosen = resolve_collection(collection)
    extracts: list[dict[str, str]] = []
    for row in load_index(data_dir):
        if file_collection(row) != chosen:
            continue
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


def grounding_instructions(grounding: str) -> str:
    if grounding == GROUNDING_STRICT:
        return STRICT_SYSTEM
    return MIXED_SYSTEM


def translation_system_prompt(target_language: str, source_language: str) -> str:
    parts = [TRANSLATION_BASE]
    if target_language == TARGET_ZH_HK:
        parts.append(TRANSLATION_TRADITIONAL)
    elif target_language == TARGET_ZH_CN:
        parts.append(TRANSLATION_SIMPLIFIED)
    else:
        parts.append(TRANSLATION_ENGLISH)
    if source_language == DEFAULT_SOURCE_LANGUAGE:
        parts.append("Detect the source language automatically.")
    else:
        label = LANGUAGE_LABELS.get(source_language, source_language)
        parts.append(f"The source language is {label}.")
    parts.append(TRANSLATION_FILE_HEADINGS)
    parts.append(FORMAT_REPLY_INSTRUCTION)
    return "\n".join(parts)


def _stuff_extracts(extracts: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
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
    return "".join(parts), sources


def build_rag_context(
    data_dir: Path,
    message: str,
    grounding: str = GROUNDING_MIXED,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return chat messages and the files actually stuffed into the prompt."""
    extracts = load_extracts(data_dir, collection=COLLECTION_RAG)
    if not extracts:
        return (
            [
                {"role": "system", "content": NO_DOCUMENTS_SYSTEM},
                {"role": "user", "content": message},
            ],
            [],
        )

    stuffed, sources = _stuff_extracts(extracts)
    system = grounding_instructions(grounding) + "\n\nUploaded extracts:" + stuffed
    return (
        [
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ],
        sources,
    )


def build_translation_context(
    data_dir: Path,
    message: str,
    *,
    target_language: str,
    source_language: str = DEFAULT_SOURCE_LANGUAGE,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return translator messages and the translation files stuffed into the prompt."""
    extracts = load_extracts(data_dir, collection=COLLECTION_TRANSLATION)
    system = translation_system_prompt(target_language, source_language)
    if not extracts:
        return (
            [
                {"role": "system", "content": system},
                {"role": "user", "content": message},
            ],
            [],
        )

    stuffed, sources = _stuff_extracts(extracts)
    system = system + "\n\nSource documents:" + stuffed
    return (
        [
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ],
        sources,
    )


def build_rag_messages(
    data_dir: Path,
    message: str,
    grounding: str = GROUNDING_MIXED,
) -> list[dict[str, str]]:
    messages, _sources = build_rag_context(data_dir, message, grounding)
    return messages
