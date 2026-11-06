from fastapi.testclient import TestClient

from app.catalog import DEFAULT_SELECTION
from app.image_projects import INDEX_NAME, MAX_PROJECT_NAME, load_projects, save_projects
from app.main import PAGE, app
from tests.test_images import TINY_PNG

PROMPT_DETAIL = {
    "subject": "a red panda at a workstation",
    "setting": "Hong Kong studio loft",
    "background": "window and plants",
    "background_attributes": "soft afternoon light",
    "objects": "laptop and teacup",
    "object_attributes": "brushed aluminum, steaming",
    "nationality_select": "East Asian",
    "nationality_other": "Hong Kong",
    "person_height_select": "average",
    "height_cm": "165",
    "body": "athletic",
    "hair_color": "black",
    "hair_length": "long",
    "hair_style": "ponytail",
    "eyes_size": "medium",
    "eyes_color": "brown",
    "dress": "",
    "top": "linen shirt",
    "bottom": "trousers",
    "shoes": "loafers",
    "props": "a teacup",
    "object_action": "holding a cup",
    "style": "cinematic still",
    "camera": "medium shot",
    "shot": "medium shot",
    "lighting": "soft window light",
    "notes": "keep the same person",
    "output_resolution": "2K",
    "aspect_ratio": "16:9",
    "format": "png",
    "n": 3,
    "count_mode": "3",
    "facial_variance": "subtle",
    "motion_variance": "strong",
    "facial_variance_notes": "from slight smile to laugh",
    "motion_variance_notes": "walk then reach",
    "facial_cycle": ["neutral", "smile"],
    "motion_cycle": ["idle", "walking", "reaching"],
    "variance_steps": [
        {
            "facial": "subtle",
            "facial_note": "a faint smile",
            "motion": "off",
            "motion_note": "planted",
        },
        {
            "facial": "medium",
            "facial_note": "speaking",
            "motion": "subtle",
            "motion_note": "weight shift",
        },
        {
            "facial": "strong",
            "facial_note": "laugh",
            "motion": "strong",
            "motion_note": "reaching for the cup",
        },
    ],
    "reference_ids": ["missing-ref-id"],
    "reference_names": ["gone.png"],
}


def _client(monkeypatch, tmp_path, *, env="development", token=None):
    monkeypatch.setenv("APP_ENV", env)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    if token:
        monkeypatch.setenv("PORTAL_API_TOKEN", token)
    else:
        monkeypatch.delenv("PORTAL_API_TOKEN", raising=False)
    return TestClient(app)


def test_page_markup_has_past_projects_and_save_project(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    home = client.get("/")
    assert home.status_code == 200
    html = home.text
    assert "Past projects" in html
    assert "Save project" in html
    assert 'id="image-project-select"' in html
    assert 'id="image-project-save"' in html
    assert 'id="image-project-name"' in html
    assert 'id="image-project-delete"' in html
    assert "No saved projects yet" in html
    assert "/api/images/projects" in html
    assert PAGE.is_file()


def test_create_list_get_restores_prompt_detail(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    empty = client.get("/api/images/projects")
    assert empty.status_code == 200
    assert empty.json() == []

    created = client.post(
        "/api/images/projects",
        json={
            "name": "  Red panda loft  ",
            "prompt_detail": PROMPT_DETAIL,
            "model_id": DEFAULT_SELECTION["image_gen"],
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Red panda loft"
    assert body["id"]
    assert body["created_at"]
    assert body["updated_at"]
    assert body["model_id"] == DEFAULT_SELECTION["image_gen"]
    detail = body["prompt_detail"]
    assert detail["subject"] == "a red panda at a workstation"
    assert detail["output_resolution"] == "2K"
    assert detail["aspect_ratio"] == "16:9"
    assert detail["n"] == 3
    assert detail["variance_steps"][2]["facial_note"] == "laugh"
    assert detail["variance_steps"][2]["motion"] == "strong"
    assert detail["reference_ids"] == []
    assert body["missing_references"] == [{"id": "missing-ref-id", "name": "gone.png"}]
    assert "google/gemini" not in created.text.lower()

    listed = client.get("/api/images/projects")
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["id"] == body["id"]
    assert rows[0]["name"] == "Red panda loft"
    assert "updated_at" in rows[0]
    assert "prompt_detail" not in rows[0]

    fetched = client.get(f"/api/images/projects/{body['id']}")
    assert fetched.status_code == 200
    restored = fetched.json()["prompt_detail"]
    assert restored["subject"] == PROMPT_DETAIL["subject"]
    assert restored["setting"] == PROMPT_DETAIL["setting"]
    assert restored["background_attributes"] == PROMPT_DETAIL["background_attributes"]
    assert restored["object_action"] == "holding a cup"
    assert restored["output_resolution"] == "2K"
    assert restored["count_mode"] == "3"
    assert restored["facial_variance"] == "subtle"
    assert restored["motion_variance"] == "strong"
    assert len(restored["variance_steps"]) == 3
    assert restored["variance_steps"][0]["motion"] == "off"
    store = tmp_path / "data" / INDEX_NAME
    assert store.is_file()
    assert "a red panda at a workstation" in store.read_text(encoding="utf-8")


def test_update_and_delete_project(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    created = client.post(
        "/api/images/projects",
        json={"name": "Draft", "prompt_detail": {"subject": "a lamp", "output_resolution": "1K"}},
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    updated = client.put(
        f"/api/images/projects/{project_id}",
        json={
            "name": "Lamp still",
            "prompt_detail": {
                "subject": "a brass lamp",
                "output_resolution": "4K",
                "n": 2,
                "variance_steps": [
                    {"facial": "off", "facial_note": "", "motion": "subtle", "motion_note": "tilt"},
                    {"facial": "medium", "facial_note": "smile", "motion": "strong", "motion_note": "reach"},
                ],
            },
        },
    )
    assert updated.status_code == 200, updated.text
    payload = updated.json()
    assert payload["id"] == project_id
    assert payload["name"] == "Lamp still"
    assert payload["prompt_detail"]["subject"] == "a brass lamp"
    assert payload["prompt_detail"]["output_resolution"] == "4K"
    assert payload["prompt_detail"]["variance_steps"][1]["motion_note"] == "reach"
    assert payload["updated_at"] >= payload["created_at"]

    deleted = client.delete(f"/api/images/projects/{project_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True, "id": project_id}
    missing = client.get(f"/api/images/projects/{project_id}")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Image project not found."
    assert client.get("/api/images/projects").json() == []


def test_empty_name_is_rejected(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    empty = client.post("/api/images/projects", json={"name": "", "prompt_detail": {"subject": "x"}})
    assert empty.status_code == 400
    assert "name" in empty.json()["detail"].lower()

    blank = client.post("/api/images/projects", json={"name": "   ", "prompt_detail": {}})
    assert blank.status_code == 400

    too_long = client.post(
        "/api/images/projects",
        json={"name": "n" * (MAX_PROJECT_NAME + 1), "prompt_detail": {}},
    )
    assert too_long.status_code in {400, 422}


def test_unknown_project_is_404(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    missing_id = "11111111-1111-1111-1111-111111111111"
    assert client.get(f"/api/images/projects/{missing_id}").status_code == 404
    assert client.put(
        f"/api/images/projects/{missing_id}",
        json={"name": "Nope", "prompt_detail": {}},
    ).status_code == 404
    assert client.delete(f"/api/images/projects/{missing_id}").status_code == 404
    assert client.get("/api/images/projects/not-a-uuid").status_code == 404


def test_list_newest_updated_first(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    first = client.post("/api/images/projects", json={"name": "Older", "prompt_detail": {"subject": "a"}}).json()
    second = client.post("/api/images/projects", json={"name": "Newer", "prompt_detail": {"subject": "b"}}).json()
    data_dir = tmp_path / "data"
    rows = load_projects(data_dir)
    by_id = {row["id"]: row for row in rows}
    by_id[first["id"]]["updated_at"] = "2026-01-01T00:00:00"
    by_id[second["id"]]["updated_at"] = "2026-02-01T00:00:00"
    save_projects(data_dir, list(by_id.values()))
    listed = client.get("/api/images/projects").json()
    assert [row["name"] for row in listed] == ["Newer", "Older"]

    client.put(
        f"/api/images/projects/{first['id']}",
        json={"name": "Older", "prompt_detail": {"subject": "updated"}},
    )
    rows = load_projects(data_dir)
    by_id = {row["id"]: row for row in rows}
    by_id[first["id"]]["updated_at"] = "2026-03-01T00:00:00"
    save_projects(data_dir, list(by_id.values()))
    listed = client.get("/api/images/projects").json()
    assert [row["name"] for row in listed] == ["Older", "Newer"]


def test_gemini_model_id_is_not_stored(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    created = client.post(
        "/api/images/projects",
        json={
            "name": "HK only",
            "model_id": "google/gemini-3.1-flash-image",
            "prompt_detail": {"subject": "a lamp", "model_id": "google/gemini-3.1-flash-image"},
        },
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["model_id"] == ""
    assert payload["prompt_detail"].get("model_id") in {"", None}
    store = (tmp_path / "data" / INDEX_NAME).read_text(encoding="utf-8")
    assert "google/gemini-3.1-flash-image" not in store


def test_kept_reference_ids_survive_when_files_exist(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    uploaded = client.post(
        "/api/images/references",
        files={"file": ("hero.png", TINY_PNG, "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    ref_id = uploaded.json()["id"]
    created = client.post(
        "/api/images/projects",
        json={
            "name": "With ref",
            "prompt_detail": {
                "subject": "same person",
                "reference_ids": [ref_id, "missing-ref"],
                "reference_names": ["hero.png", "gone.png"],
            },
        },
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["prompt_detail"]["reference_ids"] == [ref_id]
    assert payload["prompt_detail"]["references"][0]["name"] == "hero.png"
    assert payload["missing_references"] == [{"id": "missing-ref", "name": "gone.png"}]


def test_production_project_writes_require_token(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path, env="production", token="test-token")
    listed = client.get("/api/images/projects")
    assert listed.status_code == 200
    rejected = client.post("/api/images/projects", json={"name": "Secret", "prompt_detail": {}})
    assert rejected.status_code == 401
    headers = {"Authorization": "Bearer test-token"}
    created = client.post(
        "/api/images/projects",
        json={"name": "Secret", "prompt_detail": {"subject": "a lamp"}},
        headers=headers,
    )
    assert created.status_code == 201
    project_id = created.json()["id"]
    rejected_put = client.put(
        f"/api/images/projects/{project_id}",
        json={"name": "Nope", "prompt_detail": {}},
    )
    assert rejected_put.status_code == 401
    accepted_put = client.put(
        f"/api/images/projects/{project_id}",
        json={"name": "Renamed", "prompt_detail": {"subject": "a lamp"}},
        headers=headers,
    )
    assert accepted_put.status_code == 200
    rejected_delete = client.delete(f"/api/images/projects/{project_id}")
    assert rejected_delete.status_code == 401
    accepted_delete = client.delete(f"/api/images/projects/{project_id}", headers=headers)
    assert accepted_delete.status_code == 200
