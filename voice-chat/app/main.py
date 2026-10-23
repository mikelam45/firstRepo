"""LingoCoach local server. Default port is 8066."""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, Header, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.coach import public_settings, take_turn
from app.ielts_prompts import FOOD, PART3, SKILL
from app.ielts_review import review
from app.partners import PARTNERS
from app.scenarios import SCENARIOS

app = FastAPI(title="LingoCoach")
STATIC = Path(__file__).resolve().parent / "static"
_HITS: dict[str, deque] = defaultdict(deque)


def _limited(client_id: str, limit: int, window: int) -> bool:
    now = time.monotonic()
    bucket = _HITS[client_id]
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    if len(bucket) >= limit:
        return True
    bucket.append(now)
    return False


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/bootstrap")
def bootstrap():
    return {
        "partners": PARTNERS,
        "scenarios": [
            {
                "id": row["id"],
                "title": row["title"],
                "goal": row["goal"],
                "locale": row["locale"],
            }
            for row in SCENARIOS
        ],
        "ielts": {"part1": FOOD, "part2": SKILL, "part3": PART3},
        "key_loaded": bool((os.environ.get("OPENROUTER_API_KEY") or "").strip()),
    }


@app.post("/api/turn")
async def api_turn(request: Request, x_client_id: str | None = Header(default=None)):
    try:
        raw = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    if not isinstance(raw, dict):
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    history = raw.get("history") or []
    if not isinstance(history, list) or len(history) > 12:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    for item in history:
        text = (item or {}).get("text") or ""
        if len(text) > 500:
            return JSONResponse({"error": "invalid_request"}, status_code=400)
    client = x_client_id or "anonymous"
    if _limited(f"turn:{client}", 30, 600):
        return JSONResponse({"error": "slow_down"}, status_code=429, headers={"Retry-After": "30"})
    body = {
        "session_id": raw.get("session_id") or "",
        "scenario_id": raw.get("scenario_id") or "hk-cha-chaan-teng",
        "partner_id": raw.get("partner_id") or "amelia",
        "settings": public_settings(raw.get("settings") or {}),
        "history": history,
        "fired_signals": raw.get("fired_signals") or [],
    }
    try:
        payload = await take_turn(body)
    except Exception:
        return JSONResponse({"error": "coach_unavailable"}, status_code=502)
    return payload


@app.post("/api/ielts/review")
async def api_review(request: Request, x_client_id: str | None = Header(default=None)):
    try:
        raw = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    text = (raw.get("learner_text") or "") if isinstance(raw, dict) else ""
    if not isinstance(raw, dict) or len(text) > 4000:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    client = x_client_id or "anonymous"
    if _limited(f"review:{client}", 40, 1800):
        return JSONResponse({"error": "slow_down"}, status_code=429, headers={"Retry-After": "30"})
    try:
        return review(raw)
    except Exception:
        return JSONResponse({"error": "coach_unavailable"}, status_code=502)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
