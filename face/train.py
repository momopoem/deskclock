#!/usr/bin/env python3
# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
import cv2
import os
import numpy as np

PRIVATE_DIR = os.path.expanduser(
    os.environ.get("DESKCLOCK_FACE_DATA_DIR", "~/.local/share/deskclock/face")
)
DATASET_DIR = os.path.join(PRIVATE_DIR, "dataset")
MODEL_PATH = os.path.join(PRIVATE_DIR, "models", "lbph.xml")

LABELS = {"hiroshi": 0}
FACE_SIZE = (200, 200)

faces = []
labels = []

for name, label in LABELS.items():
    person_dir = os.path.join(DATASET_DIR, name)
    if not os.path.isdir(person_dir):
        raise SystemExit(f"Missing dataset dir: {person_dir}")

    for fn in sorted(os.listdir(person_dir)):
        if not fn.lower().endswith(".jpg"):
            continue
        path = os.path.join(person_dir, fn)
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        if img.shape != FACE_SIZE:
            img = cv2.resize(img, FACE_SIZE)
        faces.append(img)
        labels.append(label)

if len(faces) < 10:
    raise SystemExit(f"Too few images: {len(faces)} (need >=10)")

model = cv2.face.LBPHFaceRecognizer_create()
model.train(faces, np.array(labels, dtype=np.int32))
os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
model.save(MODEL_PATH)

print("Trained:", MODEL_PATH)
print("Images:", len(faces))

