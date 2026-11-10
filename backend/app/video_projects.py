"""Saved Video studio projects: characters, photos, clips, and a merge.

The index is ``$DATA_DIR/video-projects.json``. Character stills live under
``$DATA_DIR/video-refs/``. Generated clips and merges live under
``$DATA_DIR/videos/``.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .catalog import get_model, is_available_in_hong_kong
from .image_refs import (
    ALLOWED_EXTENSIONS,
    MAX_REFERENCE_BYTES,
    MEDIA_TYPES,
    extension_of,
    sniff_image_kind,
)

INDEX_NAME = "video-projects.json"
REFS_DIRNAME = "video-refs"
VIDEOS_DIRNAME = "videos"
MAX_PROJECT_NAME = 120
MAX_CHARACTER_NAME = 80
MAX_CHARACTERS = 3
MAX_PHOTOS_PER_CHARACTER = 5
MAX_CLIPS = 4
MIN_DURATION_SECONDS = 30
MAX_DURATION_SECONDS = 60
ROLES = ("actress", "actor", "supporting")
PROJECT_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
PHOTO_ID_RE = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)
MISSING_PROJECT = "Video project not found."
EMPTY_NAME = "name is required."
LONG_NAME = f"name must be at most {MAX_PROJECT_NAME} characters."
MISSING_PHOTO = "Character photo not found."
MISSING_CLIP = "Video clip not found."
MISSING_FRAME = "Frame image not found."


class VideoError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def index_path(data_dir: Path) -> Path:
    return Path(data_dir) / INDEX_NAME


def refs_dir(data_dir: Path) -> Path:
    path = Path(data_dir) / REFS_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def videos_dir(data_dir: Path) -> Path:
    path = Path(data_dir) / VIDEOS_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def resolve_project_name(value: object) -> str:
    if not isinstance(value, str):
        raise VideoError(400, EMPTY_NAME)
    name = value.strip()
    if not name:
        raise VideoError(400, EMPTY_NAME)
    if len(name) > MAX_PROJECT_NAME:
        raise VideoError(400, LONG_NAME)
    return name


def resolve_duration(value: object) -> int:
    try:
        seconds = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise VideoError(
            400,
            f"duration_seconds must be an integer from {MIN_DURATION_SECONDS} to {MAX_DURATION_SECONDS}.",
        ) from None
    if seconds < MIN_DURATION_SECONDS or seconds > MAX_DURATION_SECONDS:
        raise VideoError(
            400,
            f"duration_seconds must be from {MIN_DURATION_SECONDS} to {MAX_DURATION_SECONDS}.",
        )
    return seconds


def resolve_slot(value: object) -> int:
    try:
        slot = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise VideoError(400, "character slot must be 0, 1, or 2.") from None
    if slot < 0 or slot >= MAX_CHARACTERS:
        raise VideoError(400, "character slot must be 0, 1, or 2.")
    return slot


def resolve_role(value: object) -> str:
    role = str(value or "").strip().lower()
    aliases = {
        "actress": "actress",
        "major actress": "actress",
        "female": "actress",
        "actor": "actor",
        "major actor": "actor",
        "male": "actor",
        "supporting": "supporting",
        "extra": "supporting",
        "other": "supporting",
    }
    mapped = aliases.get(role, "")
    if mapped not in ROLES:
        raise VideoError(400, "role must be actress, actor, or supporting.")
    return mapped


def _clip_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _sanitize_model_id(value: object, extra_hidden: frozenset[str] | set[str] | None) -> str:
    model_id = _clip_text(value, 200)
    if not model_id:
        return ""
    if not is_available_in_hong_kong(model_id, extra_hidden):
        return ""
    model = get_model(model_id)
    if model is None or "video_gen" not in model["functions"]:  # type: ignore[operator]
        return ""
    return model_id


def empty_character(slot: int) -> dict[str, Any]:
    default_role = ROLES[slot] if slot < 2 else "supporting"
    return {
        "slot": slot,
        "role": default_role,
        "name": "",
        "photos": [],
    }


def empty_characters() -> list[dict[str, Any]]:
    return [empty_character(slot) for slot in range(MAX_CHARACTERS)]


def load_projects(data_dir: Path) -> list[dict[str, Any]]:
    path = index_path(data_dir)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    projects = raw.get("projects") if isinstance(raw, dict) else None
    if not isinstance(projects, list):
        return []
    return [row for row in projects if isinstance(row, dict) and row.get("id")]


def save_projects(data_dir: Path, projects: list[dict[str, Any]]) -> None:
    path = index_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps({"projects": projects}, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _normalize_characters(raw: object) -> list[dict[str, Any]]:
    characters = empty_characters()
    if not isinstance(raw, list):
        return characters
    for item in raw[:MAX_CHARACTERS]:
        if not isinstance(item, dict):
            continue
        try:
            slot = resolve_slot(item.get("slot"))
        except VideoError:
            continue
        role = str(item.get("role") or characters[slot]["role"]).strip().lower()
        try:
            role = resolve_role(role)
        except VideoError:
            role = characters[slot]["role"]
        photos: list[dict[str, str]] = []
        raw_photos = item.get("photos")
        if isinstance(raw_photos, list):
            for photo in raw_photos[:MAX_PHOTOS_PER_CHARACTER]:
                if not isinstance(photo, dict):
                    continue
                photo_id = str(photo.get("id") or "").strip()
                if not PHOTO_ID_RE.match(photo_id):
                    continue
                photos.append(
                    {
                        "id": photo_id,
                        "name": _clip_text(photo.get("name"), 200),
                        "stored_path": _clip_text(photo.get("stored_path"), 240),
                        "type": _clip_text(photo.get("type"), 16) or "jpeg",
                    }
                )
        characters[slot] = {
            "slot": slot,
            "role": role,
            "name": _clip_text(item.get("name"), MAX_CHARACTER_NAME),
            "photos": photos,
        }
    return characters


def _sanitize_detail(raw: object) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise VideoError(400, "detail must be an object.")
    detail: dict[str, Any] = {}
    for key in (
        "prompt",
        "title",
        "scene",
        "pan",
        "tilt",
        "dolly",
        "zoom",
        "roll",
        "aspect_ratio",
    ):
        text = _clip_text(raw.get(key), 8000 if key == "prompt" else 2000)
        if text:
            detail[key] = text
    if "cantonese_accent" in raw:
        detail["cantonese_accent"] = bool(raw.get("cantonese_accent"))
    if "character_orientation_lock" in raw:
        detail["character_orientation_lock"] = bool(raw.get("character_orientation_lock"))
    if "interpolation" in raw:
        detail["interpolation"] = bool(raw.get("interpolation"))
    if "generate_audio" in raw:
        detail["generate_audio"] = bool(raw.get("generate_audio"))
    intensity = raw.get("motion_intensity")
    if intensity is not None and intensity != "":
        try:
            value = float(intensity)
        except (TypeError, ValueError):
            value = 1.0
        detail["motion_intensity"] = max(0.0, min(3.0, value))
    duration = raw.get("duration_seconds")
    if duration not in (None, ""):
        detail["duration_seconds"] = resolve_duration(duration)
    modifiers = raw.get("cinematic_modifiers")
    if isinstance(modifiers, list):
        detail["cinematic_modifiers"] = [
            str(item).strip()[:80] for item in modifiers if str(item).strip()
        ][:12]
    frames: dict[str, dict[str, str]] = {}
    raw_frames = raw.get("frames")
    if isinstance(raw_frames, dict):
        for kind in ("first", "last"):
            item = raw_frames.get(kind)
            if not isinstance(item, dict):
                continue
            photo_id = str(item.get("id") or "").strip()
            if PHOTO_ID_RE.match(photo_id):
                frames[kind] = {
                    "id": photo_id,
                    "name": _clip_text(item.get("name"), 200),
                    "stored_path": _clip_text(item.get("stored_path"), 240),
                    "type": _clip_text(item.get("type"), 16) or "jpeg",
                }
    if frames:
        detail["frames"] = frames
    return detail


def _photo_public(photo: dict[str, Any]) -> dict[str, str]:
    photo_id = str(photo.get("id") or "")
    kind = str(photo.get("type") or "jpeg")
    return {
        "id": photo_id,
        "name": str(photo.get("name") or ""),
        "type": kind,
        "media_type": MEDIA_TYPES.get(kind, "application/octet-stream"),
        "href": f"/api/videos/photos/{photo_id}",
    }


def _character_public(character: dict[str, Any]) -> dict[str, Any]:
    photos = character.get("photos") if isinstance(character.get("photos"), list) else []
    kept = [_photo_public(photo) for photo in photos if isinstance(photo, dict)]
    return {
        "slot": int(character.get("slot") or 0),
        "role": character.get("role") or "supporting",
        "name": character.get("name") or "",
        "photos": kept,
        "photo_count": len(kept),
        "max_photos": MAX_PHOTOS_PER_CHARACTER,
    }


def _clip_public(clip: dict[str, Any]) -> dict[str, Any]:
    clip_id = str(clip.get("id") or "")
    return {
        "id": clip_id,
        "index": int(clip.get("index") or 0),
        "duration_seconds": int(clip.get("duration_seconds") or 0),
        "billed_seconds": int(clip.get("billed_seconds") or clip.get("duration_seconds") or 0),
        "prompt": clip.get("prompt") or "",
        "assembled_prompt": clip.get("assembled_prompt") or "",
        "model_id": clip.get("model_id") or "",
        "total_usd": clip.get("total_usd") or "",
        "href": f"/api/videos/clips/{clip_id}/file" if clip_id else "",
        "created_at": clip.get("created_at") or "",
        "segments": list(clip.get("segments") or []),
    }


def public_summary(row: dict[str, Any]) -> dict[str, Any]:
    clips = row.get("clips") if isinstance(row.get("clips"), list) else []
    return {
        "id": str(row["id"]),
        "name": row.get("name") or "",
        "updated_at": row.get("updated_at") or row.get("created_at") or "",
        "clip_count": len(clips),
        "max_clips": MAX_CLIPS,
    }


def public_project(data_dir: Path, row: dict[str, Any]) -> dict[str, Any]:
    characters = _normalize_characters(row.get("characters"))
    for character in characters:
        kept: list[dict[str, str]] = []
        for photo in character["photos"]:
            stored = Path(data_dir) / str(photo.get("stored_path") or "")
            if stored.is_file():
                kept.append(photo)
        character["photos"] = kept
    clips = [item for item in (row.get("clips") or []) if isinstance(item, dict)]
    detail = dict(row.get("detail") or {})
    if not isinstance(detail, dict):
        detail = {}
    frames = detail.get("frames") if isinstance(detail.get("frames"), dict) else {}
    kept_frames: dict[str, dict[str, str]] = {}
    for kind, item in frames.items():
        if not isinstance(item, dict):
            continue
        stored = Path(data_dir) / str(item.get("stored_path") or "")
        if stored.is_file():
            kept_frames[str(kind)] = item
    if kept_frames:
        detail["frames"] = {
            kind: _photo_public(item) for kind, item in kept_frames.items()
        }
    elif "frames" in detail:
        detail.pop("frames", None)
    merged = row.get("merged") if isinstance(row.get("merged"), dict) else None
    merged_public = None
    if merged and merged.get("id"):
        stored = Path(data_dir) / str(merged.get("stored_path") or "")
        if stored.is_file():
            merged_public = {
                "id": merged["id"],
                "href": f"/api/videos/merges/{merged['id']}/file",
                "clip_ids": list(merged.get("clip_ids") or []),
                "created_at": merged.get("created_at") or "",
            }
    return {
        "id": str(row["id"]),
        "name": row.get("name") or "",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at") or row.get("created_at"),
        "model_id": row.get("model_id") or "",
        "detail": detail,
        "characters": [_character_public(item) for item in characters],
        "max_characters": MAX_CHARACTERS,
        "clips": [_clip_public(item) for item in clips[:MAX_CLIPS]],
        "max_clips": MAX_CLIPS,
        "merged": merged_public,
    }


def list_projects(data_dir: Path) -> list[dict[str, Any]]:
    projects = sorted(
        load_projects(data_dir),
        key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""),
        reverse=True,
    )
    return [public_summary(row) for row in projects]


def _require_project(data_dir: Path, project_id: str) -> dict[str, Any]:
    if not PROJECT_ID_RE.match(project_id or ""):
        raise VideoError(404, MISSING_PROJECT)
    for row in load_projects(data_dir):
        if row.get("id") == project_id:
            return row
    raise VideoError(404, MISSING_PROJECT)


def get_project(data_dir: Path, project_id: str) -> dict[str, Any]:
    return public_project(data_dir, _require_project(data_dir, project_id))


def create_project(
    data_dir: Path,
    body: dict[str, Any],
    *,
    extra_hidden: frozenset[str] | set[str] | None = None,
) -> dict[str, Any]:
    name = resolve_project_name(body.get("name"))
    detail = _sanitize_detail(body.get("detail"))
    characters = _normalize_characters(body.get("characters"))
    model_id = _sanitize_model_id(body.get("model_id") or detail.get("model_id"), extra_hidden)
    now = _now()
    row = {
        "id": str(uuid.uuid4()),
        "name": name,
        "created_at": now,
        "updated_at": now,
        "model_id": model_id,
        "detail": detail,
        "characters": characters,
        "clips": [],
        "merged": None,
    }
    projects = load_projects(data_dir)
    projects.append(row)
    save_projects(data_dir, projects)
    return public_project(data_dir, row)


def update_project(
    data_dir: Path,
    project_id: str,
    body: dict[str, Any],
    *,
    extra_hidden: frozenset[str] | set[str] | None = None,
) -> dict[str, Any]:
    projects = load_projects(data_dir)
    if not PROJECT_ID_RE.match(project_id or ""):
        raise VideoError(404, MISSING_PROJECT)
    match: dict[str, Any] | None = None
    index = -1
    for position, row in enumerate(projects):
        if row.get("id") == project_id:
            match = row
            index = position
            break
    if match is None:
        raise VideoError(404, MISSING_PROJECT)
    name = resolve_project_name(body.get("name"))
    incoming_detail = body.get("detail") if "detail" in body else match.get("detail")
    detail = _sanitize_detail(incoming_detail)
    existing_frames = (match.get("detail") or {}).get("frames") if isinstance(match.get("detail"), dict) else {}
    if isinstance(existing_frames, dict) and "frames" not in detail:
        detail["frames"] = existing_frames
    if "characters" in body:
        characters = _normalize_characters(body.get("characters"))
        # Keep stored photos unless the client sent photo rows (with stored_path).
        existing = _normalize_characters(match.get("characters"))
        by_slot = {item["slot"]: item for item in existing}
        for character in characters:
            previous = by_slot.get(character["slot"])
            if previous and not character["photos"]:
                character["photos"] = previous["photos"]
    else:
        characters = _normalize_characters(match.get("characters"))
    model_id = _sanitize_model_id(
        body.get("model_id") if "model_id" in body else match.get("model_id") or "",
        extra_hidden,
    )
    updated = {
        **match,
        "name": name,
        "updated_at": _now(),
        "model_id": model_id,
        "detail": detail,
        "characters": characters,
    }
    projects[index] = updated
    save_projects(data_dir, projects)
    return public_project(data_dir, updated)


def _unlink(path: Path) -> None:
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def delete_project(data_dir: Path, project_id: str) -> dict[str, Any]:
    if not PROJECT_ID_RE.match(project_id or ""):
        raise VideoError(404, MISSING_PROJECT)
    projects = load_projects(data_dir)
    match = next((row for row in projects if row.get("id") == project_id), None)
    if match is None:
        raise VideoError(404, MISSING_PROJECT)
    for character in _normalize_characters(match.get("characters")):
        for photo in character["photos"]:
            _unlink(Path(data_dir) / str(photo.get("stored_path") or ""))
    detail = match.get("detail") if isinstance(match.get("detail"), dict) else {}
    frames = detail.get("frames") if isinstance(detail.get("frames"), dict) else {}
    for item in frames.values():
        if isinstance(item, dict):
            _unlink(Path(data_dir) / str(item.get("stored_path") or ""))
    for clip in match.get("clips") or []:
        if isinstance(clip, dict):
            _unlink(Path(data_dir) / str(clip.get("stored_path") or ""))
    merged = match.get("merged") if isinstance(match.get("merged"), dict) else None
    if merged:
        _unlink(Path(data_dir) / str(merged.get("stored_path") or ""))
    remaining = [row for row in projects if row.get("id") != project_id]
    save_projects(data_dir, remaining)
    return {"ok": True, "id": project_id}


def update_character(
    data_dir: Path,
    project_id: str,
    slot: int,
    *,
    role: object = None,
    name: object = None,
) -> dict[str, Any]:
    slot = resolve_slot(slot)
    projects = load_projects(data_dir)
    match = next((row for row in projects if row.get("id") == project_id), None)
    if match is None:
        raise VideoError(404, MISSING_PROJECT)
    characters = _normalize_characters(match.get("characters"))
    if role is not None and str(role).strip():
        characters[slot]["role"] = resolve_role(role)
    if name is not None:
        characters[slot]["name"] = _clip_text(name, MAX_CHARACTER_NAME)
    match["characters"] = characters
    match["updated_at"] = _now()
    save_projects(data_dir, projects)
    return public_project(data_dir, match)


def _write_image(
    data_dir: Path, *, filename: str, data: bytes
) -> dict[str, str]:
    name = Path(filename or "").name.strip()
    if not name:
        raise VideoError(400, "Upload must include a filename.")
    suffix = extension_of(name)
    kind = ALLOWED_EXTENSIONS.get(suffix)
    if kind is None:
        raise VideoError(400, "Unsupported file type. Accepted: jpeg, png, webp.")
    if len(data) > MAX_REFERENCE_BYTES:
        raise VideoError(400, "File exceeds the 10 MB limit.")
    sniffed = sniff_image_kind(data)
    if sniffed is None:
        raise VideoError(400, "File is not a valid jpeg, png, or webp image.")
    if sniffed != kind:
        raise VideoError(400, "File type does not match the filename extension.")
    photo_id = uuid.uuid4().hex
    stored_name = f"{photo_id}{suffix}"
    stored_rel = f"{REFS_DIRNAME}/{stored_name}"
    (refs_dir(data_dir) / stored_name).write_bytes(data)
    return {
        "id": photo_id,
        "name": name,
        "stored_path": stored_rel,
        "type": kind,
    }


def save_character_photo(
    data_dir: Path,
    project_id: str,
    slot: int,
    *,
    filename: str,
    data: bytes,
) -> dict[str, Any]:
    slot = resolve_slot(slot)
    projects = load_projects(data_dir)
    match = next((row for row in projects if row.get("id") == project_id), None)
    if match is None:
        raise VideoError(404, MISSING_PROJECT)
    characters = _normalize_characters(match.get("characters"))
    photos = characters[slot]["photos"]
    if len(photos) >= MAX_PHOTOS_PER_CHARACTER:
        raise VideoError(
            400,
            f"Each character allows at most {MAX_PHOTOS_PER_CHARACTER} photos.",
        )
    photo = _write_image(data_dir, filename=filename, data=data)
    photos.append(photo)
    characters[slot]["photos"] = photos
    match["characters"] = characters
    match["updated_at"] = _now()
    save_projects(data_dir, projects)
    return public_project(data_dir, match)


def delete_character_photo(
    data_dir: Path, project_id: str, slot: int, photo_id: str
) -> dict[str, Any]:
    slot = resolve_slot(slot)
    projects = load_projects(data_dir)
    match = next((row for row in projects if row.get("id") == project_id), None)
    if match is None:
        raise VideoError(404, MISSING_PROJECT)
    characters = _normalize_characters(match.get("characters"))
    photos = characters[slot]["photos"]
    found = next((item for item in photos if item.get("id") == photo_id), None)
    if found is None:
        raise VideoError(404, MISSING_PHOTO)
    _unlink(Path(data_dir) / str(found.get("stored_path") or ""))
    characters[slot]["photos"] = [item for item in photos if item.get("id") != photo_id]
    match["characters"] = characters
    match["updated_at"] = _now()
    save_projects(data_dir, projects)
    return public_project(data_dir, match)


def save_frame_image(
    data_dir: Path,
    project_id: str,
    kind: str,
    *,
    filename: str,
    data: bytes,
) -> dict[str, Any]:
    if kind not in {"first", "last"}:
        raise VideoError(400, "frame kind must be first or last.")
    projects = load_projects(data_dir)
    match = next((row for row in projects if row.get("id") == project_id), None)
    if match is None:
        raise VideoError(404, MISSING_PROJECT)
    detail = dict(match.get("detail") or {})
    if not isinstance(detail, dict):
        detail = {}
    frames = dict(detail.get("frames") or {})
    if not isinstance(frames, dict):
        frames = {}
    previous = frames.get(kind)
    if isinstance(previous, dict):
        _unlink(Path(data_dir) / str(previous.get("stored_path") or ""))
    frames[kind] = _write_image(data_dir, filename=filename, data=data)
    detail["frames"] = frames
    match["detail"] = detail
    match["updated_at"] = _now()
    save_projects(data_dir, projects)
    return public_project(data_dir, match)


def delete_frame_image(data_dir: Path, project_id: str, kind: str) -> dict[str, Any]:
    if kind not in {"first", "last"}:
        raise VideoError(400, "frame kind must be first or last.")
    projects = load_projects(data_dir)
    match = next((row for row in projects if row.get("id") == project_id), None)
    if match is None:
        raise VideoError(404, MISSING_PROJECT)
    detail = dict(match.get("detail") or {})
    frames = dict(detail.get("frames") or {}) if isinstance(detail, dict) else {}
    previous = frames.pop(kind, None)
    if not isinstance(previous, dict):
        raise VideoError(404, MISSING_FRAME)
    _unlink(Path(data_dir) / str(previous.get("stored_path") or ""))
    if isinstance(detail, dict):
        if frames:
            detail["frames"] = frames
        else:
            detail.pop("frames", None)
        match["detail"] = detail
    match["updated_at"] = _now()
    save_projects(data_dir, projects)
    return public_project(data_dir, match)


def _all_photos(row: dict[str, Any]) -> list[dict[str, Any]]:
    photos: list[dict[str, Any]] = []
    for character in _normalize_characters(row.get("characters")):
        photos.extend(character["photos"])
    detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
    frames = detail.get("frames") if isinstance(detail.get("frames"), dict) else {}
    for item in frames.values():
        if isinstance(item, dict):
            photos.append(item)
    return photos


def get_stored_photo(data_dir: Path, photo_id: str) -> tuple[Path, str, str]:
    chosen = (photo_id or "").strip()
    if not PHOTO_ID_RE.match(chosen):
        raise VideoError(404, MISSING_PHOTO)
    for row in load_projects(data_dir):
        for photo in _all_photos(row):
            if photo.get("id") != chosen:
                continue
            stored = Path(data_dir) / str(photo.get("stored_path") or "")
            if not stored.is_file():
                raise VideoError(404, MISSING_PHOTO)
            kind = str(photo.get("type") or "jpeg")
            name = Path(str(photo.get("name") or stored.name)).name or stored.name
            return stored, name, MEDIA_TYPES.get(kind, "application/octet-stream")
    raise VideoError(404, MISSING_PHOTO)


def character_reference_rows(data_dir: Path, row: dict[str, Any]) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for character in _normalize_characters(row.get("characters")):
        for photo in character["photos"]:
            stored = Path(data_dir) / str(photo.get("stored_path") or "")
            if not stored.is_file():
                continue
            resolved.append({**photo, "bytes": stored.read_bytes()})
    return resolved


def frame_image_rows(data_dir: Path, row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
    frames = detail.get("frames") if isinstance(detail.get("frames"), dict) else {}
    resolved: dict[str, dict[str, Any]] = {}
    for kind in ("first", "last"):
        item = frames.get(kind)
        if not isinstance(item, dict):
            continue
        stored = Path(data_dir) / str(item.get("stored_path") or "")
        if stored.is_file():
            resolved[kind] = {**item, "bytes": stored.read_bytes()}
    return resolved


def append_clip(data_dir: Path, project_id: str, clip: dict[str, Any]) -> dict[str, Any]:
    projects = load_projects(data_dir)
    match = next((row for row in projects if row.get("id") == project_id), None)
    if match is None:
        raise VideoError(404, MISSING_PROJECT)
    clips = [item for item in (match.get("clips") or []) if isinstance(item, dict)]
    if len(clips) >= MAX_CLIPS:
        raise VideoError(
            400,
            f"A project can hold at most {MAX_CLIPS} generated clips.",
        )
    clip = {**clip, "index": len(clips)}
    clips.append(clip)
    match["clips"] = clips
    match["merged"] = None
    match["updated_at"] = _now()
    save_projects(data_dir, projects)
    return public_project(data_dir, match)


def set_merged(data_dir: Path, project_id: str, merged: dict[str, Any]) -> dict[str, Any]:
    projects = load_projects(data_dir)
    match = next((row for row in projects if row.get("id") == project_id), None)
    if match is None:
        raise VideoError(404, MISSING_PROJECT)
    previous = match.get("merged") if isinstance(match.get("merged"), dict) else None
    if previous:
        _unlink(Path(data_dir) / str(previous.get("stored_path") or ""))
    match["merged"] = merged
    match["updated_at"] = _now()
    save_projects(data_dir, projects)
    return public_project(data_dir, match)


def get_stored_clip(data_dir: Path, clip_id: str) -> tuple[Path, str, str]:
    chosen = (clip_id or "").strip()
    if not PROJECT_ID_RE.match(chosen):
        raise VideoError(404, MISSING_CLIP)
    for row in load_projects(data_dir):
        for clip in row.get("clips") or []:
            if not isinstance(clip, dict) or clip.get("id") != chosen:
                continue
            stored = Path(data_dir) / str(clip.get("stored_path") or "")
            if not stored.is_file():
                raise VideoError(404, MISSING_CLIP)
            name = Path(str(clip.get("filename") or stored.name)).name or stored.name
            return stored, name, "video/mp4"
        merged = row.get("merged") if isinstance(row.get("merged"), dict) else None
        if merged and merged.get("id") == chosen:
            stored = Path(data_dir) / str(merged.get("stored_path") or "")
            if not stored.is_file():
                raise VideoError(404, MISSING_CLIP)
            name = Path(str(merged.get("filename") or stored.name)).name or stored.name
            return stored, name, "video/mp4"
    raise VideoError(404, MISSING_CLIP)


def project_clip_paths(data_dir: Path, row: dict[str, Any]) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for clip in row.get("clips") or []:
        if not isinstance(clip, dict):
            continue
        stored = Path(data_dir) / str(clip.get("stored_path") or "")
        if stored.is_file():
            found.append((str(clip.get("id") or ""), stored))
    return found
