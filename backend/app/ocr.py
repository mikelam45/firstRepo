"""Read an HKDSE math question photo through OpenRouter vision chat completions.

Photos are stored under ``$DATA_DIR/dse-ocr/`` and are not mixed into the
``collection=dse_math`` syllabus library. The image is sent as an
``image_url`` data URI on ``/api/v1/chat/completions``. This is not the
Images API and not the FLUX ``image_gen`` path. Gemini ids are never used.
The OpenRouter key stays out of return values and logs.
"""

from __future__ import annotations

import base64
import io
import uuid
from pathlib import Path
from typing import Any

from .chat import (
    ChatError,
    MISSING_KEY_DETAIL,
    complete_vision,
    is_region_or_missing_model_error,
)
from .openrouter_key import load_openrouter_api_key

MAX_OCR_BYTES = 10 * 1024 * 1024
OCR_DIRNAME = "dse-ocr"

# Live on OpenRouter in 2026. ``qwen/qwen-2.5-vl-72b-instruct`` is not a
# catalog id; the hyphenless slug is. Gemini is omitted (HK 403 / hidden).
DEFAULT_OCR_MODEL = "qwen/qwen2.5-vl-72b-instruct"
OCR_MODEL_CANDIDATES: tuple[str, ...] = (
    DEFAULT_OCR_MODEL,
    "qwen/qwen3-vl-8b-instruct",
    "qwen/qwen3-vl-30b-a3b-instruct",
    "anthropic/claude-sonnet-5.5",
)
ALLOWED_EXTENSIONS = {
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".png": "png",
    ".webp": "webp",
    ".heic": "heic",
    ".heif": "heic",
}
MEDIA_TYPES = {
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "heic": "image/heic",
}
HEIC_BRANDS = frozenset({b"heic", b"heif", b"mif1", b"msf1", b"heix", b"heim", b"hevc"})
OCR_SYSTEM = (
    "Transcribe the HKDSE mathematics question from the photo. "
    "Keep mathematics, numbers, and notation. Describe diagrams in words. "
    "Output the question text only, in the language printed on the paper. "
    "Do not solve the question. Do not add commentary. "
    "If the photo is unreadable, say so."
)
OCR_USER_TEXT = "Transcribe the HKDSE mathematics question in this photo."
UNSUPPORTED_TYPE_DETAIL = (
    "Unsupported file type. Accepted: jpeg, png, webp, heic."
)
OVERSIZE_DETAIL = "File exceeds the 10 MB limit."

_resolved_model: str | None = None


class OcrError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def reset_ocr_model_cache() -> None:
    global _resolved_model
    _resolved_model = None


def ocr_dir(data_dir: Path) -> Path:
    path = Path(data_dir) / OCR_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def extension_of(filename: str) -> str:
    return Path(filename).suffix.lower()


def sniff_image_kind(data: bytes) -> str | None:
    if len(data) >= 8 and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(data) >= 3 and data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    if _is_heic(data):
        return "heic"
    return None


def _is_heic(data: bytes) -> bool:
    if len(data) < 12:
        return False
    if data[4:8] != b"ftyp":
        return False
    return data[8:12] in HEIC_BRANDS


def _heic_to_jpeg(data: bytes) -> bytes | None:
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except Exception:
        pass
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        image = Image.open(io.BytesIO(data))
        if image.mode != "RGB":
            image = image.convert("RGB")
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=90)
        return out.getvalue()
    except Exception:
        return None


def _bytes_for_vision(kind: str, data: bytes) -> tuple[str, bytes]:
    if kind != "heic":
        return kind, data
    converted = _heic_to_jpeg(data)
    if converted is None:
        raise OcrError(
            400,
            "HEIC could not be decoded. Upload a jpeg, png, or webp copy.",
        )
    return "jpeg", converted


def _data_uri(kind: str, data: bytes) -> str:
    media_type = MEDIA_TYPES[kind]
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _candidate_models() -> list[str]:
    chosen: list[str] = []
    if _resolved_model and _resolved_model in OCR_MODEL_CANDIDATES:
        chosen.append(_resolved_model)
    for model_id in OCR_MODEL_CANDIDATES:
        if model_id.startswith("google/gemini"):
            continue
        if model_id not in chosen:
            chosen.append(model_id)
    return chosen


def _vision_messages(data_uri: str) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": OCR_SYSTEM},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": OCR_USER_TEXT},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        },
    ]


def _store_photo(data_dir: Path, *, suffix: str, data: bytes) -> Path:
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    stored = ocr_dir(data_dir) / stored_name
    stored.write_bytes(data)
    return stored


def transcribe_question_photo(
    data_dir: Path,
    *,
    filename: str,
    data: bytes,
) -> dict[str, object]:
    name = Path(filename or "").name.strip()
    if not name:
        raise OcrError(400, "Upload must include a filename.")
    if not data:
        raise OcrError(400, "Upload is empty.")
    suffix = extension_of(name)
    kind = ALLOWED_EXTENSIONS.get(suffix)
    if kind is None:
        raise OcrError(400, UNSUPPORTED_TYPE_DETAIL)
    if len(data) > MAX_OCR_BYTES:
        raise OcrError(400, OVERSIZE_DETAIL)
    sniffed = sniff_image_kind(data)
    if sniffed is None:
        raise OcrError(400, "File is not a valid jpeg, png, webp, or heic image.")
    if sniffed != kind:
        raise OcrError(400, "File type does not match the filename extension.")

    api_key = load_openrouter_api_key()
    if not api_key:
        raise ChatError(503, MISSING_KEY_DETAIL)

    _store_photo(data_dir, suffix=suffix, data=data)
    vision_kind, vision_bytes = _bytes_for_vision(kind, data)
    data_uri = _data_uri(vision_kind, vision_bytes)
    messages = _vision_messages(data_uri)

    global _resolved_model
    last_error: ChatError | None = None
    for model_id in _candidate_models():
        try:
            text = complete_vision(model_id=model_id, messages=messages)
        except ChatError as exc:
            last_error = exc
            if exc.status_code == 503:
                raise
            if is_region_or_missing_model_error(exc):
                continue
            raise
        cleaned = text.strip()
        if not cleaned:
            last_error = ChatError(502, f"empty reply from {model_id}")
            continue
        if api_key and api_key in cleaned:
            cleaned = cleaned.replace(api_key, "[redacted]")
        _resolved_model = model_id
        return {"text": cleaned, "model_id": model_id}

    if last_error is not None:
        raise last_error
    raise ChatError(502, "OpenRouter did not return a chat completion.")
