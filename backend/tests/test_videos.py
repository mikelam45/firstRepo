import base64
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.chat import OPENROUTER_CHAT_URL
from app.main import app
from app.video_projects import (
    MAX_DURATION_SECONDS,
    MIN_DURATION_SECONDS,
)
from app.videos import (
    INTERPOLATION_TEXT,
    OPENROUTER_VIDEOS_URL,
    ORIENTATION_LOCK_TEXT,
    assemble_camera_prompt,
    assemble_video_prompt,
    split_segments,
)

SECRET = "test-openrouter-key-not-a-secret"
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _client(monkeypatch, tmp_path, *, env="development", token=None):
    monkeypatch.setenv("APP_ENV", env)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    if token:
        monkeypatch.setenv("PORTAL_API_TOKEN", token)
    else:
        monkeypatch.delenv("PORTAL_API_TOKEN", raising=False)
    return TestClient(app)


def _install_key(tmp_path, monkeypatch):
    env_file = tmp_path / "openrouter.env"
    env_file.write_text(f'OPENROUTER_API_KEY="{SECRET}"\n', encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_ENV_FILE", str(env_file))
    return env_file


def _mock_videos(monkeypatch, *, status_code=200, body=None):
    seen = {"calls": 0, "payloads": []}

    def fake_post(url, json=None, headers=None, timeout=None, follow_redirects=None, **kwargs):
        if url == OPENROUTER_CHAT_URL or (isinstance(url, str) and "chat/completions" in url):
            raise AssertionError("video jobs must not use chat completions")
        seen["calls"] += 1
        seen["url"] = url
        seen["json"] = json
        seen["payloads"].append(json)
        seen["headers"] = headers
        seen["timeout"] = timeout
        payload = body if body is not None else {
            "id": "job-test",
            "status": "pending",
            "polling_url": f"{OPENROUTER_VIDEOS_URL}/job-test",
        }

        class Response:
            def json(self_inner):
                return payload

            text = f"provider echoed {SECRET}"

        Response.status_code = status_code
        return Response()

    monkeypatch.setattr("app.videos.httpx.post", fake_post)
    return seen


def test_split_segments_finds_shortest_split():
    segments = split_segments(30, (6, 10))
    assert sum(segments) >= 30
    assert all(item in (6, 10) for item in segments)


def test_split_segments_respects_30_to_60_range():
    for duration in (30, 45, 60):
        segments = split_segments(duration, tuple(range(3, 16)))
        assert sum(segments) >= duration
        assert all(3 <= item <= 15 for item in segments)


def test_camera_prompt_requires_valid_choices():
    prompt = assemble_camera_prompt({
        "pan": "left",
        "tilt": "up",
        "dolly": "forward",
        "zoom": "out",
        "roll": "cw",
        "motion_intensity": 2,
        "character_orientation_lock": True,
        "interpolation": True,
        "cinematic_modifiers": ["handheld", "orbital"],
    })
    assert "Pan left" in prompt
    assert "Tilt up" in prompt
    assert "Dolly forward" in prompt
    assert "Zoom out" in prompt
    assert "Roll clockwise" in prompt
    assert "Motion intensity 2" in prompt
    assert ORIENTATION_LOCK_TEXT in prompt
    assert INTERPOLATION_TEXT in prompt
    assert "Handheld camera shake" in prompt
    assert "360-degree orbital shot" in prompt


def test_assemble_video_prompt_requires_prompt():
    project = {
        "characters": [
            {"slot": 0, "role": "actress", "name": "Ming", "photos": [{"id": "a"}]},
        ]
    }
    prompt = assemble_video_prompt({"prompt": "walking in the rain"}, project)
    assert "walking in the rain" in prompt
    assert "Major characters" in prompt
    assert "Ming" in prompt
    # Empty prompt still yields camera intensity text so the provider gets a description.
    no_prompt = assemble_video_prompt({"motion_intensity": 1}, project)
    assert "Motion intensity 1" in no_prompt


def test_video_projects_crud(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    created = client.post(
        "/api/videos/projects",
        json={"name": "Harbour night", "detail": {"title": "Night"}, "characters": [{"slot": 0, "role": "actress", "name": "Ming"}]},
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["name"] == "Harbour night"
    assert len(payload["characters"]) == 3
    assert payload["characters"][0]["role"] == "actress"
    assert payload["characters"][0]["name"] == "Ming"

    listed = client.get("/api/videos/projects")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    got = client.get(f"/api/videos/projects/{payload['id']}")
    assert got.status_code == 200

    updated = client.put(
        f"/api/videos/projects/{payload['id']}",
        json={"name": "Harbour day", "detail": {"title": "Day"}},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Harbour day"

    deleted = client.delete(f"/api/videos/projects/{payload['id']}")
    assert deleted.status_code == 200


def test_video_character_photo_upload_and_delete(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    created = client.post(
        "/api/videos/projects",
        json={"name": "Test", "characters": [{"slot": 0, "role": "actor", "name": "Wai"}]},
    )
    project_id = created.json()["id"]
    upload = client.post(
        f"/api/videos/projects/{project_id}/characters/0/photos",
        files={"file": ("still.png", TINY_PNG, "image/png")},
    )
    assert upload.status_code == 201
    characters = upload.json()["characters"]
    assert characters[0]["photo_count"] == 1
    photo_id = characters[0]["photos"][0]["id"]

    content = client.get(f"/api/videos/photos/{photo_id}")
    assert content.status_code == 200

    deleted = client.delete(
        f"/api/videos/projects/{project_id}/characters/0/photos/{photo_id}"
    )
    assert deleted.status_code == 200
    assert deleted.json()["characters"][0]["photo_count"] == 0


def test_video_quote(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    _install_key(tmp_path, monkeypatch)
    created = client.post(
        "/api/videos/projects",
        json={"name": "Quote test", "characters": [{"slot": 0, "role": "actress", "name": "Ming", "photos": [{"id": "a"}]}]},
    )
    project_id = created.json()["id"]
    quote = client.post(
        "/api/videos/quote",
        json={
            "project_id": project_id,
            "duration_seconds": 30,
            "cantonese_accent": True,
        },
    )
    assert quote.status_code == 200
    body = quote.json()
    assert body["duration_seconds"] == 30
    assert body["billed_seconds"] >= 30
    assert float(body["total_usd"]) > 0
    assert "segments" in body
    assert body["cantonese_accent"] is True


def test_video_generate_flow(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    _install_key(tmp_path, monkeypatch)
    seen = _mock_videos(monkeypatch)

    created = client.post(
        "/api/videos/projects",
        json={"name": "Generate test", "characters": [{"slot": 0, "role": "actress", "name": "Ming"}]},
    )
    project_id = created.json()["id"]

    # Stub poll and download so generate completes.
    def fake_get(url, headers=None, timeout=None, follow_redirects=None, **kwargs):
        if "/content" in url:
            class R:
                status_code = 200
                content = b"fakevideo"
                text = ""
                def json(self_inner):
                    return {}
            return R()
        class R:
            status_code = 200
            content = b""
            text = ""
            def json(self_inner):
                return {
                    "id": "job-test",
                    "status": "completed",
                    "unsigned_urls": ["https://example.com/video.mp4"],
                }
        return R()

    monkeypatch.setattr("app.videos.httpx.get", fake_get)
    monkeypatch.setattr("app.videos.concat_videos", lambda paths, dest: dest.write_bytes(b"stitched"))

    quote = client.post(
        "/api/videos/quote",
        json={
            "project_id": project_id,
            "duration_seconds": 30,
            "prompt": "rain",
        },
    )
    assert quote.status_code == 200
    quote_id = quote.json()["quote_id"]

    generate = client.post(
        "/api/videos/generate",
        json={
            "project_id": project_id,
            "duration_seconds": 30,
            "prompt": "rain",
            "quote_id": quote_id,
        },
    )
    assert generate.status_code == 200
    project = generate.json()
    assert len(project["clips"]) == 1
    assert project["clips"][0]["duration_seconds"] == 30


def test_video_merge(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)

    created = client.post("/api/videos/projects", json={"name": "Merge test"})
    project_id = created.json()["id"]

    # Manually create two fake clip files so merge can run.
    videos_dir = Path(tmp_path / "data" / "videos")
    videos_dir.mkdir(parents=True, exist_ok=True)
    clips = []
    for i in range(2):
        clip_id = f"00000000-0000-0000-0000-00000000000{i}"
        (videos_dir / f"{clip_id}.mp4").write_bytes(b"fake")
        clips.append({
            "id": clip_id,
            "duration_seconds": 6,
            "stored_path": f"videos/{clip_id}.mp4",
            "filename": f"{clip_id}.mp4",
        })

    projects_path = Path(tmp_path / "data" / "video-projects.json")
    raw = json.loads(projects_path.read_text(encoding="utf-8"))
    raw["projects"][0]["clips"] = clips
    projects_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    monkeypatch.setattr("app.videos.concat_videos", lambda paths, dest: dest.write_bytes(b"merged"))

    merge = client.post(f"/api/videos/projects/{project_id}/merge")
    assert merge.status_code == 200
    merged = merge.json()["merged"]
    assert merged is not None
    assert merged["href"]


def test_production_video_routes_require_token(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path, env="production", token="test-token")
    public = client.get("/api/videos/projects")
    assert public.status_code == 200

    denied = client.post("/api/videos/projects", json={"name": "x"})
    assert denied.status_code == 401
