"""Small API used to prove the dev and production environments.

Development (MacBook, this cloud VM): open notes, docs enabled, SQLite under DATA_DIR.
Production (VPS): docs hidden, notes require PORTAL_API_TOKEN.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .catalog import public_state
from .chat import (
    ChatError,
    complete_chat,
    format_reply_messages,
    recorded_model,
    resolve_chat_function,
    resolve_grounding,
    resolve_source_language,
    resolve_target_language,
)
from .dse import (
    CREATE_QUESTION_USER_MESSAGE,
    DEFAULT_DSE_PRACTICE_MESSAGE,
    GUIDED_MODES,
    MODE_CREATE_AND_MARK,
    MODE_GUIDED_NO_ANSWER,
    MODE_GUIDED_WITH_ANSWER,
    MODE_PRACTICE,
    NEXT_HINT_USER_MESSAGE,
    NO_DSE_DOCUMENTS_STRICT_REPLY,
    SHOW_ANSWER_USER_MESSAGE,
    build_dse_context,
    build_mark_context,
    is_next_hint_message,
    parse_generated_question,
    parse_mark_verdict,
    public_mark_payload,
    public_question_payload,
    record_guided_turn,
    require_session,
    resolve_dse_difficulty,
    resolve_dse_level,
    resolve_dse_module,
    resolve_dse_paper,
    resolve_dse_topic,
    resolve_request_mode,
    scrub_hidden_fields,
    store_created_question,
    validate_level_topic,
)
from .ocr import OcrError, transcribe_question_photo
from .image_refs import (
    ImageRefError,
    delete_reference,
    get_stored_reference,
    list_references,
    save_reference,
)
from .images import (
    ImageError,
    enhance_prompt,
    generate_images,
    get_job,
    list_jobs,
    stored_image_path,
)
from .openrouter_key import (
    normalize_submitted_key,
    openrouter_status_fields,
    save_openrouter_api_key,
)
from .region import extra_hidden_ids, reset_probe_cache
from .rag import (
    COLLECTION_DSE_MATH,
    COLLECTION_RAG,
    COLLECTION_TRANSLATION,
    DEFAULT_TRANSLATION_MESSAGE,
    GROUNDING_STRICT,
    NO_DOCUMENTS_STRICT_REPLY,
    RagError,
    build_rag_context,
    build_translation_context,
    delete_file,
    get_stored_file,
    list_files,
    order_sources,
    resolve_collection,
    save_upload,
)
from .repack import get_translated_file, media_type_for, repack_translation_files
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
    message: str = Field(default="", max_length=8000)
    function: str = "rag_qa"
    grounding: str = "mixed"
    target_language: str | None = None
    source_language: str | None = None
    mode: str | None = None
    dse_mode: str | None = None
    topic: str | None = None
    difficulty: str | None = None
    paper: str | None = None
    module: str | None = None
    level: str | None = None
    session_id: str | None = None
    attempt_text: str | None = None


class DseAskIn(BaseModel):
    message: str = Field(default="", max_length=8000)
    grounding: str = "mixed"
    target_language: str | None = None
    mode: str | None = None
    dse_mode: str | None = None
    topic: str | None = None
    difficulty: str | None = None
    paper: str | None = None
    module: str | None = None
    level: str | None = None
    session_id: str | None = None
    attempt_text: str | None = None


class DseQuestionIn(BaseModel):
    level: str
    topic: str | None = None
    grounding: str = "mixed"
    target_language: str | None = None
    module: str | None = None
    paper: str | None = None
    difficulty: str | None = None


class OpenRouterKeyIn(BaseModel):
    api_key: str = ""


class ImageGenerateIn(BaseModel):
    prompt: str = ""
    subject: str = ""
    setting: str = ""
    background: str = ""
    background_attributes: str = ""
    objects: str = ""
    object_attributes: str = ""
    nationality: str = ""
    ethnicity: str = ""
    ethnicity_presentation: str = ""
    person_height: str = ""
    stature: str = ""
    height_cm: str = ""
    body: str = ""
    body_type: str = ""
    hair: str = ""
    hair_color: str = ""
    hair_length: str = ""
    hair_style: str = ""
    eyes: str = ""
    eyes_size: str = ""
    eyes_color: str = ""
    nose: str = ""
    nose_size: str = ""
    nose_shape: str = ""
    nose_note: str = ""
    mouth: str = ""
    mouth_size: str = ""
    mouth_shape: str = ""
    expression: str = ""
    facial_expression: str = ""
    expression_note: str = ""
    dress: str = ""
    top: str = ""
    bottom: str = ""
    shoes: str = ""
    props: str = ""
    object_action: str = ""
    action_on_objects: str = ""
    style: str = ""
    camera: str = ""
    shot: str = ""
    framing: str = ""
    camera_framing: str = ""
    lighting: str = ""
    notes: str = ""
    extra_notes: str = ""
    width: int | None = None
    height: int | None = None
    format: str = "png"
    resolution: str = ""
    aspect_ratio: str = ""
    output_resolution: str = ""
    size_tier: str = ""
    facial_variance: str = ""
    motion_variance: str = ""
    facial_change: str = ""
    motion_change: str = ""
    facial_variance_notes: str = ""
    motion_variance_notes: str = ""
    facial_notes: str = ""
    motion_notes: str = ""
    facial_cycle: list[str] | None = None
    motion_cycle: list[str] | None = None
    expression_cycle: list[str] | None = None
    movement_cycle: list[str] | None = None
    n: int | None = None
    count: int | None = None
    frames: list[str] | None = None
    reference_ids: list[str] = Field(default_factory=list)


class PromptEnhanceIn(BaseModel):
    prompt: str = ""


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


STATIC_DIR = Path(__file__).resolve().parent / "static"
PAGE = STATIC_DIR / "index.html"
SETUP_PAGE = STATIC_DIR / "setup.html"
PORTAL_CSS = STATIC_DIR / "portal.css"
CHAT_FORMAT_JS = STATIC_DIR / "chat_format.js"
if not PAGE.is_file():
    raise FileNotFoundError(f"Packaged portal page is missing: {PAGE}")
if not SETUP_PAGE.is_file():
    raise FileNotFoundError(f"Packaged setup page is missing: {SETUP_PAGE}")
if not PORTAL_CSS.is_file():
    raise FileNotFoundError(f"Packaged portal stylesheet is missing: {PORTAL_CSS}")
if not CHAT_FORMAT_JS.is_file():
    raise FileNotFoundError(f"Packaged chat formatter is missing: {CHAT_FORMAT_JS}")


@app.get("/")
def functions_page() -> FileResponse:
    return FileResponse(PAGE)


@app.get("/setup")
@app.get("/settings")
def setup_page() -> FileResponse:
    return FileResponse(SETUP_PAGE)


@app.get("/static/portal.css")
def portal_css() -> FileResponse:
    return FileResponse(PORTAL_CSS, media_type="text/css")


@app.get("/static/chat_format.js")
def chat_format_js() -> FileResponse:
    return FileResponse(CHAT_FORMAT_JS, media_type="application/javascript")


@app.get("/api/models")
def get_models() -> dict[str, object]:
    settings = get_settings()
    hidden = extra_hidden_ids()
    selection = load_selection(settings.data_dir, extra_hidden=hidden)
    payload = public_state(selection, extra_hidden=hidden)
    payload.update(openrouter_status_fields())
    return payload


@app.put("/api/models")
def put_models(
    body: Any = Body(...),
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    require_write_access(settings, authorization)
    hidden = extra_hidden_ids()
    try:
        selection = parse_selection(body, extra_hidden=hidden)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_selection(settings.data_dir, selection)
    return public_state(selection, extra_hidden=hidden)


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
    reset_probe_cache()
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
    try:
        function_id = resolve_chat_function(body.function)
        grounding = resolve_grounding(body.grounding)
        target_language = resolve_target_language(function_id, body.target_language)
        source_language = resolve_source_language(function_id, body.source_language)
        dse_mode = (
            resolve_request_mode(body.mode, body.dse_mode)
            if function_id == "dse_math"
            else None
        )
        dse_topic = resolve_dse_topic(body.topic) if function_id == "dse_math" else None
        dse_difficulty = (
            resolve_dse_difficulty(body.difficulty) if function_id == "dse_math" else None
        )
        dse_paper = resolve_dse_paper(body.paper) if function_id == "dse_math" else None
        dse_module = resolve_dse_module(body.module) if function_id == "dse_math" else None
        dse_level = resolve_dse_level(body.level) if function_id == "dse_math" else None
        dse_session = None
        if function_id == "dse_math":
            validate_level_topic(dse_level, dse_topic)
            if body.session_id:
                dse_session = require_session(settings.data_dir, body.session_id)
        hidden = extra_hidden_ids()
        selection = load_selection(settings.data_dir, extra_hidden=hidden)
        model_id = selection[function_id]
        messages = None
        sources: list[dict[str, str]] | None = None
        if function_id == "rag_qa":
            if not message:
                raise HTTPException(status_code=400, detail="message must not be empty.")
            messages, sources = build_rag_context(
                settings.data_dir, message, grounding
            )
            if grounding == GROUNDING_STRICT and not sources:
                result = recorded_model(function_id, model_id)
                result["reply"] = NO_DOCUMENTS_STRICT_REPLY
                result["grounding"] = grounding
                result["sources"] = []
                return result
        elif function_id == "dse_math":
            stored_question = str((dse_session or {}).get("question") or "")
            if not message:
                if dse_mode == MODE_PRACTICE:
                    message = DEFAULT_DSE_PRACTICE_MESSAGE
                elif dse_mode == MODE_CREATE_AND_MARK:
                    message = CREATE_QUESTION_USER_MESSAGE
                elif dse_mode == MODE_GUIDED_NO_ANSWER and dse_session is not None:
                    message = NEXT_HINT_USER_MESSAGE
                elif dse_mode == MODE_GUIDED_WITH_ANSWER and stored_question:
                    message = SHOW_ANSWER_USER_MESSAGE
                else:
                    raise HTTPException(
                        status_code=400, detail="message must not be empty."
                    )
            elif (
                dse_mode == MODE_GUIDED_NO_ANSWER
                and dse_session is not None
                and is_next_hint_message(message)
            ):
                message = NEXT_HINT_USER_MESSAGE
            history = None
            reveal_scheme = None
            prompt_question = stored_question or None
            if dse_session is not None:
                history = list(dse_session.get("messages") or [])
                if dse_mode == MODE_GUIDED_WITH_ANSWER:
                    reveal_scheme = str(dse_session.get("mark_scheme") or "") or None
            messages, sources = build_dse_context(
                settings.data_dir,
                message,
                grounding=grounding,
                target_language=target_language or "en",
                mode=dse_mode or MODE_PRACTICE,
                topic=dse_topic or (dse_session or {}).get("topic"),
                difficulty=dse_difficulty,
                paper=dse_paper,
                module=dse_module or (dse_session or {}).get("module"),
                level=dse_level or (dse_session or {}).get("level"),
                history=history,
                question=prompt_question,
                reveal_mark_scheme=reveal_scheme,
            )
            if grounding == GROUNDING_STRICT and not sources:
                result = recorded_model(function_id, model_id)
                result["reply"] = NO_DSE_DOCUMENTS_STRICT_REPLY
                result["grounding"] = grounding
                result["sources"] = []
                result["mode"] = dse_mode
                return result
        elif function_id == "translation":
            assert target_language is not None
            assert source_language is not None
            translation_files = list_files(
                settings.data_dir, collection=COLLECTION_TRANSLATION
            )
            if not message:
                if not translation_files:
                    raise HTTPException(
                        status_code=400, detail="message must not be empty."
                    )
                message = DEFAULT_TRANSLATION_MESSAGE
            messages, sources = build_translation_context(
                settings.data_dir,
                message,
                target_language=target_language,
                source_language=source_language,
            )
            if not sources:
                sources = None
        else:
            if not message:
                raise HTTPException(status_code=400, detail="message must not be empty.")
            messages = format_reply_messages(message)
        result = complete_chat(
            message=message,
            function_id=function_id,
            model_id=model_id,
            messages=messages,
        )
        result["grounding"] = grounding
        if function_id == "dse_math":
            result["mode"] = dse_mode
            reply_text = str(result.get("reply") or "")
            if dse_mode == MODE_CREATE_AND_MARK:
                parsed = parse_generated_question(reply_text)
                created = store_created_question(
                    settings.data_dir,
                    parsed=parsed,
                    level=dse_level,
                    topic=dse_topic,
                    language=target_language or "en",
                    module=dse_module,
                )
                result["reply"] = parsed["question"]
                result.update(public_question_payload(created))
                result = scrub_hidden_fields(result, include_answer=False)
            elif dse_mode in GUIDED_MODES:
                question_text = str((dse_session or {}).get("question") or "")
                if not question_text and not is_next_hint_message(message):
                    question_text = message
                guided = record_guided_turn(
                    settings.data_dir,
                    session=dse_session,
                    mode=dse_mode,
                    user_message=message,
                    assistant_reply=reply_text,
                    question=question_text or None,
                    level=dse_level,
                    topic=dse_topic,
                    language=target_language or "en",
                )
                result["session_id"] = guided["id"]
                result["question_id"] = guided.get("question_id") or guided["id"]
                result["step_count"] = guided.get("step_count") or 0
                result = scrub_hidden_fields(result, include_answer=False)
            if dse_level:
                result["level"] = dse_level
            if dse_topic:
                result["topic"] = dse_topic
        if sources is not None:
            result["sources"] = order_sources(sources, str(result.get("reply") or ""))
        if function_id == "translation":
            artifacts: list[dict[str, str]] = []
            if sources:
                try:
                    artifacts = repack_translation_files(
                        settings.data_dir,
                        target_language=target_language or "en",
                        reply=str(result.get("reply") or ""),
                        sources=sources,
                    )
                except Exception:
                    artifacts = []
            result["artifacts"] = artifacts
        return result
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.post("/api/dse/ocr")
def post_dse_ocr(
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    require_write_access(settings, authorization)
    filename = file.filename or ""
    data = file.file.read()
    try:
        return transcribe_question_photo(
            settings.data_dir, filename=filename, data=data
        )
    except (ChatError, OcrError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.post("/api/dse/ask")
def post_dse_ask(
    body: DseAskIn,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    return post_chat(
        ChatIn(
            message=body.message,
            function="dse_math",
            grounding=body.grounding,
            target_language=body.target_language,
            mode=body.mode,
            dse_mode=body.dse_mode,
            topic=body.topic,
            difficulty=body.difficulty,
            paper=body.paper,
            module=body.module,
            level=body.level,
            session_id=body.session_id,
            attempt_text=body.attempt_text,
        ),
        authorization,
    )


@app.post("/api/dse/question")
def post_dse_question(
    body: DseQuestionIn,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    return post_chat(
        ChatIn(
            message=CREATE_QUESTION_USER_MESSAGE,
            function="dse_math",
            grounding=body.grounding,
            target_language=body.target_language,
            mode=MODE_CREATE_AND_MARK,
            dse_mode=MODE_CREATE_AND_MARK,
            topic=body.topic,
            difficulty=body.difficulty,
            paper=body.paper,
            module=body.module,
            level=body.level,
        ),
        authorization,
    )


def _mark_dse_attempt(
    settings: Settings,
    *,
    session_id: str,
    attempt_text: str,
    grounding_value: str,
    target_language: str | None,
    filename: str = "",
    file_data: bytes = b"",
) -> dict[str, object]:
    session = require_session(settings.data_dir, session_id)
    attempt = (attempt_text or "").strip()
    if file_data:
        ocr = transcribe_question_photo(
            settings.data_dir, filename=filename or "attempt.png", data=file_data
        )
        transcribed = str(ocr.get("text") or "").strip()
        if transcribed:
            attempt = (attempt + "\n" + transcribed).strip() if attempt else transcribed
    if not attempt:
        raise ChatError(400, "attempt_text or an answer photo is required.")
    grounding = resolve_grounding(grounding_value)
    language = resolve_target_language("dse_math", target_language) or "en"
    messages, sources = build_mark_context(
        settings.data_dir,
        session,
        attempt,
        grounding=grounding,
        target_language=language,
    )
    if grounding == GROUNDING_STRICT and not sources:
        hidden = extra_hidden_ids()
        selection = load_selection(settings.data_dir, extra_hidden=hidden)
        result = recorded_model("dse_math", selection["dse_math"])
        result["reply"] = NO_DSE_DOCUMENTS_STRICT_REPLY
        result["grounding"] = grounding
        result["sources"] = []
        result["mode"] = MODE_CREATE_AND_MARK
        result["correct"] = False
        result["next_options"] = ["hints", "retry"]
        return scrub_hidden_fields(result, include_answer=False)
    hidden = extra_hidden_ids()
    selection = load_selection(settings.data_dir, extra_hidden=hidden)
    model_id = selection["dse_math"]
    result = complete_chat(
        message=attempt,
        function_id="dse_math",
        model_id=model_id,
        messages=messages,
    )
    verdict, reason = parse_mark_verdict(str(result.get("reply") or ""))
    marked = public_mark_payload(session, verdict=verdict, reason=reason)
    result.update(marked)
    result["grounding"] = grounding
    result["mode"] = MODE_CREATE_AND_MARK
    if sources:
        result["sources"] = order_sources(sources, reason)
    return scrub_hidden_fields(result, include_answer=bool(marked.get("correct")))


@app.post("/api/dse/mark")
async def post_dse_mark(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    require_write_access(settings, authorization)
    content_type = (request.headers.get("content-type") or "").lower()
    filename = ""
    file_data = b""
    try:
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            session_id = str(form.get("session_id") or "")
            attempt_text = str(form.get("attempt_text") or "")
            grounding_value = str(form.get("grounding") or "mixed")
            target_language = form.get("target_language")
            if isinstance(target_language, bytes):
                target_language = target_language.decode("utf-8")
            if target_language is not None:
                target_language = str(target_language)
            uploaded = form.get("file") or form.get("answer")
            if uploaded is not None and hasattr(uploaded, "read"):
                file_data = await uploaded.read()
                filename = getattr(uploaded, "filename", "") or "attempt.png"
        else:
            try:
                body = await request.json()
            except Exception as exc:
                raise HTTPException(status_code=400, detail="JSON body must be an object.") from exc
            if not isinstance(body, dict):
                raise HTTPException(status_code=400, detail="JSON body must be an object.")
            session_id = str(body.get("session_id") or "")
            attempt_text = str(body.get("attempt_text") or body.get("message") or "")
            grounding_value = str(body.get("grounding") or "mixed")
            raw_language = body.get("target_language")
            target_language = str(raw_language) if raw_language is not None else None
        if not session_id.strip():
            raise HTTPException(status_code=400, detail="session_id is required.")
        return _mark_dse_attempt(
            settings,
            session_id=session_id,
            attempt_text=attempt_text,
            grounding_value=grounding_value,
            target_language=target_language,
            filename=filename,
            file_data=file_data,
        )
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except (OcrError,) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.post("/api/images/generate")
def post_images_generate(
    body: ImageGenerateIn,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    require_write_access(settings, authorization)
    try:
        hidden = extra_hidden_ids()
        selection = load_selection(settings.data_dir, extra_hidden=hidden)
        return generate_images(
            settings.data_dir,
            body.model_dump(),
            model_id=selection["image_gen"],
            extra_hidden=hidden,
        )
    except (ChatError, ImageError, ImageRefError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/api/images/references")
def get_image_references() -> dict[str, object]:
    settings = get_settings()
    return list_references(settings.data_dir)


@app.post("/api/images/references", status_code=201)
def post_image_reference(
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    require_write_access(settings, authorization)
    filename = file.filename or ""
    data = file.file.read()
    try:
        return save_reference(settings.data_dir, filename=filename, data=data)
    except ImageRefError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/api/images/references/{ref_id}")
def get_image_reference_content(
    ref_id: str,
    authorization: str | None = Header(default=None),
) -> FileResponse:
    settings = get_settings()
    require_write_access(settings, authorization)
    try:
        stored, filename, media_type = get_stored_reference(settings.data_dir, ref_id)
    except ImageRefError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return FileResponse(
        stored,
        filename=filename,
        media_type=media_type,
        content_disposition_type="inline",
    )


@app.delete("/api/images/references/{ref_id}")
def delete_image_reference(
    ref_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    require_write_access(settings, authorization)
    try:
        return delete_reference(settings.data_dir, ref_id)
    except ImageRefError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/api/images")
def get_images() -> list[dict[str, object]]:
    settings = get_settings()
    return list_jobs(settings.data_dir)


@app.get("/api/images/{job_id}/file")
def get_image_file(
    job_id: str,
    index: int = 0,
    authorization: str | None = Header(default=None),
) -> FileResponse:
    settings = get_settings()
    require_write_access(settings, authorization)
    try:
        job = get_job(settings.data_dir, job_id)
        path, filename, media_type = stored_image_path(settings.data_dir, job, index)
    except ImageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return FileResponse(
        path,
        filename=filename,
        media_type=media_type,
        content_disposition_type="attachment",
    )


@app.post("/api/prompt/enhance")
def post_prompt_enhance(
    body: PromptEnhanceIn,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    settings = get_settings()
    require_write_access(settings, authorization)
    try:
        hidden = extra_hidden_ids()
        return enhance_prompt(
            settings.data_dir,
            body.prompt,
            extra_hidden=hidden,
        )
    except (ChatError, ImageError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/api/rag/files")
def get_rag_files(collection: str = COLLECTION_RAG) -> list[dict[str, object]]:
    settings = get_settings()
    try:
        chosen = resolve_collection(collection)
    except RagError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return list_files(settings.data_dir, collection=chosen)


@app.get("/api/rag/files/{file_id}/content")
def get_rag_file_content(
    file_id: str,
    authorization: str | None = Header(default=None),
) -> FileResponse:
    settings = get_settings()
    require_write_access(settings, authorization)
    try:
        stored, filename = get_stored_file(settings.data_dir, file_id)
    except RagError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return FileResponse(
        stored,
        filename=filename,
        content_disposition_type="attachment",
    )


@app.get("/api/rag/files/{file_id}/translated")
@app.get("/api/translation/files/{file_id}/download")
def get_translated_file_content(
    file_id: str,
    authorization: str | None = Header(default=None),
) -> FileResponse:
    settings = get_settings()
    require_write_access(settings, authorization)
    try:
        stored, filename = get_translated_file(settings.data_dir, file_id)
    except RagError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return FileResponse(
        stored,
        filename=filename,
        media_type=media_type_for(filename),
        content_disposition_type="attachment",
    )


@app.post("/api/rag/files", status_code=201)
def post_rag_file(
    file: UploadFile = File(...),
    collection: str = COLLECTION_RAG,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    require_write_access(settings, authorization)
    filename = file.filename or ""
    data = file.file.read()
    try:
        chosen = resolve_collection(collection)
        return save_upload(
            settings.data_dir, filename=filename, data=data, collection=chosen
        )
    except RagError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.delete("/api/rag/files/{file_id}")
def delete_rag_file(
    file_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    require_write_access(settings, authorization)
    try:
        return delete_file(settings.data_dir, file_id)
    except RagError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/api/translation/files")
def get_translation_files() -> list[dict[str, object]]:
    settings = get_settings()
    return list_files(settings.data_dir, collection=COLLECTION_TRANSLATION)


@app.post("/api/translation/files", status_code=201)
def post_translation_file(
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    require_write_access(settings, authorization)
    filename = file.filename or ""
    data = file.file.read()
    try:
        return save_upload(
            settings.data_dir,
            filename=filename,
            data=data,
            collection=COLLECTION_TRANSLATION,
        )
    except RagError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/api/dse/files")
def get_dse_files() -> list[dict[str, object]]:
    settings = get_settings()
    return list_files(settings.data_dir, collection=COLLECTION_DSE_MATH)


@app.post("/api/dse/files", status_code=201)
def post_dse_file(
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    require_write_access(settings, authorization)
    filename = file.filename or ""
    data = file.file.read()
    try:
        return save_upload(
            settings.data_dir,
            filename=filename,
            data=data,
            collection=COLLECTION_DSE_MATH,
        )
    except RagError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.delete("/api/dse/files/{file_id}")
def delete_dse_file(
    file_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    require_write_access(settings, authorization)
    try:
        return delete_file(settings.data_dir, file_id)
    except RagError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.delete("/api/translation/files/{file_id}")
def delete_translation_file(
    file_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    require_write_access(settings, authorization)
    try:
        return delete_file(settings.data_dir, file_id)
    except RagError as exc:
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
