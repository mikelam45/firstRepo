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


def _default_mail_path() -> str:
    return os.environ.get("THUNDERBIRD_MAIL_PATH", "./fixtures/mbox")


def _default_mail_folder() -> str:
    return os.environ.get("TARGET_MAIL_FOLDER", "Applications")


def _page_context(
    *,
    keywords: str | None = None,
    mail_path: str | None = None,
    mail_folder: str | None = None,
    result: dict | None = None,
    error: str | None = None,
) -> dict:
    path = mail_path if mail_path is not None else _default_mail_path()
    folder = mail_folder if mail_folder is not None else _default_mail_folder()
    checks, code = run_smoke(mail_path=path, mail_folder=folder)
    return {
        "role_title": _role_title(),
        "keywords": keywords if keywords is not None else _default_keywords_text(),
        "mail_path": path,
        "mail_folder": folder,
        "smoke": checks,
        "smoke_ok": code == 0,
        "result": result,
        "error": error,
        "port": PORT,
        "version": __version__,
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "port": PORT}


@app.get("/api/smoke")
def api_smoke(mail_path: str | None = None, mail_folder: str | None = None) -> JSONResponse:
    checks, code = run_smoke(mail_path=mail_path, mail_folder=mail_folder)
    return JSONResponse(checks, status_code=200 if code == 0 else (503 if code == 1 else 200))


@app.post("/api/review")
async def api_review(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    keywords = body.get("keywords")
    mail_path = body.get("mail_path") or body.get("mailbox_path")
    mail_folder = body.get("mail_folder") or body.get("mailbox_folder")
    try:
        result = run_review(keywords, mail_path=mail_path, mail_folder=mail_folder)
        return JSONResponse(result)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", _page_context())


@app.post("/review", response_class=HTMLResponse)
def review_form(
    request: Request,
    keywords: str = Form(...),
    mail_path: str = Form(...),
    mail_folder: str = Form(""),
) -> HTMLResponse:
    error = None
    result = None
    try:
        if not mail_path.strip():
            raise ValueError("Mailbox folder path is required")
        result = run_review(
            keywords,
            mail_path=mail_path.strip(),
            mail_folder=mail_folder.strip() or None,
        )
    except ValueError as exc:
        error = str(exc)
    return templates.TemplateResponse(
        request,
        "index.html",
        _page_context(
            keywords=keywords,
            mail_path=mail_path,
            mail_folder=mail_folder,
            result=result,
            error=error,
        ),
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
