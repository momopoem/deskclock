"""Bounded doorway-motion sample for DeskSideClock presence confirmation.

The script examines only the user-calibrated E2:E5 region. It does not save
frames or perform recognition. A candidate must change in at least two of
three vertical bands in every consecutive frame pair; all-frame exposure
changes are rejected rather than treated as a person entering the room.
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


def main():
    import cv2

    x0, y0, x1, y1 = _floats("DESKCLOCK_DOORWAY_ROI", (0.5, 1 / 6, 5 / 8, 5 / 6))
    frames = _int("DESKCLOCK_DOORWAY_FRAMES", 4)
    interval = _float("DESKCLOCK_DOORWAY_FRAME_INTERVAL_SEC", 0.15)
    min_ratio = _float("DESKCLOCK_DOORWAY_MIN_CHANGED_RATIO", 0.015)
    max_ratio = _float("DESKCLOCK_DOORWAY_MAX_CHANGED_RATIO", 0.45)
    min_bands = _int("DESKCLOCK_DOORWAY_MIN_ACTIVE_BANDS", 2)
    capture = cv2.VideoCapture(0)
    try:
        if not capture.isOpened():
            return {"ok": False, "error": "camera_open_failed"}
        previous = None
        pairs = []
        for index in range(frames):
            ok, frame = capture.read()
            if not ok or frame is None or frame.size == 0:
                return {"ok": False, "error": "camera_read_failed"}
            h, w = frame.shape[:2]
            left, top, right, bottom = round(w * x0), round(h * y0), round(w * x1), round(h * y1)
            if not (0 <= left < right <= w and 0 <= top < bottom <= h):
                return {"ok": False, "error": "invalid_roi"}
            roi = frame[top:bottom, left:right]
            current = cv2.GaussianBlur(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), (5, 5), 0)
            if previous is not None:
                _, mask = cv2.threshold(cv2.absdiff(previous, current), 25, 255, cv2.THRESH_BINARY)
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
                ratio = cv2.countNonZero(mask) / mask.size
                pairs.append({"ratio": round(ratio, 4), "bands": changed_bands(mask, cv2)})
            previous = current
            if index + 1 < frames:
                time.sleep(interval)
        qualified = [p for p in pairs if min_ratio <= p["ratio"] <= max_ratio and p["bands"] >= min_bands]
        return {"ok": True, "motion": len(qualified) == len(pairs), "pairs": pairs,
                "roi": [left, top, right, bottom]}
    finally:
        capture.release()


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False), flush=True)
