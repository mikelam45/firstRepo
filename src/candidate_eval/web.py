"""Local HTTP UI/API for candidate evaluation — default port 3036."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from candidate_eval import __version__
from candidate_eval.jd_match import (
    extract_keywords_from_jd,
    match_jd_to_candidates,
    parse_jd_bytes,
    resolve_mbox_for_match,
)
from candidate_eval.service import (
    _llm_config,
    load_env,
    privacy_env_summary,
    resolve_keywords,
    resolve_repo_path,
    run_review,
    run_smoke,
    test_llm_connectivity,
)

load_env()

PORT = int(os.environ.get("PORT", "3036"))
HOST = os.environ.get("HOST", "127.0.0.1")

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

app = FastAPI(
    title="Candidate Evaluation",
    version=__version__,
    description="Local screening UI — JD upload and candidate matching",
)


def _role_title() -> str:
    path = resolve_repo_path(
        os.environ.get("ROLE_CONFIG_PATH", ""),
        default_rel="./config/role_requirements.yaml",
    )
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


def _llm_env_summary() -> dict:
    load_env()
    cfg = _llm_config()
    return {
        "project_root": cfg["project_root"],
        "provider": "openrouter" if cfg["is_openrouter"] else "custom",
        "auth_source": cfg["auth_source"],
        "token_loaded": cfg["token_loaded"],
        "cert_file": cfg["cert_file"],
        "cert_file_raw": cfg["cert_file_raw"],
        "cert_exists": cfg["cert_exists"],
        "cert_required": cfg["cert_required"],
        "token_file": cfg["token_file"],
        "token_file_raw": cfg["token_file_raw"],
        "token_exists": cfg["token_exists"],
        "api_url": cfg["api_url"] or os.environ.get("API_URL", ""),
        "model_name": cfg["model_name"]
        or os.environ.get("MODEL_NAME", "")
        or os.environ.get("LLM_MODEL_NAME", ""),
    }


def _page_context(
    *,
    keywords: str | None = None,
    mail_path: str | None = None,
    mail_folder: str | None = None,
    jd_text: str | None = None,
    result: dict | None = None,
    jd_match: dict | None = None,
    error: str | None = None,
    llm_test: dict | None = None,
    llm_test_ok: bool | None = None,
    run_llm_check: bool = False,
) -> dict:
    path = mail_path if mail_path is not None else _default_mail_path()
    folder = mail_folder if mail_folder is not None else _default_mail_folder()
    checks, code = run_smoke(mail_path=path, mail_folder=folder)

    if run_llm_check and llm_test is None:
        llm_test, llm_code = test_llm_connectivity()
        llm_test_ok = llm_code == 0

    privacy = privacy_env_summary()
    source = jd_match or result
    if source:
        summary = source.get("summary") or {}
        privacy = {
            **privacy,
            "privacy_mode": source.get("privacy_mode") or privacy["privacy_mode"],
            "local_db_path": source.get("local_db_path") or privacy["local_db_path"],
            "local_db_exists": True,
            "review_use_llm": source.get("review_use_llm", privacy["review_use_llm"]),
            "redaction_status": source.get("redaction_status")
            or (
                "applied"
                if summary.get("redaction_count")
                else privacy["redaction_status"]
            ),
            "redaction_count": summary.get("redaction_count"),
            "guardrail_blocked": source.get("guardrail_blocked", 0),
            "candidate_count": summary.get("candidate_count")
            or len(source.get("candidates") or []),
        }

    return {
        "role_title": _role_title(),
        "keywords": keywords if keywords is not None else _default_keywords_text(),
        "mail_path": path,
        "mail_folder": folder,
        "jd_text": jd_text or "",
        "smoke": checks,
        "smoke_ok": code == 0,
        "result": result,
        "jd_match": jd_match,
        "error": error,
        "llm_env": _llm_env_summary(),
        "privacy": privacy,
        "llm_test": llm_test,
        "llm_test_ok": llm_test_ok,
        "port": PORT,
        "version": __version__,
    }


def _parse_keywords(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    items = [k.strip() for k in raw.split(",") if k.strip()]
    return items or None


async def _read_jd(
    jd_text: str,
    jd_file: UploadFile | None,
) -> tuple[str, str | None]:
    filename: str | None = None
    text = (jd_text or "").strip()
    if jd_file is not None and jd_file.filename:
        data = await jd_file.read()
        if data:
            filename = jd_file.filename
            text = parse_jd_bytes(filename, data)
    return text, filename


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "port": PORT}


@app.get("/api/smoke")
def api_smoke(mail_path: str | None = None, mail_folder: str | None = None) -> JSONResponse:
    checks, code = run_smoke(mail_path=mail_path, mail_folder=mail_folder)
    return JSONResponse(checks, status_code=200 if code == 0 else (503 if code == 1 else 200))


@app.get("/api/llm-test")
@app.post("/api/llm-test")
def api_llm_test() -> JSONResponse:
    result, code = test_llm_connectivity()
    return JSONResponse(result, status_code=200 if code == 0 else 503)


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


@app.post("/api/jd-match")
async def api_jd_match(request: Request) -> JSONResponse:
    content_type = request.headers.get("content-type", "")
    jd_text = ""
    jd_filename = None
    keywords_raw = None
    mail_path = None
    mail_folder = None

    if "multipart/form-data" in content_type:
        form = await request.form()
        jd_text = str(form.get("jd_text") or "")
        keywords_raw = str(form.get("keywords") or "") or None
        mail_path = str(form.get("mail_path") or "") or None
        mail_folder = str(form.get("mail_folder") or "") or None
        upload = form.get("jd_file")
        if upload is not None and hasattr(upload, "read"):
            data = await upload.read()  # type: ignore[union-attr]
            name = getattr(upload, "filename", None) or "jd.txt"
            if data:
                jd_filename = name
                jd_text = parse_jd_bytes(name, data)
    else:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        jd_text = str(body.get("jd_text") or "")
        keywords_raw = body.get("keywords")
        mail_path = body.get("mail_path")
        mail_folder = body.get("mail_folder")

    try:
        mbox_path = resolve_mbox_for_match(mail_path, mail_folder)
        keywords = _parse_keywords(keywords_raw) if isinstance(keywords_raw, str) else keywords_raw
        if not keywords and jd_text:
            keywords = extract_keywords_from_jd(jd_text)
        output_dir = resolve_repo_path(
            os.environ.get("OUTPUT_DIR", ""),
            default_rel="./output/candidate_reviews",
        )
        result = match_jd_to_candidates(
            jd_text=jd_text,
            jd_filename=jd_filename,
            mbox_path=mbox_path,
            output_dir=output_dir,
            keywords=keywords,
        )
        return JSONResponse(result)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", _page_context())


@app.post("/llm-test", response_class=HTMLResponse)
def llm_test_form(request: Request) -> HTMLResponse:
    llm_test, code = test_llm_connectivity()
    return templates.TemplateResponse(
        request,
        "index.html",
        _page_context(llm_test=llm_test, llm_test_ok=(code == 0)),
    )


@app.post("/jd-match", response_class=HTMLResponse)
async def jd_match_form(
    request: Request,
    mail_path: str = Form(...),
    mail_folder: str = Form(""),
    keywords: str = Form(""),
    jd_text: str = Form(""),
    jd_file: UploadFile | None = File(None),
) -> HTMLResponse:
    error = None
    jd_match = None
    text = jd_text
    try:
        text, filename = await _read_jd(jd_text, jd_file)
        if not mail_path.strip():
            raise ValueError("Mailbox folder path is required")
        mbox_path = resolve_mbox_for_match(mail_path.strip(), mail_folder.strip() or None)
        kw = _parse_keywords(keywords)
        if not kw:
            kw = extract_keywords_from_jd(text) if text else None
        output_dir = resolve_repo_path(
            os.environ.get("OUTPUT_DIR", ""),
            default_rel="./output/candidate_reviews",
        )
        jd_match = match_jd_to_candidates(
            jd_text=text,
            jd_filename=filename,
            mbox_path=mbox_path,
            output_dir=output_dir,
            keywords=kw,
        )
    except ValueError as exc:
        error = str(exc)
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
    return templates.TemplateResponse(
        request,
        "index.html",
        _page_context(
            keywords=keywords or _default_keywords_text(),
            mail_path=mail_path,
            mail_folder=mail_folder,
            jd_text=text,
            jd_match=jd_match,
            error=error,
        ),
    )


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
