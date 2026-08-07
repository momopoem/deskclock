#!/usr/bin/env python3
# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
import cv2, os, json, time

HAAR = "/usr/share/opencv4/haarcascades/haarcascade_frontalface_alt2.xml"
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

for _ in range(10):
    cap.read()
    time.sleep(0.03)

ret, frame = cap.read()
cap.release()

out = {"ok": True, "ret": bool(ret), "faces": 0, "rects": []}
if not ret or frame is None:
    out.update({"ok": False, "error": "camera_read_failed"})
    print(json.dumps(out)); raise SystemExit(1)

cv2.imwrite(os.path.expanduser("~/deskclock/face/debug_frame.jpg"), frame)

gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
gray = cv2.equalizeHist(gray)
cv2.imwrite(os.path.expanduser("~/deskclock/face/debug_gray.jpg"), gray)

cc = cv2.CascadeClassifier(HAAR)
faces = cc.detectMultiScale(gray, 1.05, 2, minSize=(40,40))
out["faces"] = int(len(faces))
out["rects"] = [[int(x),int(y),int(w),int(h)] for (x,y,w,h) in faces]
print(json.dumps(out))
