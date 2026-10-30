"""OpenRouter route table. Empty-key turns never call these ids."""

from __future__ import annotations

ROUTES = {
    "roleplay": {
        "model": "deepseek/deepseek-v4-flash",
        "fallback": "google/gemini-2.5-flash-lite",
    },
    "yue": {
        "model": "qwen/qwen3.7-flash",
        "fallback": "qwen/qwen3.8-flash",
    },
    "review": {
        "model": "anthropic/claude-haiku-5.5",
        "fallback": "deepseek/deepseek-v4-flash",
    },
}


def route_for_turn(target: str, support: str) -> str:
    if target == "yue" or support == "yue":
        return "yue"
    return "roleplay"


def route_for_review(support: str) -> str:
    if support == "yue":
        return "yue"
    return "review"
