"""Shared smoke/review helpers for CLI and HTTP server."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml
from dotenv import load_dotenv

# Container paths compose.yml sets; on bare-metal Mac these must map to the repo.
_CONTAINER_APP_PREFIX = "/app/"


@lru_cache(maxsize=1)
def project_root() -> Path:
    """Repo / app root for relative env paths — never process cwd alone.

    Order: PROJECT_ROOT, APP_HOME, walk from this file (src layout), walk from
    cwd for pyproject.toml markers, else parents[2] of this module (editable).
    """
    for key in ("PROJECT_ROOT", "APP_HOME"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return Path(raw).expanduser().resolve()

    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if _looks_like_project_root(candidate):
            return candidate

    cwd = Path.cwd()
    for candidate in (cwd, *cwd.parents):
        if _looks_like_project_root(candidate):
            return candidate

    # Editable src layout fallback: .../src/candidate_eval/service.py -> repo
    return Path(__file__).resolve().parents[2]


def _looks_like_project_root(path: Path) -> bool:
    if not (path / "pyproject.toml").is_file():
        return False
    return (
        (path / "SSLcert").is_dir()
        or (path / "compose.yml").is_file()
        or (path / "config" / "role_requirements.yaml").is_file()
    )


def resolve_repo_path(raw: str | None, *, default_rel: str | None = None) -> Path:
    """Resolve CERT_FILE / TOKEN_FILE (and similar) against project_root().

    - Absolute paths that exist (e.g. compose /app/SSLcert/...) are used as-is.
    - Absolute /app/... paths that are missing on the host are remapped to the
      same relative path under project_root() (Mac .env leftover from compose).
    - Relative paths (./SSLcert/...) always resolve against project_root(), not cwd.
    """
    value = (raw or "").strip() or (default_rel or "")
    if not value:
        return Path()

    path = Path(value).expanduser()
    root = project_root()

    if path.is_absolute():
        if path.exists():
            return path.resolve()
        # Mac bare-metal with compose-style /app/... in .env
        text = path.as_posix()
        if text.startswith(_CONTAINER_APP_PREFIX):
            remapped = (root / text[len(_CONTAINER_APP_PREFIX) :]).resolve()
            return remapped
        return path.resolve()

    # Strip leading ./ so join is clean; always repo-relative.
    return (root / path).resolve()


# Back-compat alias used by earlier Mac path fix.
resolve_secret_path = resolve_repo_path


def load_env() -> None:
    """Load .env from project root first so Mac runs work even if cwd differs.

    Project-root .env overrides any stale shell exports (e.g. old RHOAI vars).
    """
    root_env = project_root() / ".env"
    if root_env.is_file():
        load_dotenv(root_env, override=True)
    else:
        load_dotenv(override=False)


def resolve_keywords(cli_keywords: str | list[str] | None = None) -> list[str]:
    if isinstance(cli_keywords, list):
        keywords = [k.strip() for k in cli_keywords if str(k).strip()]
    elif isinstance(cli_keywords, str):
        keywords = [k.strip() for k in cli_keywords.split(",") if k.strip()]
    else:
        raw = os.environ.get("ROLE_CONFIG_PATH", "./config/role_requirements.yaml")
        config_path = resolve_repo_path(raw, default_rel="./config/role_requirements.yaml")
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
    """Resolve OpenRouter / LLM settings from env.

    Auth preference: OPENROUTER_API_KEY or LLM_API_KEY in .env, else TOKEN_FILE.
    CERT_FILE is optional (used only for private TLS endpoints).
    """
    cert_raw = (os.environ.get("CERT_FILE") or "").strip()
    token_raw = (os.environ.get("TOKEN_FILE") or "").strip()
    cert_path = (
        resolve_repo_path(cert_raw) if cert_raw else Path()
    )
    token_path = (
        resolve_repo_path(token_raw) if token_raw else Path()
    )

    api_url = (os.environ.get("API_URL") or "").strip()
    if not api_url:
        base = (os.environ.get("LLM_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
        api_url = f"{base}/chat/completions"

    model_name = (
        os.environ.get("MODEL_NAME", "").strip()
        or os.environ.get("LLM_MODEL_NAME", "").strip()
        or "qwen/qwen3-32b"
    )

    # Prefer API key in .env for OpenRouter; fall back to TOKEN_FILE for legacy RHOAI.
    token = (
        (os.environ.get("OPENROUTER_API_KEY") or "").strip()
        or (os.environ.get("LLM_API_KEY") or "").strip()
    )
    auth_source = "OPENROUTER_API_KEY" if (os.environ.get("OPENROUTER_API_KEY") or "").strip() else (
        "LLM_API_KEY" if (os.environ.get("LLM_API_KEY") or "").strip() else ""
    )
    if not token and token_path.is_file():
        token = token_path.read_text(encoding="utf-8").strip()
        auth_source = "TOKEN_FILE"

    is_openrouter = "openrouter.ai" in api_url.lower()

    verify: str | bool = True
    if cert_raw and cert_path.is_file():
        verify = str(cert_path)

    cert_display = str(cert_path) if cert_raw and str(cert_path) != "." else (cert_raw or "")
    token_display = str(token_path) if token_raw and str(token_path) != "." else (token_raw or "")

    return {
        "cert_file": cert_display,
        "cert_file_raw": cert_raw,
        "cert_exists": bool(cert_raw) and cert_path.is_file(),
        "cert_required": bool(cert_raw) and not is_openrouter,
        "token_file": token_display,
        "token_file_raw": token_raw,
        "token_exists": bool(token_raw) and token_path.is_file(),
        "token_loaded": bool(token),
        "auth_source": auth_source or ("none" if not token else "unknown"),
        "is_openrouter": is_openrouter,
        "project_root": str(project_root()),
        "api_url": api_url,
        "model_name": model_name,
        "verify": verify,
        "token": token,
        "timeout": float(os.environ.get("LLM_TIMEOUT_SECONDS", "60")),
        "temperature": float(os.environ.get("LLM_TEMPERATURE", "0.2")),
        "max_tokens": int(os.environ.get("LLM_MAX_TOKENS", "2048")),
        "http_referer": (os.environ.get("OPENROUTER_HTTP_REFERER") or "http://127.0.0.1:3036").strip(),
        "app_title": (os.environ.get("OPENROUTER_APP_TITLE") or "Candidate Evaluation").strip(),
    }


def llm_chat(messages: list[dict], *, max_tokens: int | None = None) -> dict:
    """POST to API_URL with Bearer auth (OpenRouter or local OpenAI-compatible)."""
    cfg = _llm_config()
    if not cfg["api_url"]:
        raise ValueError("API_URL is not set")
    if not cfg["token_loaded"]:
        raise ValueError("OPENROUTER_API_KEY / LLM_API_KEY unset (and no TOKEN_FILE)")
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
    if cfg["is_openrouter"]:
        headers["HTTP-Referer"] = cfg["http_referer"]
        headers["X-Title"] = cfg["app_title"]

    with httpx.Client(timeout=cfg["timeout"], verify=cfg["verify"]) as client:
        resp = client.post(cfg["api_url"], headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()


def test_llm_connectivity() -> tuple[dict, int]:
    """UI/API connectivity check for OpenRouter / LLM endpoint."""
    load_env()
    cfg = _llm_config()
    host = urlparse(cfg["api_url"]).netloc if cfg["api_url"] else ""
    result: dict = {
        "ok": False,
        "test": "llm_connectivity",
        "provider": "openrouter" if cfg["is_openrouter"] else "custom",
        "project_root": cfg["project_root"],
        "cert_file": cfg["cert_file"],
        "cert_file_raw": cfg["cert_file_raw"],
        "cert_exists": cfg["cert_exists"],
        "cert_required": cfg["cert_required"],
        "auth_source": cfg["auth_source"],
        "token_file": cfg["token_file"],
        "token_file_raw": cfg["token_file_raw"],
        "token_exists": cfg["token_exists"],
        "token_loaded": cfg["token_loaded"],
        "api_url": cfg["api_url"],
        "model_name": cfg["model_name"],
        "api_host": host,
        "tls_verify": cfg["verify"] if isinstance(cfg["verify"], bool) else str(cfg["verify"]),
        "llm_reachable": False,
    }

    if cfg["cert_required"]:
        if not cfg["cert_file"]:
            result["error"] = "CERT_FILE is not set in .env"
            return result, 1
        if not cfg["cert_exists"]:
            result["error"] = f"CERT_FILE not found: {cfg['cert_file']}"
            return result, 1
    if not cfg["token_loaded"]:
        result["error"] = "OPENROUTER_API_KEY or LLM_API_KEY missing in .env"
        return result, 1
    if not cfg["api_url"]:
        result["error"] = "API_URL is not set"
        return result, 1
    if not cfg["model_name"]:
        result["error"] = "MODEL_NAME is not set"
        return result, 1

    # Prefer a short probe timeout so the UI button fails fast offline.
    probe_timeout = float(
        os.environ.get(
            "LLM_PROBE_TIMEOUT_SECONDS",
            os.environ.get("LLM_SMOKE_TIMEOUT_SECONDS", "8"),
        )
    )
    prev_timeout = os.environ.get("LLM_TIMEOUT_SECONDS")
    os.environ["LLM_TIMEOUT_SECONDS"] = str(probe_timeout)
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
    finally:
        if prev_timeout is None:
            os.environ.pop("LLM_TIMEOUT_SECONDS", None)
        else:
            os.environ["LLM_TIMEOUT_SECONDS"] = prev_timeout


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
    if not path.is_absolute():
        path = resolve_repo_path(str(path))
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
    *,
    probe_llm: bool = False,
) -> tuple[dict, int]:
    """Return (checks, exit_code). 0=ok, 1=fail, 2=warn.

    By default skips the network LLM call so the HTTP UI can render even when
    RHOAI is unreachable (Mac/cloud without VPN). Pass probe_llm=True for CLI
    smoke or when an explicit connectivity check is wanted.
    """
    load_env()

    mail = resolve_mail_paths(mail_path, mail_folder)
    output_dir = resolve_repo_path(
        os.environ.get("OUTPUT_DIR", ""),
        default_rel="./output/candidate_reviews",
    )
    role_config = resolve_repo_path(
        os.environ.get("ROLE_CONFIG_PATH", ""),
        default_rel="./config/role_requirements.yaml",
    )
    port = int(os.environ.get("PORT", "3036"))
    cfg = _llm_config()

    try:
        keywords = resolve_keywords(None)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "deployment": "local", "port": port}, 1

    host = urlparse(cfg["api_url"]).netloc if cfg["api_url"] else ""
    privacy = privacy_env_summary()
    # mailbox:// is a logical URI — do not claim a filesystem mbox exists.
    mbox_exists = mail["mbox_exists"]
    if mail["scheme"] == "mailbox":
        mbox_exists = Path(mail["mbox_path"]).is_file()

    checks: dict = {
        "ok": False,
        "project_root": cfg["project_root"],
        "mail_path": mail["mail_path"],
        "mail_account": mail.get("mail_account"),
        "mail_folder": mail["mail_folder"],
        "mbox_path": mail["mbox_path"],
        "mail_scheme": mail["scheme"],
        "mail_path_exists": mail["mail_path_exists"],
        "mbox_exists": mbox_exists,
        "output_dir": str(output_dir),
        "role_config_exists": role_config.is_file(),
        "review_keywords": keywords,
        "privacy_mode": privacy["privacy_mode"],
        "local_db_path": privacy["local_db_path"],
        "review_use_llm": privacy["review_use_llm"],
        "cert_file": cfg["cert_file"],
        "cert_file_raw": cfg["cert_file_raw"],
        "cert_exists": cfg["cert_exists"],
        "cert_required": cfg["cert_required"],
        "auth_source": cfg["auth_source"],
        "provider": "openrouter" if cfg["is_openrouter"] else "custom",
        "token_file": cfg["token_file"],
        "token_file_raw": cfg["token_file_raw"],
        "token_exists": cfg["token_exists"],
        "token_loaded": cfg["token_loaded"],
        "api_url": cfg["api_url"],
        "model_name": cfg["model_name"],
        "api_host": host,
        "llm_reachable": None,
        "llm_probed": False,
        "deployment": "macbook-local",
        "port": port,
    }

    if not mail["mail_path_exists"]:
        checks["error"] = f"Mailbox folder path not found: {mail['mail_path']}"
        return checks, 1

    if cfg["cert_required"] and not cfg["cert_exists"]:
        checks["error"] = f"CERT_FILE not found: {cfg['cert_file']}"
        return checks, 1
    if not cfg["token_loaded"]:
        checks["error"] = "OPENROUTER_API_KEY or LLM_API_KEY missing in .env"
        return checks, 1
    if not cfg["api_url"] or not cfg["model_name"]:
        checks["error"] = "API_URL and MODEL_NAME are required"
        return checks, 1

    output_dir.mkdir(parents=True, exist_ok=True)

    if not probe_llm:
        checks["ok"] = True
        checks["llm_reachable"] = None
        checks["message"] = (
            "local smoke passed (mail + API key + API_URL config); "
            "LLM not probed — use Test LLM connectivity"
        )
        return checks, 0

    checks["llm_probed"] = True
    # Short timeout so CLI/API probes fail fast when RHOAI is unreachable.
    smoke_timeout = float(os.environ.get("LLM_SMOKE_TIMEOUT_SECONDS", "8"))
    prev_timeout = os.environ.get("LLM_TIMEOUT_SECONDS")
    os.environ["LLM_TIMEOUT_SECONDS"] = str(smoke_timeout)
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
        checks["llm_reachable"] = False
        checks["llm_error"] = str(exc)
        checks["error"] = f"cannot reach LLM at {cfg['api_url']}"
        return checks, 1
    finally:
        if prev_timeout is None:
            os.environ.pop("LLM_TIMEOUT_SECONDS", None)
        else:
            os.environ["LLM_TIMEOUT_SECONDS"] = prev_timeout


def run_review(
    keywords: str | list[str] | None = None,
    *,
    mail_path: str | None = None,
    mail_folder: str | None = None,
) -> dict:
    """Ingest mbox → store sensitive PII locally → send redacted text to LLM."""
    from candidate_eval.review_pipeline import run_privacy_review

    load_env()
    resolved = resolve_keywords(keywords)
    mail = resolve_mail_paths(mail_path, mail_folder)
    output_dir = resolve_repo_path(
        os.environ.get("OUTPUT_DIR", ""),
        default_rel="./output/candidate_reviews",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg = _llm_config()

    if not mail["mail_path"]:
        raise ValueError("Mailbox folder path is required")

    mbox_path = _require_filesystem_mbox(mail)

    use_llm = _review_use_llm()
    local_db = resolve_repo_path(
        (os.environ.get("LOCAL_DB_PATH") or "").strip() or None,
        default_rel="./data/candidate_eval.sqlite",
    )

    result = run_privacy_review(
        keywords=resolved,
        mbox_path=mbox_path,
        output_dir=output_dir,
        use_llm=use_llm,
    )
    result.update(
        {
            "mail_path": mail["mail_path"],
            "mail_account": mail.get("mail_account"),
            "mail_folder": mail["mail_folder"],
            "mail_scheme": mail["scheme"],
            "mbox_path": mbox_path,
            "mbox_exists": True,
            "output_dir": str(output_dir),
            "api_url": cfg["api_url"],
            "model_name": cfg["model_name"],
            "auth_source": cfg.get("auth_source"),
            "provider": "openrouter" if cfg.get("is_openrouter") else "custom",
            "project_root": cfg["project_root"],
            "deployment": "macbook-local",
            "port": int(os.environ.get("PORT", "3036")),
            "privacy_mode": "local_db_plus_llm_redaction",
            "local_db_path": result.get("local_db_path") or str(local_db),
            "review_use_llm": use_llm,
            "redaction_status": "applied",
            "guardrail": "assert_safe_for_llm",
        }
    )
    return result


def _review_use_llm() -> bool:
    return (os.environ.get("REVIEW_USE_LLM", "true") or "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def privacy_env_summary() -> dict:
    """UI/runtime summary of the local privacy guardrail."""
    load_env()
    db = resolve_repo_path(
        (os.environ.get("LOCAL_DB_PATH") or "").strip() or None,
        default_rel="./data/candidate_eval.sqlite",
    )
    return {
        "privacy_mode": "local_db_plus_llm_redaction",
        "local_db_path": str(db),
        "local_db_exists": db.is_file(),
        "review_use_llm": _review_use_llm(),
        "redaction_status": "enabled",
        "guardrail": "assert_safe_for_llm",
        "note": (
            "Sensitive contact fields stay in the local SQLite DB; "
            "only redacted analysis text may leave the Mac for LLM scoring."
        ),
    }


def _require_filesystem_mbox(mail: dict) -> str:
    """Privacy review needs a real on-disk mbox (not a bare mailbox:// URI)."""
    mbox_path = mail.get("mbox_path") or ""
    if mbox_path and Path(mbox_path).is_file():
        return str(Path(mbox_path).resolve())

    candidate = Path(mail.get("mail_path") or "")
    if candidate.is_file():
        return str(candidate.resolve())

    if mail.get("scheme") == "mailbox" or str(mbox_path).lower().startswith("mailbox:"):
        raise ValueError(
            "Privacy review needs a filesystem mbox file. "
            "mailbox:// URIs are not readable without a local Thunderbird path — "
            "set THUNDERBIRD_MAIL_PATH to a folder that contains the mbox "
            "(e.g. ./fixtures/mbox with TARGET_MAIL_FOLDER=Applications), "
            f"got {mbox_path!r}."
        )
    raise ValueError(
        "Readable mbox file required for privacy review. "
        "Set THUNDERBIRD_MAIL_PATH to a local folder containing the mbox, "
        f"or a file path. Resolved mbox_path={mbox_path!r}"
    )
