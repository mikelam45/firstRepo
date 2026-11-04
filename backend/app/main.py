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
from .chat import ChatError, complete_chat, resolve_chat_function
from .openrouter_key import (
    normalize_submitted_key,
    openrouter_status_fields,
    save_openrouter_api_key,
)
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


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    function: str = "rag_qa"


class OpenRouterKeyIn(BaseModel):
    api_key: str = ""


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
if not PAGE.is_file():
    raise FileNotFoundError(f"Packaged portal page is missing: {PAGE}")


@app.get("/")
def model_selection_page() -> FileResponse:
    return FileResponse(PAGE)


@app.get("/api/models")
def get_models() -> dict[str, object]:
    settings = get_settings()
    selection = load_selection(settings.data_dir)
    payload = public_state(selection)
    payload.update(openrouter_status_fields())
    return payload


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


@app.post("/api/openrouter/key")
def post_openrouter_key(
    body: OpenRouterKeyIn,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    require_write_access(settings, authorization)
    api_key = normalize_submitted_key(body.api_key)
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key must not be empty.")
    return save_openrouter_api_key(api_key, settings.data_dir)


@app.post("/api/openrouter/test")
def post_openrouter_test(
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    require_write_access(settings, authorization)
    return openrouter_status_fields()


@app.post("/api/chat")
def post_chat(
    body: ChatIn,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    require_write_access(settings, authorization)
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message must not be empty.")
    try:
        function_id = resolve_chat_function(body.function)
        selection = load_selection(settings.data_dir)
        model_id = selection[function_id]
        return complete_chat(
            message=message,
            function_id=function_id,
            model_id=model_id,
        )
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/health")
def health() -> dict[str, object]:
    settings = get_settings()
    with connect(settings) as connection:
        connection.execute("SELECT 1").fetchone()
    configured = openrouter_status_fields(probe=False)
    return {"status": "ok", "env": settings.env, **configured}


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
