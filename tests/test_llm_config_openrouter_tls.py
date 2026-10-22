"""CERT_FILE / TOKEN_FILE are skipped by default (API key + system CA only)."""

from __future__ import annotations

import os
from pathlib import Path

from candidate_eval.service import _llm_config


def test_skips_cert_and_token_by_default(tmp_path: Path, monkeypatch) -> None:
    cert = tmp_path / "qwen-tls.crt"
    cert.write_text("-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n", encoding="utf-8")
    token_file = tmp_path / "token.txt"
    token_file.write_text("should-be-ignored", encoding="utf-8")

    monkeypatch.setenv("API_URL", "https://openrouter.ai/api/v1/chat/completions")
    monkeypatch.setenv("CERT_FILE", str(cert))
    monkeypatch.setenv("TOKEN_FILE", str(token_file))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test-key")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("ALLOW_LEGACY_TLS", raising=False)
    monkeypatch.setenv("MODEL_NAME", "qwen/qwen3-32b")

    cfg = _llm_config()

    assert cfg["skip_ssl_cert_token"] is True
    assert cfg["verify"] is True
    assert cfg["cert_file"] == ""
    assert cfg["token_file"] == ""
    assert cfg["cert_required"] is False
    assert cfg["auth_source"] == "OPENROUTER_API_KEY"
    assert cfg["token"] == "sk-or-v1-test-key"


def test_token_file_ignored_without_api_key(tmp_path: Path, monkeypatch) -> None:
    token_file = tmp_path / "token.txt"
    token_file.write_text("rhoai-only-token", encoding="utf-8")

    monkeypatch.setenv("API_URL", "https://openrouter.ai/api/v1/chat/completions")
    monkeypatch.setenv("TOKEN_FILE", str(token_file))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("ALLOW_LEGACY_TLS", raising=False)

    cfg = _llm_config()

    assert cfg["token_loaded"] is False
    assert cfg["auth_source"] == "none"
    assert cfg["verify"] is True


def test_legacy_tls_opt_in(tmp_path: Path, monkeypatch) -> None:
    cert = tmp_path / "qwen-tls.crt"
    cert.write_text("-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n", encoding="utf-8")
    token_file = tmp_path / "token.txt"
    token_file.write_text("legacy-file-token", encoding="utf-8")

    monkeypatch.setenv("ALLOW_LEGACY_TLS", "true")
    monkeypatch.setenv("API_URL", "https://rhoai.example.local/v1/chat/completions")
    monkeypatch.setenv("CERT_FILE", str(cert))
    monkeypatch.setenv("TOKEN_FILE", str(token_file))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("MODEL_NAME", "Qwen38-27b-int4")

    cfg = _llm_config()

    assert cfg["skip_ssl_cert_token"] is False
    assert cfg["verify"] == str(cert.resolve())
    assert cfg["auth_source"] == "TOKEN_FILE"
    assert cfg["token"] == "legacy-file-token"


if __name__ == "__main__":
    class _MP:
        def __init__(self) -> None:
            self._saved: dict[str, str | None] = {}

        def setenv(self, key: str, value: str) -> None:
            if key not in self._saved:
                self._saved[key] = os.environ.get(key)
            os.environ[key] = value

        def delenv(self, key: str, raising: bool = True) -> None:
            if key not in self._saved:
                self._saved[key] = os.environ.get(key)
            if key in os.environ:
                del os.environ[key]
            elif raising:
                raise KeyError(key)

        def restore(self) -> None:
            for key, value in self._saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        mp = _MP()
        try:
            test_skips_cert_and_token_by_default(tmp, mp)
            print("PASS: skips CERT_FILE / TOKEN_FILE by default")
            mp.restore()
            mp = _MP()
            test_token_file_ignored_without_api_key(tmp, mp)
            print("PASS: TOKEN_FILE ignored without API key")
            mp.restore()
            mp = _MP()
            test_legacy_tls_opt_in(tmp, mp)
            print("PASS: ALLOW_LEGACY_TLS opt-in")
        finally:
            mp.restore()
    print("All SSL skip checks passed.")
