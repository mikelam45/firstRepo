"""Mailbox folder browser: allowlist + listing."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from candidate_eval import browse_mail as bm
from candidate_eval.web import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_default_browse_lists_fixtures(client: TestClient) -> None:
    res = client.get("/api/browse-mail")
    assert res.status_code == 200
    data = res.json()
    assert "cwd" in data
    assert "entries" in data
    assert "shortcuts" in data
    assert "parent" in data
    names = {e["name"] for e in data["entries"]}
    # Demo mbox lives under fixtures/mbox when that is the default cwd.
    if Path(data["cwd"]).name == "mbox":
        assert "Applications" in names
        mbox = next(e for e in data["entries"] if e["name"] == "Applications")
        assert mbox["type"] == "file"
        assert mbox["is_mbox"] is True


def test_browse_project_relative_path(client: TestClient) -> None:
    res = client.get("/api/browse-mail", params={"path": "./fixtures/mbox"})
    assert res.status_code == 200
    data = res.json()
    assert data["cwd"].endswith("fixtures/mbox") or data["cwd"].endswith("fixtures/mbox/")
    names = {e["name"] for e in data["entries"]}
    assert "Applications" in names


def test_browse_rejects_path_outside_roots(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Force allow roots to a tiny sandbox so /etc is clearly outside.
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "ok").mkdir()
    monkeypatch.setattr(bm, "browse_roots", lambda: [sandbox.resolve()])
    monkeypatch.setattr(bm, "project_root", lambda: sandbox.resolve())
    monkeypatch.setattr(bm, "default_browse_cwd", lambda: sandbox.resolve())

    res = client.get("/api/browse-mail", params={"path": "/etc"})
    assert res.status_code == 400
    assert "outside" in res.json()["error"].lower()


def test_browse_rejects_traversal(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sandbox = tmp_path / "proj"
    sandbox.mkdir()
    (sandbox / "fixtures").mkdir()
    monkeypatch.setattr(bm, "browse_roots", lambda: [sandbox.resolve()])
    monkeypatch.setattr(bm, "project_root", lambda: sandbox.resolve())

    sneaky = sandbox / "fixtures" / ".." / ".." / "etc"
    res = client.get("/api/browse-mail", params={"path": str(sneaky)})
    assert res.status_code == 400


def test_looks_like_mbox_sniffs_from_header(tmp_path: Path) -> None:
    mbox = tmp_path / "Applications"
    mbox.write_text("From someone@example.com Sat Jan 1 00:00:00 2000\n", encoding="utf-8")
    assert bm.looks_like_mbox(mbox) is True

    other = tmp_path / "notes.txt"
    other.write_text("hello\n", encoding="utf-8")
    assert bm.looks_like_mbox(other) is False


def test_mailbox_uri_falls_back_to_default(client: TestClient) -> None:
    res = client.get(
        "/api/browse-mail",
        params={"path": "mailbox://user@host/Inbox/SE_2026"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["cwd"]
    assert "shortcuts" in data


def test_parent_stops_at_allow_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "home"
    nested = root / "Library" / "Thunderbird"
    nested.mkdir(parents=True)
    monkeypatch.setattr(bm, "browse_roots", lambda: [root.resolve()])

    parent = bm.parent_if_allowed(nested.resolve())
    assert parent == str((root / "Library").resolve())

    top_parent = bm.parent_if_allowed(root.resolve())
    assert top_parent is None
