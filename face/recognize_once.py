#!/usr/bin/env python3
# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
import cv2
import os
import sys
import json
import time
import math

PRIVATE_DIR = os.path.expanduser(
    os.environ.get("DESKCLOCK_FACE_DATA_DIR", "~/.local/share/deskclock/face")
)
MODEL_PATH = os.path.join(PRIVATE_DIR, "models", "lbph.xml")

HAAR_LIST = [
    "/usr/share/opencv4/haarcascades/haarcascade_frontalface_alt2.xml",
    "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
]

THRESHOLD = 75
RETRY_GRAY_MAX = 80

DEVICE = "/dev/video0"
FACE_SIZE = (200, 200)

# read が重い前提：最大数枚だけ見る（省エネ）
TRY_FRAMES = 4
MAX_SECONDS = 10.0

# 誤検出フィルタ（小さすぎるのは捨てる）
MIN_W = 80
MIN_H = 80
MIN_AREA = 8000

# ★重要：切り出しを「縮める」。0.18 = 矩形の左右上下を18%ずつ内側へ
INSET = 0.18

DEBUG_DIR = PRIVATE_DIR
DEBUG_FRAME = os.path.join(DEBUG_DIR, "debug_frame.jpg")
DEBUG_GRAY  = os.path.join(DEBUG_DIR, "debug_gray.jpg")
DEBUG_FACE  = os.path.join(DEBUG_DIR, "debug_face.jpg")


def load_cascades():
    out = []
    for p in HAAR_LIST:
        cc = cv2.CascadeClassifier(p)
        if not cc.empty():
            out.append((p, cc))
    return out


def filter_faces(faces):
    out = []
    for (x, y, w, h) in faces:
        x, y, w, h = int(x), int(y), int(w), int(h)
        area = w * h
        if w < MIN_W or h < MIN_H:
            continue
        if area < MIN_AREA:
            continue
        out.append((x, y, w, h, area))
    return out


def crop_face_tight(gray, rect):
    """rect=(x,y,w,h) -> タイトに切って正方形化して返す"""
    x, y, w, h = rect
    H, W = gray.shape[:2]

    # インセット（内側へ縮める）
    ix = int(w * INSET)
    iy = int(h * INSET)

    x0 = max(0, x + ix)
    y0 = max(0, y + iy)
    x1 = min(W, x + w - ix)
    y1 = min(H, y + h - iy)

    # インセットしすぎて逆転したら元の矩形を使う
    if x1 <= x0 or y1 <= y0:
        x0, y0, x1, y1 = x, y, min(W, x+w), min(H, y+h)

    roi = gray[y0:y1, x0:x1]

    # 正方形化（中央トリム）
    rh, rw = roi.shape[:2]
    side = min(rh, rw)
    cy = rh // 2
    cx = rw // 2
    y0s = max(0, cy - side // 2)
    x0s = max(0, cx - side // 2)
    roi_sq = roi[y0s:y0s+side, x0s:x0s+side]

    roi_sq = cv2.resize(roi_sq, FACE_SIZE)
    return roi_sq, [x0, y0, x1 - x0, y1 - y0]


def open_camera():
    gst = (
        f"v4l2src device={DEVICE} ! "
        "video/x-raw, width=640, height=480, framerate=30/1 ! "
        "videoconvert ! "
        "appsink drop=true max-buffers=1 sync=false"
    )
    cap = cv2.VideoCapture(gst, cv2.CAP_GSTREAMER)
    if cap.isOpened():
        return cap, "gstreamer"
    cap.release()

    cap = cv2.VideoCapture(0)
    if cap.isOpened():
        return cap, "auto"
    cap.release()
    return None, "failed"


def recognize_once(model, cascades):
    cap, backend = open_camera()
    if cap is None:
        return {"error": "camera_open_failed"}

    start = time.monotonic()
    frames_tried = 0

    os.makedirs(DEBUG_DIR, exist_ok=True)

    best = None
    # best = dict(conf, label, rect_tight, rect_raw, haar_path, frame, gray, face_img, ...)

    last_frame = None
    last_gray = None

    while frames_tried < TRY_FRAMES and (time.monotonic() - start) < MAX_SECONDS:
        ret, frame = cap.read()
        frames_tried += 1
        if not ret or frame is None:
            continue

        last_frame = frame.copy()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        last_gray = gray.copy()

        for haar_path, cc in cascades:
            faces = cc.detectMultiScale(
                gray,
                scaleFactor=1.05,
                minNeighbors=2,
                minSize=(40, 40)
            )
            raw_n = int(len(faces))
            cand = filter_faces(faces)
            if not cand:
                continue

            # ★候補ごとにLBPHのconfidenceを出して一番小さいものを採用
            for (x, y, w, h, area) in cand:
                face_img, rect_tight = crop_face_tight(gray, (x, y, w, h))
                label, conf = model.predict(face_img)

                item = {
                    "label": int(label),
                    "confidence": float(conf),
                    "area": int(area),
                    "rect_raw": [x, y, w, h],
                    "rect_tight": rect_tight,
                    "haar_path": haar_path,
                    "faces_raw": raw_n,
                    "faces_after_filter": len(cand),
                    "frame": frame.copy(),
                    "gray": gray.copy(),
                    "face_img": face_img,
                }
                if (best is None) or (item["confidence"] < best["confidence"]):
                    best = item

        time.sleep(0.02)

    cap.release()

    # デバッグ（最後のフレームは必ず残す）
    if last_frame is not None:
        cv2.imwrite(DEBUG_FRAME, last_frame)
    if last_gray is not None:
        cv2.imwrite(DEBUG_GRAY, last_gray)

    if best is None:
        return {
            "ok": True,
            "found_face": False,
            "frames_tried": frames_tried,
            "seconds": round(time.monotonic() - start, 3),
            "backend": backend,
            "haar_tried": [p for p, _ in cascades],
            "filter": {"min_w": MIN_W, "min_h": MIN_H, "min_area": MIN_AREA},
            "inset": INSET,
            "debug_frame": DEBUG_FRAME,
            "debug_gray": DEBUG_GRAY,
        }

    # ベストのデバッグ保存
    cv2.imwrite(DEBUG_FRAME, best["frame"])
    cv2.imwrite(DEBUG_GRAY, best["gray"])
    cv2.imwrite(DEBUG_FACE, best["face_img"])

    is_hiroshi = (best["label"] == 0 and best["confidence"] < THRESHOLD)

    return {
        "ok": True,
        "found_face": True,
        "label": best["label"],
        "confidence": best["confidence"],
        "is_hiroshi": bool(is_hiroshi),
        "threshold": THRESHOLD,
        "rect": best["rect_tight"],      # タイト矩形（インセット後）
        "rect_raw": best["rect_raw"],    # 元の検出矩形
        "area": best["area"],
        "haar": best["haar_path"],
        "frames_tried": frames_tried,
        "seconds": round(time.monotonic() - start, 3),
        "backend": backend,
        "faces_raw": best["faces_raw"],
        "faces_after_filter": best["faces_after_filter"],
        "filter": {"min_w": MIN_W, "min_h": MIN_H, "min_area": MIN_AREA},
        "inset": INSET,
        "debug_face": DEBUG_FACE
    }


# ---- main ----
if not os.path.exists(MODEL_PATH):
    print(json.dumps({"ok": False, "error": "model_missing", "model": MODEL_PATH}))
    sys.exit(2)

cascades = load_cascades()
if not cascades:
    print(json.dumps({"ok": False, "error": "haar_load_failed", "haar_list": HAAR_LIST}))
    sys.exit(4)

model = cv2.face.LBPHFaceRecognizer_create()
model.read(MODEL_PATH)

r = recognize_once(model, cascades)

# 灰色ゾーン救済（75〜80ならもう一回だけ）
if r.get("ok") and r.get("found_face") and (not r.get("is_hiroshi")):
    if r.get("label") == 0 and (THRESHOLD <= r.get("confidence", 1e9) < RETRY_GRAY_MAX):
        time.sleep(0.25)
        r2 = recognize_once(model, cascades)
        # 2回目がより良い（confidenceが小さい）なら採用
        if r2.get("ok") and r2.get("found_face"):
            if r2.get("confidence", 1e9) < r.get("confidence", 1e9):
                r = r2

print(json.dumps(r, ensure_ascii=False))
sys.exit(0)
