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
    # Raw PIR only becomes a timer refresh after the caller selects the
    # already-active-session policy.
    assert p.last_motion == 0
    p.accept_active_pir(20.7)
    assert p.last_motion == 20.7
    p.update_pir(40, True)
    assert p.last_motion == 20.7


def test_camera_failure_or_no_face_does_not_retract_an_active_pir_session():
    p = PresenceController(100)
    p.update_pir(200, True)
    assert p.update_pir(200.7, True)
    p.accept_active_pir(200.7)
    p.record_camera(201, {'ok': False, 'error': 'camera_open_failed'})
    p.record_camera(202, {'ok': True, 'found_face': False})
    assert p.last_motion == 200.7


def test_pir_candidate_does_not_wake_until_doorway_motion_confirms():
    p = PresenceController(0)
    p.update_pir(10, True)
    assert p.update_pir(10.7, True)
    assert not p.confirm_wake_motion(11, {'doorway_detail': {'ok': True, 'motion': False}})
    assert p.last_motion == 0
    assert p.confirm_wake_motion(12, {'doorway_detail': {'ok': True, 'motion': True}})
    assert p.last_motion == 12


def test_camera_error_rejects_off_state_wake_candidate():
    p = PresenceController(0)
    assert not p.confirm_wake_motion(10, {'doorway_detail': {'ok': False, 'error': 'camera_open_failed'}})
    assert p.last_motion == 0


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
    def recognize(purpose):
        assert purpose == 'idle'
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
        result = worker.poll()
        assert result['found_face']
        assert result['_purpose'] == 'idle'
        assert worker.poll() is None
    finally:
        release.set()
        worker.close()


def test_requeued_camera_check_runs_after_current_check_finishes():
    calls = []
    entered, release = threading.Event(), threading.Event()
    def recognize(purpose):
        assert purpose in {'idle', 'pir_recognition'}
        calls.append(1)
        entered.set()
        release.wait(2)
        return {'ok': True, 'found_face': True, 'is_authorized_user': True}
    worker = CameraCheckWorker(recognize)
    try:
        assert worker.request()
        assert entered.wait(1)
        assert not worker.request(requeue=True)
        release.set()
        worker.future.result(timeout=1)
        assert worker.poll()['is_authorized_user']
        worker.future.result(timeout=1)
        assert worker.poll()['is_authorized_user']
        assert len(calls) == 2
    finally:
        release.set()
        worker.close()


def test_camera_worker_passes_pir_recognition_purpose_to_checker():
    purposes = []
    def recognize(purpose):
        purposes.append(purpose)
        return {'ok': True, 'motion': True}
    worker = CameraCheckWorker(recognize)
    try:
        assert worker.request(purpose='pir_recognition')
        worker.future.result(timeout=1)
        assert worker.poll()['_purpose'] == 'pir_recognition'
        assert purposes == ['pir_recognition']
    finally:
        worker.close()


def test_camera_exception_becomes_diagnostic_result():
    def fail(purpose):
        assert purpose == 'idle'
        raise RuntimeError('camera unavailable')
    worker = CameraCheckWorker(fail)
    try:
        worker.request()
        try:
            worker.future.result(timeout=1)
        except RuntimeError:
            pass
        result = worker.poll()
        assert result == {'ok': False, 'error': 'RuntimeError', '_purpose': 'idle'}
    finally:
        worker.close()
