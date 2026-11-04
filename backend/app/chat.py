"""Call OpenRouter chat completions for text functions only.

Image and video functions are rejected here. They never go to
``/api/v1/chat/completions``. Prices in the reply come from the recorded
catalog, not a live quote. The OpenRouter key and provider body stay out of
return values, logs, and error text.
"""

from __future__ import annotations

from typing import Any

import httpx

from .catalog import FUNCTION_LABELS, PRICES_RECORDED_ON, TEXT_FUNCTIONS, get_model
from .openrouter_key import MAC_KEY_PATH, load_openrouter_api_key

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_CHAT_TIMEOUT_SECONDS = 20.0
CHAT_FUNCTIONS = TEXT_FUNCTIONS
MISSING_KEY_DETAIL = (
    "OpenRouter is not configured. The Mac file "
    f"{MAC_KEY_PATH} is missing. The page still loads."
)


class ChatError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def resolve_chat_function(function_id: str | None) -> str:
    chosen = (function_id or "rag_qa").strip() or "rag_qa"
    if chosen in {"image_gen", "video_gen"}:
        raise ChatError(
            400,
            f"{chosen} is not a chat completion. POST /api/chat only accepts "
            "rag_qa, translation, or cantonese_script.",
        )
    if chosen not in CHAT_FUNCTIONS:
        raise ChatError(
            400,
            f"Unknown function: {chosen}. Allowed chat functions: "
            "rag_qa, translation, cantonese_script.",
        )
    return chosen


def recorded_model(function_id: str, model_id: str) -> dict[str, object]:
    model = get_model(model_id)
    if model is None:
        raise ChatError(500, "The selected model is not in the catalog.")
    return {
        "function": function_id,
        "function_label": FUNCTION_LABELS[function_id],
        "model_id": model_id,
        "provider": model["provider"],
        "name": model["name"],
        "prices": list(model["prices"]),  # type: ignore[arg-type]
        "prices_recorded_on": PRICES_RECORDED_ON,
    }


def _assistant_text(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
    return None


def complete_chat(
    *,
    message: str,
    function_id: str,
    model_id: str,
    messages: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    api_key = load_openrouter_api_key()
    if not api_key:
        raise ChatError(503, MISSING_KEY_DETAIL)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_id,
        "messages": messages if messages is not None else [{"role": "user", "content": message}],
        "stream": False,
    }
    try:
        response = httpx.post(
            OPENROUTER_CHAT_URL,
            json=payload,
            headers=headers,
            timeout=OPENROUTER_CHAT_TIMEOUT_SECONDS,
            follow_redirects=False,
        )
        status_code = response.status_code
    except Exception:
        raise ChatError(502, "OpenRouter did not return a chat completion.") from None

    if status_code != 200:
        raise ChatError(502, "OpenRouter did not return a chat completion.")
    try:
        body = response.json()
    except Exception:
        raise ChatError(502, "OpenRouter did not return a chat completion.") from None
    text = _assistant_text(body)
    if text is None:
        raise ChatError(502, "OpenRouter did not return a chat completion.")
    result = recorded_model(function_id, model_id)
    result["reply"] = text
    return result
