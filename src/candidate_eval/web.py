"""Local HTTP UI/API for candidate evaluation — default port 3036."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from candidate_eval import __version__
from candidate_eval.service import resolve_keywords, run_review, run_smoke

load_dotenv(override=False)

PORT = int(os.environ.get("PORT", "3036"))
HOST = os.environ.get("HOST", "0.0.0.0")

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

app = FastAPI(
    title="Candidate Evaluation",
    version=__version__,
    description="Local screening UI — keyword-scoped candidate review",
)


def _role_title() -> str:
    path = Path(os.environ.get("ROLE_CONFIG_PATH", "./config/role_requirements.yaml"))
    if not path.is_file():
        return "Candidate review"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return (data.get("role") or {}).get("title") or "Candidate review"


def _default_keywords_text() -> str:
    try:
        return ", ".join(resolve_keywords(None))
    except ValueError:
        return ""


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "port": PORT}


@app.get("/api/smoke")
def api_smoke() -> JSONResponse:
    checks, code = run_smoke()
    return JSONResponse(checks, status_code=200 if code == 0 else (503 if code == 1 else 200))


@app.post("/api/review")
async def api_review(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    keywords = body.get("keywords")
    try:
        result = run_review(keywords)
        return JSONResponse(result)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    checks, code = run_smoke()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "role_title": _role_title(),
            "keywords": _default_keywords_text(),
            "smoke": checks,
            "smoke_ok": code == 0,
            "port": PORT,
            "version": __version__,
        },
    )


@app.post("/review", response_class=HTMLResponse)
def review_form(
    request: Request,
    keywords: str = Form(...),
) -> HTMLResponse:
    error = None
    result = None
    try:
        result = run_review(keywords)
    except ValueError as exc:
        error = str(exc)
    checks, code = run_smoke()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "role_title": _role_title(),
            "keywords": keywords,
            "smoke": checks,
            "smoke_ok": code == 0,
            "result": result,
            "error": error,
            "port": PORT,
            "version": __version__,
        },
    )


def main() -> None:
    import uvicorn

    uvicorn.run(
        "candidate_eval.web:app",
        host=HOST,
        port=PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()
