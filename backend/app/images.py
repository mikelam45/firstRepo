"""Generate stills and storyboard frames through the OpenRouter Images API.

Jobs never go to ``/api/v1/chat/completions``. Prompt rewrite is a separate
text-model call. Prices in the reply come from the recorded catalog. Files
are stored under ``$DATA_DIR/images/``. The OpenRouter key stays out of
return values and logs.
"""

from __future__ import annotations

import base64
import io
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

try:
    from PIL import Image
except ImportError:  # pragma: no cover - conversion is optional
    Image = None  # type: ignore[assignment,misc]

from .catalog import (
    FUNCTION_LABELS,
    PRICES_RECORDED_ON,
    RECOMMENDED_HK_TEXT_MODEL,
    get_model,
    is_available_in_hong_kong,
)
from .chat import (
    ChatError,
    MISSING_KEY_DETAIL,
    REGION_SETUP_HINT,
    _sanitize_provider_message,
    complete_chat,
    recorded_model,
)
from .image_refs import MEDIA_TYPES, ImageRefError, resolve_references
from .openrouter_key import load_openrouter_api_key

OPENROUTER_IMAGES_URL = "https://openrouter.ai/api/v1/images"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_IMAGES_TIMEOUT_SECONDS = 120.0
OPENROUTER_IMAGE_TIMEOUT_SECONDS = OPENROUTER_IMAGES_TIMEOUT_SECONDS
OPENROUTER_DOWNLOAD_TIMEOUT_SECONDS = 60.0

INDEX_NAME = "image-jobs.json"
IMAGES_DIRNAME = "images"
MAX_DIMENSION = 2048
MAX_PROMPT_CHARS = 8000
MAX_FIELD_CHARS = 2000
ALLOWED_FORMATS = ("png", "jpeg", "webp")
ALLOWED_FRAME_COUNTS = frozenset({1, 4, 6, 8})
PROVIDER_RASTER_FORMATS = frozenset({"png", "jpeg"})
GEMINI_IMAGE_ID = "google/gemini-3.1-flash-image"
IMAGE_REGION_SETUP_HINT = REGION_SETUP_HINT.replace("text model", "image model")
JOB_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
ENHANCE_SYSTEM = (
    "Rewrite the user's image prompt for a text-to-image model. "
    "Keep the same subject and intent. Add concrete visual detail "
    "(composition, lighting, materials, camera). "
    "Return only the enhanced prompt, with no preamble or quotes."
)
MISSING_PROMPT_DETAIL = (
    "prompt or guided fields (subject, setting, background, objects, style, "
    "camera, lighting, notes) are required."
)
PROMPT_FIELDS: tuple[tuple[str, str], ...] = (
    ("subject", "Subject"),
    ("setting", "Setting"),
    ("background", "Background"),
    ("background_attributes", "Attributes of background"),
    ("objects", "Objects"),
    ("object_attributes", "Attributes of objects"),
    ("style", "Style"),
    ("camera", "Camera"),
    ("lighting", "Lighting"),
    ("notes", "Notes"),
)
ALLOWED_RESOLUTIONS: tuple[str, ...] = (
    "1:1",
    "4:3",
    "3:4",
    "3:2",
    "2:3",
    "16:9",
    "9:16",
    "21:9",
    "auto",
)
DEFAULT_RESOLUTION = "1:1"
STRICT_FORMATS = ("png", "jpeg")
SIZE_TO_RATIO: dict[tuple[int, int], str] = {
    (1024, 1024): "1:1",
    (1024, 768): "4:3",
    (768, 1024): "3:4",
    (1344, 768): "16:9",
    (1920, 1080): "16:9",
}


def _aspect_from_wh(width: int, height: int) -> str:
    """Map pixel size to FLUX.2 Pro ``aspect_ratio``."""
    mapped = SIZE_TO_RATIO.get((width, height))
    if mapped:
        return mapped
    target = width / height if height else 1.0
    best = DEFAULT_RESOLUTION
    best_diff = 10.0
    for item in ALLOWED_RESOLUTIONS:
        if item == "auto":
            continue
        left, right = item.split(":")
        diff = abs((int(left) / int(right)) - target)
        if diff < best_diff:
            best = item
            best_diff = diff
    return best


class ImageError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def images_dir(data_dir: Path) -> Path:
    path = Path(data_dir) / IMAGES_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def index_path(data_dir: Path) -> Path:
    return Path(data_dir) / INDEX_NAME


def file_href(job_id: str, index: int = 0) -> str:
    if index:
        return f"/api/images/{job_id}/file?index={index}"
    return f"/api/images/{job_id}/file"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _strip(value: object, limit: int = MAX_FIELD_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def assemble_prompt(body: dict[str, Any] | None) -> str:
    """Build the image prompt in a fixed field order.

    Each non-empty guided factor becomes ``{Label}: {value}`` on its own line.
    """
    mapping = body or {}
    lines: list[str] = []
    for field_id, label in PROMPT_FIELDS:
        if field_id == "camera":
            value = _strip(
                mapping.get("camera")
                or mapping.get("shot")
                or mapping.get("framing")
                or mapping.get("camera_framing")
            )
        elif field_id == "notes":
            value = _strip(mapping.get("notes") or mapping.get("extra_notes"))
        else:
            value = _strip(mapping.get(field_id))
        if value:
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


def resolve_prompt(body: dict[str, Any]) -> str:
    guided = assemble_prompt(body)
    extra = _strip(body.get("prompt"), MAX_PROMPT_CHARS)
    if guided and extra:
        if extra == guided or extra.startswith(guided):
            chosen = extra
        else:
            chosen = f"{guided}\n{extra}"
    else:
        chosen = guided or extra
    if not chosen:
        raise ImageError(400, MISSING_PROMPT_DETAIL)
    if len(chosen) > MAX_PROMPT_CHARS:
        raise ImageError(400, f"Assembled prompt must be at most {MAX_PROMPT_CHARS} characters.")
    return chosen


def resolve_resolution(value: object, width: object = None, height: object = None) -> str:
    if isinstance(value, str) and value.strip():
        chosen = value.strip()
        if chosen not in ALLOWED_RESOLUTIONS:
            allowed = ", ".join(ALLOWED_RESOLUTIONS)
            raise ImageError(400, f"resolution must be an aspect ratio from: {allowed}.")
        return chosen
    if value not in (None, ""):
        raise ImageError(400, "resolution must be a string.")
    return DEFAULT_RESOLUTION


def resolve_format(value: object) -> str:
    chosen = _strip(value).lower() or "png"
    if chosen == "jpg":
        chosen = "jpeg"
    if chosen not in ALLOWED_FORMATS:
        raise ImageError(400, "format must be 'png', 'jpeg', or 'webp'.")
    return chosen


def resolve_size(width: object, height: object) -> tuple[int, int]:
    try:
        wide = int(width)  # type: ignore[arg-type]
        high = int(height)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ImageError(400, "width and height must be integers.") from None
    if wide < 1 or high < 1:
        raise ImageError(400, "width and height must be at least 1.")
    if wide > MAX_DIMENSION or high > MAX_DIMENSION:
        raise ImageError(
            400,
            f"width and height must be at most {MAX_DIMENSION}.",
        )
    return wide, high


def resolve_frames(value: object) -> list[str]:
    if value is None:
        return [""]
    if not isinstance(value, list):
        raise ImageError(400, "frames must be a list of beat captions.")
    beats: list[str] = []
    for item in value:
        if item is None:
            beats.append("")
        elif isinstance(item, str):
            beats.append(item.strip()[:MAX_FIELD_CHARS])
        else:
            raise ImageError(400, "frames must be a list of beat captions.")
    if not beats:
        return [""]
    if len(beats) not in ALLOWED_FRAME_COUNTS:
        raise ImageError(400, "frames must contain 1, 4, 6, or 8 beats.")
    return beats


def _provider_output_format(requested: str) -> str:
    if requested in PROVIDER_RASTER_FORMATS:
        return requested
    return "png"


def _sniff_format(data: bytes, media_type: str | None) -> str:
    if media_type:
        lowered = media_type.lower()
        if "png" in lowered:
            return "png"
        if "jpeg" in lowered or "jpg" in lowered:
            return "jpeg"
        if "webp" in lowered:
            return "webp"
    if data.startswith(b"\x89PNG"):
        return "png"
    if data.startswith(b"\xff\xd8"):
        return "jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "png"


def convert_image_bytes(data: bytes, requested: str, media_type: str | None = None) -> bytes:
    source = _sniff_format(data, media_type)
    if source == requested or Image is None:
        return data
    image = Image.open(io.BytesIO(data))
    extra: dict[str, Any] = {}
    if requested == "jpeg":
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        pillow_format = "JPEG"
        extra = {"quality": 92}
    elif requested == "webp":
        if image.mode == "P":
            image = image.convert("RGBA")
        pillow_format = "WEBP"
        extra = {"quality": 90}
    else:
        if image.mode == "P":
            image = image.convert("RGBA")
        pillow_format = "PNG"
    buffer = io.BytesIO()
    image.save(buffer, format=pillow_format, **extra)
    return buffer.getvalue()


def _bytes_from_data_url(url: str) -> bytes:
    _, separator, payload = url.partition(",")
    if not separator:
        raise ImageError(502, "OpenRouter returned an unreadable image data URL.")
    try:
        return base64.b64decode(payload)
    except Exception as exc:
        raise ImageError(502, "OpenRouter returned an unreadable image data URL.") from exc


def _download_image_url(url: str, api_key: str) -> bytes:
    if url.startswith("data:"):
        return _bytes_from_data_url(url)
    headers: dict[str, str] = {}
    host = (urlparse(url).hostname or "").lower()
    if host == "openrouter.ai" or host.endswith(".openrouter.ai"):
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        response = httpx.get(
            url,
            headers=headers,
            timeout=OPENROUTER_DOWNLOAD_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
    except Exception as exc:
        raise ImageError(502, "Could not download the generated image.") from exc
    if response.status_code != 200 or not response.content:
        raise ImageError(502, "Could not download the generated image.")
    return response.content


def _image_bytes_from_item(item: Any, api_key: str) -> tuple[bytes, str | None]:
    if isinstance(item, str) and item.strip():
        raw = item.strip()
        if raw.startswith(("data:", "http://", "https://")):
            return _download_image_url(raw, api_key), None
        try:
            return base64.b64decode(raw), None
        except Exception as exc:
            raise ImageError(502, "OpenRouter did not return image bytes.") from exc
    if not isinstance(item, dict):
        raise ImageError(502, "OpenRouter did not return image bytes.")
    media_type = item.get("media_type") if isinstance(item.get("media_type"), str) else None
    b64 = item.get("b64_json") or item.get("b64")
    if isinstance(b64, str) and b64.strip():
        try:
            return base64.b64decode(b64), media_type
        except Exception as exc:
            raise ImageError(502, "OpenRouter did not return image bytes.") from exc
    url = item.get("url")
    image_url = item.get("image_url")
    if isinstance(image_url, str):
        url = image_url
    elif isinstance(image_url, dict):
        nested = image_url.get("url")
        if isinstance(nested, str):
            url = nested
    if isinstance(url, str) and url.strip():
        return _download_image_url(url.strip(), api_key), media_type
    raise ImageError(502, "OpenRouter did not return image bytes.")


def load_jobs(data_dir: Path) -> list[dict[str, Any]]:
    path = index_path(data_dir)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    jobs = raw.get("jobs") if isinstance(raw, dict) else None
    if not isinstance(jobs, list):
        return []
    return [row for row in jobs if isinstance(row, dict) and row.get("id")]


def save_jobs(data_dir: Path, jobs: list[dict[str, Any]]) -> None:
    path = index_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps({"jobs": jobs}, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    job_id = str(job["id"])
    images = []
    for item in job.get("images") or []:
        if not isinstance(item, dict):
            continue
        index = int(item.get("index") or 0)
        images.append(
            {
                "index": index,
                "caption": item.get("caption") or "",
                "filename": item.get("filename") or "",
                "href": file_href(job_id, index),
            }
        )
    return {
        "id": job_id,
        "created_at": job.get("created_at"),
        "function": "image_gen",
        "function_label": FUNCTION_LABELS["image_gen"],
        "model_id": job.get("model_id"),
        "provider": job.get("provider"),
        "name": job.get("name"),
        "prompt": job.get("prompt"),
        "width": job.get("width"),
        "height": job.get("height"),
        "format": job.get("format"),
        "prices": list(job.get("prices") or []),
        "prices_recorded_on": job.get("prices_recorded_on") or PRICES_RECORDED_ON,
        "images": images,
        "reference_ids": list(job.get("reference_ids") or []),
    }


def list_jobs(data_dir: Path) -> list[dict[str, Any]]:
    jobs = sorted(
        load_jobs(data_dir),
        key=lambda row: str(row.get("created_at") or ""),
        reverse=True,
    )
    return [public_job(job) for job in jobs]


def get_job(data_dir: Path, job_id: str) -> dict[str, Any]:
    if not JOB_ID_RE.match(job_id or ""):
        raise ImageError(404, "Image job not found.")
    for job in load_jobs(data_dir):
        if job.get("id") == job_id:
            return job
    raise ImageError(404, "Image job not found.")


def stored_image_path(data_dir: Path, job: dict[str, Any], index: int) -> tuple[Path, str, str]:
    images = job.get("images") if isinstance(job.get("images"), list) else []
    match: dict[str, Any] | None = None
    for item in images:
        if isinstance(item, dict) and int(item.get("index") or 0) == index:
            match = item
            break
    if match is None:
        raise ImageError(404, "Image file not found.")
    relative = str(match.get("stored_path") or "")
    if not relative or ".." in relative or relative.startswith("/"):
        raise ImageError(404, "Image file not found.")
    path = Path(data_dir) / relative
    if not path.is_file():
        raise ImageError(404, "Image file not found.")
    filename = str(match.get("filename") or path.name)
    fmt = str(job.get("format") or "png")
    media_type = {
        "png": "image/png",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
    }.get(fmt, "application/octet-stream")
    return path, filename, media_type


def _frame_prompt(base: str, caption: str, index: int, total: int) -> str:
    if total == 1:
        return base
    beat = caption or f"Frame {index + 1}"
    return f"{base}\n\nStoryboard frame {index + 1} of {total}. Beat: {beat}."


def _assert_image_model(model_id: str, extra_hidden: frozenset[str] | set[str] | None) -> None:
    if model_id == GEMINI_IMAGE_ID or not is_available_in_hong_kong(model_id, extra_hidden):
        raise ImageError(400, f"{model_id} is not available in Hong Kong.")
    model = get_model(model_id)
    if model is None or "image_gen" not in model["functions"]:  # type: ignore[operator]
        raise ImageError(400, f"{model_id} is not allowed for image_gen.")


def _provider_message(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, str) and error.strip():
        return error
    if isinstance(error, dict):
        raw = error.get("message")
        if isinstance(raw, str) and raw.strip():
            return raw
    return None


def _images_failure(
    *,
    status_code: int | None,
    payload: Any,
    api_key: str | None = None,
) -> ImageError:
    provider = _provider_message(payload)
    if provider:
        cleaned = _sanitize_provider_message(provider, api_key)
        detail = (
            f"OpenRouter returned HTTP {status_code}: {cleaned}"
            if status_code is not None
            else f"OpenRouter error: {cleaned}"
        )
        lowered = cleaned.lower()
        if status_code == 403 and (
            "region" in lowered or "not available in your" in lowered
        ):
            detail = f"{detail} {IMAGE_REGION_SETUP_HINT}"
        return ImageError(502, detail)
    if status_code is not None and status_code != 200:
        return ImageError(502, f"OpenRouter returned HTTP {status_code} without an image.")
    return ImageError(502, "OpenRouter did not return an image.")


def _reference_payload(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """OpenRouter Image API / FLUX.2 Pro ``input_references``.

    Docs: https://openrouter.ai/docs/guides/overview/multimodal/image-generation
    and https://openrouter.ai/black-forest-labs/flux.2-pro/llms.txt

    Provider field name is ``input_references`` (not portal ``reference_ids``).
    Each item is ``{ "type": "image_url", "image_url": { "url": "<https or data URL>" } }``.
    The url is an https URL or a base64 data URL. FLUX.2 Pro accepts up to 8;
    this portal stores at most 5.
    """
    items: list[dict[str, Any]] = []
    for row in rows:
        kind = str(row.get("type") or "png")
        media = MEDIA_TYPES.get(kind, "image/png")
        data = row.get("bytes")
        if not isinstance(data, (bytes, bytearray)):
            continue
        encoded = base64.b64encode(bytes(data)).decode("ascii")
        items.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{media};base64,{encoded}"},
            }
        )
    return items


def _post_openrouter_image(
    *,
    api_key: str,
    model_id: str,
    prompt: str,
    width: int,
    height: int,
    output_format: str,
    input_references: list[dict[str, Any]] | None = None,
    aspect_ratio: str | None = None,
) -> tuple[bytes, str | None]:
    if OPENROUTER_IMAGES_URL == OPENROUTER_CHAT_URL:
        raise ImageError(500, "Image jobs must not use chat completions.")
    # Provider field names (OpenRouter Image API / FLUX.2 Pro):
    #   prompt, n, aspect_ratio (from portal resolution or width/height),
    #   output_format (portal format), input_references (portal reference_ids).
    # FLUX.2 Pro does not list ``size``; unlisted fields are rejected.
    # https://openrouter.ai/black-forest-labs/flux.2-pro/llms.txt
    # Portal width/height stay on the job record; they are mapped to aspect_ratio here.
    del width, height  # not a provider field; aspect_ratio is.
    payload: dict[str, Any] = {
        "model": model_id,
        "prompt": prompt,
        "n": 1,
        "aspect_ratio": aspect_ratio or "1:1",
        "output_format": output_format,
    }
    if input_references:
        payload["input_references"] = input_references
    try:
        response = httpx.post(
            OPENROUTER_IMAGES_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=OPENROUTER_IMAGES_TIMEOUT_SECONDS,
            follow_redirects=False,
        )
        status_code = response.status_code
    except Exception:
        raise ImageError(502, "OpenRouter did not return an image.") from None

    body: Any = None
    try:
        body = response.json()
    except Exception:
        body = None

    if status_code != 200:
        raise _images_failure(status_code=status_code, payload=body, api_key=api_key)
    if not isinstance(body, dict):
        raise ImageError(502, "OpenRouter did not return an image.")
    if body.get("error"):
        raise _images_failure(status_code=status_code, payload=body, api_key=api_key)
    data = body.get("data")
    if not isinstance(data, list) or not data:
        raise ImageError(502, "OpenRouter did not return an image.")
    return _image_bytes_from_item(data[0], api_key)


def generate_images(
    data_dir: Path,
    body: dict[str, Any],
    *,
    model_id: str,
    extra_hidden: frozenset[str] | set[str] | None = None,
) -> dict[str, Any]:
    _assert_image_model(model_id, extra_hidden)
    prompt = resolve_prompt(body)
    width, height = resolve_size(
        1024 if body.get("width") is None else body.get("width"),
        1024 if body.get("height") is None else body.get("height"),
    )
    fmt = resolve_format(body.get("format", "png"))
    frames = resolve_frames(body.get("frames"))
    raw_ids = body.get("reference_ids") or []
    if not isinstance(raw_ids, list):
        raise ImageError(400, "reference_ids must be a list.")
    try:
        stored_refs = resolve_references(data_dir, [str(item) for item in raw_ids])
    except ImageRefError as exc:
        raise ImageError(exc.status_code, exc.detail) from exc
    used_ids = [str(row["id"]) for row in stored_refs]
    references = _reference_payload(stored_refs)
    api_key = load_openrouter_api_key()
    if not api_key:
        raise ImageError(503, MISSING_KEY_DETAIL)

    meta = recorded_model("image_gen", model_id)
    job_id = str(uuid.uuid4())
    folder = images_dir(data_dir)
    extension = "jpg" if fmt == "jpeg" else fmt
    provider_format = _provider_output_format(fmt)
    aspect = (
        resolve_resolution(body.get("resolution"))
        if _strip(body.get("resolution"))
        else _aspect_from_wh(width, height)
    )
    written: list[Path] = []
    image_rows: list[dict[str, Any]] = []
    try:
        for index, caption in enumerate(frames):
            frame_prompt = _frame_prompt(prompt, caption, index, len(frames))
            raw, media_type = _post_openrouter_image(
                api_key=api_key,
                model_id=model_id,
                prompt=frame_prompt,
                width=width,
                height=height,
                output_format=provider_format,
                input_references=references or None,
                aspect_ratio=aspect,
            )
            converted = convert_image_bytes(raw, fmt, media_type)
            filename = f"{job_id}-{index}.{extension}"
            relative = f"{IMAGES_DIRNAME}/{filename}"
            path = folder / filename
            path.write_bytes(converted)
            written.append(path)
            image_rows.append(
                {
                    "index": index,
                    "caption": caption,
                    "filename": filename,
                    "stored_path": relative,
                }
            )
    except Exception:
        for path in written:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise

    job = {
        "id": job_id,
        "created_at": _now(),
        "model_id": model_id,
        "provider": meta["provider"],
        "name": meta["name"],
        "prompt": prompt,
        "width": width,
        "height": height,
        "format": fmt,
        "prices": meta["prices"],
        "prices_recorded_on": meta["prices_recorded_on"],
        "images": image_rows,
        "reference_ids": used_ids,
    }
    jobs = load_jobs(data_dir)
    jobs.append(job)
    save_jobs(data_dir, jobs)
    return public_job(job)


def enhance_prompt(
    data_dir: Path,
    prompt: str,
    *,
    extra_hidden: frozenset[str] | set[str] | None = None,
) -> dict[str, str]:
    text = prompt.strip()
    if not text:
        raise ImageError(400, "prompt is required.")
    if len(text) > MAX_PROMPT_CHARS:
        text = text[:MAX_PROMPT_CHARS]
    from .selection import load_selection

    selection = load_selection(data_dir, extra_hidden=extra_hidden)
    model_id = selection.get("rag_qa") or RECOMMENDED_HK_TEXT_MODEL
    model = get_model(model_id)
    if (
        model is None
        or "rag_qa" not in model["functions"]  # type: ignore[operator]
        or not is_available_in_hong_kong(model_id, extra_hidden)
    ):
        model_id = RECOMMENDED_HK_TEXT_MODEL
    try:
        result = complete_chat(
            message=text,
            function_id="rag_qa",
            model_id=model_id,
            messages=[
                {"role": "system", "content": ENHANCE_SYSTEM},
                {"role": "user", "content": text},
            ],
        )
    except ChatError as exc:
        raise ImageError(exc.status_code, exc.detail) from exc
    enhanced = str(result.get("reply") or "").strip()
    if not enhanced:
        raise ImageError(502, "OpenRouter did not return an enhanced prompt.")
    return {"enhanced_prompt": enhanced}


def generate_image(
    *,
    data_dir: Path,
    body: dict[str, Any],
    model_id: str,
    extra_hidden: frozenset[str] | set[str] | None = None,
) -> dict[str, Any]:
    """Same as generate_images; persists files under $DATA_DIR/images/."""
    return generate_images(
        data_dir,
        body,
        model_id=model_id,
        extra_hidden=extra_hidden,
    )

