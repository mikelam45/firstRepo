import os
import shlex
import subprocess
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.openrouter_key import (
    MAC_KEY_PATH,
    OPENROUTER_KEY_URL,
    OPENROUTER_TIMEOUT_SECONDS,
    load_openrouter_api_key,
    parse_key_text,
)

SECRET = "test-openrouter-key-not-a-secret"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _assert_secret_absent(text: str) -> None:
    assert SECRET not in text
    assert SECRET[:18] not in text


def test_parse_dotenv_quoted_values_and_ignores_comments():
    text = """
# comment
export OPENROUTER_API_KEY="test-openrouter-key-not-a-secret"

OTHER=ignored
"""
    assert parse_key_text(text) == SECRET


def test_parse_openrouter_key_alias_and_raw_line():
    assert parse_key_text("OPENROUTER_KEY='test-openrouter-key-not-a-secret'\n") == SECRET
    assert parse_key_text("\n\n# note\n  'test-openrouter-key-not-a-secret'  \n") == SECRET
    assert parse_key_text("# only a comment\n\n") is None


def test_process_env_beats_env_file_and_mac_path(tmp_path, monkeypatch):
    env_file = tmp_path / "from-file.env"
    env_file.write_text("OPENROUTER_API_KEY=from-file\n", encoding="utf-8")
    mac = tmp_path / "mac.env"
    mac.write_text("from-mac\n", encoding="utf-8")
    monkeypatch.setattr("app.openrouter_key.MAC_KEY_PATH", mac)
    monkeypatch.setenv("OPENROUTER_ENV_FILE", str(env_file))
    monkeypatch.setenv("OPENROUTER_API_KEY", f'  "{SECRET}"  ')
    assert load_openrouter_api_key() == SECRET


def test_env_file_beats_mac_path(tmp_path, monkeypatch):
    env_file = tmp_path / "from-file.env"
    env_file.write_text(f"OPENROUTER_KEY={SECRET}\n", encoding="utf-8")
    mac = tmp_path / "mac.env"
    mac.write_text("from-mac\n", encoding="utf-8")
    monkeypatch.setattr("app.openrouter_key.MAC_KEY_PATH", mac)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_ENV_FILE", str(env_file))
    assert load_openrouter_api_key() == SECRET


def test_mac_path_is_used_when_env_sources_are_unset(tmp_path, monkeypatch):
    mac = tmp_path / "mac.env"
    mac.write_text(f"{SECRET}\n", encoding="utf-8")
    monkeypatch.setattr("app.openrouter_key.MAC_KEY_PATH", mac)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_ENV_FILE", raising=False)
    assert load_openrouter_api_key() == SECRET
    assert MAC_KEY_PATH == Path("/Users/mikelam/firstRepo/openrouter_key/.env_RAG_portal")


def test_missing_env_file_is_unconfigured_and_does_not_fall_through(tmp_path, monkeypatch):
    mac = tmp_path / "mac.env"
    mac.write_text(f"{SECRET}\n", encoding="utf-8")
    monkeypatch.setattr("app.openrouter_key.MAC_KEY_PATH", mac)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_ENV_FILE", str(tmp_path / "absent.env"))
    assert load_openrouter_api_key() is None


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("PORTAL_API_TOKEN", raising=False)
    return TestClient(app)


def test_models_and_health_hide_the_secret_when_key_is_accepted(tmp_path, monkeypatch):
    env_file = tmp_path / "openrouter.env"
    env_file.write_text(f'OPENROUTER_API_KEY="{SECRET}"\n', encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_ENV_FILE", str(env_file))
    seen = {"calls": 0}

    def fake_get(url, headers=None, timeout=None, follow_redirects=None):
        seen["calls"] += 1
        seen["url"] = url
        seen["headers"] = headers
        seen["timeout"] = timeout
        seen["follow_redirects"] = follow_redirects

        class Response:
            status_code = 200
            text = f"provider echoed {SECRET}"

        return Response()

    monkeypatch.setattr("app.openrouter_key.httpx.get", fake_get)
    client = _client(monkeypatch, tmp_path)

    models = client.get("/api/models")
    assert models.status_code == 200
    _assert_secret_absent(models.text)
    body = models.json()
    assert body["openrouter_configured"] is True
    assert body["openrouter_status"] == "key_accepted"
    assert seen["url"] == OPENROUTER_KEY_URL
    assert seen["headers"]["Authorization"] == f"Bearer {SECRET}"
    assert seen["timeout"] == OPENROUTER_TIMEOUT_SECONDS
    assert seen["follow_redirects"] is False

    assert seen["calls"] == 1
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["openrouter_configured"] is True
    _assert_secret_absent(health.text)
    assert "openrouter_status" not in health.json()
    assert seen["calls"] == 1


def test_rejected_provider_body_is_not_returned(tmp_path, monkeypatch):
    env_file = tmp_path / "openrouter.env"
    env_file.write_text(SECRET + "\n", encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_ENV_FILE", str(env_file))

    def fake_get(url, headers=None, timeout=None, follow_redirects=None):
        class Response:
            status_code = 401
            text = f"invalid {SECRET} prefix {SECRET[:8]}"

        return Response()

    monkeypatch.setattr("app.openrouter_key.httpx.get", fake_get)
    client = _client(monkeypatch, tmp_path)
    models = client.get("/api/models")
    assert models.status_code == 200
    assert models.json()["openrouter_configured"] is True
    assert models.json()["openrouter_status"] == "key_rejected"
    _assert_secret_absent(models.text)
    assert "invalid" not in models.text


def test_transport_error_is_key_rejected_without_details(tmp_path, monkeypatch):
    env_file = tmp_path / "openrouter.env"
    env_file.write_text(f"OPENROUTER_API_KEY={SECRET}\n", encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_ENV_FILE", str(env_file))

    def fake_get(url, headers=None, timeout=None, follow_redirects=None):
        raise httpx.ConnectError(f"boom {SECRET}")

    monkeypatch.setattr("app.openrouter_key.httpx.get", fake_get)
    client = _client(monkeypatch, tmp_path)
    models = client.get("/api/models")
    assert models.json()["openrouter_status"] == "key_rejected"
    _assert_secret_absent(models.text)


def test_missing_file_skips_openrouter_and_reports_unconfigured(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_ENV_FILE", str(tmp_path / "no-such.env"))

    def fake_get(*args, **kwargs):
        raise AssertionError("OpenRouter should not be called")

    monkeypatch.setattr("app.openrouter_key.httpx.get", fake_get)
    client = _client(monkeypatch, tmp_path)
    models = client.get("/api/models")
    assert models.status_code == 200
    assert models.json()["openrouter_configured"] is False
    assert models.json()["openrouter_status"] == "not_configured"
    health = client.get("/health")
    assert health.json()["openrouter_configured"] is False
    page = client.get("/")
    assert page.status_code == 200
    assert "loads without an API key" in page.text
    _assert_secret_absent(page.text)


def _run_shell(script: str, env_file: Path | None, expected: str | None, extra_env: dict | None = None):
    env = os.environ.copy()
    env.pop("OPENROUTER_API_KEY", None)
    env["OPENROUTER_ENV_FILE"] = ""
    env.pop("MAC_OPENROUTER_KEY_FILE", None)
    if extra_env:
        env.update(extra_env)
    completed = subprocess.run(
        ["bash", "-c", script],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = completed.stdout + completed.stderr
    if expected:
        assert expected not in completed.stdout
        assert expected not in completed.stderr
    assert "MATCH" in completed.stdout
    assert "NOMATCH" not in completed.stdout
    assert completed.returncode == 0, combined
    return completed


def test_shell_loader_reads_file_shapes_without_printing(tmp_path):
    cases = {
        "dotenv": f'export OPENROUTER_API_KEY="{SECRET}"\n# comment\n\n',
        "alias": f"OPENROUTER_KEY='{SECRET}'\n",
        "raw": f"\n# comment\n{SECRET}\n",
    }
    for name, contents in cases.items():
        path = tmp_path / f"{name}.env"
        path.write_text(contents, encoding="utf-8")
        quoted = shlex.quote(str(path))
        script = f"""
set -euo pipefail
source scripts/load-openrouter-key.sh
unset OPENROUTER_API_KEY
unset OPENROUTER_ENV_FILE
load_openrouter_key_file {quoted}
if [ "${{OPENROUTER_API_KEY:-}}" = "$EXPECTED_KEY" ]; then
  printf '%s\n' MATCH
else
  printf '%s\n' NOMATCH
fi
"""
        _run_shell(script, path, SECRET, {"EXPECTED_KEY": SECRET})


def test_shell_loader_missing_file_and_mac_priority(tmp_path):
    missing = tmp_path / "missing.env"
    mac = tmp_path / "mac.env"
    mac.write_text(SECRET + "\n", encoding="utf-8")
    script = f"""
set -euo pipefail
source scripts/load-openrouter-key.sh
unset OPENROUTER_API_KEY
export OPENROUTER_ENV_FILE={shlex.quote(str(missing))}
export MAC_OPENROUTER_KEY_FILE={shlex.quote(str(mac))}
load_openrouter_key
if [ -z "${{OPENROUTER_API_KEY:-}}" ]; then
  printf '%s\n' MATCH
else
  printf '%s\n' NOMATCH
fi
unset OPENROUTER_ENV_FILE
load_openrouter_key
if [ "${{OPENROUTER_API_KEY:-}}" = "$EXPECTED_KEY" ]; then
  printf '%s\n' MATCH
else
  printf '%s\n' NOMATCH
fi
"""
    _run_shell(script, missing, SECRET, {"EXPECTED_KEY": SECRET})


def test_shell_loader_keeps_existing_process_env(tmp_path):
    mac = tmp_path / "mac.env"
    mac.write_text("from-mac\n", encoding="utf-8")
    script = f"""
set -euo pipefail
source scripts/load-openrouter-key.sh
unset OPENROUTER_ENV_FILE
export MAC_OPENROUTER_KEY_FILE={shlex.quote(str(mac))}
export OPENROUTER_API_KEY="$EXPECTED_KEY"
load_openrouter_key
if [ "$OPENROUTER_API_KEY" = "$EXPECTED_KEY" ]; then
  printf '%s\n' MATCH
else
  printf '%s\n' NOMATCH
fi
"""
    _run_shell(script, mac, SECRET, {"EXPECTED_KEY": SECRET})


def test_dev_script_and_readme_point_at_the_uncommitted_mac_file():
    dev = (REPO_ROOT / "scripts" / "dev.sh").read_text(encoding="utf-8")
    loader = (REPO_ROOT / "scripts" / "load-openrouter-key.sh").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    mac = "/Users/mikelam/firstRepo/openrouter_key/.env_RAG_portal"
    assert "load-openrouter-key.sh" in dev
    assert "load_openrouter_key" in dev
    assert mac in loader
    assert mac in readme
    assert "is not committed" in readme
    assert ".env" in gitignore
    assert "echo \"$OPENROUTER_API_KEY\"" not in dev
    assert "echo \"$OPENROUTER_API_KEY\"" not in loader


def test_gitignore_keeps_env_files_untracked():
    ignored = subprocess.run(
        [
            "git",
            "check-ignore",
            "-v",
            ".env",
            ".env.development",
            ".env.production",
            ".env_RAG_portal",
            "openrouter.env",
            "openrouter_key/.env_RAG_portal",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ignored.returncode == 0
    for path in (
        ".env",
        ".env.development",
        ".env.production",
        ".env_RAG_portal",
        "openrouter.env",
        "openrouter_key/.env_RAG_portal",
    ):
        assert path in ignored.stdout
    tracked_examples = subprocess.run(
        ["git", "check-ignore", "-v", ".env.development.example", ".env.production.example"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tracked_examples.returncode == 1
    assert SECRET not in ignored.stdout
