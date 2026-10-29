"""HTTP service for LingoCoach. Port comes from the process, default 8066.

TOTP: set LINGOCOACH_TOTP_SECRET or TOTP_SECRET (base32), or run
`python -m app.totp_setup` to write voice-chat/.totp_secret, then open
Authenticator and enter the code at /login. Unset secret = gate off (dev).
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.coach import ServiceError, handle_turn, validate_request
from app.keyfile import ensure_openrouter_key
from app.ielts_prompts import DIAGNOSTIC, gloss_for, public_bank
from app.ielts_review import handle_review, validate_review_request
from app.ielts_writing import PROMPTS as WRITING_PROMPTS
from app.ielts_writing import check_script
from app.limits import LIMITER
from app.partners import all_partners, public_partner
from app.scenarios import enabled_scenarios, public_scenario
from app import totp_gate

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
    totp_gate.ensure_configured()


class TotpMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not totp_gate.is_enabled():
            return await call_next(request)
        path = request.url.path
        if totp_gate.is_public_path(path):
            return await call_next(request)
        token = request.cookies.get(totp_gate.COOKIE_NAME)
        if totp_gate.session_valid(token):
            return await call_next(request)
        wants_html = "text/html" in (request.headers.get("accept") or "")
        if path.startswith("/api/") or not wants_html:
            return JSONResponse({"error": "auth_required"}, status_code=401)
        return RedirectResponse(url="/login", status_code=303)


app.add_middleware(TotpMiddleware)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/login")
def login_page() -> FileResponse:
    return FileResponse(STATIC / "login.html")


@app.post("/api/totp/verify")
async def totp_verify(request: Request):
    if not totp_gate.is_enabled():
        return JSONResponse({"error": "totp_disabled"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    code = body.get("code") if isinstance(body, dict) else None
    if not totp_gate.verify_code(str(code or "")):
        return JSONResponse({"error": "invalid_code"}, status_code=401)
    token = totp_gate.mint_session_token()
    if not token:
        return JSONResponse({"error": "totp_disabled"}, status_code=404)
    response = JSONResponse({"ok": True})
    secure = request.url.scheme == "https"
    response.set_cookie(
        key=totp_gate.COOKIE_NAME,
        value=token,
        max_age=totp_gate.SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
    return response


@app.get("/api/totp/setup")
def totp_setup():
    """One-shot otpauth URI after a secret was just created this process. Never logs the URI."""
    uri = totp_gate.consume_setup_uri()
    if not uri:
        return JSONResponse({"error": "setup_unavailable"}, status_code=404)
    return {"otpauth_uri": uri, "secret_length": len(totp_gate.current_secret() or "")}


@app.get("/api/openrouter/status")
def openrouter_status() -> dict:
    """Say whether OpenRouter accepts the configured key.

    The body is only booleans and a short reason. The key, account payload,
    and response body never leave this function.
    """
    if not ensure_openrouter_key():
        logger.info("openrouter_status status=- reason=no_key")
        return {"connected": False, "reason": "no_key"}
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        logger.info("openrouter_status status=- reason=no_key")
        return {"connected": False, "reason": "no_key"}
    return _probe_openrouter(key)


def _probe_openrouter(key: str) -> dict:
    status_code = None
    try:
        with httpx.Client(timeout=4.0) as client:
            response = client.get(
                "https://openrouter.ai/api/v1/key",
                headers={
                    "Authorization": f"Bearer {key}",
                    "X-Title": "LingoCoach",
                },
            )
            status_code = response.status_code
    except (httpx.TimeoutException, httpx.HTTPError, OSError):
        logger.info("openrouter_status status=- reason=unreachable")
        return {"connected": False, "reason": "unreachable"}
    if status_code == 200:
        logger.info("openrouter_status status=200 reason=ok")
        return {"connected": True}
    if status_code in (401, 403):
        logger.info("openrouter_status status=%s reason=auth", status_code)
        return {"connected": False, "reason": "auth"}
    logger.info("openrouter_status status=%s reason=unreachable", status_code)
    return {"connected": False, "reason": "unreachable"}


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
