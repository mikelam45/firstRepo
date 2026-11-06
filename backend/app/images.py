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
from dataclasses import dataclass
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
MAX_MEGAPIXELS = 4.0
MAX_PROMPT_CHARS = 8000
MAX_FIELD_CHARS = 2000
ALLOWED_FORMATS = ("png", "jpeg", "webp")
ALLOWED_FRAME_COUNTS = frozenset({1, 4, 6, 8})
MIN_IMAGE_COUNT = 1
MAX_IMAGE_COUNT = 10
DEFAULT_IMAGE_COUNT = 1
EXPRESSION_VARIANTS: tuple[str, ...] = (
    "neutral",
    "slight smile",
    "smile",
    "focused",
    "speaking",
    "surprised",
)
MOVEMENT_VARIANTS: tuple[str, ...] = (
    "idle",
    "walking",
    "turning",
    "reaching",
    "sitting",
    "stepping",
)
FACIAL_SUBTLE_VARIANTS: tuple[str, ...] = (
    "nearly the same expression, a faint softening around the eyes",
    "a barely-there hint of a smile",
    "a slight brightening of the mouth",
    "a small increase in focus, brow barely tightened",
    "lips slightly parted as if about to speak",
    "a tiny lift of surprise in the eyelids",
)
FACIAL_STRONG_VARIANTS: tuple[str, ...] = (
    "neutral, composed, eyes steady",
    "a clear warm smile",
    "an open laugh, teeth visible, eyes crinkled",
    "intensely focused, brow engaged",
    "mid-sentence, mouth clearly shaping words",
    "obvious surprise, eyes wide, brows raised",
)
MOTION_SUBTLE_VARIANTS: tuple[str, ...] = (
    "almost idle, a tiny weight shift",
    "the start of a step, heel just lifting",
    "a small turn of the shoulders",
    "fingers beginning to reach",
    "a slight settle as if considering sitting",
    "a short, contained step in place",
)
MOTION_STRONG_VARIANTS: tuple[str, ...] = (
    "planted and still",
    "a clear walking stride",
    "a decisive turn of the torso and head",
    "arm fully extended, reaching for an object",
    "sitting down or already seated in motion",
    "a full stepping motion across the frame",
)
VARIANCE_LEVELS: tuple[str, ...] = ("off", "subtle", "medium", "strong")
DEFAULT_VARIANCE_LEVEL = "medium"
MAX_CYCLE_ITEMS = 12
IDENTITY_LOCK = (
    "Keep the same person, identity, facial structure, hair, clothing, props, "
    "and setting as the other photos in this set. Do not change who they are."
)
OUTPUT_RESOLUTIONS: tuple[str, ...] = ("1K", "2K", "4K")
DEFAULT_OUTPUT_RESOLUTION = "1K"
OUTPUT_RESOLUTION_ALIASES: dict[str, str] = {
    "1k": "1K",
    "1K": "1K",
    "1024": "1K",
    "studio": "1K",
    "2k": "2K",
    "2K": "2K",
    "2048": "2K",
    "4k": "4K",
    "4K": "4K",
    "4096": "4K",
}
RESOLUTION_HINTS: dict[str, str] = {
    "2K": "High-resolution 2K photograph, sharp fine detail, about two megapixels.",
    "4K": (
        "Ultra high-resolution 4K photograph, maximum FLUX.2 detail, about four "
        "megapixels, extremely sharp textures."
    ),
}
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
    "prompt or guided fields (subject, setting, background, objects, person, style, "
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
PERSON_SLOT_BEFORE = "style"
PERSON_PARTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("nationality", ("nationality", "ethnicity", "ethnicity_presentation")),
    ("height", ("person_height", "stature")),
    ("body", ("body", "body_type")),
    ("hair", ("hair",)),
    ("eyes", ("eyes",)),
    ("nose", ("nose",)),
    ("mouth", ("mouth",)),
    ("expression", ("expression", "facial_expression")),
)
CLOTHING_PARTS: tuple[tuple[str, str], ...] = (
    ("dress", "dress"),
    ("top", "top"),
    ("bottom", "bottom"),
    ("shoes", "shoes"),
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
DEFAULT_ASPECT_RATIO = DEFAULT_RESOLUTION
STRICT_FORMATS = ("png", "jpeg")
SIZE_TO_RATIO: dict[tuple[int, int], str] = {
    (1024, 1024): "1:1",
    (1024, 768): "4:3",
    (768, 1024): "3:4",
    (1152, 768): "3:2",
    (768, 1152): "2:3",
    (1344, 768): "16:9",
    (768, 1344): "9:16",
    (1536, 656): "21:9",
    (1920, 1080): "16:9",
    (1440, 1440): "1:1",
    (1632, 1216): "4:3",
    (1216, 1632): "3:4",
    (1728, 1152): "3:2",
    (1152, 1728): "2:3",
    (1920, 1088): "16:9",
    (1088, 1920): "9:16",
    (2048, 880): "21:9",
    (2048, 2048): "1:1",
    (2048, 1536): "4:3",
    (1536, 2048): "3:4",
    (2048, 1360): "3:2",
    (1360, 2048): "2:3",
    (2048, 1152): "16:9",
    (1152, 2048): "9:16",
}
# Long-edge pixel sizes per OpenRouter-style 1K/2K/4K tier. FLUX.2 Pro via
# OpenRouter only accepts aspect_ratio (not size/resolution); these populate
# portal metadata and the prompt hint. Sides are multiples of 16, capped at
# 2048 and 4 megapixels (the native FLUX.2 maximum).
PIXELS_FOR_OUTPUT: dict[str, dict[str, tuple[int, int]]] = {
    "1K": {
        "1:1": (1024, 1024),
        "4:3": (1024, 768),
        "3:4": (768, 1024),
        "3:2": (1152, 768),
        "2:3": (768, 1152),
        "16:9": (1344, 768),
        "9:16": (768, 1344),
        "21:9": (1536, 656),
        "auto": (1024, 1024),
    },
    "2K": {
        "1:1": (1440, 1440),
        "4:3": (1632, 1216),
        "3:4": (1216, 1632),
        "3:2": (1728, 1152),
        "2:3": (1152, 1728),
        "16:9": (1920, 1088),
        "9:16": (1088, 1920),
        "21:9": (2048, 880),
        "auto": (1440, 1440),
    },
    "4K": {
        "1:1": (2048, 2048),
        "4:3": (2048, 1536),
        "3:4": (1536, 2048),
        "3:2": (2048, 1360),
        "2:3": (1360, 2048),
        "16:9": (2048, 1152),
        "9:16": (1152, 2048),
        "21:9": (2048, 880),
        "auto": (2048, 2048),
    },
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


def pixels_for(output_resolution: str, aspect_ratio: str) -> tuple[int, int]:
    """Studio pixel size for a 1K/2K/4K tier and FLUX.2 aspect ratio."""
    tier = output_resolution if output_resolution in PIXELS_FOR_OUTPUT else DEFAULT_OUTPUT_RESOLUTION
    table = PIXELS_FOR_OUTPUT[tier]
    if aspect_ratio in table:
        return table[aspect_ratio]
    return table[DEFAULT_ASPECT_RATIO]


def infer_output_resolution(width: int, height: int) -> str:
    megapixels = (width * height) / 1_000_000
    if megapixels >= 3.0:
        return "4K"
    if megapixels >= 1.6:
        return "2K"
    return "1K"


def images_timeout_seconds(output_resolution: str) -> float:
    if output_resolution == "4K":
        return 180.0
    if output_resolution == "2K":
        return 150.0
    return OPENROUTER_IMAGES_TIMEOUT_SECONDS


@dataclass(frozen=True)
class VarianceSpec:
    facial_level: str = DEFAULT_VARIANCE_LEVEL
    motion_level: str = DEFAULT_VARIANCE_LEVEL
    facial_notes: str = ""
    motion_notes: str = ""
    facial_cycle: tuple[str, ...] = EXPRESSION_VARIANTS
    motion_cycle: tuple[str, ...] = MOVEMENT_VARIANTS

    def uses_legacy_suffix(self) -> bool:
        return (
            self.facial_level == "medium"
            and self.motion_level == "medium"
            and not self.facial_notes
            and not self.motion_notes
            and self.facial_cycle == EXPRESSION_VARIANTS
            and self.motion_cycle == MOVEMENT_VARIANTS
        )


@dataclass(frozen=True)
class VarianceStep:
    """Explicit per-photo facial + motion settings (1–10 steps)."""

    facial_level: str = DEFAULT_VARIANCE_LEVEL
    motion_level: str = DEFAULT_VARIANCE_LEVEL
    facial_note: str = ""
    motion_note: str = ""

    def as_public(self) -> dict[str, str]:
        return {
            "facial": self.facial_level,
            "facial_note": self.facial_note,
            "motion": self.motion_level,
            "motion_note": self.motion_note,
        }


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


def _comma(*parts: str) -> str:
    return ", ".join(part for part in parts if part)


def _first_text(mapping: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return _strip(value)
    return ""


def _person_height(mapping: dict[str, Any]) -> str:
    """Person stature. Pixel ``height`` stays an integer on the generate payload."""
    selected = _first_text(mapping, ("person_height", "stature"))
    if not selected and isinstance(mapping.get("height"), str):
        selected = _strip(mapping.get("height"))
    extra = _strip(mapping.get("height_cm"))
    if extra and extra.replace(".", "", 1).isdigit():
        extra = f"{extra} cm"
    if selected in {"short", "average", "tall"} and extra:
        return f"{selected}, {extra}"
    if selected:
        return selected
    return extra


def _person_hair(mapping: dict[str, Any]) -> str:
    combined = _strip(mapping.get("hair"))
    if combined:
        return combined
    return _comma(
        _strip(mapping.get("hair_color")),
        _strip(mapping.get("hair_length")),
        _strip(mapping.get("hair_style")),
    )


def _person_eyes(mapping: dict[str, Any]) -> str:
    combined = _strip(mapping.get("eyes"))
    if combined:
        return combined
    return _comma(_strip(mapping.get("eyes_size")), _strip(mapping.get("eyes_color")))


def _person_nose(mapping: dict[str, Any]) -> str:
    combined = _strip(mapping.get("nose"))
    if combined:
        return combined
    return _comma(
        _strip(mapping.get("nose_size")),
        _strip(mapping.get("nose_shape") or mapping.get("nose_note")),
    )


def _person_mouth(mapping: dict[str, Any]) -> str:
    combined = _strip(mapping.get("mouth"))
    if combined:
        return combined
    return _comma(
        _strip(mapping.get("mouth_size")),
        _strip(mapping.get("mouth_shape")),
    )


def _person_expression(mapping: dict[str, Any]) -> str:
    chosen = _first_text(mapping, ("expression", "facial_expression"))
    note = _strip(mapping.get("expression_note"))
    if chosen and note and note not in chosen:
        return f"{chosen}, {note}"
    return chosen or note


def _labeled_parts(pairs: list[tuple[str, str]]) -> str:
    return "; ".join(f"{label} {value}" for label, value in pairs if value)


def person_prompt_lines(mapping: dict[str, Any] | None) -> list[str]:
    """Stable Person / Clothing / Props / Action block. Empty fields omitted."""
    data = mapping or {}
    values = {
        "nationality": _first_text(data, ("nationality", "ethnicity", "ethnicity_presentation")),
        "height": _person_height(data),
        "body": _first_text(data, ("body", "body_type")),
        "hair": _person_hair(data),
        "eyes": _person_eyes(data),
        "nose": _person_nose(data),
        "mouth": _person_mouth(data),
        "expression": _person_expression(data),
    }
    person = _labeled_parts([(label, values[label]) for label, _keys in PERSON_PARTS])
    clothing = _labeled_parts(
        [(label, _strip(data.get(field))) for label, field in CLOTHING_PARTS]
    )
    props = _strip(data.get("props"))
    action = _strip(data.get("object_action") or data.get("action_on_objects"))
    lines: list[str] = []
    if person:
        lines.append(f"Person: {person}")
    if clothing:
        lines.append(f"Clothing: {clothing}")
    if props:
        lines.append(f"Props: {props}")
    if action:
        lines.append(f"Action on objects: {action}")
    return lines


def assemble_prompt(body: dict[str, Any] | None) -> str:
    """Build the image prompt in a fixed field order.

    Each non-empty guided factor becomes ``{Label}: {value}`` on its own line.
    The Person block sits after Objects attributes and before Style.
    """
    mapping = body or {}
    lines: list[str] = []
    inserted_person = False
    for field_id, label in PROMPT_FIELDS:
        if field_id == PERSON_SLOT_BEFORE and not inserted_person:
            lines.extend(person_prompt_lines(mapping))
            inserted_person = True
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
    if not inserted_person:
        lines.extend(person_prompt_lines(mapping))
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
    """Portal aspect ratio. OpenRouter field is ``aspect_ratio``, not ``size``."""
    if isinstance(value, str) and value.strip():
        chosen = value.strip()
        if chosen in OUTPUT_RESOLUTION_ALIASES:
            # ``resolution: "2K"`` is the output-size tier, not an aspect ratio.
            return DEFAULT_RESOLUTION
        if chosen not in ALLOWED_RESOLUTIONS:
            allowed = ", ".join(ALLOWED_RESOLUTIONS)
            raise ImageError(400, f"resolution must be an aspect ratio from: {allowed}.")
        return chosen
    if value not in (None, ""):
        raise ImageError(400, "resolution must be a string.")
    if width not in (None, "") and height not in (None, ""):
        try:
            return _aspect_from_wh(int(width), int(height))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            pass
    return DEFAULT_RESOLUTION


def resolve_aspect_ratio(body: dict[str, Any]) -> str:
    raw = body.get("aspect_ratio")
    if isinstance(raw, str) and raw.strip():
        return resolve_resolution(raw)
    raw_resolution = body.get("resolution")
    if isinstance(raw_resolution, str) and raw_resolution.strip() in OUTPUT_RESOLUTION_ALIASES:
        return DEFAULT_RESOLUTION
    return resolve_resolution(raw_resolution, body.get("width"), body.get("height"))


def resolve_output_resolution(value: object) -> str:
    if value is None or value == "":
        return DEFAULT_OUTPUT_RESOLUTION
    if not isinstance(value, str):
        allowed = ", ".join(OUTPUT_RESOLUTIONS)
        raise ImageError(400, f"output_resolution must be one of: {allowed}.")
    chosen = value.strip()
    mapped = OUTPUT_RESOLUTION_ALIASES.get(chosen) or OUTPUT_RESOLUTION_ALIASES.get(chosen.upper())
    if mapped is None:
        allowed = ", ".join(OUTPUT_RESOLUTIONS)
        raise ImageError(400, f"output_resolution must be one of: {allowed}.")
    return mapped


def resolve_output_and_size(body: dict[str, Any]) -> tuple[int, int, str, str]:
    """Return width, height, aspect_ratio, output_resolution (1K/2K/4K)."""
    aspect = resolve_aspect_ratio(body)
    raw_tier = body.get("output_resolution")
    if raw_tier in (None, "") and isinstance(body.get("size_tier"), str):
        raw_tier = body.get("size_tier")
    if raw_tier in (None, "") and isinstance(body.get("resolution"), str):
        maybe = body.get("resolution")
        if maybe in OUTPUT_RESOLUTION_ALIASES or str(maybe).strip() in OUTPUT_RESOLUTION_ALIASES:
            raw_tier = maybe
    width_in = body.get("width")
    height_in = body.get("height")
    if width_in in (None, "") and height_in in (None, ""):
        output_resolution = resolve_output_resolution(raw_tier)
        width, height = pixels_for(output_resolution, aspect)
        return width, height, aspect, output_resolution
    width, height = resolve_size(
        1024 if width_in in (None, "") else width_in,
        1024 if height_in in (None, "") else height_in,
    )
    if raw_tier not in (None, ""):
        output_resolution = resolve_output_resolution(raw_tier)
    else:
        output_resolution = infer_output_resolution(width, height)
    return width, height, aspect, output_resolution


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


def resolve_count(value: object) -> int:
    """Portal photo count. Provider ``n`` stays 1; extra photos are sequential calls."""
    if value is None or value == "":
        return DEFAULT_IMAGE_COUNT
    try:
        count = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ImageError(
            400,
            f"n must be an integer from {MIN_IMAGE_COUNT} to {MAX_IMAGE_COUNT}.",
        ) from None
    if count < MIN_IMAGE_COUNT or count > MAX_IMAGE_COUNT:
        raise ImageError(
            400,
            f"n must be an integer from {MIN_IMAGE_COUNT} to {MAX_IMAGE_COUNT}.",
        )
    return count


def _body_value(body: dict[str, Any], *keys: str) -> object:
    for key in keys:
        if key in body and body[key] not in (None, ""):
            return body[key]
    return None


def resolve_variance_level(value: object, field: str) -> str:
    if value is None or value == "":
        return DEFAULT_VARIANCE_LEVEL
    if not isinstance(value, str):
        allowed = ", ".join(VARIANCE_LEVELS)
        raise ImageError(400, f"{field} must be one of: {allowed}.")
    chosen = value.strip().lower()
    if chosen not in VARIANCE_LEVELS:
        allowed = ", ".join(VARIANCE_LEVELS)
        raise ImageError(400, f"{field} must be one of: {allowed}.")
    return chosen


def resolve_cycle(value: object, *, field: str, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None or value == "":
        return default
    if isinstance(value, str):
        items = [part.strip()[:MAX_FIELD_CHARS] for part in value.split(",") if part.strip()]
    elif isinstance(value, list):
        items = []
        for item in value:
            if item is None or item == "":
                continue
            if not isinstance(item, str):
                raise ImageError(400, f"{field} must be a list of labels.")
            label = item.strip()[:MAX_FIELD_CHARS]
            if label:
                items.append(label)
    else:
        raise ImageError(400, f"{field} must be a list of labels.")
    if not items:
        return default
    if len(items) > MAX_CYCLE_ITEMS:
        raise ImageError(400, f"{field} can list at most {MAX_CYCLE_ITEMS} items.")
    return tuple(items)


def _cycle_for_level(level: str, custom: tuple[str, ...], default: tuple[str, ...], subtle: tuple[str, ...], strong: tuple[str, ...]) -> tuple[str, ...]:
    if custom != default:
        return custom
    if level == "subtle":
        return subtle
    if level == "strong":
        return strong
    return default


def resolve_variance(body: dict[str, Any]) -> VarianceSpec:
    facial_level = resolve_variance_level(
        _body_value(body, "facial_variance", "facial_change", "face_variance"),
        "facial_variance",
    )
    motion_level = resolve_variance_level(
        _body_value(body, "motion_variance", "motion_change", "movement_variance"),
        "motion_variance",
    )
    facial_notes = _strip(
        _body_value(body, "facial_variance_notes", "facial_notes", "facial_change_notes") or ""
    )
    motion_notes = _strip(
        _body_value(body, "motion_variance_notes", "motion_notes", "motion_change_notes") or ""
    )
    facial_custom = resolve_cycle(
        _body_value(body, "facial_cycle", "expression_cycle"),
        field="facial_cycle",
        default=EXPRESSION_VARIANTS,
    )
    motion_custom = resolve_cycle(
        _body_value(body, "motion_cycle", "movement_cycle"),
        field="motion_cycle",
        default=MOVEMENT_VARIANTS,
    )
    return VarianceSpec(
        facial_level=facial_level,
        motion_level=motion_level,
        facial_notes=facial_notes,
        motion_notes=motion_notes,
        facial_cycle=_cycle_for_level(
            facial_level,
            facial_custom,
            EXPRESSION_VARIANTS,
            FACIAL_SUBTLE_VARIANTS,
            FACIAL_STRONG_VARIANTS,
        ),
        motion_cycle=_cycle_for_level(
            motion_level,
            motion_custom,
            MOVEMENT_VARIANTS,
            MOTION_SUBTLE_VARIANTS,
            MOTION_STRONG_VARIANTS,
        ),
    )


def resolve_variance_steps(
    body: dict[str, Any],
    count: int,
    fallback: VarianceSpec | None = None,
) -> list[VarianceStep] | None:
    """Parse explicit per-photo variance. ``None`` keeps global intensity + cycle.

    When provided, ``variance_steps`` must be a list whose length equals ``count``
    (the photo / storyboard frame count, 1–10). Each item is an object::

        {"facial": "off|subtle|medium|strong", "facial_note": "...",
         "motion": "off|subtle|medium|strong", "motion_note": "..."}

    Omitted levels fall back to the global ``facial_variance`` / ``motion_variance``.
    """
    raw = body.get("variance_steps")
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ImageError(400, "variance_steps must be a list.")
    if len(raw) != count:
        raise ImageError(
            400,
            f"variance_steps must have exactly {count} items, one per photo.",
        )
    chosen = fallback or VarianceSpec()
    steps: list[VarianceStep] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ImageError(400, f"variance_steps[{index}] must be an object.")
        raw_facial = _body_value(item, "facial", "facial_variance", "facial_change")
        raw_motion = _body_value(item, "motion", "motion_variance", "motion_change")
        facial_level = resolve_variance_level(
            raw_facial if raw_facial is not None else chosen.facial_level,
            f"variance_steps[{index}].facial",
        )
        motion_level = resolve_variance_level(
            raw_motion if raw_motion is not None else chosen.motion_level,
            f"variance_steps[{index}].motion",
        )
        facial_note = _strip(
            _body_value(item, "facial_note", "facial_notes", "expression") or ""
        )
        motion_note = _strip(
            _body_value(item, "motion_note", "motion_notes", "movement") or ""
        )
        steps.append(
            VarianceStep(
                facial_level=facial_level,
                motion_level=motion_level,
                facial_note=facial_note,
                motion_note=motion_note,
            )
        )
    return steps


def variance_spec_for_step(
    step: VarianceStep | None,
    fallback: VarianceSpec,
    _index: int = 0,
) -> VarianceSpec:
    """Build the prompt spec for one photo from an explicit step."""
    if step is None:
        return fallback
    facial_custom = (
        fallback.facial_cycle
        if fallback.facial_cycle
        not in (EXPRESSION_VARIANTS, FACIAL_SUBTLE_VARIANTS, FACIAL_STRONG_VARIANTS)
        else EXPRESSION_VARIANTS
    )
    motion_custom = (
        fallback.motion_cycle
        if fallback.motion_cycle
        not in (MOVEMENT_VARIANTS, MOTION_SUBTLE_VARIANTS, MOTION_STRONG_VARIANTS)
        else MOVEMENT_VARIANTS
    )
    if step.facial_note:
        facial_cycle: tuple[str, ...] = (step.facial_note,)
    else:
        facial_cycle = _cycle_for_level(
            step.facial_level,
            facial_custom,
            EXPRESSION_VARIANTS,
            FACIAL_SUBTLE_VARIANTS,
            FACIAL_STRONG_VARIANTS,
        )
    if step.motion_note:
        motion_cycle: tuple[str, ...] = (step.motion_note,)
    else:
        motion_cycle = _cycle_for_level(
            step.motion_level,
            motion_custom,
            MOVEMENT_VARIANTS,
            MOTION_SUBTLE_VARIANTS,
            MOTION_STRONG_VARIANTS,
        )
    return VarianceSpec(
        facial_level=step.facial_level,
        motion_level=step.motion_level,
        facial_notes="",
        motion_notes="",
        facial_cycle=facial_cycle,
        motion_cycle=motion_cycle,
    )


def variant_spec(index: int, spec: VarianceSpec | None = None) -> tuple[str, str]:
    chosen = spec or VarianceSpec()
    if chosen.facial_level == "off":
        expression = "same face"
    else:
        cycle = chosen.facial_cycle or EXPRESSION_VARIANTS
        expression = cycle[index % len(cycle)]
    if chosen.motion_level == "off":
        movement = "same pose"
    else:
        cycle = chosen.motion_cycle or MOVEMENT_VARIANTS
        movement = cycle[index % len(cycle)]
    return expression, movement


def variant_suffix(index: int, spec: VarianceSpec | None = None) -> str:
    chosen = spec or VarianceSpec()
    if chosen.uses_legacy_suffix():
        expression, movement = variant_spec(index, chosen)
        return f"Facial expression: {expression}. Movement: {movement}."
    return "\n".join(_variance_lines(index, max(index + 1, 2), chosen))


def _progress_note(notes: str, index: int, total: int) -> str:
    if not notes:
        return ""
    if total <= 1:
        return notes
    return f"Progress {index + 1} of {total} along: {notes}"


def _variance_lines(index: int, total: int, spec: VarianceSpec) -> list[str]:
    lines = [IDENTITY_LOCK, f"Photo {index + 1} of {total}."]
    if spec.facial_level == "off":
        lines.append(
            "Facial change: off. Keep the same facial expression, gaze, head angle, "
            "and emotion. Only microscopic natural variation is allowed."
        )
    else:
        expression, _movement = variant_spec(index, spec)
        lines.append(
            f"Facial change ({spec.facial_level}): {expression}. "
            "Vary expression, gaze, head turn, and emotion intensity while keeping identity stable."
        )
        progress = _progress_note(spec.facial_notes, index, total)
        if progress:
            lines.append(f"Facial direction: {progress}.")
    if spec.motion_level == "off":
        lines.append(
            "Motion change: off. Keep the same pose, gesture, and body position. "
            "Only microscopic natural variation is allowed."
        )
    else:
        _expression, movement = variant_spec(index, spec)
        lines.append(
            f"Motion change ({spec.motion_level}): {movement}. "
            "Vary pose, gesture, body movement, and action on objects."
        )
        progress = _progress_note(spec.motion_notes, index, total)
        if progress:
            lines.append(f"Motion direction: {progress}.")
    return lines


def variant_prompt(
    base: str,
    index: int,
    total: int,
    spec: VarianceSpec | None = None,
    *,
    explicit_step: bool = False,
) -> str:
    if total <= 1:
        return base
    chosen = spec or VarianceSpec()
    if not explicit_step and chosen.uses_legacy_suffix():
        return f"{base}\n\n{variant_suffix(index, chosen)}"
    extra = "\n".join(_variance_lines(index, total, chosen))
    return f"{base}\n\n{extra}"


def step_variant_caption(index: int, spec: VarianceSpec) -> str:
    expression, movement = variant_spec(index, spec)
    return f"{expression} ({spec.facial_level}), {movement} ({spec.motion_level})"


def resolution_prompt(base: str, output_resolution: str) -> str:
    hint = RESOLUTION_HINTS.get(output_resolution, "")
    if not hint:
        return base
    return f"{base}\n\n{hint}"


def variant_caption(index: int, total: int, spec: VarianceSpec | None = None) -> str:
    if total <= 1:
        return ""
    expression, movement = variant_spec(index, spec)
    return f"{expression}, {movement}"


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
                "output_resolution": item.get("output_resolution") or job.get("output_resolution"),
                "width": item.get("width") or job.get("width"),
                "height": item.get("height") or job.get("height"),
                "facial": item.get("facial") or "",
                "motion": item.get("motion") or "",
                "facial_level": item.get("facial_level") or "",
                "motion_level": item.get("motion_level") or "",
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
        "aspect_ratio": job.get("aspect_ratio") or job.get("resolution"),
        "output_resolution": job.get("output_resolution") or DEFAULT_OUTPUT_RESOLUTION,
        "facial_variance": job.get("facial_variance") or DEFAULT_VARIANCE_LEVEL,
        "motion_variance": job.get("motion_variance") or DEFAULT_VARIANCE_LEVEL,
        "facial_variance_notes": job.get("facial_variance_notes") or "",
        "motion_variance_notes": job.get("motion_variance_notes") or "",
        "variance_steps": job.get("variance_steps"),
        "n": int(job.get("n") or len(images) or DEFAULT_IMAGE_COUNT),
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
    seed: int | None = None,
    timeout: float | None = None,
) -> tuple[bytes, str | None]:
    if OPENROUTER_IMAGES_URL == OPENROUTER_CHAT_URL:
        raise ImageError(500, "Image jobs must not use chat completions.")
    # Provider field names (OpenRouter Image API / FLUX.2 Pro endpoints API):
    #   prompt, n, aspect_ratio, output_format, input_references, seed.
    # FLUX.2 Pro does not list ``size``, ``resolution``, ``width``, or ``height``;
    # unlisted fields are rejected. Portal 1K/2K/4K is stored as metadata and a
    # prompt hint; OpenRouter still receives aspect_ratio only for dimensions.
    # https://openrouter.ai/black-forest-labs/flux.2-pro/llms.txt
    payload: dict[str, Any] = {
        "model": model_id,
        "prompt": prompt,
        "n": 1,
        "aspect_ratio": aspect_ratio or _aspect_from_wh(width, height),
        "output_format": output_format,
    }
    if input_references:
        payload["input_references"] = input_references
    if seed is not None:
        payload["seed"] = seed
    try:
        response = httpx.post(
            OPENROUTER_IMAGES_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout if timeout is not None else OPENROUTER_IMAGES_TIMEOUT_SECONDS,
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
    width, height, aspect, output_resolution = resolve_output_and_size(body)
    fmt = resolve_format(body.get("format", "png"))
    frames_value = body.get("frames")
    storyboard = isinstance(frames_value, list) and len(frames_value) > 1
    count = resolve_count(body.get("n") if body.get("n") not in (None, "") else body.get("count"))
    if storyboard:
        frames = resolve_frames(frames_value)
        count = len(frames)
    else:
        if frames_value is not None:
            resolve_frames(frames_value)
        frames = [""] * count
    variance = resolve_variance(body)
    steps = resolve_variance_steps(body, count, variance)
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
    timeout = images_timeout_seconds(output_resolution)
    written: list[Path] = []
    image_rows: list[dict[str, Any]] = []
    try:
        for index, caption in enumerate(frames):
            step = steps[index] if steps else None
            spec = variance_spec_for_step(step, variance, index)
            explicit_step = steps is not None
            if storyboard:
                frame_prompt = _frame_prompt(prompt, caption, index, len(frames))
                if count > 1:
                    frame_prompt = variant_prompt(
                        frame_prompt, index, count, spec, explicit_step=explicit_step
                    )
            else:
                frame_prompt = variant_prompt(
                    prompt, index, count, spec, explicit_step=explicit_step
                )
            frame_prompt = resolution_prompt(frame_prompt, output_resolution)
            seed = None
            if count > 1 and spec.facial_level == "off" and spec.motion_level == "off":
                seed = 1000 + index
            raw, media_type = _post_openrouter_image(
                api_key=api_key,
                model_id=model_id,
                prompt=frame_prompt,
                width=width,
                height=height,
                output_format=provider_format,
                input_references=references or None,
                aspect_ratio=aspect,
                seed=seed,
                timeout=timeout,
            )
            converted = convert_image_bytes(raw, fmt, media_type)
            filename = f"{job_id}-{index}.{extension}"
            relative = f"{IMAGES_DIRNAME}/{filename}"
            path = folder / filename
            path.write_bytes(converted)
            written.append(path)
            size_label = f"{output_resolution} · {width}×{height}"
            expression, movement = variant_spec(index, spec) if count > 1 else ("", "")
            row_caption = caption or size_label
            if count > 1:
                if explicit_step:
                    variant_label = step_variant_caption(index, spec)
                else:
                    variant_label = variant_caption(index, count, spec)
                if storyboard and caption:
                    row_caption = f"{size_label} · {caption} · {variant_label}"
                else:
                    row_caption = f"{size_label} · {variant_label}"
            elif not storyboard:
                row_caption = size_label
            image_rows.append(
                {
                    "index": index,
                    "caption": row_caption,
                    "filename": filename,
                    "stored_path": relative,
                    "output_resolution": output_resolution,
                    "width": width,
                    "height": height,
                    "facial": expression,
                    "motion": movement,
                    "facial_level": spec.facial_level if count > 1 else "",
                    "motion_level": spec.motion_level if count > 1 else "",
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
        "aspect_ratio": aspect,
        "output_resolution": output_resolution,
        "facial_variance": variance.facial_level,
        "motion_variance": variance.motion_level,
        "facial_variance_notes": variance.facial_notes,
        "motion_variance_notes": variance.motion_notes,
        "variance_steps": [step.as_public() for step in steps] if steps else None,
        "n": count,
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

