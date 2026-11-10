"""Generate 30–60s movies through the OpenRouter Videos API.

Jobs never go to ``/api/v1/chat/completions``. A catalog quote must be
confirmed before generate. Provider clips are shorter than a minute, so a
movie is split into allowed lengths and stitched with ffmpeg. Files live
under ``$DATA_DIR/videos/``. Quotes live in ``$DATA_DIR/video-quotes.json``.
The OpenRouter key stays out of return values and logs.
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from .catalog import (
    PRICES_RECORDED_ON,
    PRICE_SOURCE,
    get_model,
    is_available_in_hong_kong,
)
from .chat import (
    MISSING_KEY_DETAIL,
    REGION_SETUP_HINT,
    _sanitize_provider_message,
    recorded_model,
)
from .image_refs import MEDIA_TYPES
from .openrouter_key import load_openrouter_api_key
from .video_projects import (
    MAX_CLIPS,
    MIN_DURATION_SECONDS,
    VideoError,
    append_clip,
    character_reference_rows,
    frame_image_rows,
    get_project,
    project_clip_paths,
    resolve_duration,
    set_merged,
    videos_dir,
    _now,
    _require_project,
)

OPENROUTER_VIDEOS_URL = "https://openrouter.ai/api/v1/videos"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_VIDEOS_TIMEOUT_SECONDS = 60.0
OPENROUTER_VIDEO_POLL_TIMEOUT_SECONDS = 240.0
OPENROUTER_DOWNLOAD_TIMEOUT_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 2.0
QUOTE_TTL_SECONDS = 15 * 60
QUOTES_NAME = "video-quotes.json"
MAX_PROMPT_CHARS = 8000
CANTONESE_ACCENT_TEXT = "speaks with a natural Hong Kong Cantonese accent"
MONEY = Decimal("0.0001")

# Allowed provider clip lengths. A 30–60s movie is billed as the sum of these.
MODEL_ALLOWED_DURATIONS: dict[str, tuple[int, ...]] = {
    "minimax/hailuo-2.3": (6, 10),
    "minimax/hailuo-3": tuple(range(5, 16)),
    "kwaivgi/kling-v3.0-std": tuple(range(3, 16)),
}
MODEL_SUPPORTS_AUDIO = frozenset(
    {
        "minimax/hailuo-3",
        "kwaivgi/kling-v3.0-std",
    }
)
MODEL_SUPPORTS_LAST_FRAME = frozenset(
    {
        "minimax/hailuo-3",
        "kwaivgi/kling-v3.0-std",
    }
)
HAILUO3_FREE_REFERENCES = 5
HAILUO3_EXTRA_REFERENCE_USD = Decimal("0.04")
HAILUO3_ID = "minimax/hailuo-3"
KLING_ID = "kwaivgi/kling-v3.0-std"

PAN_CHOICES = ("", "left", "right")
TILT_CHOICES = ("", "up", "down")
DOLLY_CHOICES = ("", "forward", "backward")
ZOOM_CHOICES = ("", "in", "out")
ROLL_CHOICES = ("", "cw", "ccw")
CINEMATIC_MODIFIERS: dict[str, str] = {
    "handheld": "Handheld camera shake / Unstable documentary style",
    "steadicam": "Steadicam tracking shot / Smooth follow shot",
    "whip_pan": "Fast whip pan / Motion blur transition",
    "orbital": "360-degree orbital shot / Arc shot around the subject",
    "jib": "Jib crane shot lifting up / Drone rising shot",
}

CAMERA_LINES = {
    ("pan", "left"): "Pan left: the camera turns horizontally left to reveal the scene or follow the subject.",
    ("pan", "right"): "Pan right: the camera turns horizontally right to reveal the scene or follow the subject.",
    ("tilt", "up"): "Tilt up: the camera angles upward, a low-angle look.",
    ("tilt", "down"): "Tilt down: the camera angles downward, a bird’s-eye look.",
    ("dolly", "forward"): "Dolly forward: the camera physically pushes in; background perspective changes.",
    ("dolly", "backward"): "Dolly backward: the camera physically pulls away; background perspective changes.",
    ("zoom", "in"): "Zoom in: the lens optically enlarges the subject.",
    ("zoom", "out"): "Zoom out: the lens optically widens the frame.",
    ("roll", "cw"): "Roll clockwise: the frame rotates to suggest dizziness, chaos, or a dream.",
    ("roll", "ccw"): "Roll counter-clockwise: the frame rotates the other way.",
}
ORIENTATION_LOCK_TEXT = (
    "Character orientation lock: keep subject action independent of camera "
    "motion so dolly and zoom do not warp or distort the people."
)
INTERPOLATION_TEXT = (
    "First and end frame interpolation: start on the first still and finish on "
    "the last still; interpolate the physically optical camera move between them."
)
INTENSITY_TEXT = {
    0: "Motion intensity 0: smooth, locked-off, almost no camera energy.",
    1: "Motion intensity 1: gentle, stable camera moves.",
    2: "Motion intensity 2: noticeable cinematic camera energy.",
    3: "Motion intensity 3: high-tension, explosive camera moves.",
}


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _ffmpeg_bin() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def _money(value: Decimal) -> str:
    quantized = value.quantize(MONEY, rounding=ROUND_HALF_UP)
    return format(quantized, "f")


def _strip(value: object, limit: int = 2000) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _choice(value: object, allowed: tuple[str, ...], field: str) -> str:
    raw = _strip(value, 40).lower()
    aliases = {
        "none": "",
        "off": "",
        "+": "in",
        "zoom in": "in",
        "zoom out": "out",
        "-": "out",
        "clockwise": "cw",
        "counterclockwise": "ccw",
        "counter-clockwise": "ccw",
        "anticlockwise": "ccw",
        "in": "in",
        "out": "out",
    }
    mapped = aliases.get(raw, raw)
    if mapped not in allowed:
        raise VideoError(400, f"{field} must be one of: {', '.join(item or 'none' for item in allowed)}.")
    return mapped


def resolve_motion_intensity(value: object) -> int:
    if value in (None, ""):
        return 1
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise VideoError(400, "motion_intensity must be 0, 1, 2, or 3.") from None
    intensity = int(round(number))
    if intensity < 0 or intensity > 3:
        raise VideoError(400, "motion_intensity must be 0, 1, 2, or 3.")
    return intensity


def resolve_modifiers(value: object) -> list[str]:
    if value in (None, "", []):
        return []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",") if part.strip()]
    elif isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
    else:
        raise VideoError(400, "cinematic_modifiers must be a list.")
    unknown = [item for item in items if item not in CINEMATIC_MODIFIERS]
    if unknown:
        raise VideoError(
            400,
            "Unknown cinematic modifier: "
            + ", ".join(unknown)
            + ". Allowed: "
            + ", ".join(CINEMATIC_MODIFIERS)
            + ".",
        )
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def split_segments(duration_seconds: int, allowed: tuple[int, ...]) -> list[int]:
    allowed_sorted = tuple(sorted(set(int(item) for item in allowed if int(item) > 0)))
    if not allowed_sorted:
        raise VideoError(400, "This video model has no listed clip lengths.")
    max_piece = allowed_sorted[-1]
    ceiling = duration_seconds + max_piece
    inf = 10**9
    best = [inf] * (ceiling + 1)
    prev = [-1] * (ceiling + 1)
    pick = [0] * (ceiling + 1)
    best[0] = 0
    for total in range(1, ceiling + 1):
        for piece in allowed_sorted:
            if piece > total or best[total - piece] >= inf:
                continue
            candidate = best[total - piece] + 1
            if candidate < best[total]:
                best[total] = candidate
                prev[total] = total - piece
                pick[total] = piece
    billed = next((total for total in range(duration_seconds, ceiling + 1) if best[total] < inf), None)
    if billed is None:
        raise VideoError(400, "Cannot split this duration into the model’s clip lengths.")
    parts: list[int] = []
    cursor = billed
    while cursor > 0:
        piece = pick[cursor]
        if piece <= 0:
            raise VideoError(400, "Cannot split this duration into the model’s clip lengths.")
        parts.append(piece)
        cursor = prev[cursor]
    parts.reverse()
    return parts


def allowed_durations(model_id: str) -> tuple[int, ...]:
    allowed = MODEL_ALLOWED_DURATIONS.get(model_id)
    if not allowed:
        return tuple(range(MIN_DURATION_SECONDS, MIN_DURATION_SECONDS + 1))
    return allowed


def assemble_camera_prompt(body: dict[str, Any]) -> str:
    pan = _choice(body.get("pan"), PAN_CHOICES, "pan")
    tilt = _choice(body.get("tilt"), TILT_CHOICES, "tilt")
    dolly = _choice(body.get("dolly"), DOLLY_CHOICES, "dolly")
    zoom = _choice(body.get("zoom"), ZOOM_CHOICES, "zoom")
    roll = _choice(body.get("roll"), ROLL_CHOICES, "roll")
    intensity = resolve_motion_intensity(body.get("motion_intensity"))
    lines: list[str] = []
    for key, value in (
        ("pan", pan),
        ("tilt", tilt),
        ("dolly", dolly),
        ("zoom", zoom),
        ("roll", roll),
    ):
        text = CAMERA_LINES.get((key, value))
        if text:
            lines.append(text)
    if pan == "left" and zoom == "in" and dolly == "backward":
        lines.append("Dolly zoom / Hitchcock zoom: dolly back while zooming in.")
    if pan == "right" and zoom == "out" and dolly == "forward":
        lines.append("Dolly zoom / Hitchcock zoom: dolly forward while zooming out.")
    lines.append(INTENSITY_TEXT[intensity])
    if body.get("character_orientation_lock"):
        lines.append(ORIENTATION_LOCK_TEXT)
    if body.get("interpolation"):
        lines.append(INTERPOLATION_TEXT)
    for modifier in resolve_modifiers(body.get("cinematic_modifiers")):
        lines.append(CINEMATIC_MODIFIERS[modifier])
    return " ".join(lines)


def _character_prompt(project: dict[str, Any]) -> str:
    lines: list[str] = []
    for character in project.get("characters") or []:
        if not isinstance(character, dict):
            continue
        photos = character.get("photos") or []
        name = str(character.get("name") or "").strip()
        role = str(character.get("role") or "").strip()
        if not name and not photos:
            continue
        label = role or "character"
        who = name or f"unnamed {label}"
        count = len(photos) if isinstance(photos, list) else 0
        extra = f", {count} reference photo{'s' if count != 1 else ''}" if count else ""
        lines.append(f"{label} {who}{extra}")
    if not lines:
        return ""
    return (
        "Major characters; keep likeness from the uploaded photos: "
        + "; ".join(lines)
        + "."
    )


def assemble_video_prompt(body: dict[str, Any], project: dict[str, Any] | None = None) -> str:
    parts: list[str] = []
    title = _strip(body.get("title"), 200)
    scene = _strip(body.get("scene"), 2000)
    prompt = _strip(body.get("prompt"), MAX_PROMPT_CHARS)
    if title:
        parts.append(title)
    if scene:
        parts.append(scene)
    if prompt:
        parts.append(prompt)
    if project:
        character_line = _character_prompt(project)
        if character_line:
            parts.append(character_line)
    if body.get("cantonese_accent"):
        parts.append(f"Dialogue {CANTONESE_ACCENT_TEXT}.")
    camera = assemble_camera_prompt(body)
    if camera:
        parts.append(camera)
    assembled = "\n".join(part for part in parts if part).strip()
    if not assembled:
        raise VideoError(400, "prompt is required.")
    return assembled[:MAX_PROMPT_CHARS]


def _assert_video_model(model_id: str, extra_hidden: frozenset[str] | set[str] | None) -> dict[str, object]:
    if not is_available_in_hong_kong(model_id, extra_hidden):
        raise VideoError(400, "That video model is not available.")
    model = get_model(model_id)
    if model is None or "video_gen" not in model["functions"]:  # type: ignore[operator]
        raise VideoError(400, "That video model is not in the catalog.")
    return model


def _output_rate(model_id: str, *, generate_audio: bool) -> tuple[Decimal, str, str]:
    model = get_model(model_id)
    if model is None:
        raise VideoError(400, "That video model is not in the catalog.")
    prices = list(model.get("prices") or [])  # type: ignore[arg-type]
    with_audio = None
    output = None
    for price in prices:
        if not isinstance(price, dict):
            continue
        label = str(price.get("label") or "")
        if label == "Output with audio":
            with_audio = price
        elif label == "Output":
            output = price
    chosen = with_audio if generate_audio and with_audio is not None else output
    if chosen is None:
        raise VideoError(500, "This video model has no recorded output price.")
    return (
        Decimal(str(chosen["amount_usd"])),
        str(chosen["label"]),
        str(chosen["unit"]),
    )


def _wants_audio(body: dict[str, Any], model_id: str) -> bool:
    if model_id not in MODEL_SUPPORTS_AUDIO:
        return False
    if "generate_audio" in body and body.get("generate_audio") is not None:
        return bool(body.get("generate_audio"))
    return bool(body.get("cantonese_accent"))


def quote_fingerprint(
    *,
    model_id: str,
    duration_seconds: int,
    generate_audio: bool,
    reference_image_count: int,
    interpolation: bool,
    project_id: str,
) -> str:
    payload = {
        "model_id": model_id,
        "duration_seconds": duration_seconds,
        "generate_audio": generate_audio,
        "reference_image_count": reference_image_count,
        "interpolation": bool(interpolation),
        "project_id": project_id,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _quotes_path(data_dir: Path) -> Path:
    return Path(data_dir) / QUOTES_NAME


def load_quotes(data_dir: Path) -> list[dict[str, Any]]:
    path = _quotes_path(data_dir)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = raw.get("quotes") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and row.get("id")]


def save_quotes(data_dir: Path, quotes: list[dict[str, Any]]) -> None:
    path = _quotes_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps({"quotes": quotes}, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _parse_when(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_quote(
    data_dir: Path,
    body: dict[str, Any],
    *,
    model_id: str,
    extra_hidden: frozenset[str] | set[str] | None = None,
) -> dict[str, Any]:
    _assert_video_model(model_id, extra_hidden)
    project_id = _strip(body.get("project_id"), 80)
    project: dict[str, Any] | None = None
    reference_count = 0
    if project_id:
        row = _require_project(data_dir, project_id)
        project = get_project(data_dir, project_id)
        reference_count = len(character_reference_rows(data_dir, row))
        if len(project.get("clips") or []) >= MAX_CLIPS:
            raise VideoError(
                400,
                f"A project can hold at most {MAX_CLIPS} generated clips.",
            )
    duration = resolve_duration(body.get("duration_seconds") or 30)
    generate_audio = _wants_audio(body, model_id)
    interpolation = bool(body.get("interpolation"))
    segments = split_segments(duration, allowed_durations(model_id))
    billed = sum(segments)
    rate, label, unit = _output_rate(model_id, generate_audio=generate_audio)
    line_items: list[dict[str, Any]] = [
        {
            "label": label,
            "amount_usd": _money(rate),
            "unit": unit,
            "quantity": billed,
            "subtotal_usd": _money(rate * billed),
        }
    ]
    extra_refs = 0
    extra_cost = Decimal("0")
    if model_id == HAILUO3_ID and reference_count > HAILUO3_FREE_REFERENCES:
        extra_refs = reference_count - HAILUO3_FREE_REFERENCES
        extra_cost = HAILUO3_EXTRA_REFERENCE_USD * extra_refs
        line_items.append(
            {
                "label": "Reference image",
                "amount_usd": _money(HAILUO3_EXTRA_REFERENCE_USD),
                "unit": "USD per image",
                "quantity": extra_refs,
                "subtotal_usd": _money(extra_cost),
                "detail": "The first 5 reference images are free.",
            }
        )
    total = (rate * billed) + extra_cost
    fingerprint = quote_fingerprint(
        model_id=model_id,
        duration_seconds=duration,
        generate_audio=generate_audio,
        reference_image_count=reference_count,
        interpolation=interpolation,
        project_id=project_id,
    )
    now = datetime.now(timezone.utc).replace(microsecond=0)
    expires = now + timedelta(seconds=QUOTE_TTL_SECONDS)
    quote_id = str(uuid.uuid4())
    public = {
        "quote_id": quote_id,
        "expires_at": expires.isoformat().replace("+00:00", "Z"),
        "model_id": model_id,
        "provider": get_model(model_id)["provider"] if get_model(model_id) else "",
        "name": get_model(model_id)["name"] if get_model(model_id) else "",
        "duration_seconds": duration,
        "billed_seconds": billed,
        "segments": segments,
        "generate_audio": generate_audio,
        "cantonese_accent": bool(body.get("cantonese_accent")),
        "reference_image_count": reference_count,
        "interpolation": interpolation,
        "project_id": project_id,
        "line_items": line_items,
        "total_usd": _money(total),
        "prices_recorded_on": PRICES_RECORDED_ON,
        "price_source": PRICE_SOURCE,
        "note": (
            "Catalog list prices, not a live OpenRouter invoice. "
            "Confirm this estimate before generate."
        ),
        "assembled_prompt": assemble_video_prompt(body, project),
    }
    stored = {
        "id": quote_id,
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": public["expires_at"],
        "consumed": False,
        "fingerprint": fingerprint,
        "total_usd": public["total_usd"],
        "public": public,
    }
    quotes = [row for row in load_quotes(data_dir) if not row.get("consumed")]
    quotes.append(stored)
    save_quotes(data_dir, quotes[-40:])
    return public


def _require_quote(data_dir: Path, quote_id: str, fingerprint: str) -> dict[str, Any]:
    chosen = (quote_id or "").strip()
    if not chosen:
        raise VideoError(400, "quote_id is required. Estimate cost and confirm first.")
    now = datetime.now(timezone.utc)
    quotes = load_quotes(data_dir)
    match = next((row for row in quotes if row.get("id") == chosen), None)
    if match is None:
        raise VideoError(400, "Unknown quote. Estimate cost again.")
    if match.get("consumed"):
        raise VideoError(409, "This estimate was already used. Estimate cost again.")
    expires = _parse_when(match.get("expires_at"))
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires is not None and expires < now:
        raise VideoError(400, "Quote expired. Estimate cost again.")
    if match.get("fingerprint") != fingerprint:
        raise VideoError(
            409,
            "The estimate no longer matches these settings. Estimate cost again.",
        )
    return match


def consume_quote(data_dir: Path, quote_id: str) -> None:
    quotes = load_quotes(data_dir)
    for row in quotes:
        if row.get("id") == quote_id:
            row["consumed"] = True
    save_quotes(data_dir, quotes)


def _reference_payload(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def _frame_payload(
    frames: dict[str, dict[str, Any]], *, model_id: str
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    order = ("first", "last") if model_id in MODEL_SUPPORTS_LAST_FRAME else ("first",)
    for kind in order:
        row = frames.get(kind)
        if not row:
            continue
        data = row.get("bytes")
        if not isinstance(data, (bytes, bytearray)):
            continue
        kind_name = "first_frame" if kind == "first" else "last_frame"
        media = MEDIA_TYPES.get(str(row.get("type") or "png"), "image/png")
        encoded = base64.b64encode(bytes(data)).decode("ascii")
        items.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{media};base64,{encoded}"},
                "frame_type": kind_name,
            }
        )
    return items


def _videos_failure(status_code: int, payload: Any, api_key: str | None) -> VideoError:
    message = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            raw = error.get("message")
            if isinstance(raw, str):
                message = raw
        elif isinstance(error, str):
            message = error
    cleaned = _sanitize_provider_message(message or "", api_key)
    if status_code == 403:
        return VideoError(502, REGION_SETUP_HINT if not cleaned else f"{REGION_SETUP_HINT} {cleaned}")
    if cleaned:
        return VideoError(502, cleaned)
    return VideoError(502, "OpenRouter did not return a video.")


def _post_video_job(
    *,
    api_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if OPENROUTER_VIDEOS_URL == OPENROUTER_CHAT_URL:
        raise VideoError(500, "Video jobs must not use chat completions.")
    try:
        response = httpx.post(
            OPENROUTER_VIDEOS_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=OPENROUTER_VIDEOS_TIMEOUT_SECONDS,
            follow_redirects=False,
        )
        status_code = response.status_code
    except Exception:
        raise VideoError(502, "OpenRouter did not return a video.") from None
    body: Any = None
    try:
        body = response.json()
    except Exception:
        body = None
    if status_code not in {200, 202}:
        raise _videos_failure(status_code=status_code, payload=body, api_key=api_key)
    if not isinstance(body, dict):
        raise VideoError(502, "OpenRouter did not return a video.")
    if body.get("error"):
        raise _videos_failure(status_code=status_code, payload=body, api_key=api_key)
    return body


def _poll_video_job(api_key: str, job_id: str, started: dict[str, Any]) -> dict[str, Any]:
    status = str(started.get("status") or "")
    if status in {"completed", "complete", "succeeded"}:
        return started
    poll_url = started.get("polling_url")
    if isinstance(poll_url, str) and poll_url.startswith("https://"):
        url = poll_url
    else:
        url = f"{OPENROUTER_VIDEOS_URL}/{job_id}"
    deadline = time.monotonic() + OPENROUTER_VIDEO_POLL_TIMEOUT_SECONDS
    current = started
    while time.monotonic() < deadline:
        status = str(current.get("status") or "")
        if status in {"completed", "complete", "succeeded"}:
            return current
        if status in {"failed", "cancelled", "canceled", "expired"}:
            raise _videos_failure(502, current, api_key)
        _sleep(POLL_INTERVAL_SECONDS)
        try:
            response = httpx.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=OPENROUTER_VIDEOS_TIMEOUT_SECONDS,
                follow_redirects=False,
            )
        except Exception:
            raise VideoError(502, "OpenRouter did not return a video.") from None
        try:
            body = response.json()
        except Exception:
            body = None
        if response.status_code != 200 or not isinstance(body, dict):
            raise _videos_failure(response.status_code, body, api_key)
        current = body
    raise VideoError(502, "OpenRouter video job timed out.")


def _download_video_bytes(api_key: str, job: dict[str, Any], job_id: str) -> bytes:
    content_url = f"{OPENROUTER_VIDEOS_URL}/{job_id}/content"
    try:
        response = httpx.get(
            content_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=OPENROUTER_DOWNLOAD_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        if response.status_code == 200 and response.content:
            return bytes(response.content)
    except Exception:
        pass
    urls = job.get("unsigned_urls") or job.get("urls") or []
    if isinstance(urls, list) and urls:
        first = urls[0]
        url = first if isinstance(first, str) else (first.get("url") if isinstance(first, dict) else "")
        if isinstance(url, str) and url.startswith("https://"):
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
            except Exception:
                raise VideoError(502, "Could not download the generated video.") from None
            if response.status_code == 200 and response.content:
                return bytes(response.content)
    data = job.get("data")
    if isinstance(data, list) and data and isinstance(data[0], dict):
        b64 = data[0].get("b64_json") or data[0].get("b64")
        if isinstance(b64, str) and b64:
            try:
                return base64.b64decode(b64)
            except Exception as exc:
                raise VideoError(502, "OpenRouter returned an unreadable video.") from exc
    raise VideoError(502, "OpenRouter did not return a video.")


def generate_segment(
    *,
    api_key: str,
    model_id: str,
    prompt: str,
    duration: int,
    generate_audio: bool,
    input_references: list[dict[str, Any]] | None,
    frame_images: list[dict[str, Any]] | None,
    aspect_ratio: str,
) -> bytes:
    payload: dict[str, Any] = {
        "model": model_id,
        "prompt": prompt,
        "duration": duration,
        "aspect_ratio": aspect_ratio,
    }
    if generate_audio and model_id in MODEL_SUPPORTS_AUDIO:
        payload["generate_audio"] = True
    if input_references:
        payload["input_references"] = input_references
    if frame_images:
        payload["frame_images"] = frame_images
    started = _post_video_job(api_key=api_key, payload=payload)
    job_id = str(started.get("id") or started.get("generation_id") or "").strip()
    if not job_id:
        raise VideoError(502, "OpenRouter did not return a video.")
    finished = _poll_video_job(api_key, job_id, started)
    return _download_video_bytes(api_key, finished, job_id)


def concat_videos(paths: list[Path], dest: Path) -> None:
    if not paths:
        raise VideoError(500, "No video segments to stitch.")
    if len(paths) == 1:
        dest.write_bytes(paths[0].read_bytes())
        return
    binary = _ffmpeg_bin()
    inputs: list[str] = []
    for path in paths:
        inputs.extend(["-i", str(path)])
    n = len(paths)
    video_only = "".join(f"[{index}:v:0]" for index in range(n)) + f"concat=n={n}:v=1:a=0[v]"
    cmd = [
        binary,
        "-y",
        *inputs,
        "-filter_complex",
        video_only,
        "-map",
        "[v]",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(dest),
    ]
    try:
        completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise VideoError(503, "ffmpeg is required to stitch video clips.") from exc
    if completed.returncode != 0 or not dest.is_file() or dest.stat().st_size == 0:
        raise VideoError(502, "Could not stitch the video clips.")


def generate_video(
    data_dir: Path,
    body: dict[str, Any],
    *,
    model_id: str,
    extra_hidden: frozenset[str] | set[str] | None = None,
) -> dict[str, Any]:
    _assert_video_model(model_id, extra_hidden)
    project_id = _strip(body.get("project_id"), 80)
    if not project_id:
        raise VideoError(400, "project_id is required.")
    row = _require_project(data_dir, project_id)
    project = get_project(data_dir, project_id)
    if len(project.get("clips") or []) >= MAX_CLIPS:
        raise VideoError(
            400,
            f"A project can hold at most {MAX_CLIPS} generated clips.",
        )
    duration = resolve_duration(body.get("duration_seconds") or 30)
    generate_audio = _wants_audio(body, model_id)
    interpolation = bool(body.get("interpolation"))
    references = character_reference_rows(data_dir, row)
    frames = frame_image_rows(data_dir, row)
    if interpolation and not frames.get("first"):
        raise VideoError(400, "First-frame image is required for interpolation.")
    fingerprint = quote_fingerprint(
        model_id=model_id,
        duration_seconds=duration,
        generate_audio=generate_audio,
        reference_image_count=len(references),
        interpolation=interpolation,
        project_id=project_id,
    )
    quote = _require_quote(data_dir, str(body.get("quote_id") or ""), fingerprint)
    prompt = assemble_video_prompt(body, project)
    segments = split_segments(duration, allowed_durations(model_id))
    api_key = load_openrouter_api_key()
    if not api_key:
        raise VideoError(503, MISSING_KEY_DETAIL)
    aspect = _strip(body.get("aspect_ratio"), 16) or "16:9"
    input_references = _reference_payload(references)
    frame_images = _frame_payload(frames, model_id=model_id) if interpolation else []
    folder = videos_dir(data_dir)
    clip_id = str(uuid.uuid4())
    segment_paths: list[Path] = []
    try:
        for index, seconds in enumerate(segments):
            piece_prompt = prompt
            if len(segments) > 1:
                piece_prompt = (
                    f"{prompt}\nThis is beat {index + 1} of {len(segments)} "
                    f"in a continuous {duration}-second short movie. Continue the same scene."
                )
            raw = generate_segment(
                api_key=api_key,
                model_id=model_id,
                prompt=piece_prompt,
                duration=seconds,
                generate_audio=generate_audio,
                input_references=input_references or None,
                frame_images=frame_images or None,
                aspect_ratio=aspect,
            )
            piece = folder / f"{clip_id}-seg{index}.mp4"
            piece.write_bytes(raw)
            segment_paths.append(piece)
        dest = folder / f"{clip_id}.mp4"
        concat_videos(segment_paths, dest)
        consume_quote(data_dir, str(quote["id"]))
    except Exception:
        for path in segment_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    finally:
        for path in segment_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
    meta = recorded_model("video_gen", model_id)
    clip = {
        "id": clip_id,
        "duration_seconds": duration,
        "billed_seconds": sum(segments),
        "prompt": _strip(body.get("prompt"), MAX_PROMPT_CHARS),
        "assembled_prompt": prompt,
        "model_id": model_id,
        "provider": meta["provider"],
        "name": meta["name"],
        "total_usd": quote.get("total_usd") or (quote.get("public") or {}).get("total_usd"),
        "quote_id": quote["id"],
        "segments": segments,
        "filename": f"{clip_id}.mp4",
        "stored_path": f"videos/{clip_id}.mp4",
        "created_at": _now(),
        "cantonese_accent": bool(body.get("cantonese_accent")),
        "generate_audio": generate_audio,
    }
    public = append_clip(data_dir, project_id, clip)
    return public


def merge_project_clips(data_dir: Path, project_id: str) -> dict[str, Any]:
    row = _require_project(data_dir, project_id)
    clips = project_clip_paths(data_dir, row)
    if len(clips) < 2:
        raise VideoError(400, "Merge needs at least 2 generated clips.")
    if len(clips) > MAX_CLIPS:
        raise VideoError(400, f"Merge accepts at most {MAX_CLIPS} clips.")
    merge_id = str(uuid.uuid4())
    dest = videos_dir(data_dir) / f"{merge_id}.mp4"
    concat_videos([path for _clip_id, path in clips], dest)
    merged = {
        "id": merge_id,
        "clip_ids": [clip_id for clip_id, _path in clips],
        "filename": f"{merge_id}.mp4",
        "stored_path": f"videos/{merge_id}.mp4",
        "created_at": _now(),
        "total_usd": "0.0000",
        "note": "Local ffmpeg stitch. No OpenRouter charge.",
    }
    return set_merged(data_dir, project_id, merged)
