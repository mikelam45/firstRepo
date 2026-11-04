"""Call OpenRouter chat completions for text functions only.

Image and video functions are rejected here. They never go to
``/api/v1/chat/completions``. Prices in the reply come from the recorded
catalog, not a live quote. The OpenRouter key, request body, and raw
provider payload stay out of return values and logs. A short
``error.message`` and the HTTP status may be shown to the user.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from .catalog import FUNCTION_LABELS, PRICES_RECORDED_ON, TEXT_FUNCTIONS, get_model
from .openrouter_key import MAC_KEY_PATH, load_openrouter_api_key
from .rag import (
    ALLOWED_GROUNDING,
    ALLOWED_SOURCE_LANGUAGES,
    ALLOWED_TARGET_LANGUAGES,
    DEFAULT_SOURCE_LANGUAGE,
    FORMAT_REPLY_INSTRUCTION,
    GROUNDING_MIXED,
)

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_CHAT_TIMEOUT_SECONDS = 20.0
CHAT_FUNCTIONS = TEXT_FUNCTIONS
GENERIC_COMPLETION_ERROR = "OpenRouter did not return a chat completion."
MAX_PROVIDER_ERROR_CHARS = 400
REGION_SETUP_HINT = (
    "This model is not available in your region. Open Setup and choose another text model."
)
MISSING_KEY_DETAIL = (
    "OpenRouter is not configured. The Mac file "
    f"{MAC_KEY_PATH} is missing. The page still loads."
)
_KEY_PATTERN = re.compile(r"sk-or-[A-Za-z0-9_-]+")
_BEARER_PATTERN = re.compile(r"(?i)bearer\s+\S+")


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
            + ", ".join(CHAT_FUNCTIONS)
            + ".",
        )
    if chosen not in CHAT_FUNCTIONS:
        raise ChatError(
            400,
            f"Unknown function: {chosen}. Allowed chat functions: "
            + ", ".join(CHAT_FUNCTIONS)
            + ".",
        )
    return chosen


def format_reply_messages(message: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": FORMAT_REPLY_INSTRUCTION},
        {"role": "user", "content": message},
    ]


def resolve_grounding(value: str | None) -> str:
    if value is None:
        return GROUNDING_MIXED
    chosen = value.strip() if isinstance(value, str) else ""
    if chosen not in ALLOWED_GROUNDING:
        raise ChatError(400, "grounding must be 'strict' or 'mixed'.")
    return chosen


def resolve_target_language(function_id: str, value: str | None) -> str | None:
    if function_id == "dse_math":
        from .dse import resolve_dse_language

        return resolve_dse_language(value)
    if function_id != "translation":
        return None
    chosen = value.strip() if isinstance(value, str) else ""
    if not chosen:
        raise ChatError(400, "target_language is required for translation.")
    if chosen not in ALLOWED_TARGET_LANGUAGES:
        raise ChatError(
            400,
            "target_language must be 'en', 'zh_cn', or 'zh_hk'.",
        )
    return chosen


def resolve_source_language(function_id: str, value: str | None) -> str | None:
    if function_id != "translation":
        return None
    if value is None:
        return DEFAULT_SOURCE_LANGUAGE
    chosen = value.strip() if isinstance(value, str) else ""
    if not chosen:
        return DEFAULT_SOURCE_LANGUAGE
    if chosen not in ALLOWED_SOURCE_LANGUAGES:
        raise ChatError(
            400,
            "source_language must be 'auto', 'en', 'zh_cn', or 'zh_hk'.",
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


def _sanitize_provider_message(text: str, api_key: str | None = None) -> str:
    cleaned = " ".join(text.split())
    if api_key:
        cleaned = cleaned.replace(api_key, "[redacted]")
    cleaned = _KEY_PATTERN.sub("[redacted]", cleaned)
    cleaned = _BEARER_PATTERN.sub("Bearer [redacted]", cleaned)
    if len(cleaned) > MAX_PROVIDER_ERROR_CHARS:
        cleaned = cleaned[:MAX_PROVIDER_ERROR_CHARS].rstrip() + "…"
    return cleaned


def _provider_error_message(payload: Any, api_key: str | None = None) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    message: str | None = None
    if isinstance(error, str) and error.strip():
        message = error
    elif isinstance(error, dict):
        raw = error.get("message")
        if isinstance(raw, str) and raw.strip():
            message = raw
    if message is None:
        return None
    return _sanitize_provider_message(message, api_key)


def _text_from_content(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str) and item:
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text:
                    parts.append(text)
        joined = "".join(parts)
        if joined.strip():
            return joined
    return None


def _first_choice(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    return first if isinstance(first, dict) else None


def _assistant_text(payload: Any) -> str | None:
    first = _first_choice(payload)
    if first is None:
        return None
    message = first.get("message")
    if isinstance(message, dict):
        text = _text_from_content(message.get("content"))
        if text:
            return text
        text = _text_from_content(message.get("reasoning"))
        if text:
            return text
        text = _text_from_content(message.get("reasoning_content"))
        if text:
            return text
    text = _text_from_content(first.get("text"))
    if text:
        return text
    return None


def _is_region_block(status_code: int | None, message: str | None) -> bool:
    if status_code != 403 or not message:
        return False
    lowered = message.lower()
    return "region" in lowered or "not available in your" in lowered


def _with_region_hint(detail: str, status_code: int | None, message: str | None) -> str:
    if _is_region_block(status_code, message):
        return f"{detail} {REGION_SETUP_HINT}"
    return detail


def _openrouter_failure(
    *,
    status_code: int | None,
    payload: Any,
    model_id: str,
    api_key: str | None = None,
) -> ChatError:
    provider = _provider_error_message(payload, api_key)
    if provider and status_code is not None:
        return ChatError(
            502,
            _with_region_hint(
                f"OpenRouter returned HTTP {status_code}: {provider}",
                status_code,
                provider,
            ),
        )
    if provider:
        return ChatError(502, _with_region_hint(f"OpenRouter error: {provider}", status_code, provider))
    if status_code == 200 and _first_choice(payload) is not None:
        return ChatError(502, f"empty reply from {model_id}")
    if status_code is not None and status_code != 200:
        return ChatError(502, f"OpenRouter returned HTTP {status_code} without a chat completion.")
    return ChatError(502, GENERIC_COMPLETION_ERROR)


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
        raise ChatError(502, GENERIC_COMPLETION_ERROR) from None

    body: Any = None
    try:
        body = response.json()
    except Exception:
        body = None

    if status_code != 200:
        raise _openrouter_failure(
            status_code=status_code,
            payload=body,
            model_id=model_id,
            api_key=api_key,
        )
    if body is None:
        raise ChatError(502, GENERIC_COMPLETION_ERROR)

    provider = _provider_error_message(body, api_key)
    if provider:
        raise ChatError(502, f"OpenRouter returned HTTP {status_code}: {provider}")

    text = _assistant_text(body)
    if text is None:
        raise _openrouter_failure(
            status_code=status_code,
            payload=body,
            model_id=model_id,
            api_key=api_key,
        )
    result = recorded_model(function_id, model_id)
    result["reply"] = text
    return result
