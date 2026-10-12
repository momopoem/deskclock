"""Display-only occupancy policy; raw PIR/light control remains independent."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass


@dataclass(frozen=True)
class PresenceSettings:
    pir_confirm_sec: float = 0.6
    motion_hold_sec: float = 300.0
    face_hold_sec: float = 600.0
    check_idle_sec: float = 30.0
    check_interval_sec: float = 60.0
    misses_required: int = 3
    failure_grace_sec: float = 120.0


class PresenceController:
    def __init__(self, now, settings=None, log=lambda message: None):
        self.settings = settings or PresenceSettings()
        self.log = log
        self.last_motion = now
        self.last_face = None
        self.high_since = None
        self.previous_raw = None
        self.edge_time = now
        self.accepted = False
        self.misses = 0
        self.next_check = now + self.settings.check_idle_sec
        self.holding = True

    def update_pir(self, now, high):
        high = bool(high)
        if high != self.previous_raw:
            self.log(f'pir={int(high)} previous_duration_sec={now-self.edge_time:.2f}')
            self.previous_raw = high
            self.edge_time = now
        if not high:
            self.high_since = None
            self.accepted = False
            return False
        if self.high_since is None:
            self.high_since = now
        if now - self.high_since >= self.settings.pir_confirm_sec:
            if not self.accepted:
                self.log('motion=accepted')
                self.misses = 0
                newly_accepted = True
            else:
                newly_accepted = False
            self.accepted = True
            self.last_motion = now
            return newly_accepted
        return False

    def touch(self, now):
        self.last_motion = now
        self.misses = 0

    def record_camera(self, now, result):
        self.next_check = now + self.settings.check_interval_sec
        if result.get('ok') and result.get('found_face') is True:
            self.last_face = now
            self.misses = 0
            self.log('camera=face_found')
        elif result.get('ok') and result.get('found_face') is False:
            self.misses += 1
            self.log(f'camera=no_face misses={self.misses}')
        else:
            # An unavailable camera is not evidence that the room is empty.
            # Nevertheless, the bounded grace prevents indefinite screen-on.
            self.log(f'camera=error error={result.get("error", "invalid_result")}')
        return bool(result.get('ok') and result.get('found_face')
                    and result.get('is_authorized_user'))

    def check_due(self, now, display_state):
        return (display_state != 'OFF' and now >= self.next_check
                and now - self.last_motion >= self.settings.check_idle_sec)

    def hold(self, now):
        deadline = self.last_motion + self.settings.motion_hold_sec
        if self.last_face is not None:
            deadline = max(deadline, self.last_face + self.settings.face_hold_sec)
        # Require multiple misses, but camera errors must not hold forever.
        if self.misses < self.settings.misses_required:
            deadline += self.settings.failure_grace_sec
        holding = now < deadline
        if holding != self.holding:
            self.holding = holding
            self.log(f'display_hold={int(holding)} misses={self.misses}')
        return holding


class CameraCheckWorker:
    """One camera user at a time, without blocking the renderer."""
    def __init__(self, recognize):
        self.recognize = recognize
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='presence-camera')
        self.future = None
        self.recheck_requested = False

    def request(self, *, requeue: bool = False):
        if self.future is not None:
            # A new PIR session must receive its own recognition result.  Keep
            # one follow-up request rather than silently discarding it.
            self.recheck_requested = self.recheck_requested or requeue
            return False
        self.future = self.executor.submit(self.recognize)
        return True

    def poll(self):
        if self.future is None or not self.future.done():
            return None
        future, self.future = self.future, None
        try:
            result = future.result()
            result = result if isinstance(result, dict) else {'ok': False, 'error': 'invalid_result'}
        except Exception as exc:
            result = {'ok': False, 'error': type(exc).__name__}
        if self.recheck_requested:
            self.recheck_requested = False
            self.request()
        return result

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
