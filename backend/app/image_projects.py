"""Saved Image studio projects for reuse.

The index is ``$DATA_DIR/image-projects.json``. Each row keeps the guided
prompt fields and generation settings so a past project can restore the
studio. Reference photo ids are stored; missing files are reported, not fatal.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .catalog import get_model, is_available_in_hong_kong
from .image_refs import load_index as load_reference_index
from .images import (
    GEMINI_IMAGE_ID,
    ImageError,
    MAX_FIELD_CHARS,
    MAX_IMAGE_COUNT,
    MAX_PERSONS,
    MAX_PROMPT_CHARS,
    VARIANCE_LEVELS,
)

INDEX_NAME = "image-projects.json"
MAX_PROJECT_NAME = 120
MAX_LIST_ITEMS = 16
PROJECT_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
MISSING_PROJECT = "Image project not found."
EMPTY_NAME = "name is required."
LONG_NAME = f"name must be at most {MAX_PROJECT_NAME} characters."

# Studio fields plus UI-only keys (select vs combined nationality, count_mode).
PROMPT_DETAIL_KEYS = frozenset(
    {
        "prompt",
        "prompt_dirty",
        "subject",
        "setting",
        "background",
        "background_attributes",
        "objects",
        "object_attributes",
        "nationality",
        "nationality_select",
        "nationality_other",
        "ethnicity",
        "ethnicity_presentation",
        "person_height",
        "person_height_select",
        "stature",
        "height_cm",
        "body",
        "body_type",
        "hair",
        "hair_color",
        "hair_length",
        "hair_style",
        "eyes",
        "eyes_size",
        "eyes_color",
        "nose",
        "nose_size",
        "nose_shape",
        "nose_note",
        "mouth",
        "mouth_size",
        "mouth_shape",
        "expression",
        "facial_expression",
        "expression_note",
        "dress",
        "top",
        "bottom",
        "shoes",
        "props",
        "object_action",
        "action_on_objects",
        "person_count",
        "people_count",
        "people_relation",
        "together",
        "persons",
        "person_2",
        "style",
        "camera",
        "shot",
        "framing",
        "camera_framing",
        "lighting",
        "notes",
        "extra_notes",
        "width",
        "height",
        "format",
        "resolution",
        "aspect_ratio",
        "output_resolution",
        "size_tier",
        "facial_variance",
        "motion_variance",
        "facial_change",
        "motion_change",
        "facial_variance_notes",
        "motion_variance_notes",
        "facial_notes",
        "motion_notes",
        "facial_cycle",
        "motion_cycle",
        "expression_cycle",
        "movement_cycle",
        "variance_steps",
        "n",
        "count",
        "count_mode",
        "frames",
        "beats",
        "reference_ids",
        "reference_names",
        "references",
        "model_id",
    }
)


def index_path(data_dir: Path) -> Path:
    return Path(data_dir) / INDEX_NAME


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def resolve_project_name(value: object) -> str:
    if not isinstance(value, str):
        raise ImageError(400, EMPTY_NAME)
    name = value.strip()
    if not name:
        raise ImageError(400, EMPTY_NAME)
    if len(name) > MAX_PROJECT_NAME:
        raise ImageError(400, LONG_NAME)
    return name


def _clip_text(value: object, limit: int = MAX_FIELD_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _sanitize_model_id(value: object, extra_hidden: frozenset[str] | set[str] | None) -> str:
    model_id = _clip_text(value, 200)
    if not model_id or model_id == GEMINI_IMAGE_ID:
        return ""
    if not is_available_in_hong_kong(model_id, extra_hidden):
        return ""
    model = get_model(model_id)
    if model is None or "image_gen" not in model["functions"]:  # type: ignore[operator]
        return ""
    return model_id


def _sanitize_scalar(value: object, *, prompt: bool = False) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        limit = MAX_PROMPT_CHARS if prompt else MAX_FIELD_CHARS
        return value[:limit]
    return None


def _sanitize_cycle(value: object) -> list[str]:
    if isinstance(value, str):
        items = [part.strip()[:MAX_FIELD_CHARS] for part in value.split(",") if part.strip()]
        return items[:MAX_LIST_ITEMS]
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value[:MAX_LIST_ITEMS]:
        if isinstance(item, str) and item.strip():
            items.append(item.strip()[:MAX_FIELD_CHARS])
    return items


def _sanitize_variance_steps(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    steps: list[dict[str, str]] = []
    for item in value[:MAX_IMAGE_COUNT]:
        if not isinstance(item, dict):
            continue
        facial = _clip_text(item.get("facial") or item.get("facial_variance")).lower()
        motion = _clip_text(item.get("motion") or item.get("motion_variance")).lower()
        if facial not in VARIANCE_LEVELS:
            facial = "medium"
        if motion not in VARIANCE_LEVELS:
            motion = "medium"
        steps.append(
            {
                "facial": facial,
                "facial_note": _clip_text(
                    item.get("facial_note") or item.get("facial_notes") or ""
                ),
                "motion": motion,
                "motion_note": _clip_text(
                    item.get("motion_note") or item.get("motion_notes") or ""
                ),
            }
        )
    return steps


def _sanitize_frames(value: object) -> list[str]:
    if isinstance(value, str):
        lines = [line.strip()[:MAX_FIELD_CHARS] for line in value.splitlines()]
        return lines[:MAX_IMAGE_COUNT]
    if not isinstance(value, list):
        return []
    frames: list[str] = []
    for item in value[:MAX_IMAGE_COUNT]:
        if item is None:
            frames.append("")
        elif isinstance(item, str):
            frames.append(item.strip()[:MAX_FIELD_CHARS])
    return frames


PERSON_DETAIL_KEYS = frozenset(
    {
        "nationality",
        "nationality_select",
        "nationality_other",
        "ethnicity",
        "ethnicity_presentation",
        "person_height",
        "person_height_select",
        "stature",
        "height_cm",
        "body",
        "body_type",
        "hair",
        "hair_color",
        "hair_length",
        "hair_style",
        "eyes",
        "eyes_size",
        "eyes_color",
        "nose",
        "nose_size",
        "nose_shape",
        "nose_note",
        "mouth",
        "mouth_size",
        "mouth_shape",
        "expression",
        "facial_expression",
        "expression_note",
        "dress",
        "top",
        "bottom",
        "shoes",
        "props",
        "object_action",
        "action_on_objects",
    }
)


def _sanitize_person_detail(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    detail: dict[str, Any] = {}
    for key, item in value.items():
        if str(key) not in PERSON_DETAIL_KEYS:
            continue
        cleaned = _sanitize_scalar(item)
        if cleaned is not None:
            detail[str(key)] = cleaned
    return detail


def _sanitize_persons(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    people: list[dict[str, Any]] = []
    for item in value[:MAX_PERSONS]:
        if isinstance(item, dict):
            people.append(_sanitize_person_detail(item))
    return people


def _sanitize_references(value: object, names: object = None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if isinstance(value, list):
        for index, item in enumerate(value[:5]):
            ref_id = ""
            name = ""
            if isinstance(item, dict):
                ref_id = _clip_text(item.get("id"), 80)
                name = _clip_text(item.get("name"), 200)
            elif isinstance(item, str):
                ref_id = item.strip()[:80]
                if isinstance(names, list) and index < len(names) and isinstance(names[index], str):
                    name = names[index].strip()[:200]
            if ref_id:
                rows.append({"id": ref_id, "name": name})
    return rows


def sanitize_prompt_detail(
    raw: object,
    extra_hidden: frozenset[str] | set[str] | None = None,
) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ImageError(400, "prompt_detail must be an object.")
    mapping = {str(key): value for key, value in raw.items() if str(key) in PROMPT_DETAIL_KEYS}
    detail: dict[str, Any] = {}
    for key, value in mapping.items():
        if key in {"facial_cycle", "motion_cycle", "expression_cycle", "movement_cycle"}:
            detail[key] = _sanitize_cycle(value)
        elif key == "variance_steps":
            detail[key] = _sanitize_variance_steps(value)
        elif key in {"frames"}:
            detail[key] = _sanitize_frames(value)
        elif key == "references":
            continue
        elif key == "reference_ids":
            continue
        elif key == "reference_names":
            continue
        elif key == "prompt":
            text = _sanitize_scalar(value, prompt=True)
            if text is not None:
                detail[key] = text
        elif key == "prompt_dirty":
            detail[key] = bool(value)
        elif key in {"n", "count", "width", "height"}:
            try:
                detail[key] = int(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
        elif key in {"person_count", "people_count"}:
            try:
                count = int(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            if count in (1, 2):
                detail[key] = count
        elif key == "persons":
            people = _sanitize_persons(value)
            if people:
                detail[key] = people
        elif key == "person_2":
            person = _sanitize_person_detail(value)
            if person:
                detail[key] = person
        else:
            cleaned = _sanitize_scalar(value)
            if cleaned is not None:
                detail[key] = cleaned
    references = _sanitize_references(
        mapping.get("references") or mapping.get("reference_ids"),
        mapping.get("reference_names"),
    )
    if references:
        detail["references"] = references
        detail["reference_ids"] = [row["id"] for row in references]
        detail["reference_names"] = [row["name"] for row in references]
    if "model_id" in detail:
        cleaned_model = _sanitize_model_id(detail.get("model_id"), extra_hidden)
        if cleaned_model:
            detail["model_id"] = cleaned_model
        else:
            detail.pop("model_id", None)
    return detail


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


def _split_references(
    data_dir: Path, detail: dict[str, Any]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    stored = {str(row["id"]): row for row in load_reference_index(data_dir)}
    wanted = detail.get("references")
    if not isinstance(wanted, list):
        ids = detail.get("reference_ids") or []
        names = detail.get("reference_names") or []
        wanted = []
        if isinstance(ids, list):
            for index, ref_id in enumerate(ids):
                if not isinstance(ref_id, str) or not ref_id.strip():
                    continue
                name = ""
                if isinstance(names, list) and index < len(names) and isinstance(names[index], str):
                    name = names[index]
                wanted.append({"id": ref_id.strip(), "name": name})
    kept: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    seen: set[str] = set()
    if not isinstance(wanted, list):
        return kept, missing
    for item in wanted:
        if isinstance(item, dict):
            ref_id = str(item.get("id") or "").strip()
            name = str(item.get("name") or "").strip()
        elif isinstance(item, str):
            ref_id = item.strip()
            name = ""
        else:
            continue
        if not ref_id or ref_id in seen:
            continue
        seen.add(ref_id)
        match = stored.get(ref_id)
        stored_path = Path(data_dir) / str((match or {}).get("stored_path") or "")
        if match is not None and stored_path.is_file():
            kept.append({"id": ref_id, "name": str(match.get("name") or name)})
        else:
            missing.append({"id": ref_id, "name": name})
    return kept, missing


def public_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row.get("name") or "",
        "updated_at": row.get("updated_at") or row.get("created_at") or "",
    }


def public_project(data_dir: Path, row: dict[str, Any]) -> dict[str, Any]:
    detail = dict(row.get("prompt_detail") or {})
    if not isinstance(detail, dict):
        detail = {}
    kept, missing = _split_references(data_dir, detail)
    detail["references"] = kept
    detail["reference_ids"] = [item["id"] for item in kept]
    detail["reference_names"] = [item["name"] for item in kept]
    return {
        "id": str(row["id"]),
        "name": row.get("name") or "",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at") or row.get("created_at"),
        "model_id": row.get("model_id") or "",
        "prompt_detail": detail,
        "missing_references": missing,
    }


def list_projects(data_dir: Path) -> list[dict[str, Any]]:
    projects = sorted(
        load_projects(data_dir),
        key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""),
        reverse=True,
    )
    return [public_summary(row) for row in projects]


def get_project(data_dir: Path, project_id: str) -> dict[str, Any]:
    row = _require_project(data_dir, project_id)
    return public_project(data_dir, row)


def _require_project(data_dir: Path, project_id: str) -> dict[str, Any]:
    if not PROJECT_ID_RE.match(project_id or ""):
        raise ImageError(404, MISSING_PROJECT)
    for row in load_projects(data_dir):
        if row.get("id") == project_id:
            return row
    raise ImageError(404, MISSING_PROJECT)


def create_project(
    data_dir: Path,
    body: dict[str, Any],
    *,
    extra_hidden: frozenset[str] | set[str] | None = None,
) -> dict[str, Any]:
    name = resolve_project_name(body.get("name"))
    detail = sanitize_prompt_detail(body.get("prompt_detail"), extra_hidden)
    model_id = _sanitize_model_id(body.get("model_id") or detail.get("model_id"), extra_hidden)
    now = _now()
    row = {
        "id": str(uuid.uuid4()),
        "name": name,
        "created_at": now,
        "updated_at": now,
        "model_id": model_id,
        "prompt_detail": detail,
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
        raise ImageError(404, MISSING_PROJECT)
    match: dict[str, Any] | None = None
    index = -1
    for position, row in enumerate(projects):
        if row.get("id") == project_id:
            match = row
            index = position
            break
    if match is None:
        raise ImageError(404, MISSING_PROJECT)
    name = resolve_project_name(body.get("name"))
    detail = sanitize_prompt_detail(body.get("prompt_detail"), extra_hidden)
    model_id = _sanitize_model_id(
        body.get("model_id") if "model_id" in body else match.get("model_id") or detail.get("model_id"),
        extra_hidden,
    )
    updated = {
        **match,
        "name": name,
        "updated_at": _now(),
        "model_id": model_id,
        "prompt_detail": detail,
    }
    projects[index] = updated
    save_projects(data_dir, projects)
    return public_project(data_dir, updated)


def delete_project(data_dir: Path, project_id: str) -> dict[str, Any]:
    if not PROJECT_ID_RE.match(project_id or ""):
        raise ImageError(404, MISSING_PROJECT)
    projects = load_projects(data_dir)
    remaining = [row for row in projects if row.get("id") != project_id]
    if len(remaining) == len(projects):
        raise ImageError(404, MISSING_PROJECT)
    save_projects(data_dir, remaining)
    return {"ok": True, "id": project_id}
