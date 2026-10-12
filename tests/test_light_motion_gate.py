import ast
from pathlib import Path
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).parents[1] / 'app'))
from services.light_controller import LightMotionGate, arm_light_off, light_off_due


def test_isolated_one_second_pulses_do_not_trigger():
    gate = LightMotionGate()
    for start in range(0, 3600, 300):
        for offset in (0, .5, 1.2):
            assert not gate.update(start+offset, True)
        assert not gate.update(start+1.3, False)
    assert gate.last_motion is None


def test_continuous_signal_triggers_at_two_seconds_without_extra_wait():
    gate = LightMotionGate()
    assert not gate.update(10, True)
    assert not gate.update(11.99, True)
    assert gate.update(12, True)
    assert gate.update(20, True)
    assert gate.last_motion == 20


def test_two_real_pulses_trigger_on_second_pulse():
    gate = LightMotionGate()
    assert not gate.update(0, True)
    assert not gate.update(.5, True)
    assert not gate.update(1.2, False)
    assert not gate.update(4, True)
    assert gate.update(4.5, True)
    assert gate.last_motion == 4.5


def test_one_signal_is_not_counted_twice_by_polling():
    gate = LightMotionGate()
    for step in range(20):
        assert not gate.update(step/10, True)
    assert len(gate.hits) == 1


def test_tiny_pulses_and_old_pulses_do_not_accumulate():
    gate = LightMotionGate()
    for t in range(4):
        assert not gate.update(t, True)
        assert not gate.update(t+.1, False)
    assert not gate.update(5, True)
    assert not gate.update(5.5, True)
    gate.update(6, False)
    assert not gate.update(20, True)
    assert not gate.update(20.5, True)


def test_sensor_error_cancels_candidate_and_stale_high():
    gate = LightMotionGate()
    gate.update(0, True)
    gate.update(.5, True)
    assert not gate.update(1, True, valid=False)
    assert not gate.update(2, True)
    assert not gate.update(2.5, True)
    assert gate.update(4, True)
    assert not gate.update(5, True, valid=False)
    assert gate.last_motion == 4


def test_clock_uses_display_light_controller_instead_of_legacy_light_timer():
    source = (Path(__file__).parents[1] / 'app/clock.py').read_text(encoding='utf-8')
    assert 'DisplayLightController(' in source
    assert 'LIGHT_OFF_TIMEOUT_SEC' not in source
    assert 'light_motion_active' not in source
