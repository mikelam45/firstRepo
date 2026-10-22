"""OpenRouter must use system CA verify=True even when CERT_FILE is set."""

from __future__ import annotations

import os
from pathlib import Path

from candidate_eval.service import _llm_config


def test_openrouter_ignores_cert_file_for_tls(tmp_path: Path, monkeypatch) -> None:
    cert = tmp_path / "qwen-tls.crt"
    cert.write_text("-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n", encoding="utf-8")

    monkeypatch.setenv("API_URL", "https://openrouter.ai/api/v1/chat/completions")
    monkeypatch.setenv("CERT_FILE", str(cert))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test-key")
    monkeypatch.delenv("TOKEN_FILE", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("MODEL_NAME", "qwen/qwen3-32b")

    cfg = _llm_config()

    assert cfg["is_openrouter"] is True
    assert cfg["verify"] is True
    assert cfg["verify"] != str(cert)
    assert cfg["cert_required"] is False
    assert cfg["auth_source"] == "OPENROUTER_API_KEY"
    assert cfg["token_loaded"] is True


def test_private_endpoint_uses_cert_file_when_present(tmp_path: Path, monkeypatch) -> None:
    cert = tmp_path / "qwen-tls.crt"
    cert.write_text("-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n", encoding="utf-8")

    monkeypatch.setenv("API_URL", "https://rhoai.example.local/v1/chat/completions")
    monkeypatch.setenv("CERT_FILE", str(cert))
    monkeypatch.setenv("LLM_API_KEY", "legacy-token")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("MODEL_NAME", "Qwen38-27b-int4")

    cfg = _llm_config()

    assert cfg["is_openrouter"] is False
    assert cfg["verify"] == str(cert.resolve())
    assert cfg["cert_required"] is True


def test_openrouter_api_key_beats_token_file(tmp_path: Path, monkeypatch) -> None:
    token_file = tmp_path / "token.txt"
    token_file.write_text("file-token-should-lose", encoding="utf-8")

    monkeypatch.setenv("API_URL", "https://openrouter.ai/api/v1/chat/completions")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-env-wins")
    monkeypatch.setenv("TOKEN_FILE", str(token_file))
    monkeypatch.delenv("CERT_FILE", raising=False)

    cfg = _llm_config()

    assert cfg["auth_source"] == "OPENROUTER_API_KEY"
    assert cfg["token"] == "sk-or-v1-env-wins"
    assert cfg["verify"] is True


if __name__ == "__main__":
    # Minimal runner without pytest dependency.
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
            test_openrouter_ignores_cert_file_for_tls(tmp, mp)
            print("PASS: openrouter ignores CERT_FILE for TLS")
            mp.restore()
            mp = _MP()
            test_private_endpoint_uses_cert_file_when_present(tmp, mp)
            print("PASS: private endpoint uses CERT_FILE")
            mp.restore()
            mp = _MP()
            test_openrouter_api_key_beats_token_file(tmp, mp)
            print("PASS: OPENROUTER_API_KEY beats TOKEN_FILE")
        finally:
            mp.restore()
    print("All OpenRouter TLS checks passed.")
