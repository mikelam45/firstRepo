"""Rebuild uploaded translation sources as downloadable files in the same type.

After a translation chat, each source file gets a sibling under
``$DATA_DIR/translated/`` (for example ``report.zh_hk.pdf``). Structure-preserving
replace is attempted for Office files; PDF is always a new document with a simple
layout and an embedded CJK-capable font when one is available.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from .rag import (
    RagError,
    extract_path,
    load_index,
    save_index,
    translated_href,
)

TRANSLATED_DIRNAME = "translated"
TRANSLATED_NOT_FOUND = "Translated file not found."

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
PAGE_HEADING_RE = re.compile(r"^##\s+Page\s+(\d+)\s*$", re.MULTILINE | re.IGNORECASE)
SLIDE_HEADING_RE = re.compile(r"^##\s+Slide\s+(\d+)\s*$", re.MULTILINE | re.IGNORECASE)
JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

_FONT_NAME: str | None = None

BUNDLED_FONTS_DIR = Path(__file__).resolve().parent / "fonts"

SYSTEM_FONT_CANDIDATES = (
    # Linux CJK (TTF first so reportlab does not need a collection index)
    Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"),
    Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansSC-Regular.otf"),
    Path("/usr/share/fonts/truetype/noto/NotoSansTC-Regular.otf"),
    Path("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"),
    # macOS
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/System/Library/Fonts/STHeiti Light.ttc"),
    Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
    # Windows
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
    Path("C:/Windows/Fonts/simsun.ttc"),
    # Latin fallback
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    Path("/Library/Fonts/Arial.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
)

MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".ppt": "application/vnd.ms-powerpoint",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
}


def translated_dir(data_dir: Path) -> Path:
    path = Path(data_dir) / TRANSLATED_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def translated_download_href(file_id: str) -> str:
    return f"/api/translation/files/{file_id}/download"


def translated_filename(original: str, target_language: str) -> str:
    path = Path(original or "document")
    stem = path.stem or "document"
    suffix = path.suffix.lower()
    lang = (target_language or "en").strip() or "en"
    return f"{stem}.{lang}{suffix}"


def media_type_for(filename: str) -> str | None:
    return MEDIA_TYPES.get(Path(filename).suffix.lower())


def _artifact(file_id: str, name: str, source_name: str) -> dict[str, str]:
    return {
        "id": file_id,
        "name": name,
        "href": translated_href(file_id),
        "source_name": source_name,
    }


def candidate_font_paths() -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        try:
            resolved = path.resolve()
        except OSError:
            return
        key = str(resolved)
        if key in seen or not resolved.is_file():
            return
        seen.add(key)
        found.append(resolved)

    if BUNDLED_FONTS_DIR.is_dir():
        for suffix in ("*.ttf", "*.otf", "*.ttc"):
            for path in sorted(BUNDLED_FONTS_DIR.glob(suffix)):
                add(path)
    for path in SYSTEM_FONT_CANDIDATES:
        add(path)
    return found


def register_cjk_font() -> str:
    """Register a Unicode TTF/TTC with reportlab. Prefer CJK, then DejaVu, then Helvetica."""
    global _FONT_NAME
    if _FONT_NAME:
        return _FONT_NAME
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for path in candidate_font_paths():
        for index in (0, 1):
            try:
                pdfmetrics.registerFont(TTFont("PortalCJK", str(path), subfontIndex=index))
                _FONT_NAME = "PortalCJK"
                return _FONT_NAME
            except Exception:
                continue
    _FONT_NAME = "Helvetica"
    return _FONT_NAME


def split_paragraphs(text: str) -> list[str]:
    cleaned = (text or "").replace("\r\n", "\n").strip()
    if not cleaned:
        return []
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict) and isinstance(parsed.get("paragraphs"), list):
        values = [str(item).strip() for item in parsed["paragraphs"] if str(item).strip()]
        if values:
            return values
    fenced = JSON_FENCE_RE.search(cleaned)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1))
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict) and isinstance(parsed.get("paragraphs"), list):
            values = [str(item).strip() for item in parsed["paragraphs"] if str(item).strip()]
            if values:
                return values
    blocks = [re.sub(r"[ \t]+", " ", block).strip() for block in re.split(r"\n\s*\n", cleaned)]
    blocks = [block for block in blocks if block]
    if len(blocks) <= 1:
        lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
        if len(lines) > 1:
            return lines
    return blocks


def split_marked_sections(text: str, pattern: re.Pattern[str]) -> list[str] | None:
    matches = list(pattern.finditer(text or ""))
    if not matches:
        return None
    sections: list[str] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text or "")
        sections.append((text or "")[start:end].strip())
    return sections


def _match_filename(title: str, names: list[str]) -> str | None:
    lowered = title.strip().strip("*").strip("`").lower()
    for name in names:
        if name.lower() == lowered:
            return name
    for name in names:
        if name.lower() in lowered or lowered in name.lower():
            return name
    return None


def _strip_filename_heading(text: str, filename: str) -> str:
    cleaned = (text or "").replace("\r\n", "\n").strip()
    match = HEADING_RE.match(cleaned)
    if match and _match_filename(match.group(2), [filename]):
        return cleaned[match.end() :].lstrip("\n")
    return cleaned


def translations_for_files(reply: str, names: list[str]) -> dict[str, str]:
    """Map a translation chat reply onto source filenames."""
    names = [name for name in names if name]
    if not names:
        return {}
    if len(names) == 1:
        return {names[0]: _strip_filename_heading(reply or "", names[0])}

    matches: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for match in HEADING_RE.finditer(reply or ""):
        matched = _match_filename(match.group(2), names)
        if matched and matched not in seen:
            matches.append((match.start(), match.end(), matched))
            seen.add(matched)
    if not matches:
        return {name: reply or "" for name in names}

    result: dict[str, str] = {}
    for index, (_start, end, name) in enumerate(matches):
        body_end = matches[index + 1][0] if index + 1 < len(matches) else len(reply or "")
        result[name] = (reply or "")[end:body_end].strip()
    for name in names:
        result.setdefault(name, "")
    return result


def _can_structure_replace(target_count: int, paragraph_count: int) -> bool:
    if target_count <= 0 or paragraph_count <= 0:
        return False
    if paragraph_count == target_count:
        return True
    if paragraph_count > target_count:
        return True
    return paragraph_count >= max(2, target_count // 2)


def _align_to_count(paragraphs: list[str], count: int) -> list[str]:
    if count <= 0:
        return []
    if len(paragraphs) == count:
        return list(paragraphs)
    if len(paragraphs) > count:
        if count == 1:
            return ["\n\n".join(paragraphs)]
        head = paragraphs[: count - 1]
        tail = "\n\n".join(paragraphs[count - 1 :])
        return head + [tail]
    return list(paragraphs) + [""] * (count - len(paragraphs))


def _set_docx_paragraph_text(paragraph: Any, text: str) -> None:
    runs = paragraph.runs
    if runs:
        runs[0].text = text
        for run in runs[1:]:
            run.text = ""
        return
    paragraph.add_run(text)


def _iter_docx_paragraphs(document: Any) -> list[Any]:
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    paragraphs: list[Any] = []
    seen_cells: set[int] = set()

    def walk_table(table: Any) -> None:
        for row in table.rows:
            for cell in row.cells:
                ident = id(cell._tc)
                if ident in seen_cells:
                    continue
                seen_cells.add(ident)
                for para in cell.paragraphs:
                    paragraphs.append(para)
                for nested in cell.tables:
                    walk_table(nested)

    body = document.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            paragraphs.append(Paragraph(child, document))
        elif child.tag == qn("w:tbl"):
            walk_table(Table(child, document))
    return paragraphs


def _iter_pptx_shapes(shapes: Any) -> Any:
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    for shape in shapes:
        yield shape
        try:
            if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                yield from _iter_pptx_shapes(shape.shapes)
        except Exception:
            continue


def _pptx_text_paragraphs(presentation: Any) -> list[Any]:
    paragraphs: list[Any] = []
    seen_cells: set[int] = set()
    for slide in presentation.slides:
        for shape in _iter_pptx_shapes(slide.shapes):
            if getattr(shape, "has_text_frame", False):
                for para in shape.text_frame.paragraphs:
                    if (para.text or "").strip():
                        paragraphs.append(para)
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    for cell in row.cells:
                        ident = id(cell._tc)
                        if ident in seen_cells:
                            continue
                        seen_cells.add(ident)
                        for para in cell.text_frame.paragraphs:
                            if (para.text or "").strip():
                                paragraphs.append(para)
        if slide.has_notes_slide:
            for para in slide.notes_slide.notes_text_frame.paragraphs:
                if (para.text or "").strip():
                    paragraphs.append(para)
    return paragraphs


def write_pdf_bytes(*, title: str, pages: list[str]) -> bytes:
    """Simple title + body PDF. Never returns an empty file."""
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate

    font_name = register_cjk_font()
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title=title or "Translation",
    )
    title_style = ParagraphStyle(
        "PortalTranslatedTitle",
        fontName=font_name,
        fontSize=14,
        leading=20,
        spaceAfter=12,
        wordWrap="CJK",
        alignment=TA_LEFT,
    )
    body_style = ParagraphStyle(
        "PortalTranslatedBody",
        fontName=font_name,
        fontSize=11,
        leading=16,
        spaceAfter=8,
        wordWrap="CJK",
        alignment=TA_LEFT,
    )

    def as_paragraph(text: str, style: ParagraphStyle) -> Paragraph:
        cleaned = (text or "").strip() or "\u00a0"
        markup = xml_escape(cleaned).replace("\n", "<br/>")
        return Paragraph(markup, style)

    chunks = [page if page is not None else "" for page in (pages or [""])]
    if not chunks:
        chunks = [""]
    story: list[Any] = []
    for index, page_text in enumerate(chunks):
        if index == 0 and title:
            story.append(as_paragraph(title, title_style))
        paras = split_paragraphs(page_text)
        if not paras:
            raw = (page_text or "").strip()
            paras = [raw] if raw else ["\u00a0"]
        for para in paras:
            story.append(as_paragraph(para, body_style))
        if index < len(chunks) - 1:
            story.append(PageBreak())
    if not story:
        story.append(as_paragraph(title or "Translation", title_style))
    document.build(story)
    data = buffer.getvalue()
    if not data.startswith(b"%PDF") or len(data) < 8:
        raise RuntimeError("PDF writer produced an empty file.")
    return data


def write_docx_bytes(*, title: str, paragraphs: list[str]) -> bytes:
    from docx import Document

    document = Document()
    if title:
        document.add_heading(title, level=1)
    body = [para for para in paragraphs if para and para.strip()]
    if not body:
        document.add_paragraph("\u00a0")
    else:
        for para in body:
            document.add_paragraph(para)
    buffer = io.BytesIO()
    document.save(buffer)
    data = buffer.getvalue()
    if not data.startswith(b"PK") or len(data) < 8:
        raise RuntimeError("DOCX writer produced an empty file.")
    return data


def write_pptx_bytes(*, title: str, slides: list[str]) -> bytes:
    from pptx import Presentation
    from pptx.util import Inches, Pt

    presentation = Presentation()
    presentation.slide_width = Inches(13.333)
    presentation.slide_height = Inches(7.5)
    blank = presentation.slide_layouts[6]
    chunks = slides or [""]
    for index, text in enumerate(chunks):
        slide = presentation.slides.add_slide(blank)
        box = slide.shapes.add_textbox(Inches(0.5), Inches(0.4), Inches(12.3), Inches(6.6))
        frame = box.text_frame
        frame.word_wrap = True
        body = (text or "").strip() or "\u00a0"
        if index == 0 and title:
            frame.paragraphs[0].text = title
            frame.paragraphs[0].font.size = Pt(22)
            added = frame.add_paragraph()
            added.text = body
            added.font.size = Pt(16)
        else:
            frame.paragraphs[0].text = body
            frame.paragraphs[0].font.size = Pt(16)
    buffer = io.BytesIO()
    presentation.save(buffer)
    data = buffer.getvalue()
    if not data.startswith(b"PK") or len(data) < 8:
        raise RuntimeError("PPTX writer produced an empty file.")
    return data


def write_xlsx_bytes(*, title: str, paragraphs: list[str]) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = (title or "Translation")[:31] or "Translation"
    rows = [para for para in paragraphs if para and para.strip()] or ["\u00a0"]
    for index, para in enumerate(rows, start=1):
        sheet.cell(row=index, column=1, value=para)
    buffer = io.BytesIO()
    workbook.save(buffer)
    data = buffer.getvalue()
    if not data.startswith(b"PK") or len(data) < 8:
        raise RuntimeError("XLSX writer produced an empty file.")
    return data


def _repack_docx(data: bytes, title: str, translated_text: str) -> bytes:
    from docx import Document

    paragraphs = split_paragraphs(translated_text)
    try:
        document = Document(io.BytesIO(data))
        targets = [
            para
            for para in _iter_docx_paragraphs(document)
            if (para.text or "").strip()
        ]
        if _can_structure_replace(len(targets), len(paragraphs)):
            aligned = _align_to_count(paragraphs, len(targets))
            for para, text in zip(targets, aligned):
                _set_docx_paragraph_text(para, text)
            buffer = io.BytesIO()
            document.save(buffer)
            out = buffer.getvalue()
            if out.startswith(b"PK") and len(out) >= 8:
                return out
    except Exception:
        pass
    return write_docx_bytes(title=title, paragraphs=paragraphs or [translated_text])


def _repack_pptx(data: bytes, title: str, translated_text: str, extract: str) -> bytes:
    from pptx import Presentation

    paragraphs = split_paragraphs(translated_text)
    slide_texts = split_marked_sections(translated_text, SLIDE_HEADING_RE)
    source_slides = split_marked_sections(extract, SLIDE_HEADING_RE)
    try:
        presentation = Presentation(io.BytesIO(data))
        targets = _pptx_text_paragraphs(presentation)
        if _can_structure_replace(len(targets), len(paragraphs)):
            aligned = _align_to_count(paragraphs, len(targets))
            for para, text in zip(targets, aligned):
                para.text = text
            buffer = io.BytesIO()
            presentation.save(buffer)
            out = buffer.getvalue()
            if out.startswith(b"PK") and len(out) >= 8:
                return out
    except Exception:
        pass
    slides = slide_texts
    if not slides and source_slides:
        slides = _align_to_count(paragraphs or [translated_text], len(source_slides))
    if not slides:
        slides = paragraphs or [translated_text]
    return write_pptx_bytes(title=title, slides=slides)


def _repack_xlsx(data: bytes, title: str, translated_text: str) -> bytes:
    from openpyxl import load_workbook

    paragraphs = split_paragraphs(translated_text)
    try:
        workbook = load_workbook(io.BytesIO(data))
        cells: list[Any] = []
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str) and cell.value.strip():
                        cells.append(cell)
        if _can_structure_replace(len(cells), len(paragraphs)):
            aligned = _align_to_count(paragraphs, len(cells))
            for cell, text in zip(cells, aligned):
                cell.value = text
            buffer = io.BytesIO()
            workbook.save(buffer)
            out = buffer.getvalue()
            if out.startswith(b"PK") and len(out) >= 8:
                return out
    except Exception:
        pass
    return write_xlsx_bytes(title=title, paragraphs=paragraphs or [translated_text])


def _repack_pdf(data: bytes, title: str, translated_text: str, extract: str) -> bytes:
    translated_pages = split_marked_sections(translated_text, PAGE_HEADING_RE)
    source_pages = split_marked_sections(extract, PAGE_HEADING_RE)
    if translated_pages:
        pages = translated_pages
        if source_pages and len(source_pages) > len(pages):
            pages = pages + [""] * (len(source_pages) - len(pages))
        return write_pdf_bytes(title=title, pages=pages)

    paragraphs = split_paragraphs(translated_text) or [translated_text]
    page_count = 0
    if source_pages:
        page_count = len(source_pages)
    else:
        try:
            from pypdf import PdfReader

            page_count = len(PdfReader(io.BytesIO(data)).pages)
        except Exception:
            page_count = 0
    if page_count > 1 and len(paragraphs) >= page_count:
        return write_pdf_bytes(title=title, pages=_align_to_count(paragraphs, page_count))
    if page_count > 1 and source_pages:
        return write_pdf_bytes(title=title, pages=_align_to_count(paragraphs, page_count))
    return write_pdf_bytes(title=title, pages=["\n\n".join(paragraphs)])


def _repack_bytes(suffix: str, data: bytes, title: str, translated_text: str, extract: str) -> bytes:
    if suffix == ".pdf":
        return _repack_pdf(data, title, translated_text, extract)
    if suffix == ".docx":
        return _repack_docx(data, title, translated_text)
    if suffix == ".pptx":
        return _repack_pptx(data, title, translated_text, extract)
    if suffix == ".xlsx":
        return _repack_xlsx(data, title, translated_text)
    if suffix in {".txt", ".md"}:
        body = translated_text if translated_text.endswith("\n") else translated_text + "\n"
        encoded = body.encode("utf-8")
        if not encoded:
            raise RuntimeError("Text writer produced an empty file.")
        return encoded
    if suffix == ".doc":
        return _repack_docx(data, title, translated_text)
    if suffix == ".ppt":
        return _repack_pptx(data, title, translated_text, extract)
    if suffix == ".xls":
        return _repack_xlsx(data, title, translated_text)
    raise RuntimeError(f"No repacker for {suffix}.")


def _output_suffix(source_suffix: str) -> str:
    if source_suffix == ".doc":
        return ".docx"
    if source_suffix == ".ppt":
        return ".pptx"
    if source_suffix == ".xls":
        return ".xlsx"
    return source_suffix


def _load_row(data_dir: Path, file_id: str) -> dict[str, Any]:
    chosen = file_id.strip()
    if not chosen or "/" in chosen or "\\" in chosen:
        raise RagError(404, "File not found.")
    match = next((row for row in load_index(data_dir) if row.get("id") == chosen), None)
    if match is None:
        raise RagError(404, "File not found.")
    return match


def get_translated_file(data_dir: Path, file_id: str) -> tuple[Path, str]:
    match = _load_row(data_dir, file_id)
    rel = str(match.get("translated_path") or "").strip()
    if not rel:
        raise RagError(404, TRANSLATED_NOT_FOUND)
    root = Path(data_dir).resolve()
    stored = (root / rel).resolve()
    if root not in stored.parents:
        raise RagError(404, "File not found.")
    if not stored.is_file():
        raise RagError(404, TRANSLATED_NOT_FOUND)
    name = Path(str(match.get("translated_name") or stored.name)).name or stored.name
    return stored, name


def _store_translated(
    data_dir: Path,
    row: dict[str, Any],
    *,
    filename: str,
    payload: bytes,
) -> dict[str, str]:
    file_id = str(row["id"])
    suffix = Path(filename).suffix.lower() or ".bin"
    stored_name = f"{file_id}{suffix}"
    stored_rel = f"{TRANSLATED_DIRNAME}/{stored_name}"
    stored_abs = translated_dir(data_dir) / stored_name
    stored_abs.write_bytes(payload)
    files = load_index(data_dir)
    for item in files:
        if item.get("id") == file_id:
            item["translated_path"] = stored_rel
            item["translated_name"] = filename
            break
    save_index(data_dir, files)
    return _artifact(file_id, filename, str(row.get("name") or filename))


def repack_translation(
    data_dir: Path,
    file_id: str,
    target_language: str,
    translated_text: str,
) -> dict[str, str] | None:
    """Apply translated text onto a copy of the stored file and record the sibling."""
    try:
        row = _load_row(data_dir, file_id)
    except RagError:
        return None
    source_name = str(row.get("name") or file_id)
    suffix = Path(source_name).suffix.lower()
    if not suffix:
        suffix = f".{row.get('type') or 'txt'}"
    stored_rel = str(row.get("stored_path") or "")
    stored_abs = Path(data_dir) / stored_rel
    if not stored_abs.is_file():
        return None
    extract = ""
    extract_abs = extract_path(data_dir, file_id)
    if extract_abs.is_file():
        try:
            extract = extract_abs.read_text(encoding="utf-8")
        except OSError:
            extract = ""
    text = (translated_text or "").strip()
    if not text:
        text = extract.strip()
    if not text:
        return None
    out_suffix = _output_suffix(suffix)
    filename = translated_filename(source_name, target_language)
    if Path(filename).suffix.lower() != out_suffix:
        filename = f"{Path(filename).stem}{out_suffix}"
    try:
        payload = _repack_bytes(suffix, stored_abs.read_bytes(), source_name, text, extract)
    except Exception:
        try:
            paragraphs = split_paragraphs(text) or [text]
            if out_suffix == ".pdf":
                payload = write_pdf_bytes(title=source_name, pages=["\n\n".join(paragraphs)])
            elif out_suffix == ".docx":
                payload = write_docx_bytes(title=source_name, paragraphs=paragraphs)
            elif out_suffix == ".pptx":
                payload = write_pptx_bytes(title=source_name, slides=paragraphs)
            elif out_suffix == ".xlsx":
                payload = write_xlsx_bytes(title=source_name, paragraphs=paragraphs)
            elif out_suffix in {".txt", ".md"}:
                body = text if text.endswith("\n") else text + "\n"
                payload = body.encode("utf-8")
            else:
                return None
        except Exception:
            return None
    if not payload:
        return None
    return _store_translated(data_dir, row, filename=filename, payload=payload)


def repack_translation_files(
    data_dir: Path,
    *,
    target_language: str,
    reply: str,
    sources: list[dict[str, str]],
) -> list[dict[str, str]]:
    names = [str(row.get("name") or "") for row in sources]
    mapped = translations_for_files(reply, names)
    artifacts: list[dict[str, str]] = []
    for row in sources:
        file_id = str(row.get("id") or "").strip()
        name = str(row.get("name") or "")
        if not file_id:
            continue
        text = mapped.get(name, reply)
        artifact = repack_translation(data_dir, file_id, target_language, text)
        if artifact:
            artifacts.append(artifact)
    return artifacts
