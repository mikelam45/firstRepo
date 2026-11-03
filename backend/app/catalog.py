"""Curated model catalog and the prices shown in the selection UI.

Prices were fetched on 3 Nov 2026. Every figure below is a list price from
OpenRouter that day, not a live quote and not an estimate.

Sources:
- Text models and Gemini image token rates: https://openrouter.ai/api/v1/models
  and the model pages cited on each entry.
- FLUX.2 Pro: https://openrouter.ai/black-forest-labs/flux.2-pro and
  https://openrouter.ai/api/v1/images/models/black-forest-labs/flux.2-pro/endpoints
  (output_image, unit megapixel, cost_usd 0.03).
- Video models: https://openrouter.ai/api/v1/videos/models (pricing_skus)
  and the model pages cited on each entry.

Checked and intentionally omitted: anthropic/claude-3.5-sonnet (retired),
google/gemini-flash-tts, black-forest-labs/flux-1-pro, luma/ray-2, kling-1.5,
minimax/video-01, hailuo/minimax.

anthropic/claude-sonnet-5.5 was confirmed on the models API and on
https://openrouter.ai/anthropic/claude-sonnet-5.5 the same day.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

PriceStatus = Literal["confirmed", "estimate"]

PRICES_RECORDED_ON = "2026-11-03"
PRICE_SOURCE = (
    "OpenRouter model pages and the models, image, and video APIs, fetched 3 Nov 2026"
)
COST_NOTE = (
    "A single total is not shown. Text, images, and video use different units, "
    "so adding them would not mean anything. Text is USD per 1M tokens, images are "
    "USD per 1M image-output tokens or USD per megapixel, and video is USD per second. "
    "Each function below shows its own unit price."
)

# (id, label) in the order the UI presents them.
FUNCTIONS: tuple[tuple[str, str], ...] = (
    ("rag_qa", "RAG and document analysis"),
    ("translation", "Standard translation"),
    ("cantonese_script", "Cantonese script writing"),
    ("image_gen", "Image and storyboard"),
    ("video_gen", "Video generation"),
)

FUNCTION_IDS: tuple[str, ...] = tuple(function_id for function_id, _label in FUNCTIONS)
FUNCTION_LABELS: dict[str, str] = dict(FUNCTIONS)

TEXT_FUNCTIONS = ("rag_qa", "translation", "cantonese_script")

DEFAULT_SELECTION: dict[str, str] = {
    "rag_qa": "google/gemini-2.5-flash",
    "translation": "google/gemini-2.5-flash",
    "cantonese_script": "deepseek/deepseek-chat",
    "image_gen": "google/gemini-3.1-flash-image",
    "video_gen": "minimax/hailuo-2.3",
}


def _price(
    label: str,
    amount_usd: str,
    unit: str,
    detail: str = "",
    price_status: PriceStatus = "confirmed",
) -> dict[str, str]:
    return {
        "label": label,
        "amount_usd": amount_usd,
        "unit": unit,
        "price_status": price_status,
        "detail": detail,
    }


# compare_amount / compare_unit rank options that share a unit. Image options
# use different units, so the summary does not rank them against each other.
MODELS: tuple[dict[str, object], ...] = (
    {
        "id": "google/gemini-2.5-flash",
        "provider": "Google",
        "name": "Gemini 2.5 Flash",
        # https://openrouter.ai/google/gemini-2.5-flash — $0.30 / $2.50 per 1M
        # models API: prompt 0.0000003, completion 0.0000025 USD per token.
        "good_for": "Fast document reading and grounded answers.",
        "quality_cost": "Balanced",
        "functions": TEXT_FUNCTIONS,
        "compare_amount": "2.50",
        "compare_unit": "USD per 1M tokens",
        "prices": (
            _price("Input", "0.30", "USD per 1M tokens"),
            _price("Output", "2.50", "USD per 1M tokens"),
        ),
    },
    {
        "id": "deepseek/deepseek-chat",
        "provider": "DeepSeek",
        "name": "DeepSeek V3",
        # https://openrouter.ai/deepseek/deepseek-chat — $0.2574 / $1.029 per 1M.
        # models API: prompt 0.0000002574, completion 0.0000010287 USD per token
        # (the model page rounds the output rate to $1.029 per 1M).
        "good_for": "Chinese and Cantonese drafting at the lowest text rate here.",
        "quality_cost": "Lower cost",
        "functions": TEXT_FUNCTIONS,
        "compare_amount": "1.029",
        "compare_unit": "USD per 1M tokens",
        "prices": (
            _price("Input", "0.2574", "USD per 1M tokens"),
            _price("Output", "1.029", "USD per 1M tokens"),
        ),
    },
    {
        "id": "openai/gpt-4o",
        "provider": "OpenAI",
        "name": "GPT-4o",
        # https://openrouter.ai/openai/gpt-4o — $2.50 / $10 per 1M.
        # models API: prompt 0.0000025, completion 0.00001 USD per token.
        "good_for": "General writing and analysis when you want a familiar OpenAI model.",
        "quality_cost": "Higher quality",
        "functions": TEXT_FUNCTIONS,
        "compare_amount": "10",
        "compare_unit": "USD per 1M tokens",
        "prices": (
            _price("Input", "2.50", "USD per 1M tokens"),
            _price("Output", "10", "USD per 1M tokens"),
        ),
    },
    {
        "id": "anthropic/claude-sonnet-5.5",
        "provider": "Anthropic",
        "name": "Claude Sonnet 5.5",
        # https://openrouter.ai/anthropic/claude-sonnet-5.5 — $2 / $10 per 1M.
        # models API: prompt 0.000002, completion 0.00001 USD per token.
        # Live Sonnet id on 3 Nov 2026. Not claude-3.5-sonnet.
        "good_for": "Careful long-form writing and document work.",
        "quality_cost": "Higher quality",
        "functions": TEXT_FUNCTIONS,
        "compare_amount": "10",
        "compare_unit": "USD per 1M tokens",
        "prices": (
            _price("Input", "2", "USD per 1M tokens"),
            _price("Output", "10", "USD per 1M tokens"),
        ),
    },
    {
        "id": "google/gemini-3.1-flash-image",
        "provider": "Google",
        "name": "Gemini 3.1 Flash Image",
        # https://openrouter.ai/google/gemini-3.1-flash-image
        # $0.50/M input, $3/M text output, $60/M image-output tokens.
        # Image endpoints API (AI Studio and Vertex global): output_image
        # unit token, cost_usd 0.00006. One Vertex US endpoint lists 0.000066.
        "good_for": "Fast storyboard frames and image edits.",
        "quality_cost": "Balanced",
        "functions": ("image_gen",),
        "compare_amount": "60",
        "compare_unit": "USD per 1M image-output tokens",
        "prices": (
            _price("Input", "0.50", "USD per 1M tokens"),
            _price(
                "Output",
                "60",
                "USD per 1M image-output tokens",
                "Image tokens, not a flat fee per picture. Text output is a separate 3 USD per 1M tokens. One Google Vertex US endpoint lists 66 USD per 1M image-output tokens.",
            ),
        ),
    },
    {
        "id": "black-forest-labs/flux.2-pro",
        "provider": "Black Forest Labs",
        "name": "FLUX.2 Pro",
        # Model page: first output megapixel $0.03, each further megapixel $0.015,
        # reference-image input $0.015 per megapixel.
        # Endpoints API confirms output_image at 0.03 USD per megapixel.
        "good_for": "Production stills with tight prompt following.",
        "quality_cost": "Higher quality",
        "functions": ("image_gen",),
        "compare_amount": "0.03",
        "compare_unit": "USD per megapixel",
        "prices": (
            _price(
                "Output",
                "0.03",
                "USD per megapixel",
                "First megapixel of the generated image.",
            ),
            _price(
                "Further output",
                "0.015",
                "USD per megapixel",
                "Each megapixel after the first.",
            ),
            _price(
                "Reference image",
                "0.015",
                "USD per megapixel",
                "Reference images used for an edit.",
            ),
        ),
    },
    {
        "id": "minimax/hailuo-2.3",
        "provider": "MiniMax",
        "name": "Hailuo 2.3",
        # videos API pricing_skus.duration_seconds "0.0817".
        # https://openrouter.ai/minimax/hailuo-2.3 — $0.0817/second.
        "good_for": "Short 1080p clips with realistic motion.",
        "quality_cost": "Lower cost",
        "functions": ("video_gen",),
        "compare_amount": "0.0817",
        "compare_unit": "USD per second of video",
        "prices": (
            _price("Output", "0.0817", "USD per second of video"),
        ),
    },
    {
        "id": "minimax/hailuo-3",
        "provider": "MiniMax",
        "name": "Hailuo 3",
        # videos API pricing_skus: duration_seconds "0.13", reference_images "0.04".
        # https://openrouter.ai/minimax/hailuo-3 — $0.13/second, and $0.04/image
        # for reference images after the first five, which are free.
        "good_for": "Longer clips with native audio and tighter edits.",
        "quality_cost": "Higher quality",
        "functions": ("video_gen",),
        "compare_amount": "0.13",
        "compare_unit": "USD per second of video",
        "prices": (
            _price("Output", "0.13", "USD per second of video"),
            _price(
                "Reference image",
                "0.04",
                "USD per image",
                "The first 5 reference images are free.",
            ),
        ),
    },
    {
        "id": "kwaivgi/kling-v3.0-std",
        "provider": "Kuaishou",
        "name": "Kling v3.0 Standard",
        # videos API pricing_skus: duration_seconds "0.084",
        # duration_seconds_with_audio "0.126".
        # https://openrouter.ai/kwaivgi/kling-v3.0-std
        "good_for": "Clips of 3 to 15 seconds, with first and last frame control.",
        "quality_cost": "Balanced",
        "functions": ("video_gen",),
        "compare_amount": "0.084",
        "compare_unit": "USD per second of video",
        "prices": (
            _price(
                "Output",
                "0.084",
                "USD per second of video",
                "Without audio.",
            ),
            _price(
                "Output with audio",
                "0.126",
                "USD per second of video",
                "With native audio. The model page lists this as the from-price.",
            ),
        ),
    },
)

_BY_ID: dict[str, dict[str, object]] = {str(model["id"]): model for model in MODELS}


def get_model(model_id: str) -> dict[str, object] | None:
    return _BY_ID.get(model_id)


def models_for(function_id: str) -> list[dict[str, object]]:
    return [
        model
        for model in MODELS
        if function_id in model["functions"]  # type: ignore[operator]
    ]


def relative_note(function_id: str, model_id: str) -> str:
    options = models_for(function_id)
    units = {str(model["compare_unit"]) for model in options}
    if len(units) != 1:
        return (
            "The options for this function are not ranked, because their prices "
            "use different units."
        )
    amounts = [Decimal(str(model["compare_amount"])) for model in options]
    mine = Decimal(str(_BY_ID[model_id]["compare_amount"]))
    lowest, highest = min(amounts), max(amounts)
    if lowest == highest:
        return "Every option for this function has the same listed output rate."
    if mine == lowest:
        return "Lowest listed output rate for this function."
    if mine == highest:
        return "Highest listed output rate for this function."
    return "Between the other listed output rates for this function."


def _public_model(model: dict[str, object], function_id: str) -> dict[str, object]:
    return {
        "id": model["id"],
        "provider": model["provider"],
        "name": model["name"],
        "good_for": model["good_for"],
        "quality_cost": model["quality_cost"],
        "prices": list(model["prices"]),  # type: ignore[arg-type]
        "relative_note": relative_note(function_id, str(model["id"])),
    }


def _summary_row(function_id: str, model_id: str) -> dict[str, object]:
    model = _BY_ID[model_id]
    return {
        "function_id": function_id,
        "label": FUNCTION_LABELS[function_id],
        "model_id": model_id,
        "provider": model["provider"],
        "name": model["name"],
        "good_for": model["good_for"],
        "quality_cost": model["quality_cost"],
        "prices": list(model["prices"]),  # type: ignore[arg-type]
        "relative_note": relative_note(function_id, model_id),
    }


def public_state(selection: dict[str, str]) -> dict[str, object]:
    functions = []
    for function_id, label in FUNCTIONS:
        functions.append(
            {
                "id": function_id,
                "label": label,
                "selected_model_id": selection[function_id],
                "options": [_public_model(model, function_id) for model in models_for(function_id)],
            }
        )
    return {
        "prices_recorded_on": PRICES_RECORDED_ON,
        "price_source": PRICE_SOURCE,
        "cost_note": COST_NOTE,
        "functions": functions,
        "selection": {function_id: selection[function_id] for function_id in FUNCTION_IDS},
        "summary": [
            _summary_row(function_id, selection[function_id]) for function_id in FUNCTION_IDS
        ],
    }
