"""Small API used to prove the dev and production environments.

Development (MacBook, this cloud VM): open notes, docs enabled, SQLite under DATA_DIR.
Production (VPS): docs hidden, notes require PORTAL_API_TOKEN.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .catalog import public_state
from .selection import load_selection, parse_selection, save_selection

ALLOWED_ENVS = ("development", "production")


class Settings:
    def __init__(self) -> None:
        env = os.getenv("APP_ENV", "development")
        if env not in ALLOWED_ENVS:
            raise RuntimeError("APP_ENV must be development or production")
        data_dir = Path(os.getenv("DATA_DIR", "data"))
        data_dir.mkdir(parents=True, exist_ok=True)
        token = os.getenv("PORTAL_API_TOKEN", "").strip()
        if env == "production" and not token:
            raise RuntimeError("PORTAL_API_TOKEN is required when APP_ENV=production")
        self.env = env
        self.data_dir = data_dir
        self.token = token
        self.db_path = data_dir / "notes.db"


def get_settings() -> Settings:
    return Settings()


app = FastAPI(title="Fieldnote dev shell")


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


def connect(settings: Settings) -> sqlite3.Connection:
    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, body TEXT NOT NULL)"
    )
    return connection


def require_write_access(settings: Settings, authorization: str | None) -> None:
    if settings.env != "production":
        return
    expected = f"Bearer {settings.token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


PAGE = Path(__file__).resolve().parent / "static" / "index.html"


@app.get("/")
def model_selection_page() -> FileResponse:
    return FileResponse(PAGE)


@app.get("/api/models")
def get_models() -> dict[str, object]:
    settings = get_settings()
    selection = load_selection(settings.data_dir)
    return public_state(selection)


@app.put("/api/models")
def put_models(
    body: Any = Body(...),
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    require_write_access(settings, authorization)
    try:
        selection = parse_selection(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_selection(settings.data_dir, selection)
    return public_state(selection)


@app.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    with connect(settings) as connection:
        connection.execute("SELECT 1").fetchone()
    return {"status": "ok", "env": settings.env}


@app.get("/api/notes")
def list_notes() -> list[dict[str, object]]:
    settings = get_settings()
    with connect(settings) as connection:
        rows = connection.execute("SELECT id, body FROM notes ORDER BY id").fetchall()
    return [{"id": row["id"], "body": row["body"]} for row in rows]


@app.post("/api/notes", status_code=201)
def create_note(
    note: NoteIn,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    require_write_access(settings, authorization)
    with connect(settings) as connection:
        cursor = connection.execute("INSERT INTO notes (body) VALUES (?)", (note.body,))
        note_id = cursor.lastrowid
    return {"id": note_id, "body": note.body}
