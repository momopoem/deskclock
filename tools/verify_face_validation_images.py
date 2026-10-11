#!/usr/bin/env python3
"""Run the pre-LBPH face gate against saved images without opening a camera."""
import argparse
import ast
import json
from pathlib import Path

import cv2


def load_validation_functions(recognizer):
    source = Path(recognizer).read_text(encoding="utf-8")
    wanted = {"rect_iou", "filter_faces", "has_eye_pair", "validated_faces"}
    nodes = [node for node in ast.parse(source).body if
             (isinstance(node, ast.Assign) and any(
                 isinstance(target, ast.Name) and target.id in {
                     "MIN_W", "MIN_H", "MIN_AREA", "DETECT_MIN_NEIGHBORS",
                     "MIN_CASCADE_AGREEMENT", "MIN_FACE_IOU"} for target in node.targets)) or
             (isinstance(node, ast.FunctionDef) and node.name in wanted)]
    env = {"cv2": cv2}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), recognizer, "exec"), env)
    return env["validated_faces"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--recognizer", default="face/recognize_once.py")
    parser.add_argument("--diagnose", action="store_true")
    args = parser.parse_args()
    gray = cv2.imread(str(args.image), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise SystemExit(f"cannot read: {args.image}")
    haar_dir = Path(cv2.data.haarcascades)
    make = lambda name: cv2.CascadeClassifier(str(haar_dir / name))
    faces = [("alt2", make("haarcascade_frontalface_alt2.xml")),
             ("default", make("haarcascade_frontalface_default.xml"))]
    if any(cascade.empty() for _, cascade in faces):
        raise SystemExit("required Haar cascade unavailable")
    gray = cv2.equalizeHist(gray)
    approved, raw = load_validation_functions(args.recognizer)(gray, faces)
    result = {"image": str(args.image), "raw_detections": raw,
              "approved_faces": approved, "found_face": bool(approved)}
    if args.diagnose:
        result["face_detections"] = {
            name: [[int(value) for value in rect] for rect in cascade.detectMultiScale(
                gray, scaleFactor=1.05, minNeighbors=5, minSize=(40, 40))]
            for name, cascade in faces
        }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
