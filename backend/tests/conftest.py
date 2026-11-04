import pytest


@pytest.fixture(autouse=True)
def isolate_openrouter_key(tmp_path, monkeypatch):
    """Keep tests off the Mac key file and off the network."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_ENV_FILE", str(tmp_path / "missing-openrouter.env"))
    monkeypatch.setattr(
        "app.openrouter_key.MAC_KEY_PATH",
        tmp_path / "missing-mac-openrouter" / ".env_RAG_portal",
    )
    monkeypatch.setattr(
        "app.openrouter_key.MAC_REPO_ROOT",
        tmp_path / "missing-mac-repo",
    )
