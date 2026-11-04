"""Persist function-to-model choices under DATA_DIR."""

from __future__ import annotations

import json
from pathlib import Path

from .catalog import (
    DEFAULT_SELECTION,
    FUNCTION_IDS,
    coerce_selection,
    get_model,
    is_available_in_hong_kong,
)


def selection_path(data_dir: Path) -> Path:
    return data_dir / "model-selection.json"


def load_selection(
    data_dir: Path,
    extra_hidden: frozenset[str] | set[str] | None = None,
) -> dict[str, str]:
    """Return saved choices, coerced so hidden models never reach the UI.

    A missing file uses DEFAULT_SELECTION (Hong Kong-available ids only).
    A leftover Gemini (or any other hidden) choice is replaced with the first
    HK-available option for that function.
    """
    selection = dict(DEFAULT_SELECTION)
    path = selection_path(data_dir)
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = None
        stored = raw.get("selection") if isinstance(raw, dict) else None
        if isinstance(stored, dict):
            for function_id in FUNCTION_IDS:
                model_id = stored.get(function_id)
                if not isinstance(model_id, str):
                    continue
                model = get_model(model_id)
                if model is not None and function_id in model["functions"]:  # type: ignore[operator]
                    selection[function_id] = model_id
    return coerce_selection(selection, extra_hidden)


def save_selection(data_dir: Path, selection: dict[str, str]) -> None:
    path = selection_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "selection": {function_id: selection[function_id] for function_id in FUNCTION_IDS}
    }
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def parse_selection(
    body: object,
    extra_hidden: frozenset[str] | set[str] | None = None,
) -> dict[str, str]:
    """Return the five choices or raise ValueError with a client-facing message."""
    if not isinstance(body, dict):
        raise ValueError("Body must be a JSON object with the function keys.")
    unknown_keys = sorted(set(body) - set(FUNCTION_IDS))
    missing_keys = [function_id for function_id in FUNCTION_IDS if function_id not in body]
    if unknown_keys or missing_keys:
        expected = ", ".join(FUNCTION_IDS)
        raise ValueError(f"Body must map exactly these keys to model ids: {expected}.")
    parsed: dict[str, str] = {}
    for function_id in FUNCTION_IDS:
        model_id = body[function_id]
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError(f"{function_id} must be a model id.")
        model_id = model_id.strip()
        model = get_model(model_id)
        if model is None:
            raise ValueError(f"Unknown model id: {model_id}")
        allowed = model["functions"]
        if function_id not in allowed:  # type: ignore[operator]
            raise ValueError(f"{model_id} is not allowed for {function_id}.")
        if not is_available_in_hong_kong(model_id, extra_hidden):
            raise ValueError(f"{model_id} is not available in Hong Kong.")
        parsed[function_id] = model_id
    return parsed
