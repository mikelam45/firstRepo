"""CLI for local Podman/Docker screening runs."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urljoin

import httpx
import yaml
from dotenv import load_dotenv


def _load_env() -> None:
    load_dotenv(override=False)


def _require_keywords(cli_keywords: str | None) -> list[str]:
    if cli_keywords is not None:
        keywords = [k.strip() for k in cli_keywords.split(",") if k.strip()]
    else:
        config_path = Path(os.environ.get("ROLE_CONFIG_PATH", "./config/role_requirements.yaml"))
        if not config_path.is_file():
            raise SystemExit(f"ROLE_CONFIG_PATH not found: {config_path}")
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        keywords = list(data.get("review_keywords") or [])

    if not keywords:
        raise SystemExit(
            "review_keywords is required (set in role YAML or pass --keywords). Empty list rejected."
        )
    return keywords


def cmd_smoke(_: argparse.Namespace) -> int:
    """Validate env, role keywords, mail mount, and LLM /models reachability."""
    _load_env()

    mail_path = Path(os.environ.get("THUNDERBIRD_MAIL_PATH", "/data/mail"))
    output_dir = Path(os.environ.get("OUTPUT_DIR", "/data/output"))
    role_config = Path(os.environ.get("ROLE_CONFIG_PATH", "/app/config/role_requirements.yaml"))
    base_url = os.environ.get("LLM_BASE_URL", "").rstrip("/") + "/"
    model = os.environ.get("LLM_MODEL_NAME", "")
    timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "60"))

    keywords = _require_keywords(None)

    checks: dict[str, object] = {
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
    }

    if not mail_path.exists():
        print(json.dumps(checks, indent=2))
        print("FAIL: THUNDERBIRD_MAIL_PATH / mail volume missing", file=sys.stderr)
        return 1

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
                print(json.dumps(checks, indent=2))
                print(
                    f"WARN: LLM_MODEL_NAME={model!r} not in /models listing {ids}",
                    file=sys.stderr,
                )
                return 2
            checks["llm_model_listed"] = True if model else None
    except Exception as exc:  # noqa: BLE001 — surface any connectivity failure for smoke
        checks["llm_error"] = str(exc)
        print(json.dumps(checks, indent=2))
        print(f"FAIL: cannot reach LLM at {models_url}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(checks, indent=2))
    print("OK: container smoke passed (mail mount + keywords + LLM)")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    """Placeholder review entry — validates keywords/config; full pipeline TBD."""
    _load_env()
    keywords = _require_keywords(args.keywords)
    mail_path = Path(os.environ.get("THUNDERBIRD_MAIL_PATH", "/data/mail"))
    folder = os.environ.get("TARGET_MAIL_FOLDER", "INBOX")
    mbox = mail_path / folder
    output_dir = Path(os.environ.get("OUTPUT_DIR", "/data/output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "status": "not_implemented",
        "message": (
            "Review pipeline scaffold only. Config and keyword confinement validated; "
            "implement ingest→LLM→artifacts next."
        ),
        "review_keywords": keywords,
        "mbox_path": str(mbox),
        "mbox_exists": mbox.is_file() or mbox.is_dir(),
        "output_dir": str(output_dir),
        "deployment": "podman-or-docker-local",
    }
    print(json.dumps(result, indent=2))
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Candidate evaluation (local container)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_smoke = sub.add_parser("smoke", help="Validate mounts, keywords, and LLM connectivity")
    p_smoke.set_defaults(func=cmd_smoke)

    p_review = sub.add_parser("review", help="Run screening (scaffold)")
    p_review.add_argument(
        "--keywords",
        default=None,
        help="Comma-separated topic keywords (overrides role YAML for this run)",
    )
    p_review.set_defaults(func=cmd_review)

    args = parser.parse_args(argv)
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
