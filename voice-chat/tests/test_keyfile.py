"""The key file is read into the environment. The secret is not logged."""

import logging
import os

from app.coach import resolve_provider
from app.keyfile import ensure_openrouter_key, parse_key_text


def test_parse_accepts_export_quotes_and_a_raw_line():
    assert parse_key_text('export OPENROUTER_API_KEY="abc123"\n') == "abc123"
    assert parse_key_text("OPENROUTER_API_KEY='abc123'\r\n") == "abc123"
    assert parse_key_text("  export OPENROUTER_API_KEY=abc123\n") == "abc123"
    assert parse_key_text("abc123\n") == "abc123"
    assert parse_key_text("export FOO=1\nnot a key\n") == ""


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


def test_pytest_does_not_read_a_key_file_unless_asked(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("LINGOCOACH_ENV_FILE", raising=False)
    path = tmp_path / ".env_voice_chat"
    path.write_text("OPENROUTER_API_KEY=should-not-load\n", encoding="utf-8")
    assert ensure_openrouter_key() is False
    assert os.environ.get("OPENROUTER_API_KEY", "") == ""
