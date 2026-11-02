"""Warp each coach's rest portrait into photographic expression frames.

Frames are derived from avatars/{id}.jpg + the face mesh, not a new identity.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1] / "app" / "static" / "avatars"
COACHES = ("amelia", "mei", "chloe", "celine")

BROW_L = (70, 63, 105, 66, 107)
BROW_R = (336, 296, 334, 293, 300)
INNER_LIP = (78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95)
LOWER_INNER = {324, 318, 402, 317, 14, 87, 178, 88, 95}
LOWER_OUTER = {146, 91, 181, 84, 17, 314, 405, 321, 375}
UPPER_LIP = {
    191, 80, 81, 82, 13, 312, 311, 310, 415, 185, 40, 39, 37, 0, 267, 269, 270, 409, 61, 291, 78, 308,
}
LIP = set(INNER_LIP) | LOWER_INNER | LOWER_OUTER | UPPER_LIP
LID_UPPER_L = (160, 159, 158, 157, 173)
LID_LOWER_L = (144, 145, 153, 154, 155)
LID_UPPER_R = (387, 386, 385, 384, 398)
LID_LOWER_R = (373, 374, 380, 381, 390)


def on_lower(index: int, y: float, seal: float) -> bool:
    if index in LOWER_INNER or index in LOWER_OUTER:
        return True
    if index in UPPER_LIP:
        return False
    return y > seal


def pose(rest: np.ndarray, face_count: int, kind: str) -> np.ndarray:
    pts = rest.copy()
    n = face_count
    mw = float(np.hypot(*(rest[61] - rest[291]))) or 0.14
    cx = float((rest[61][0] + rest[291][0]) / 2)
    cy = float((rest[13][1] + rest[14][1]) / 2)
    lip_top = float(rest[0][1])
    nose = float(min(rest[4][1], rest[1][1], rest[2][1]))
    lower_y = float(rest[17][1])
    open_amt = 0.0
    smile = 0.0
    brow = 0.0
    blink = 0.0
    wide = 0.0
    if kind == "mouth-open":
        open_amt = 0.4
        wide = 0.04
    elif kind == "smile":
        smile = 0.72
        open_amt = 0.08
        wide = 0.2
    elif kind == "eyes-semi":
        blink = 0.4
    elif kind == "brow":
        brow = 0.48
    up = mw * 0.2
    down = mw * 0.28
    u = open_amt * up
    d = open_amt * down
    for i in range(n):
        p = rest[i]
        dx = (p[0] - cx) / mw
        y = float(p[1])
        t = float(np.clip(1 - abs(dx) / 1.35, 0, 1))
        hx = t * t * (3 - 2 * t)
        lip = i in LIP
        dy = 0.0
        dx_px = 0.0
        if kind in {"mouth-open", "smile"} and (lip or kind == "smile"):
            if not on_lower(i, y, cy):
                fade = 1.0 if lip else float(np.clip((y - nose) / max(0.02, lip_top - nose), 0, 1))
                dy = -u * fade * hx
            elif y <= lower_y or lip:
                dy = d * hx
            side = 1.0 if dx >= 0 else -1.0
            corner = float(np.clip((abs(dx) - 0.2) / 0.45, 0, 1))
            dx_px = side * wide * mw * 0.05 * corner
            if kind == "smile":
                dy -= smile * mw * 0.055 * corner
                dx_px += side * smile * mw * 0.028 * corner
            if kind == "mouth-open" and not lip:
                dy *= 0.12
        pts[i][0] = p[0] + dx_px
        pts[i][1] = p[1] + dy
    if kind == "smile":
        for i in (50, 101, 205, 187, 280, 330, 425, 411):
            pts[i][1] -= smile * mw * 0.1
    if kind == "brow":
        lid_y = float(min(rest[159][1], rest[386][1]))
        for i in range(n):
            y = float(rest[i][1])
            if y >= lid_y - mw * 0.02:
                continue
            fall = max(
                0.0,
                1.0 - min(abs(rest[i][0] - rest[105][0]), abs(rest[i][0] - rest[334][0])) / (mw * 0.55),
            )
            if fall > 0:
                pts[i][1] -= brow * mw * 0.16 * fall
        for i in BROW_L + BROW_R:
            pts[i][1] = rest[i][1] - brow * mw * 0.22
    if kind == "eyes-semi":
        for upper, lower, iris in (
            (LID_UPPER_L, LID_LOWER_L, (468, 469, 470, 471, 472)),
            (LID_UPPER_R, LID_LOWER_R, (473, 474, 475, 476, 477)),
        ):
            gap = float(rest[lower[2]][1] - rest[upper[2]][1])
            eye_cx = float((rest[upper[2]][0] + rest[lower[2]][0]) / 2)
            eye_cy = float((rest[upper[2]][1] + rest[lower[2]][1]) / 2)
            for i in range(n):
                dist = float(np.hypot(rest[i][0] - eye_cx, rest[i][1] - eye_cy))
                fall = max(0.0, 1.0 - dist / (mw * 0.28))
                if fall <= 0:
                    continue
                if rest[i][1] <= eye_cy:
                    pts[i][1] += blink * gap * 0.55 * fall
                else:
                    pts[i][1] -= blink * gap * 0.18 * fall
            for idx in iris:
                if idx < len(pts):
                    pts[idx][1] += blink * gap * 0.2
    return pts


def paint_mouth_ellipse(frame: np.ndarray, posed: np.ndarray) -> np.ndarray:
    """Feathered inner-mouth cavity that covers triangle seams."""
    h, w = frame.shape[:2]
    cx = (posed[61][0] + posed[291][0]) / 2 * w
    cy = (posed[13][1] + posed[14][1]) / 2 * h
    mw = max(12.0, abs(posed[291][0] - posed[61][0]) * w)
    rx = mw * 0.28
    ry = max(6.0, mw * 0.09)
    overlay = frame.copy()
    center = (int(cx), int(cy))
    axes = (int(rx), int(ry))
    cv2.ellipse(overlay, center, axes, 0, 0, 360, (34, 16, 22), -1)
    t_center = (int(cx), int(cy - ry * 0.32))
    t_axes = (max(2, int(rx * 0.72)), max(1, int(ry * 0.22)))
    tooth = overlay.copy()
    cv2.ellipse(tooth, t_center, t_axes, 0, 0, 360, (236, 228, 218), -1)
    tmask = np.zeros((h, w), dtype=np.uint8)
    cv2.ellipse(tmask, t_center, t_axes, 0, 0, 360, 255, -1)
    tmask = cv2.GaussianBlur(tmask, (5, 5), 0)
    ta = (tmask.astype(np.float32) / 255.0 * 0.55)[..., None]
    overlay = (tooth.astype(np.float32) * ta + overlay.astype(np.float32) * (1 - ta)).astype(np.uint8)
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.ellipse(mask, center, axes, 0, 0, 360, 255, -1)
    k = max(11, int(max(rx, ry) * 1.1) | 1)
    if k % 2 == 0:
        k += 1
    mask = cv2.GaussianBlur(mask, (k, k), 0)
    blend = (mask.astype(np.float32) / 255.0 * 0.8)[..., None]
    return (overlay.astype(np.float32) * blend + frame.astype(np.float32) * (1 - blend)).astype(np.uint8)


def warp_image(img: np.ndarray, rest: np.ndarray, posed: np.ndarray, triangles: list, face_count: int) -> np.ndarray:
    h, w = img.shape[:2]
    acc = np.zeros((h, w, 3), dtype=np.float32)
    weight = np.zeros((h, w), dtype=np.float32)
    src_mask = np.zeros((h, w), dtype=np.uint8)
    dst_mask = np.zeros((h, w), dtype=np.uint8)
    for tri in triangles:
        if max(tri) >= face_count:
            continue
        src = np.float32([[rest[i][0] * w, rest[i][1] * h] for i in tri])
        dst = np.float32([[posed[i][0] * w, posed[i][1] * h] for i in tri])
        if cv2.contourArea(dst) < 1.0 or cv2.contourArea(src) < 1.0:
            continue
        box = cv2.boundingRect(np.vstack([src, dst]))
        x, y, bw, bh = box
        pad = 3
        x0 = max(0, x - pad)
        y0 = max(0, y - pad)
        x1 = min(w, x + bw + pad)
        y1 = min(h, y + bh + pad)
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        src_l = src - np.float32([x0, y0])
        dst_l = dst - np.float32([x0, y0])
        try:
            matrix = cv2.getAffineTransform(src_l, dst_l)
        except cv2.error:
            continue
        crop = img[y0:y1, x0:x1]
        warped = cv2.warpAffine(
            crop, matrix, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101
        )
        patch = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
        cv2.fillConvexPoly(patch, np.int32(dst_l), 255)
        src_patch = np.zeros_like(patch)
        cv2.fillConvexPoly(src_patch, np.int32(src_l), 255)
        sel = patch > 0
        acc[y0:y1, x0:x1][sel] += warped[sel]
        weight[y0:y1, x0:x1][sel] += 1
        dst_mask[y0:y1, x0:x1] = cv2.bitwise_or(dst_mask[y0:y1, x0:x1], patch)
        src_mask[y0:y1, x0:x1] = cv2.bitwise_or(src_mask[y0:y1, x0:x1], src_patch)
    out = img.copy()
    filled = weight > 0
    if filled.any():
        out[filled] = np.clip(acc[filled] / weight[filled][:, None], 0, 255).astype(np.uint8)
    hole = cv2.subtract(src_mask, dst_mask)
    if hole.any():
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        hole = cv2.dilate(hole, kernel)
        out = cv2.inpaint(out, hole, 5, cv2.INPAINT_TELEA)
    region = cv2.bitwise_or(src_mask, dst_mask)
    if region.any():
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        ring = cv2.subtract(cv2.dilate(region, kernel), cv2.erode(region, kernel))
        soft = cv2.GaussianBlur(ring, (9, 9), 0)
        alpha = (soft.astype(np.float32) / 255.0)[..., None]
        out = (out.astype(np.float32) * (1 - alpha) + img.astype(np.float32) * alpha).astype(np.uint8)
    return out


def main() -> None:
    kinds = ("mouth-open", "smile", "eyes-open", "eyes-semi", "brow")
    for coach in COACHES:
        photo = cv2.imread(str(ROOT / f"{coach}.jpg"), cv2.IMREAD_COLOR)
        mesh = json.loads((ROOT / f"{coach}.json").read_text())
        rest = np.array(mesh["points"], dtype=np.float64)
        face_count = int(mesh["faceCount"])
        triangles = mesh["triangles"]
        for kind in kinds:
            dest = ROOT / f"{coach}-{kind}.jpg"
            if kind == "eyes-open":
                dest.write_bytes((ROOT / f"{coach}.jpg").read_bytes())
                print("wrote", dest.name, "copy")
                continue
            elif kind == "mouth-open":
                frame = paint_mouth_ellipse(photo, rest)
            else:
                posed = pose(rest, face_count, kind)
                frame = warp_image(photo, rest, posed, triangles, face_count)
            cv2.imwrite(str(dest), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
            print("wrote", dest.name, frame.shape)


if __name__ == "__main__":
    main()
