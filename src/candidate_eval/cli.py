"""CLI for local Podman/Docker screening runs."""

from __future__ import annotations

import argparse
import json
import sys

from candidate_eval.service import load_env, run_review, run_smoke


def cmd_smoke(_: argparse.Namespace) -> int:
    load_env()
    checks, code = run_smoke()
    print(json.dumps(checks, indent=2))
    if code == 0:
        print("OK: container smoke passed (mail mount + keywords + LLM)")
    elif code == 2:
        print(checks.get("warning", "model warning"), file=sys.stderr)
    else:
        print(f"FAIL: {checks.get('error', 'smoke failed')}", file=sys.stderr)
    return code


def cmd_review(args: argparse.Namespace) -> int:
    load_env()
    try:
        result = run_review(
            args.keywords,
            mail_path=getattr(args, "mail_path", None),
            mail_folder=getattr(args, "mail_folder", None),
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import os

    import uvicorn

    load_env()
    host = args.host or os.environ.get("HOST", "0.0.0.0")
    port = args.port or int(os.environ.get("PORT", "3036"))
    print(f"Serving candidate-eval on http://{host}:{port}", flush=True)
    uvicorn.run("candidate_eval.web:app", host=host, port=port, reload=False)
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
    p_review.add_argument(
        "--mail-path",
        default=None,
        help="Mailbox folder path (overrides THUNDERBIRD_MAIL_PATH)",
    )
    p_review.add_argument(
        "--mail-folder",
        default=None,
        help="mbox folder name inside mail path (overrides TARGET_MAIL_FOLDER)",
    )
    p_review.set_defaults(func=cmd_review)

    p_serve = sub.add_parser("serve", help="Run local HTTP UI/API (default port 3036)")
    p_serve.add_argument("--host", default=None, help="Bind host (default 0.0.0.0)")
    p_serve.add_argument("--port", type=int, default=None, help="Bind port (default 3036)")
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
