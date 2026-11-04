"""Store up to five image reference photos for storyboard generation.

Files live under ``$DATA_DIR/image-refs/``. The index is
``$DATA_DIR/image-refs/index.json``. A sixth upload is rejected with 400.
Accepted types are jpeg, png, and webp, 10 MB each.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_REFERENCE_BYTES = 10 * 1024 * 1024
MAX_REFERENCES = 5
REFS_DIRNAME = "image-refs"
INDEX_NAME = "index.json"

ALLOWED_EXTENSIONS = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".webp": "webp"}
MEDIA_TYPES = {
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


class ImageRefError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def refs_dir(data_dir: Path) -> Path:
    path = Path(data_dir) / REFS_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def index_path(data_dir: Path) -> Path:
    return refs_dir(data_dir) / INDEX_NAME


def content_href(ref_id: str) -> str:
    return f"/api/images/references/{ref_id}"


def extension_of(filename: str) -> str:
    return Path(filename).suffix.lower()


def sniff_image_kind(data: bytes) -> str | None:
    if len(data) >= 8 and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(data) >= 3 and data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    return None


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
    payload = {"files": files, "max": MAX_REFERENCES}
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def public_record(row: dict[str, Any]) -> dict[str, Any]:
    kind = str(row.get("type") or "jpeg")
    return {
        "id": row["id"],
        "name": row["name"],
        "size": row["size"],
        "type": kind,
        "media_type": MEDIA_TYPES.get(kind, "application/octet-stream"),
        "href": content_href(str(row["id"])),
        "created_at": row["created_at"],
    }


def list_references(data_dir: Path) -> dict[str, Any]:
    files = [public_record(row) for row in load_index(data_dir)]
    return {"files": files, "count": len(files), "max": MAX_REFERENCES}


def get_stored_reference(data_dir: Path, ref_id: str) -> tuple[Path, str, str]:
    chosen = ref_id.strip()
    if not chosen or "/" in chosen or "\\" in chosen:
        raise ImageRefError(404, "Reference photo not found.")
    match = next((row for row in load_index(data_dir) if row.get("id") == chosen), None)
    if match is None:
        raise ImageRefError(404, "Reference photo not found.")
    root = Path(data_dir).resolve()
    stored = (root / str(match.get("stored_path") or "")).resolve()
    if root not in stored.parents:
        raise ImageRefError(404, "Reference photo not found.")
    if not stored.is_file():
        raise ImageRefError(404, "Reference photo not found.")
    name = Path(str(match.get("name") or stored.name)).name or stored.name
    media_type = MEDIA_TYPES.get(str(match.get("type") or ""), "application/octet-stream")
    return stored, name, media_type


def save_reference(data_dir: Path, *, filename: str, data: bytes) -> dict[str, Any]:
    name = Path(filename or "").name.strip()
    if not name:
        raise ImageRefError(400, "Upload must include a filename.")
    suffix = extension_of(name)
    kind = ALLOWED_EXTENSIONS.get(suffix)
    if kind is None:
        raise ImageRefError(
            400,
            "Unsupported file type. Accepted: jpeg, png, webp.",
        )
    if len(data) > MAX_REFERENCE_BYTES:
        raise ImageRefError(400, "File exceeds the 10 MB limit.")
    sniffed = sniff_image_kind(data)
    if sniffed is None:
        raise ImageRefError(400, "File is not a valid jpeg, png, or webp image.")
    if sniffed != kind:
        raise ImageRefError(400, "File type does not match the filename extension.")

    files = load_index(data_dir)
    if len(files) >= MAX_REFERENCES:
        raise ImageRefError(
            400,
            f"At most {MAX_REFERENCES} reference photos can be stored.",
        )

    file_id = uuid.uuid4().hex
    stored_name = f"{file_id}{suffix}"
    stored_rel = f"{REFS_DIRNAME}/{stored_name}"
    stored_abs = refs_dir(data_dir) / stored_name
    stored_abs.write_bytes(data)

    row: dict[str, Any] = {
        "id": file_id,
        "name": name,
        "size": len(data),
        "type": kind,
        "stored_path": stored_rel,
        "created_at": _utc_now(),
    }
    files.append(row)
    save_index(data_dir, files)
    return public_record(row)


def delete_reference(data_dir: Path, ref_id: str) -> dict[str, Any]:
    chosen = ref_id.strip()
    files = load_index(data_dir)
    match = next((row for row in files if row.get("id") == chosen), None)
    if match is None:
        raise ImageRefError(404, "Reference photo not found.")
    stored = Path(data_dir) / str(match.get("stored_path") or "")
    if stored.is_file():
        stored.unlink()
    save_index(data_dir, [row for row in files if row.get("id") != chosen])
    return {"ok": True, "id": chosen}


def resolve_references(
    data_dir: Path, reference_ids: list[str]
) -> list[dict[str, Any]]:
    """Return stored rows in the requested order. Unknown ids are 400."""
    if len(reference_ids) > MAX_REFERENCES:
        raise ImageRefError(
            400,
            f"reference_ids accepts at most {MAX_REFERENCES} ids.",
        )
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in reference_ids:
        if not isinstance(raw, str) or not raw.strip():
            raise ImageRefError(400, "Each reference id must be a non-empty string.")
        chosen = raw.strip()
        if chosen in seen:
            continue
        seen.add(chosen)
        ordered.append(chosen)
    if len(ordered) > MAX_REFERENCES:
        raise ImageRefError(
            400,
            f"reference_ids accepts at most {MAX_REFERENCES} ids.",
        )
    by_id = {str(row["id"]): row for row in load_index(data_dir)}
    resolved: list[dict[str, Any]] = []
    for ref_id in ordered:
        row = by_id.get(ref_id)
        if row is None:
            raise ImageRefError(400, f"Unknown reference id: {ref_id}.")
        stored = Path(data_dir) / str(row.get("stored_path") or "")
        if not stored.is_file():
            raise ImageRefError(400, f"Unknown reference id: {ref_id}.")
        resolved.append({**row, "bytes": stored.read_bytes()})
    return resolved
