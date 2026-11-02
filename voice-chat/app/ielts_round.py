"""IELTS mean rounding. Speaking in v1 never calls this for an overall band."""

from __future__ import annotations

import math


def round_ielts_mean(bands: list[float] | tuple[float, float, float, float]) -> float:
    if len(bands) != 4:
        raise ValueError("round_ielts_mean needs four criterion bands")
    mean = (bands[0] + bands[1] + bands[2] + bands[3]) / 4
    whole = math.floor(mean + 1e-9)
    frac = mean - whole
    if frac < 0.25 - 1e-9:
        return float(whole)
    if frac < 0.75 - 1e-9:
        return whole + 0.5
    return float(whole + 1)
