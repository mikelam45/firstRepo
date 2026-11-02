"""The key file is read into the environment. The secret is not logged."""

import logging
import os
from pathlib import Path

from app.coach import resolve_provider
from app.keyfile import (
    _candidates,
    current_openrouter_key,
    ensure_openrouter_key,
    missing_key_reason,
    normalize_key,
    parse_key_text,
)


def test_parse_accepts_export_quotes_and_a_raw_line():
    assert parse_key_text('export OPENROUTER_API_KEY="abc123"\n') == "abc123"
    assert parse_key_text("OPENROUTER_API_KEY='abc123'\r\n") == "abc123"
    assert parse_key_text("  export OPENROUTER_API_KEY=abc123\n") == "abc123"
    assert parse_key_text("abc123\n") == "abc123"
    assert parse_key_text("export FOO=1\nnot a key\n") == ""
    assert parse_key_text("OPENROUTER_API_KEY=sk-or-abc # comment\n") == "sk-or-abc"
    assert parse_key_text('OPENROUTER_API_KEY=" sk-or-abc "\n') == "sk-or-abc"
    assert parse_key_text("OPENROUTER_API_KEY=Bearer sk-or-abc\n") == "sk-or-abc"


def test_normalize_key_strips_quotes_spaces_bearer_like_totp():
    assert normalize_key('  "sk-or-abc"  ') == "sk-or-abc"
    assert normalize_key("'sk-or-abc'") == "sk-or-abc"
    assert normalize_key('""sk-or-abc""') == "sk-or-abc"
    assert normalize_key("Bearer sk-or-abc") == "sk-or-abc"
    assert normalize_key("") == ""
    assert normalize_key(None) == ""


def test_candidates_include_vps_env_files():
    found = [str(p) for p in _candidates()]
    assert str(Path.home() / "lingocoach.env") in found
    here = Path(__file__).resolve().parents[1]
    assert str(here / ".env") in found
    assert "/Users/mikelam/firstRepo/openrouter_key/.env_voice_chat" in found


def test_quoted_env_key_is_stripped_without_logging(monkeypatch, caplog):
    secret = "sk-or-quoted-env"
    monkeypatch.setenv("OPENROUTER_API_KEY", f'  "{secret}"  ')
    monkeypatch.delenv("LINGOCOACH_ENV_FILE", raising=False)
    try:
        with caplog.at_level(logging.INFO):
            assert ensure_openrouter_key() is True
        assert os.environ["OPENROUTER_API_KEY"] == secret
        assert current_openrouter_key() == secret
        assert secret not in caplog.text
        assert resolve_provider().name == "openrouter"
    finally:
        os.environ.pop("OPENROUTER_API_KEY", None)


def test_env_file_loads_without_logging_the_secret(monkeypatch, tmp_path, caplog):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    path = tmp_path / ".env_voice_chat"
    secret = "sk-test-value"
    path.write_text(f'export OPENROUTER_API_KEY="{secret}"\n', encoding="utf-8")
    monkeypatch.setenv("LINGOCOACH_ENV_FILE", str(path))
    try:
        with caplog.at_level(logging.INFO):
            assert ensure_openrouter_key() is True
        assert os.environ["OPENROUTER_API_KEY"] == secret
        assert secret not in caplog.text
        assert resolve_provider().name == "openrouter"
    finally:
        os.environ.pop("OPENROUTER_API_KEY", None)


def test_home_lingocoach_env_loads_export_quotes(monkeypatch, tmp_path, caplog):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    path = tmp_path / "lingocoach.env"
    secret = "sk-or-vps-home"
    path.write_text(f'export OPENROUTER_API_KEY="{secret}"\n', encoding="utf-8")
    monkeypatch.setenv("LINGOCOACH_ENV_FILE", str(path))
    try:
        with caplog.at_level(logging.INFO):
            assert ensure_openrouter_key() is True
        assert os.environ["OPENROUTER_API_KEY"] == secret
        assert secret not in caplog.text
        assert "OPENROUTER_API_KEY=" not in caplog.text
    finally:
        os.environ.pop("OPENROUTER_API_KEY", None)


def test_voice_chat_dotenv_is_accepted(monkeypatch, tmp_path, caplog):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    path = tmp_path / ".env"
    secret = "sk-or-dotenv"
    path.write_text(f"OPENROUTER_API_KEY='{secret}'\n", encoding="utf-8")
    monkeypatch.setenv("LINGOCOACH_ENV_FILE", str(path))
    try:
        with caplog.at_level(logging.INFO):
            assert ensure_openrouter_key() is True
        assert os.environ["OPENROUTER_API_KEY"] == secret
        assert secret not in caplog.text
    finally:
        os.environ.pop("OPENROUTER_API_KEY", None)


def test_file_refresh_overrides_stale_quoted_env(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", '"stale-systemd-snapshot"')
    path = tmp_path / "lingocoach.env"
    secret = "sk-or-refreshed"
    path.write_text(f"OPENROUTER_API_KEY={secret}\n", encoding="utf-8")
    monkeypatch.setenv("LINGOCOACH_ENV_FILE", str(path))
    try:
        assert ensure_openrouter_key() is True
        assert os.environ["OPENROUTER_API_KEY"] == secret
    finally:
        os.environ.pop("OPENROUTER_API_KEY", None)


def test_pytest_does_not_read_a_key_file_unless_asked(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("LINGOCOACH_ENV_FILE", raising=False)
    path = tmp_path / ".env_voice_chat"
    path.write_text("OPENROUTER_API_KEY=should-not-load\n", encoding="utf-8")
    assert ensure_openrouter_key() is False
    assert os.environ.get("OPENROUTER_API_KEY", "") == ""
    assert missing_key_reason() == "no_key"


def test_missing_reason_path_when_no_files(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    missing = tmp_path / "absent.env"
    monkeypatch.setenv("LINGOCOACH_ENV_FILE", str(missing))
    monkeypatch.setattr("app.keyfile._candidates", lambda: [missing])
    assert ensure_openrouter_key() is False
    assert missing_key_reason() == "path"


def test_missing_reason_no_key_when_file_has_no_assignment(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    path = tmp_path / "lingocoach.env"
    path.write_text("LINGOCOACH_DOMAIN=example.com\n", encoding="utf-8")
    monkeypatch.setenv("LINGOCOACH_ENV_FILE", str(path))
    monkeypatch.setattr("app.keyfile._candidates", lambda: [path])
    assert ensure_openrouter_key() is False
    assert missing_key_reason() == "no_key"
