"""Regression tests for rejecting non-face Haar false positives before LBPH."""
import ast
import hashlib
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "face" / "recognize_once.py"
SHELF_IMAGE = ROOT / "tests" / "fixtures" / "shelf_false_positive.jpg"


def validation_functions():
    names = {"rect_iou", "filter_faces", "validated_faces"}
    nodes = [node for node in ast.parse(SOURCE.read_text(encoding="utf-8")).body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    env = {
        "MIN_W": 80, "MIN_H": 80, "MIN_AREA": 8000,
        "DETECT_MIN_NEIGHBORS": 5, "MIN_CASCADE_AGREEMENT": 2,
        "MIN_FACE_IOU": 0.35,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "face-validation", "exec"), env)
    return env


class Roi:
    size = 1


class Gray:
    def __getitem__(self, _key):
        return Roi()


class Cascade:
    def __init__(self, results):
        self.results = results

    def detectMultiScale(self, *_args, **_kwargs):
        return self.results


def test_single_cascade_false_positive_is_rejected_before_lbph():
    env = validation_functions()
    # The reported shelf candidate was 94x94, so size filtering alone cannot
    # protect it.  A single Haar response must never reach LBPH.
    faces, _raw = env["validated_faces"](
        Gray(), [("alt2", Cascade([(16, 328, 94, 94)]))],
    )
    assert faces == []


def test_agreed_face_can_reach_lbph():
    env = validation_functions()
    faces, _raw = env["validated_faces"](
        Gray(), [("alt2", Cascade([(100, 100, 100, 100)])),
                 ("default", Cascade([(103, 102, 98, 98)]))],
    )
    assert faces == [(100, 100, 100, 100, 10000, 2),
                     (103, 102, 98, 98, 9604, 2)]


def test_shelf_false_positive_fixture_is_the_reviewed_debug_crop():
    """Keep the exact reviewed shelf crop as a durable regression fixture."""
    assert SHELF_IMAGE.is_file()
    assert hashlib.sha256(SHELF_IMAGE.read_bytes()).hexdigest() == (
        "ca05de0f3a3fba2851b026079663969e813cb6d00c105aad2a027258f7d663cd"
    )


def test_shelf_fixture_does_not_pass_real_haar_consensus_validation():
    cv2 = pytest.importorskip("cv2")
    env = validation_functions()
    gray = cv2.imread(str(SHELF_IMAGE), cv2.IMREAD_GRAYSCALE)
    assert gray is not None
    gray = cv2.equalizeHist(gray)
    haar_dir = Path(cv2.data.haarcascades)
    face_cascades = [
        ("alt2", cv2.CascadeClassifier(str(haar_dir / "haarcascade_frontalface_alt2.xml"))),
        ("default", cv2.CascadeClassifier(str(haar_dir / "haarcascade_frontalface_default.xml"))),
    ]
    assert all(not cascade.empty() for _, cascade in face_cascades)
    assert env["validated_faces"](gray, face_cascades)[0] == []
