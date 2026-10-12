"""Single source of truth for display presence and room-light control."""
from dataclasses import dataclass


@dataclass(frozen=True)
class DisplayLightDecision:
    display_state: str
    brightness: float
    display_command: str | None = None
    light_command: str | None = None


class DisplayLightController:
    """PIR starts a five-minute session; an authorized face extends it to ten.

    The room light is commanded only when a display session wakes or finishes.
    """
    def __init__(self, now: float, *, motion_sec: float = 300.0,
                 authorized_face_sec: float = 600.0, fade_sec: float = 30.0):
        self.motion_sec = float(motion_sec)
        self.authorized_face_sec = float(authorized_face_sec)
        self.fade_sec = float(fade_sec)
        self.state = "ON"
        self.deadline = float(now) + self.motion_sec
        self.fade_started = None
        self.light_on = False

    def motion(self, now: float) -> DisplayLightDecision:
        was_off = self.state == "OFF"
        self.state = "ON"
        self.deadline = float(now) + self.motion_sec
        self.fade_started = None
        display_command = "ON" if was_off else None
        light_command = "ON" if not self.light_on else None
        self.light_on = True
        return DisplayLightDecision("ON", 1.0, display_command, light_command)

    def authorized_face(self, now: float) -> None:
        if self.state != "OFF":
            self.deadline = float(now) + self.authorized_face_sec
            self.fade_started = None
            self.state = "ON"

    def step(self, now: float) -> DisplayLightDecision:
        now = float(now)
        if self.state == "OFF":
            return DisplayLightDecision("OFF", 0.0)
        if self.fade_started is None and now >= self.deadline:
            self.state = "FADING"
            # Use the scheduled deadline, not the polling instant, so a slow
            # frame cannot silently extend the requested 30-second fade.
            self.fade_started = self.deadline
        if self.state == "FADING":
            progress = (now - self.fade_started) / self.fade_sec
            if progress >= 1.0:
                self.state = "OFF"
                light_command = "OFF" if self.light_on else None
                self.light_on = False
                return DisplayLightDecision("OFF", 0.0, "OFF", light_command)
            return DisplayLightDecision("FADING", max(0.0, 1.0 - progress))
        return DisplayLightDecision("ON", 1.0)


class LightOnDelivery:
    """Restore the proven ON delivery sequence without owning light policy.

    A display session starts this helper.  It sends an immediate command, an
    unconditional retry after three seconds, then verifies BH1750 illumination
    and performs at most one additional retry.
    """
    def __init__(self, *, repeat_sec: float = 3.0, max_attempts: int = 3):
        self.repeat_sec = float(repeat_sec)
        self.max_attempts = int(max_attempts)
        self.active = False
        self.attempts = 0
        self.next_action = 0.0
        self.phase = ""
        self.baseline_lux = None

    def start(self, now: float, baseline_lux: float | None) -> str:
        self.active = True
        self.attempts = 1
        self.baseline_lux = baseline_lux
        self.phase = "repeat"
        self.next_action = float(now) + self.repeat_sec
        return "ON"

    def cancel(self) -> None:
        self.active = False
        self.phase = ""

    def step(self, now: float, *, confirmed: bool) -> str | None:
        if not self.active or float(now) < self.next_action:
            return None
        if self.phase == "repeat":
            self.attempts += 1
            self.phase = "verify"
            self.next_action = float(now) + self.repeat_sec
            return "ON"
        if confirmed:
            self.cancel()
            return None
        if self.attempts < self.max_attempts:
            self.attempts += 1
            self.phase = "verify"
            self.next_action = float(now) + self.repeat_sec
            return "ON"
        self.cancel()
        return None
