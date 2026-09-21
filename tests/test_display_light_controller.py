import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "app"))

from services.display_light_controller import DisplayLightController, LightOnDelivery


def test_motion_starts_five_minute_display_and_light_session():
    c = DisplayLightController(0)
    d = c.motion(10)
    assert d.brightness == 1
    assert d.light_command == "ON"
    assert c.step(309).display_state == "ON"
    assert c.step(310).display_state == "FADING"


def test_authorized_hiroshi_face_extends_session_to_ten_minutes():
    c = DisplayLightController(0)
    c.motion(10)
    c.authorized_face(20)
    assert c.step(619).display_state == "ON"
    assert c.step(620).display_state == "FADING"


def test_motion_during_fade_restores_five_minute_timer_without_second_light_on():
    c = DisplayLightController(0)
    c.motion(0)
    assert c.step(315).brightness == 0.5
    d = c.motion(315)
    assert d.display_state == "ON"
    assert d.light_command is None
    assert c.step(614).display_state == "ON"


def test_after_thirty_second_fade_display_and_light_turn_off_together():
    c = DisplayLightController(0)
    c.motion(0)
    assert c.step(300).display_state == "FADING"
    d = c.step(330)
    assert d.display_state == "OFF"
    assert d.display_command == "OFF"
    assert d.light_command == "OFF"


def test_startup_does_not_send_an_unsolicited_light_off():
    c = DisplayLightController(0)
    assert c.step(330).light_command is None


def test_light_on_delivery_retries_then_confirms():
    d = LightOnDelivery(repeat_sec=3, max_attempts=3)
    assert d.start(0, 0) == "ON"
    assert d.step(2.9, confirmed=False) is None
    assert d.step(3, confirmed=False) == "ON"  # unconditional retransmission
    assert d.step(6, confirmed=False) == "ON"  # failed verification retry
    assert d.step(9, confirmed=True) is None
    assert not d.active


def test_light_on_delivery_stops_after_third_unconfirmed_attempt():
    d = LightOnDelivery(repeat_sec=3, max_attempts=3)
    d.start(0, 0)
    assert d.step(3, confirmed=False) == "ON"
    assert d.step(6, confirmed=False) == "ON"
    assert d.step(9, confirmed=False) is None
    assert not d.active
