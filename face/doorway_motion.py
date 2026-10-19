"""Bounded doorway-motion sample for DeskSideClock presence confirmation.

The script examines the user-calibrated E2:E5 region and a surrounding entry
corridor. It does not save frames or perform recognition. A candidate must
change in at least two of three vertical bands in two consecutive frame pairs;
all-frame exposure changes are rejected rather than treated as a person
entering.
"""
from __future__ import annotations

import json
import os
import time


def _floats(name, default):
    raw = os.environ.get(name)
    return tuple(float(v) for v in raw.split(",")) if raw else default


def _int(name, default):
    return int(os.environ.get(name, default))


def _float(name, default):
    return float(os.environ.get(name, default))


def changed_bands(mask, cv2):
    height = mask.shape[0]
    return sum(cv2.countNonZero(mask[(height * i) // 3:(height * (i + 1)) // 3]) > 0
               for i in range(3))


def is_motion(pairs, *, min_ratio, max_ratio, min_bands, min_qualified_pairs):
    """Return the accepted pairs and whether enough evidence supports a wake."""
    qualified = [p for p in pairs if (
        min_ratio <= p["ratio"] <= max_ratio and p["bands"] >= min_bands
    )]
    return len(qualified) >= min_qualified_pairs, qualified


def _bounds(frame, region):
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = region
    left, top, right, bottom = round(w * x0), round(h * y0), round(w * x1), round(h * y1)
    if not (0 <= left < right <= w and 0 <= top < bottom <= h):
        return None
    return left, top, right, bottom


def main():
    import cv2

    doorway_roi = _floats("DESKCLOCK_DOORWAY_ROI", (0.5, 1 / 6, 5 / 8, 5 / 6))
    corridor_roi = _floats("DESKCLOCK_DOORWAY_CORRIDOR_ROI", (3 / 8, 1 / 8, 6 / 8, 7 / 8))
    frames = _int("DESKCLOCK_DOORWAY_FRAMES", 8)
    interval = _float("DESKCLOCK_DOORWAY_FRAME_INTERVAL_SEC", 0.2)
    pixel_threshold = _int("DESKCLOCK_DOORWAY_PIXEL_THRESHOLD", 20)
    min_ratio = _float("DESKCLOCK_DOORWAY_MIN_CHANGED_RATIO", 0.015)
    corridor_min_ratio = _float("DESKCLOCK_DOORWAY_CORRIDOR_MIN_CHANGED_RATIO", 0.003)
    max_ratio = _float("DESKCLOCK_DOORWAY_MAX_CHANGED_RATIO", 0.45)
    min_bands = _int("DESKCLOCK_DOORWAY_MIN_ACTIVE_BANDS", 2)
    min_qualified_pairs = _int("DESKCLOCK_DOORWAY_MIN_QUALIFIED_PAIRS", 2)
    capture = cv2.VideoCapture(0)
    try:
        if not capture.isOpened():
            return {"ok": False, "error": "camera_open_failed"}
        regions = {
            "doorway": {"roi": doorway_roi, "min_ratio": min_ratio, "pairs": [], "previous": None},
            "corridor": {"roi": corridor_roi, "min_ratio": corridor_min_ratio, "pairs": [], "previous": None},
        }
        bounds = None
        for index in range(frames):
            ok, frame = capture.read()
            if not ok or frame is None or frame.size == 0:
                return {"ok": False, "error": "camera_read_failed"}
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            for name, region in regions.items():
                region_bounds = _bounds(frame, region["roi"])
                if region_bounds is None:
                    return {"ok": False, "error": f"invalid_{name}_roi"}
                if bounds is None:
                    bounds = {}
                bounds[name] = region_bounds
                left, top, right, bottom = region_bounds
                current = cv2.GaussianBlur(gray[top:bottom, left:right], (5, 5), 0)
                previous = region["previous"]
                if previous is not None:
                    _, mask = cv2.threshold(cv2.absdiff(previous, current), pixel_threshold, 255, cv2.THRESH_BINARY)
                    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
                    ratio = cv2.countNonZero(mask) / mask.size
                    region["pairs"].append({"ratio": round(ratio, 4), "bands": changed_bands(mask, cv2)})
                region["previous"] = current
            if index + 1 < frames:
                time.sleep(interval)
        results = {}
        for name, region in regions.items():
            motion, qualified = is_motion(
                region["pairs"], min_ratio=region["min_ratio"], max_ratio=max_ratio,
                min_bands=min_bands, min_qualified_pairs=min_qualified_pairs,
            )
            results[name] = {
                "motion": motion, "pairs": region["pairs"],
                "qualified_pairs": len(qualified), "min_ratio": region["min_ratio"],
                "roi": list(bounds[name]),
            }
        accepted_regions = [name for name, result in results.items() if result["motion"]]
        doorway = results["doorway"]
        return {
            "ok": True, "motion": bool(accepted_regions), "pairs": doorway["pairs"],
            "qualified_pairs": doorway["qualified_pairs"], "min_qualified_pairs": min_qualified_pairs,
            "pixel_threshold": pixel_threshold, "min_ratio": min_ratio,
            "min_bands": min_bands, "roi": doorway["roi"],
            "accepted_regions": accepted_regions, "regions": results,
        }
    finally:
        capture.release()


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False), flush=True)
