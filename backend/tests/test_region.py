from app.region import _probe_catalog_ids_impl, is_region_unavailable

SECRET = "test-openrouter-key-not-a-secret"


def _response(status_code, body):
    class Response:
        def json(self_inner):
            return body

    Response.status_code = status_code
    return Response()


def test_is_region_unavailable_detects_403_wording():
    assert is_region_unavailable(
        403, {"error": {"message": "This model is not available in your region."}}
    )
    assert not is_region_unavailable(403, {"error": {"message": "Terms Of Service"}})
    assert not is_region_unavailable(401, {"error": {"message": "not available in your region"}})
    assert not is_region_unavailable(200, None)


def test_probe_hides_region_403_and_keeps_200(monkeypatch):
    seen_keys = []
    seen_models = []

    def fake_post(url, json=None, headers=None, timeout=None, follow_redirects=None):
        seen_keys.append(headers.get("Authorization") if headers else None)
        model_id = json["model"]
        seen_models.append(model_id)
        if "gemini" in model_id:
            return _response(
                403,
                {"error": {"message": "This model is not available in your region."}},
            )
        return _response(200, {"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr("app.region.httpx.post", fake_post)
    hidden, ok = _probe_catalog_ids_impl(SECRET)
    assert "google/gemini-2.5-flash" in hidden
    assert "google/gemini-2.5-flash" not in seen_models
    assert "google/gemini-3.1-flash-image" not in hidden
    assert "google/gemini-3.1-flash-image" not in ok
    assert "google/gemini-3.1-flash-image" not in seen_models
    assert "bytedance-seed/seedream-5-0-flash" not in hidden
    assert "bytedance-seed/seedream-5-0-flash" not in seen_models
    assert "deepseek/deepseek-chat" in ok
    assert SECRET not in hidden
    assert SECRET not in ok
    assert all(item is not None for item in seen_keys)


def test_probe_without_key_does_not_call_openrouter(monkeypatch):
    def fake_post(*args, **kwargs):
        raise AssertionError("OpenRouter should not be called")

    monkeypatch.setattr("app.region.httpx.post", fake_post)
    hidden, ok = _probe_catalog_ids_impl(None)
    assert hidden == frozenset()
    assert ok == frozenset()
