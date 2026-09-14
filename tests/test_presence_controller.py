import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / 'app'))
from services.presence_controller import PresenceController, CameraCheckWorker


def test_short_pir_pulse_does_not_extend_presence():
    p = PresenceController(0)
    p.update_pir(10, True)
    p.update_pir(10.3, False)
    assert p.last_motion == 0
    p.update_pir(20, True)
    p.update_pir(20.7, True)
    assert p.last_motion == 20.7
    p.update_pir(40, True)
    assert p.last_motion == 40


def test_motion_without_faces_expires_after_five_minutes():
    p = PresenceController(0)
    for t in (30, 90, 150):
        p.record_camera(t, {'ok': True, 'found_face': False})
    assert p.hold(299)
    assert not p.hold(300)


def test_stationary_face_keeps_display_on_for_hours():
    p = PresenceController(0)
    for t in range(30, 7200, 60):
        p.record_camera(t, {'ok': True, 'found_face': True})
        assert p.hold(t + 59)
    assert p.last_motion == 0  # Camera must not alter the room-light PIR timer.


def test_one_missed_face_does_not_turn_off_and_leaving_eventually_does():
    p = PresenceController(0)
    p.record_camera(30, {'ok': True, 'found_face': True})
    p.record_camera(90, {'ok': True, 'found_face': False})
    assert p.hold(630)
    for t in (650, 710):
        p.record_camera(t, {'ok': True, 'found_face': False})
    assert not p.hold(710)


def test_camera_failure_is_not_absence_but_cannot_hold_forever():
    p = PresenceController(0)
    for t in (30, 90, 150, 210, 270, 330, 390):
        p.record_camera(t, {'ok': False, 'error': 'timeout'})
    assert p.misses == 0
    assert p.hold(419)
    assert not p.hold(420)


def test_camera_only_checked_when_visible_and_idle():
    p = PresenceController(0)
    assert not p.check_due(29, 'ON')
    assert p.check_due(30, 'ON')
    assert not p.check_due(30, 'OFF')
    p.record_camera(30, {'ok': True, 'found_face': False})
    assert not p.check_due(89, 'ON')
    assert p.check_due(90, 'ON')
    p.touch(90)
    assert not p.check_due(91, 'ON')


def test_camera_worker_is_nonblocking_and_does_not_queue_duplicates():
    entered, release = threading.Event(), threading.Event()
    def recognize():
        entered.set()
        release.wait(2)
        return {'ok': True, 'found_face': True}
    worker = CameraCheckWorker(recognize)
    try:
        assert worker.request()
        assert entered.wait(1)
        assert worker.poll() is None
        assert not worker.request()
        future = worker.future
        release.set()
        future.result(timeout=1)
        assert worker.poll()['found_face']
        assert worker.poll() is None
    finally:
        release.set()
        worker.close()


def test_camera_exception_becomes_diagnostic_result():
    def fail():
        raise RuntimeError('camera unavailable')
    worker = CameraCheckWorker(fail)
    try:
        worker.request()
        try:
            worker.future.result(timeout=1)
        except RuntimeError:
            pass
        assert worker.poll() == {'ok': False, 'error': 'RuntimeError'}
    finally:
        worker.close()
