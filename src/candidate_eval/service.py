"""Shared smoke/review helpers for CLI and HTTP server."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

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


def _llm_config() -> dict:
    """Resolve CERT_FILE / TOKEN_FILE / API_URL / MODEL_NAME from env."""
    cert_file = os.environ.get("CERT_FILE", "").strip()
    token_file = os.environ.get("TOKEN_FILE", "").strip()
    api_url = os.environ.get("API_URL", "").strip()
    model_name = (
        os.environ.get("MODEL_NAME", "").strip()
        or os.environ.get("LLM_MODEL_NAME", "").strip()
    )

    if not api_url:
        base = os.environ.get("LLM_BASE_URL", "").rstrip("/")
        if base:
            api_url = f"{base}/chat/completions"

    token = ""
    if token_file:
        path = Path(token_file)
        if path.is_file():
            token = path.read_text(encoding="utf-8").strip()
    if not token:
        token = os.environ.get("LLM_API_KEY", "").strip()

    verify: str | bool = True
    if cert_file:
        cert_path = Path(cert_file)
        verify = str(cert_path) if cert_path.is_file() else True

    return {
        "cert_file": cert_file,
        "cert_exists": bool(cert_file and Path(cert_file).is_file()),
        "token_file": token_file,
        "token_exists": bool(token_file and Path(token_file).is_file()),
        "token_loaded": bool(token),
        "api_url": api_url,
        "model_name": model_name,
        "verify": verify,
        "token": token,
        "timeout": float(os.environ.get("LLM_TIMEOUT_SECONDS", "60")),
        "temperature": float(os.environ.get("LLM_TEMPERATURE", "0.2")),
        "max_tokens": int(os.environ.get("LLM_MAX_TOKENS", "2048")),
    }


def llm_chat(messages: list[dict], *, max_tokens: int | None = None) -> dict:
    """POST to API_URL with Bearer token and optional CERT_FILE verify."""
    cfg = _llm_config()
    if not cfg["api_url"]:
        raise ValueError("API_URL is not set")
    if not cfg["token_loaded"]:
        raise ValueError("TOKEN_FILE missing/empty (or LLM_API_KEY unset)")
    if not cfg["model_name"]:
        raise ValueError("MODEL_NAME is not set")

    payload = {
        "model": cfg["model_name"],
        "messages": messages,
        "temperature": cfg["temperature"],
        "max_tokens": max_tokens if max_tokens is not None else cfg["max_tokens"],
    }
    headers = {
        "Authorization": f"Bearer {cfg['token']}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=cfg["timeout"], verify=cfg["verify"]) as client:
        resp = client.post(cfg["api_url"], headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()


def test_llm_connectivity() -> tuple[dict, int]:
    """UI/API connectivity check for CERT_FILE + TOKEN_FILE + API_URL + MODEL_NAME."""
    load_env()
    cfg = _llm_config()
    host = urlparse(cfg["api_url"]).netloc if cfg["api_url"] else ""
    result: dict = {
        "ok": False,
        "test": "llm_connectivity",
        "cert_file": cfg["cert_file"],
        "cert_exists": cfg["cert_exists"],
        "token_file": cfg["token_file"],
        "token_exists": cfg["token_exists"],
        "token_loaded": cfg["token_loaded"],
        "api_url": cfg["api_url"],
        "model_name": cfg["model_name"],
        "api_host": host,
        "tls_verify": cfg["verify"] if isinstance(cfg["verify"], bool) else str(cfg["verify"]),
        "llm_reachable": False,
    }

    if not cfg["cert_file"]:
        result["error"] = "CERT_FILE is not set in .env"
        return result, 1
    if not cfg["cert_exists"]:
        result["error"] = f"CERT_FILE not found: {cfg['cert_file']}"
        return result, 1
    if not cfg["token_file"]:
        result["error"] = "TOKEN_FILE is not set in .env"
        return result, 1
    if not cfg["token_loaded"]:
        result["error"] = f"TOKEN_FILE missing/empty: {cfg['token_file']}"
        return result, 1
    if not cfg["api_url"]:
        result["error"] = "API_URL is not set"
        return result, 1
    if not cfg["model_name"]:
        result["error"] = "MODEL_NAME is not set"
        return result, 1

    try:
        payload = llm_chat(
            [{"role": "user", "content": "Reply with exactly: pong"}],
            max_tokens=16,
        )
        result["llm_reachable"] = True
        choices = payload.get("choices") or []
        if choices:
            msg = (choices[0].get("message") or {}).get("content")
            result["llm_sample"] = (msg or "")[:200]
        result["ok"] = True
        result["message"] = "LLM connectivity OK"
        return result, 0
    except Exception as exc:  # noqa: BLE001
        result["llm_error"] = str(exc)
        result["error"] = f"cannot reach LLM at {cfg['api_url']}"
        return result, 1


def resolve_mail_paths(
    mail_path: str | None = None,
    mail_folder: str | None = None,
) -> dict:
    """Resolve Thunderbird mailbox URI or filesystem path from UI/CLI/env."""
    load_env()
    base = (mail_path or "").strip() or os.environ.get("THUNDERBIRD_MAIL_PATH", "/data/mail")
    folder_override = (mail_folder or "").strip()
    default_folder = os.environ.get("TARGET_MAIL_FOLDER", "INBOX")

    # Thunderbird mailbox URI, e.g. mailbox://user@host/Inbox/SE_2026
    if base.lower().startswith("mailbox:"):
        parsed = urlparse(base)
        uri_folder = parsed.path.lstrip("/")
        folder = folder_override or uri_folder or default_folder
        return {
            "scheme": "mailbox",
            "mail_path": base,
            "mail_account": parsed.netloc,
            "mail_folder": folder,
            "mbox_path": base if not folder_override else f"mailbox://{parsed.netloc}/{folder}",
            "mail_path_exists": True,  # logical URI — validated at ingest time
            "mbox_exists": True,
            "is_uri": True,
        }

    path = Path(base).expanduser()
    folder = folder_override or default_folder
    if path.is_file():
        mbox = path
        mail_dir = path.parent
        folder = path.name
    else:
        mail_dir = path
        mbox = path / folder
    return {
        "scheme": "filesystem",
        "mail_path": str(mail_dir),
        "mail_account": None,
        "mail_folder": folder,
        "mbox_path": str(mbox),
        "mail_path_exists": mail_dir.exists(),
        "mbox_exists": mbox.is_file() or mbox.is_dir(),
        "is_uri": False,
    }


def run_smoke(
    mail_path: str | None = None,
    mail_folder: str | None = None,
) -> tuple[dict, int]:
    """Return (checks, exit_code). 0=ok, 1=fail, 2=warn."""
    load_env()

    mail = resolve_mail_paths(mail_path, mail_folder)
    output_dir = Path(os.environ.get("OUTPUT_DIR", "/data/output"))
    role_config = Path(os.environ.get("ROLE_CONFIG_PATH", "/app/config/role_requirements.yaml"))
    port = int(os.environ.get("PORT", "3036"))
    cfg = _llm_config()

    try:
        keywords = resolve_keywords(None)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "deployment": "local", "port": port}, 1

    host = urlparse(cfg["api_url"]).netloc if cfg["api_url"] else ""
    checks: dict = {
        "ok": False,
        "mail_path": mail["mail_path"],
        "mail_account": mail.get("mail_account"),
        "mail_folder": mail["mail_folder"],
        "mbox_path": mail["mbox_path"],
        "mail_scheme": mail["scheme"],
        "mail_path_exists": mail["mail_path_exists"],
        "mbox_exists": mail["mbox_exists"],
        "output_dir": str(output_dir),
        "role_config_exists": role_config.is_file(),
        "review_keywords": keywords,
        "cert_file": cfg["cert_file"],
        "cert_exists": cfg["cert_exists"],
        "token_file": cfg["token_file"],
        "token_exists": cfg["token_exists"],
        "token_loaded": cfg["token_loaded"],
        "api_url": cfg["api_url"],
        "model_name": cfg["model_name"],
        "api_host": host,
        "llm_reachable": False,
        "deployment": "podman-or-docker-local",
        "port": port,
    }

    if not mail["mail_path_exists"]:
        checks["error"] = f"Mailbox folder path not found: {mail['mail_path']}"
        return checks, 1

    if not cfg["cert_exists"]:
        checks["error"] = f"CERT_FILE not found: {cfg['cert_file']}"
        return checks, 1
    if not cfg["token_loaded"]:
        checks["error"] = f"TOKEN_FILE missing/empty: {cfg['token_file']}"
        return checks, 1
    if not cfg["api_url"] or not cfg["model_name"]:
        checks["error"] = "API_URL and MODEL_NAME are required"
        return checks, 1

    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        payload = llm_chat(
            [{"role": "user", "content": "Reply with exactly: pong"}],
            max_tokens=16,
        )
        checks["llm_reachable"] = True
        choices = payload.get("choices") or []
        if choices:
            msg = (choices[0].get("message") or {}).get("content")
            checks["llm_sample"] = (msg or "")[:120]
        checks["ok"] = True
        checks["message"] = "smoke passed (mail + CERT_FILE + TOKEN_FILE + API_URL)"
        return checks, 0
    except Exception as exc:  # noqa: BLE001
        checks["llm_error"] = str(exc)
        checks["error"] = f"cannot reach LLM at {cfg['api_url']}"
        return checks, 1


def run_review(
    keywords: str | list[str] | None = None,
    *,
    mail_path: str | None = None,
    mail_folder: str | None = None,
) -> dict:
    load_env()
    resolved = resolve_keywords(keywords)
    mail = resolve_mail_paths(mail_path, mail_folder)
    output_dir = Path(os.environ.get("OUTPUT_DIR", "/data/output"))
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg = _llm_config()

    if not mail["mail_path"]:
        raise ValueError("Mailbox folder path is required")

    return {
        "status": "not_implemented",
        "message": (
            "Review pipeline scaffold only. Config and keyword confinement validated; "
            "implement ingest→LLM→artifacts next."
        ),
        "review_keywords": resolved,
        "mail_path": mail["mail_path"],
        "mail_account": mail.get("mail_account"),
        "mail_folder": mail["mail_folder"],
        "mail_scheme": mail["scheme"],
        "mbox_path": mail["mbox_path"],
        "mbox_exists": mail["mbox_exists"],
        "output_dir": str(output_dir),
        "api_url": cfg["api_url"],
        "model_name": cfg["model_name"],
        "cert_file": cfg["cert_file"],
        "token_file": cfg["token_file"],
        "deployment": "podman-or-docker-local",
        "port": int(os.environ.get("PORT", "3036")),
    }
