"""HTTP service for LingoCoach. Port comes from the process, default 8066."""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.coach import ServiceError, handle_turn, validate_request
from app.keyfile import ensure_openrouter_key
from app.ielts_prompts import DIAGNOSTIC, gloss_for, public_bank
from app.ielts_review import handle_review, validate_review_request
from app.ielts_writing import PROMPTS as WRITING_PROMPTS
from app.ielts_writing import check_script
from app.limits import LIMITER
from app.partners import all_partners, public_partner
from app.scenarios import enabled_scenarios, public_scenario

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("lingocoach")

STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="LingoCoach", docs_url=None, redoc_url=None)

if "pytest" not in sys.modules:
    if ensure_openrouter_key():
        logger.info(
            "OpenRouter key is available (%s characters).",
            len(os.environ.get("OPENROUTER_API_KEY", "").strip()),
        )
    else:
        logger.info("No OpenRouter key. Replies use offline examples.")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/catalogue")
def catalogue() -> dict:
    return {
        "partners": [public_partner(partner) for partner in all_partners()],
        "scenarios": [public_scenario(scenario) for scenario in enabled_scenarios()],
        "ielts": public_bank("drill"),
        "diagnostic": DIAGNOSTIC,
        "writing": {
            key: {"task": value["task"], "module": value["module"], "prompt": value["prompt"]}
            for key, value in WRITING_PROMPTS.items()
        },
        "key_loaded": ensure_openrouter_key(),
    }


@app.get("/api/ielts/gloss")
def ielts_gloss(prompt_id: str, support: str = "en", kind: str = "drill") -> dict:
    try:
        text = gloss_for(prompt_id, support, kind)
    except KeyError:
        return JSONResponse({"error": "invalid_request", "message": "Unknown prompt."}, status_code=400)
    return {"gloss": text}


@app.post("/api/turn")
async def turn(request: Request):
    started = time.perf_counter()
    try:
        body = await request.json()
    except Exception:
        return _error(ServiceError(400, "invalid_request", "Body must be JSON."))
    try:
        payload = validate_request(body)
        client_id = request.headers.get("x-client-id") or "anonymous"
        allowed, retry = LIMITER.allow(f"turn:{client_id}", 30, 10 * 60)
        if not allowed:
            raise ServiceError(429, "slow_down", "Too many turns. Wait a moment.", retry)
        result = handle_turn(payload)
    except ServiceError as exc:
        logger.info(
            "turn session_id=%s ms=%d result=%s",
            body.get("session_id") if isinstance(body, dict) else "-",
            int((time.perf_counter() - started) * 1000),
            exc.error,
        )
        return _error(exc)
    logger.info(
        "turn session_id=%s ms=%d result=ok",
        payload["session_id"],
        int((time.perf_counter() - started) * 1000),
    )
    return result


@app.post("/api/ielts/review")
async def ielts_review(request: Request):
    started = time.perf_counter()
    try:
        body = await request.json()
    except Exception:
        return _error(ServiceError(400, "invalid_request", "Body must be JSON."))
    try:
        payload = validate_review_request(body)
        client_id = request.headers.get("x-client-id") or "anonymous"
        allowed, retry = LIMITER.allow(f"review:{client_id}", 40, 30 * 60)
        if not allowed:
            raise ServiceError(429, "slow_down", "Too many turns. Wait a moment.", retry)
        result = handle_review(payload, _provider())
    except ServiceError as exc:
        logger.info(
            "review session_id=%s ms=%d result=%s",
            body.get("session_id") if isinstance(body, dict) else "-",
            int((time.perf_counter() - started) * 1000),
            exc.error,
        )
        return _error(exc)
    logger.info(
        "review session_id=%s ms=%d result=ok",
        payload["session_id"],
        int((time.perf_counter() - started) * 1000),
    )
    return result


@app.post("/api/ielts/writing-check")
async def writing_check(request: Request):
    try:
        body = await request.json()
    except Exception:
        return _error(ServiceError(400, "invalid_request", "Body must be JSON."))
    task = body.get("task")
    module = body.get("module")
    text = body.get("text")
    if task not in {"task1", "task2"} or module not in {"academic", "general", "both"}:
        return _error(ServiceError(400, "invalid_request", "task or module is invalid."))
    if not isinstance(text, str):
        return _error(ServiceError(400, "invalid_request", "text is required."))
    return check_script(task, module, text)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


def _provider():
    from app.coach import resolve_provider

    return resolve_provider()


def _error(exc: ServiceError) -> JSONResponse:
    body = {"error": exc.error}
    if exc.message and exc.status == 400:
        body["message"] = exc.message
    headers = {}
    if exc.retry_after:
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(body, status_code=exc.status, headers=headers)


app.mount("/static", StaticFiles(directory=STATIC), name="static")
