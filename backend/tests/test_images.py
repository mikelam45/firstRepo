import base64

from fastapi.testclient import TestClient

from app.catalog import DEFAULT_SELECTION, get_model
from app.chat import MISSING_KEY_DETAIL, OPENROUTER_CHAT_URL
from app.image_refs import MAX_REFERENCE_BYTES, MAX_REFERENCES
from app.images import (
    OPENROUTER_IMAGE_TIMEOUT_SECONDS,
    OPENROUTER_IMAGES_TIMEOUT_SECONDS,
    OPENROUTER_IMAGES_URL,
)
from app.main import PAGE, app
from app.openrouter_key import MAC_KEY_PATH

SECRET = "test-openrouter-key-not-a-secret"

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
TINY_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
)
TINY_WEBP = b"RIFF\x1a\x00\x00\x00WEBPVP8L\x0d\x00\x00\x00\x2f\x00\x00\x00\x00\x00"
MOCK_B64 = base64.b64encode(TINY_PNG).decode("ascii")


def _assert_secret_absent(text: str) -> None:
    assert SECRET not in text
    assert SECRET[:18] not in text


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


def _mock_images(monkeypatch, *, status_code=200, raise_error=None, body=None):
    seen = {"calls": 0, "payloads": []}

    def fake_post(url, json=None, headers=None, timeout=None, follow_redirects=None, **kwargs):
        seen["calls"] += 1
        seen["url"] = url
        seen["json"] = json
        seen["payloads"].append(json)
        seen["headers"] = headers
        seen["timeout"] = timeout
        seen["follow_redirects"] = follow_redirects
        if raise_error is not None:
            raise raise_error
        payload = body if body is not None else {
            "created": 1748372400,
            "data": [{"b64_json": MOCK_B64, "media_type": "image/png"}],
            "usage": {"cost": 0.04},
        }

        class Response:
            def json(self_inner):
                return payload

            text = f"provider echoed {SECRET}"

        Response.status_code = status_code
        return Response()

    def guarded_post(url, json=None, headers=None, timeout=None, follow_redirects=None, **kwargs):
        if url == OPENROUTER_CHAT_URL or (isinstance(url, str) and "chat/completions" in url):
            raise AssertionError("chat completions must not be called")
        return fake_post(
            url,
            json=json,
            headers=headers,
            timeout=timeout,
            follow_redirects=follow_redirects,
        )

    # chat.py and images.py share the httpx module, so one patch covers both.
    monkeypatch.setattr("app.images.httpx.post", guarded_post)
    return seen


def _upload(client, name, data, content_type):
    return client.post(
        "/api/images/references",
        files={"file": (name, data, content_type)},
    )


def test_page_has_five_reference_slots(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    home = client.get("/")
    assert home.status_code == 200
    html = home.text
    assert 'id="ref-slots"' in html
    assert "0/5" in html
    assert "Reference photos" in html
    assert "Background" in html
    assert "Objects" in html
    assert "Attributes of background" in html
    assert "Attributes of objects" in html
    assert "Assembled prompt" in html
    assert "/api/images/references" in html
    assert "reference_ids" in html
    assert PAGE.is_file()


def test_five_reference_photos_accepted_sixth_is_400(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    data_dir = tmp_path / "data"
    ids = []
    for index in range(MAX_REFERENCES):
        response = _upload(client, f"ref-{index}.png", TINY_PNG, "image/png")
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["name"] == f"ref-{index}.png"
        assert payload["type"] == "png"
        assert payload["size"] == len(TINY_PNG)
        assert payload["href"].startswith("/api/images/references/")
        ids.append(payload["id"])
        stored = data_dir / "image-refs" / f"{payload['id']}.png"
        assert stored.is_file()

    listed = client.get("/api/images/references")
    assert listed.status_code == 200
    body = listed.json()
    assert body["count"] == 5
    assert body["max"] == 5
    assert len(body["files"]) == 5
    assert {row["id"] for row in body["files"]} == set(ids)

    sixth = _upload(client, "ref-5.png", TINY_PNG, "image/png")
    assert sixth.status_code == 400
    assert "at most 5" in sixth.json()["detail"].lower()
    after = client.get("/api/images/references").json()
    assert after["count"] == 5
    ref_files = [
        path for path in (data_dir / "image-refs").iterdir() if path.suffix == ".png"
    ]
    assert len(ref_files) == 5

    jpeg = _upload(client, "too-many.jpg", TINY_JPEG, "image/jpeg")
    assert jpeg.status_code == 400


def test_jpeg_png_webp_and_reject_other_types(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    png = _upload(client, "a.png", TINY_PNG, "image/png")
    jpeg = _upload(client, "b.jpg", TINY_JPEG, "image/jpeg")
    webp = _upload(client, "c.webp", TINY_WEBP, "image/webp")
    assert png.status_code == 201
    assert jpeg.status_code == 201
    assert webp.status_code == 201
    assert jpeg.json()["type"] == "jpeg"
    assert webp.json()["type"] == "webp"

    gif = _upload(client, "no.gif", b"GIF89a", "image/gif")
    assert gif.status_code == 400
    assert "jpeg" in gif.json()["detail"].lower()

    oversized = _upload(
        client,
        "huge.png",
        b"x" * (MAX_REFERENCE_BYTES + 1),
        "image/png",
    )
    assert oversized.status_code == 400
    assert "10 MB" in oversized.json()["detail"]

    downloaded = client.get(png.json()["href"])
    assert downloaded.status_code == 200
    assert downloaded.content == TINY_PNG

    deleted = client.delete(f"/api/images/references/{png.json()['id']}")
    assert deleted.status_code == 200
    remaining = {
        row["name"] for row in client.get("/api/images/references").json()["files"]
    }
    assert remaining == {"b.jpg", "c.webp"}


def test_generate_sends_input_references_not_chat_completions(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_images(monkeypatch)
    client = _client(monkeypatch, tmp_path)

    first = _upload(client, "hero.png", TINY_PNG, "image/png")
    second = _upload(client, "pal.jpg", TINY_JPEG, "image/jpeg")
    assert first.status_code == 201
    assert second.status_code == 201
    ids = [first.json()["id"], second.json()["id"]]

    response = client.post(
        "/api/images/generate",
        json={
            "subject": "a red panda at a workstation",
            "style": "cinematic still",
            "prompt": "keep the face from the first reference",
            "width": 1024,
            "height": 1024,
            "format": "png",
            "reference_ids": ids,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["model_id"] == DEFAULT_SELECTION["image_gen"]
    assert payload["model_id"] == "black-forest-labs/flux.2-pro"
    assert payload["function"] == "image_gen"
    assert payload["reference_ids"] == ids
    _assert_secret_absent(response.text)

    assert seen["calls"] == 1
    assert seen["url"] == OPENROUTER_IMAGES_URL
    assert seen["url"] != OPENROUTER_CHAT_URL
    assert seen["timeout"] == OPENROUTER_IMAGE_TIMEOUT_SECONDS
    assert seen["follow_redirects"] is False
    assert seen["headers"]["Authorization"] == f"Bearer {SECRET}"
    outbound = seen["json"]
    assert outbound["model"] == "black-forest-labs/flux.2-pro"
    assert outbound.get("output_format") == "png"
    assert outbound.get("aspect_ratio") == "1:1"
    assert "size" not in outbound
    assert "reference_ids" not in outbound
    assert "messages" not in outbound
    assert OPENROUTER_CHAT_URL not in str(seen["url"])
    refs = outbound["input_references"]
    assert len(refs) == 2
    for item in refs:
        assert item["type"] == "image_url"
        url = item["image_url"]["url"]
        assert url.startswith("data:image/")
        assert ";base64," in url
    assert refs[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert refs[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert base64.b64decode(refs[0]["image_url"]["url"].split(",", 1)[1]) == TINY_PNG
    assert base64.b64decode(refs[1]["image_url"]["url"].split(",", 1)[1]) == TINY_JPEG


def test_generate_without_refs_omits_input_references(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_images(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/images/generate",
        json={"prompt": "a quiet harbor at dusk", "width": 1024, "height": 1024},
    )
    assert response.status_code == 200, response.text
    assert seen["calls"] == 1
    assert "input_references" not in seen["json"]
    assert seen["json"].get("output_format") == "png"


def test_generate_missing_key_is_503(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_ENV_FILE", str(tmp_path / "no-such.env"))
    seen = _mock_images(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/images/generate", json={"prompt": "a lamp"})
    assert response.status_code == 503
    assert response.json()["detail"] == MISSING_KEY_DETAIL
    assert str(MAC_KEY_PATH) in response.json()["detail"]
    _assert_secret_absent(response.text)
    assert seen["calls"] == 0


def test_generate_rejects_unknown_and_too_many_refs(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_images(monkeypatch)
    client = _client(monkeypatch, tmp_path)

    unknown = client.post(
        "/api/images/generate",
        json={"prompt": "x", "reference_ids": ["missing-id"]},
    )
    assert unknown.status_code == 400
    assert "unknown reference" in unknown.json()["detail"].lower()

    too_many = client.post(
        "/api/images/generate",
        json={"prompt": "x", "reference_ids": [f"id-{n}" for n in range(6)]},
    )
    assert too_many.status_code == 400
    assert seen["calls"] == 0


def test_production_image_ref_routes_require_token(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_images(monkeypatch)
    client = _client(monkeypatch, tmp_path, env="production", token="test-token")
    listed = client.get("/api/images/references")
    assert listed.status_code == 200
    assert listed.json()["count"] == 0

    rejected_upload = _upload(client, "a.png", TINY_PNG, "image/png")
    assert rejected_upload.status_code == 401

    rejected_gen = client.post("/api/images/generate", json={"prompt": "a lamp"})
    assert rejected_gen.status_code == 401
    assert seen["calls"] == 0

    headers = {"Authorization": "Bearer test-token"}
    accepted = client.post(
        "/api/images/references",
        files={"file": ("a.png", TINY_PNG, "image/png")},
        headers=headers,
    )
    assert accepted.status_code == 201
    generated = client.post(
        "/api/images/generate",
        json={"prompt": "a lamp", "reference_ids": [accepted.json()["id"]]},
        headers=headers,
    )
    assert generated.status_code == 200
    assert seen["calls"] == 1
    assert "input_references" in seen["json"]
    _assert_secret_absent(generated.text)


def test_generate_accepts_background_and_object_guides(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_images(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/images/generate",
        json={
            "subject": "a tea master",
            "setting": "a quiet teahouse",
            "background": "wooden interior with rain on the windows",
            "background_attributes": "warm tungsten lamps, steam, wet pavement",
            "objects": "a gaiwan, a tea tray, two cups",
            "object_attributes": "celadon glaze, visible tea stains",
            "style": "cinematic still",
            "camera": "50mm, eye level",
            "lighting": "soft window light from the left",
            "notes": "no text, no watermark",
            "resolution": "16:9",
            "format": "png",
        },
    )
    assert response.status_code == 200, response.text
    prompt = seen["json"]["prompt"]
    assert seen["url"] == OPENROUTER_IMAGES_URL
    assert seen["url"] != OPENROUTER_CHAT_URL
    assert seen["json"]["n"] == 1
    assert seen["json"]["aspect_ratio"] == "16:9"
    assert seen["json"]["output_format"] == "png"
    assert "messages" not in seen["json"]
    order = [
        "Subject: a tea master",
        "Setting: a quiet teahouse",
        "Background: wooden interior with rain on the windows",
        "Attributes of background: warm tungsten lamps, steam, wet pavement",
        "Objects: a gaiwan, a tea tray, two cups",
        "Attributes of objects: celadon glaze, visible tea stains",
        "Style: cinematic still",
        "Camera: 50mm, eye level",
        "Lighting: soft window light from the left",
        "Notes: no text, no watermark",
    ]
    positions = [prompt.index(line) for line in order]
    assert positions == sorted(positions)
    assert prompt == "\n".join(order)
    assert response.json()["prompt"] == prompt
    _assert_secret_absent(response.text)


def test_page_has_guided_fields_and_output_controls(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    home = client.get("/")
    assert home.status_code == 200
    html = home.text
    assert 'id="image-panel"' in html
    assert 'id="image-subject"' in html
    assert 'id="image-setting"' in html
    assert 'id="image-style"' in html
    assert "cinematic still" in html
    assert "product photo" in html
    assert "storyboard frame" in html
    assert "ink wash" in html
    assert "documentary" in html
    assert 'id="image-camera"' in html
    assert 'id="image-lighting"' in html
    assert 'id="image-notes"' in html
    assert 'id="image-prompt"' in html
    assert 'id="image-enhance"' in html
    assert "1024x1024" in html
    assert "1024x768" in html
    assert "768x1024" in html
    assert "1344x768" in html
    assert "1920x1080" in html
    assert 'id="image-format"' in html
    assert 'id="image-width"' in html
    assert 'id="image-height"' in html
    assert 'id="image-generate"' in html
    assert "/api/images/generate" in html
    assert "not sent as chat completions" in html
    assert "google/gemini-3.1-flash-image" not in html


def test_generate_saves_png_and_list_file_work(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_images(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    data_dir = tmp_path / "data"
    response = client.post(
        "/api/images/generate",
        json={
            "subject": "a red panda at a workstation",
            "setting": "a quiet studio",
            "style": "cinematic still",
            "camera": "close-up",
            "lighting": "golden hour",
            "notes": "keep the desk tidy",
            "width": 1024,
            "height": 1024,
            "format": "png",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["model_id"] == "black-forest-labs/flux.2-pro"
    assert payload["function"] == "image_gen"
    assert payload["width"] == 1024
    assert payload["height"] == 1024
    assert payload["format"] == "png"
    catalog_prices = list(get_model("black-forest-labs/flux.2-pro")["prices"])
    assert payload["prices"] == catalog_prices
    assert len(payload["images"]) == 1
    href = payload["images"][0]["href"]
    _assert_secret_absent(response.text)
    assert seen["calls"] == 1
    assert seen["url"] == OPENROUTER_IMAGES_URL
    assert seen["url"] != OPENROUTER_CHAT_URL
    assert seen["timeout"] == OPENROUTER_IMAGES_TIMEOUT_SECONDS
    assert seen["json"]["model"] == "black-forest-labs/flux.2-pro"
    assert seen["json"]["aspect_ratio"] == "1:1"
    assert "size" not in seen["json"]
    assert seen["json"]["output_format"] == "png"
    assert "messages" not in seen["json"]
    stored = list((data_dir / "images").glob("*.png"))
    assert len(stored) == 1
    assert stored[0].read_bytes() == TINY_PNG
    assert (data_dir / "image-jobs.json").is_file()
    listed = client.get("/api/images")
    assert listed.status_code == 200
    jobs = listed.json()
    assert jobs[0]["id"] == payload["id"]
    downloaded = client.get(href)
    assert downloaded.status_code == 200
    assert downloaded.content == TINY_PNG
    assert "png" in downloaded.headers.get("content-type", "")
    assert "attachment" in downloaded.headers.get("content-disposition", "")


def test_invalid_format_and_resolution_are_400(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_images(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    empty = client.post("/api/images/generate", json={})
    assert empty.status_code == 400
    bad_fmt = client.post(
        "/api/images/generate",
        json={"prompt": "a lamp", "format": "gif", "width": 1024, "height": 1024},
    )
    assert bad_fmt.status_code == 400
    assert "format" in bad_fmt.json()["detail"].lower()
    too_wide = client.post(
        "/api/images/generate",
        json={"prompt": "a lamp", "format": "png", "width": 4096, "height": 1024},
    )
    assert too_wide.status_code == 400
    assert "2048" in too_wide.json()["detail"]
    bad_frames = client.post(
        "/api/images/generate",
        json={"prompt": "a lamp", "frames": ["one", "two"]},
    )
    assert bad_frames.status_code == 400
    assert seen["calls"] == 0


def test_storyboard_frames_save_one_file_each(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_images(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/images/generate",
        json={
            "prompt": "a harbor at dusk",
            "width": 1344,
            "height": 768,
            "format": "png",
            "frames": ["boats come in", "lanterns light", "a figure waits", "the tide turns"],
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["images"]) == 4
    assert seen["calls"] == 4
    assert seen["json"]["aspect_ratio"] == "16:9"
    assert "size" not in seen["json"]
    files = list((tmp_path / "data" / "images").glob("*.png"))
    assert len(files) == 4
    second = client.get(payload["images"][1]["href"])
    assert second.status_code == 200
    assert second.content == TINY_PNG


def test_webp_is_converted_with_pillow(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    _mock_images(monkeypatch)
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/images/generate",
        json={"prompt": "a lamp", "format": "webp", "width": 1024, "height": 1024},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["format"] == "webp"
    downloaded = client.get(payload["images"][0]["href"])
    assert downloaded.status_code == 200
    assert downloaded.content[:4] == b"RIFF"
    assert downloaded.content[8:12] == b"WEBP"


def test_region_403_is_surfaced(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    _mock_images(
        monkeypatch,
        status_code=403,
        body={"error": {"message": "This model is not available in your region.", "code": 403}},
    )
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/images/generate", json={"prompt": "a lamp"})
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "not available in your region" in detail
    assert "image model" in detail
    _assert_secret_absent(response.text)


def test_enhance_prompt_uses_text_chat_not_images(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = {"calls": 0}

    def fake_post(url, json=None, headers=None, timeout=None, follow_redirects=None, **kwargs):
        if isinstance(url, str) and "/api/v1/images" in url:
            raise AssertionError("prompt enhance must not call the Images API")
        seen["calls"] += 1
        seen["url"] = url
        seen["json"] = json

        class Response:
            status_code = 200

            def json(self_inner):
                return {
                    "choices": [
                        {"message": {"role": "assistant", "content": "A cinematic still of a red panda."}}
                    ]
                }

        return Response()

    monkeypatch.setattr("app.chat.httpx.post", fake_post)
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/prompt/enhance", json={"prompt": "red panda"})
    assert response.status_code == 200
    assert response.json() == {"enhanced_prompt": "A cinematic still of a red panda."}
    assert seen["url"] == OPENROUTER_CHAT_URL
    assert seen["json"]["model"] == DEFAULT_SELECTION["rag_qa"]
    _assert_secret_absent(response.text)


def test_leftover_gemini_image_is_not_used(tmp_path, monkeypatch):
    _install_key(tmp_path, monkeypatch)
    seen = _mock_images(monkeypatch)
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "model-selection.json").write_text(
        '{"selection": {"rag_qa": "deepseek/deepseek-chat",'
        ' "translation": "deepseek/deepseek-chat",'
        ' "cantonese_script": "deepseek/deepseek-chat",'
        ' "image_gen": "google/gemini-3.1-flash-image",'
        ' "video_gen": "minimax/hailuo-2.3"}}\n',
        encoding="utf-8",
    )
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/images/generate", json={"prompt": "a lamp"})
    assert response.status_code == 200
    assert response.json()["model_id"] == "black-forest-labs/flux.2-pro"
    assert seen["json"]["model"] == "black-forest-labs/flux.2-pro"
