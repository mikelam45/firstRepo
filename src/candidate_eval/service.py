"""Shared smoke/review helpers for CLI and HTTP server."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urljoin

import httpx
import yaml
from dotenv import load_dotenv


def load_env() -> None:
    load_dotenv(override=False)


def resolve_keywords(cli_keywords: str | list[str] | None = None) -> list[str]:
    if isinstance(cli_keywords, list):
        keywords = [k.strip() for k in cli_keywords if str(k).strip()]
    elif isinstance(cli_keywords, str):
        keywords = [k.strip() for k in cli_keywords.split(",") if k.strip()]
    else:
        config_path = Path(os.environ.get("ROLE_CONFIG_PATH", "./config/role_requirements.yaml"))
        if not config_path.is_file():
            raise ValueError(f"ROLE_CONFIG_PATH not found: {config_path}")
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        keywords = list(data.get("review_keywords") or [])

    if not keywords:
        raise ValueError(
            "review_keywords is required (set in role YAML or pass keywords). Empty list rejected."
        )
    return keywords


def run_smoke() -> tuple[dict, int]:
    """Return (checks, exit_code). 0=ok, 1=fail, 2=model warn."""
    load_env()

    mail_path = Path(os.environ.get("THUNDERBIRD_MAIL_PATH", "/data/mail"))
    output_dir = Path(os.environ.get("OUTPUT_DIR", "/data/output"))
    role_config = Path(os.environ.get("ROLE_CONFIG_PATH", "/app/config/role_requirements.yaml"))
    base_url = os.environ.get("LLM_BASE_URL", "").rstrip("/") + "/"
    model = os.environ.get("LLM_MODEL_NAME", "")
    timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "60"))
    port = int(os.environ.get("PORT", "3036"))

    try:
        keywords = resolve_keywords(None)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "deployment": "local", "port": port}, 1

    checks: dict = {
        "ok": False,
        "mail_path": str(mail_path),
        "mail_path_exists": mail_path.exists(),
        "output_dir": str(output_dir),
        "role_config_exists": role_config.is_file(),
        "review_keywords": keywords,
        "llm_base_url": base_url.rstrip("/"),
        "llm_model_name": model,
        "llm_reachable": False,
        "llm_models": [],
        "deployment": "podman-or-docker-local",
        "port": port,
    }

    if not mail_path.exists():
        checks["error"] = "THUNDERBIRD_MAIL_PATH / mail volume missing"
        return checks, 1

    output_dir.mkdir(parents=True, exist_ok=True)

    models_url = urljoin(base_url, "models")
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(
                models_url,
                headers={"Authorization": f"Bearer {os.environ.get('LLM_API_KEY', 'lm-studio')}"},
            )
            resp.raise_for_status()
            payload = resp.json()
            ids = [m.get("id") for m in payload.get("data", []) if isinstance(m, dict)]
            checks["llm_reachable"] = True
            checks["llm_models"] = ids
            if model and model not in ids and ids:
                checks["llm_model_listed"] = False
                checks["warning"] = f"LLM_MODEL_NAME={model!r} not in /models listing"
                return checks, 2
            checks["llm_model_listed"] = True if model else None
    except Exception as exc:  # noqa: BLE001
        checks["llm_error"] = str(exc)
        checks["error"] = f"cannot reach LLM at {models_url}"
        return checks, 1

    checks["ok"] = True
    checks["message"] = "smoke passed (mail mount + keywords + LLM)"
    return checks, 0


def run_review(keywords: str | list[str] | None = None) -> dict:
    load_env()
    resolved = resolve_keywords(keywords)
    mail_path = Path(os.environ.get("THUNDERBIRD_MAIL_PATH", "/data/mail"))
    folder = os.environ.get("TARGET_MAIL_FOLDER", "INBOX")
    mbox = mail_path / folder
    output_dir = Path(os.environ.get("OUTPUT_DIR", "/data/output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    return {
        "status": "not_implemented",
        "message": (
            "Review pipeline scaffold only. Config and keyword confinement validated; "
            "implement ingest→LLM→artifacts next."
        ),
        "review_keywords": resolved,
        "mbox_path": str(mbox),
        "mbox_exists": mbox.is_file() or mbox.is_dir(),
        "output_dir": str(output_dir),
        "deployment": "podman-or-docker-local",
        "port": int(os.environ.get("PORT", "3036")),
    }
