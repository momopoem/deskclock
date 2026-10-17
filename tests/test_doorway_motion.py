import importlib.util
from pathlib import Path


SOURCE = Path(__file__).parents[1] / 'face' / 'doorway_motion.py'
SPEC = importlib.util.spec_from_file_location('doorway_motion', SOURCE)
doorway_motion = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(doorway_motion)


def test_doorway_region_defaults_to_selected_e2_to_e5():
    assert doorway_motion._floats('MISSING_DOORWAY_ROI', (4 / 8, 1 / 6, 5 / 8, 5 / 6)) == (
        0.5, 1 / 6, 0.625, 5 / 6,
    )


def test_doorway_env_region_is_parseable(monkeypatch):
    monkeypatch.setenv('TEST_DOORWAY_ROI', '0.5,0.1666667,0.625,0.8333333')
    assert doorway_motion._floats('TEST_DOORWAY_ROI', ()) == (0.5, 0.1666667, 0.625, 0.8333333)
