#!/usr/bin/env python3
# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
import cv2
import os
import time

NAME = "hiroshi"
SAVE_DIR = os.path.expanduser(f"~/deskclock/face/dataset/{NAME}")
os.makedirs(SAVE_DIR, exist_ok=True)

HAAR = "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"
DEVICE_INDEX = 0
TARGET_COUNT = 30
FACE_SIZE = (200, 200)

cap = cv2.VideoCapture(DEVICE_INDEX)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

face_cascade = cv2.CascadeClassifier(HAAR)
if face_cascade.empty():
    raise SystemExit(f"Failed to load Haar cascade: {HAAR}")

count = 0
last_save = 0.0
start = time.time()

print("Headless register mode (no GUI).")
print("Look at the camera. Collecting faces...")
print(f"Saving to: {SAVE_DIR}")
print("Press Ctrl+C to stop.")

try:
    while count < TARGET_COUNT:
        ret, frame = cap.read()
        if not ret:
            print("Camera read failed")
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5)

        if len(faces) > 0:
            x, y, w, h = sorted(faces, key=lambda r: r[2]*r[3], reverse=True)[0]
            face_img = gray[y:y+h, x:x+w]
            face_img = cv2.resize(face_img, FACE_SIZE)

            now = time.time()
            if now - last_save > 0.25:  # 連写抑制
                path = os.path.join(SAVE_DIR, f"{count:03d}.jpg")
                cv2.imwrite(path, face_img)
                count += 1
                last_save = now
                print(f"Saved {count}/{TARGET_COUNT}")

        # 顔が見つからないと永久に終わらないのを防ぐ（60秒で終了）
        if time.time() - start > 60 and count < 10:
            print("Timeout: too few faces detected. Check lighting/position.")
            break

        time.sleep(0.03)

finally:
    cap.release()

print("Done.")
