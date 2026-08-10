# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Optional

from config import (
    BRIGHTNESS_GAMMA,
    BH1750_DARK_LX,
    BH1750_DIM_TO_LIGHTOFF,
    BH1750_ENABLE,
    BH1750_FADE_SEC,
    BH1750_LIGHT_ON_LX,
    BH1750_STALE_SEC,
    BH1750_WAKE_LX,
    DISPLAY_PM_ENABLE,
    PIR_DIM_TO,
    PIR_ENABLE,
    PIR_FADE_SEC,
    PIR_NO_MOTION_SEC,
    PIR_WAKE_OVERRIDE_SEC,
)
from utils.common import _log_brt_event


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x

def _apply_brightness(color, brightness: float):
    """Multiply RGB by brightness (0..1) with perceptual gamma correction."""
    b = _clamp01(brightness)
    # Gamma-correct so perceived fade is closer to linear.
    try:
        gamma = float(BRIGHTNESS_GAMMA)
    except Exception:
        gamma = 1.0
    if gamma > 0.0 and abs(gamma - 1.0) > 1e-6:
        b = b ** gamma
    r, g, bb = color
    return (int(r * b), int(g * b), int(bb * b))

def compute_desired_brightness(now_mono: float, shared: dict) -> float:
    """Compute target brightness from SR501(PIR) + BH1750(lux) spec (0..1).

    Spec summary:
      - SR501 is always monitored. Any detection (HIGH) wakes to 100%.
      - If no motion for PIR_NO_MOTION_SEC (default 3min), dim to PIR_DIM_TO (20%).
      - BH1750 is always monitored.
          * 0..BH1750_DARK_LX (default 0..2 lx): treat as lights-off => dim to BH1750_DIM_TO_LIGHTOFF (20%),
            and if also no motion for 3min => turn OFF (0%).
          * >= BH1750_LIGHT_ON_LX (default >=5 lx): treat as light/day => do not dim by lux; dim only by PIR timer.
          * Crossing into >= BH1750_WAKE_LX (default >=10 lx): treat as a
            "wake event" => 100% immediately. A steady bright reading must not
            keep resetting the inactivity timer.
      - Fade down is handled outside (PIR_FADE_SEC/BH1750_FADE_SEC ~10s).
    """
    # 0) Immediate wake by recent activity (touch/key/motion/lux wake)
    activity_mono = shared.get("activity_mono", None)
    if isinstance(activity_mono, (int, float)) and ((now_mono - float(activity_mono)) <= PIR_WAKE_OVERRIDE_SEC):
        return 1.0

    # 1) Read PIR (last motion time)
    pir_mono = shared.get("pir_mono", None)
    pir_recent = False
    no_motion = False
    if PIR_ENABLE and isinstance(pir_mono, (int, float)):
        pir_recent = (now_mono - float(pir_mono)) <= PIR_WAKE_OVERRIDE_SEC
        no_motion = (now_mono - float(pir_mono)) >= PIR_NO_MOTION_SEC

    # Any motion detection => wake to 100% (even if it's dark)
    if pir_recent:
        return 1.0

    # 2) Read Lux (BH1750)
    lux = shared.get("lux", None)
    lux_mono = shared.get("lux_mono", None)
    bh_stale = globals().get("BH1750_STALE_SEC", 10.0)
    lux_ok = BH1750_ENABLE and isinstance(lux, (int, float)) and isinstance(lux_mono, (int, float)) and ((now_mono - float(lux_mono)) <= bh_stale)

    # Maintain a simple hysteresis state to avoid flicker around thresholds
    lux_state = shared.get("_lux_state", "light")  # "dark" or "light"
    lx = None
    if lux_ok:
        lx = float(lux)

        # Lux wake is edge-triggered. A level-triggered check here would update
        # activity_mono on every frame while the room light is on, preventing
        # the PIR no-motion timeout from ever dimming the screen.
        lux_wake_high = bool(shared.get("_lux_wake_high", False))
        if lx >= BH1750_WAKE_LX and not lux_wake_high:
            shared["activity_mono"] = now_mono
            shared["_lux_wake_high"] = True
            shared["_lux_state"] = "light"
            return 1.0
        if lx <= BH1750_LIGHT_ON_LX:
            shared["_lux_wake_high"] = False

        if lx <= BH1750_DARK_LX:
            lux_state = "dark"
        elif lx >= BH1750_LIGHT_ON_LX:
            lux_state = "light"
        # 2..5 lx: keep previous lux_state (hysteresis)
        shared["_lux_state"] = lux_state

    # 3) Decide target by combined rules
    if lux_state == "dark":
        # Dark room: dim to 20%; if also no motion for 3min => OFF (0%)
        if no_motion:
            return 0.0
        return BH1750_DIM_TO_LIGHTOFF  # 20%
    else:
        # Light/day: dim only by PIR timer
        if no_motion:
            return PIR_DIM_TO  # 20%
        return 1.0


# -----------------------------------------------------------------------------
# Brightness Controller (v2 skeleton)
#   - Fully compatible with v1.1.2 brightness behavior (compute_desired_brightness + fade logic)
#   - Owns brightness_cur/brightness_target and fade state (fade_start_mono/val)
# -----------------------------------------------------------------------------

@dataclass
class BrightnessState:
    """Brightness state snapshot."""
    brightness_cur: float = 1.0
    brightness_target: float = 1.0
    fade_start_mono: float | None = None
    fade_start_val: float = 1.0


@dataclass(frozen=True)
class BrightnessDecision:
    """Decision returned by BrightnessController.update().

    This mirrors the DisplayPowerDecision style so logs can be unified.
    """
    prev_cur: float
    prev_target: float
    prev_fade_start_mono: float | None
    prev_fade_start_val: float

    state: BrightnessState               # updated snapshot
    desired: float                       # desired brightness (0..1) after DIM forcing

    reason: str = ""                     # e.g. snap_up / start_fade / fading / fade_done / hold / dim_forced
    disp_state: str = ""                 # ON/DIM/OFF (context)


class BrightnessController:
    """Brightness controller: computes desired brightness and applies v1-compatible transitions.

    Behavior (must match v1.1.2/v1.2.x):
      - compute_desired_brightness() returns the desired brightness (0..1) based on PIR/BH1750 rules.
      - If Display PM is in DIM, desired is forced to 0.0 (burn-in prevention).
      - Brighten-up is immediate (jump).
      - Fade-down is linear over fade_sec = max(PIR_FADE_SEC, BH1750_FADE_SEC).
      - Target changes restart the fade from the current value.

    v2 additions:
      - Returns BrightnessDecision (prev/next + reason)
      - Optional on_transition hook, called when state changes materially.
    """

    def __init__(self) -> None:
        self.state = BrightnessState()
        self._on_transition: Optional[Callable[..., None]] = self._default_on_transition

    def set_on_transition(self, cb: Optional[Callable[..., None]]) -> None:
        """Set a transition hook.

        Hook signature: cb(decision, **context)
        Pass None to disable.
        """
        self._on_transition = cb

    def _default_on_transition(self, decision: "BrightnessDecision", **ctx) -> None:
        try:
            prev_cur = decision.prev_cur
            prev_tgt = decision.prev_target
            cur = decision.state.brightness_cur
            tgt = decision.state.brightness_target
            disp = decision.disp_state or ctx.get('disp_state', '')
            reason = decision.reason or '-'
            parts = [f"{disp} bcur:{prev_cur:.4f}->{cur:.4f}", f"btgt:{prev_tgt:.4f}->{tgt:.4f}", f"desired={decision.desired:.4f}", f"reason={reason}"]
            if ctx.get('lux') is not None:
                try:
                    parts.append(f"lux={float(ctx.get('lux')):.2f}")
                except Exception:
                    pass
            _log_brt_event(' '.join(parts))
        except Exception:
            pass

    @property
    def brightness_cur(self) -> float:
        return float(self.state.brightness_cur)

    @property
    def brightness_target(self) -> float:
        return float(self.state.brightness_target)

    def update(
        self,
        *,
        now_mono: float,
        shared: dict,
        disp_state: str,
        lux: float | None = None,
    ) -> BrightnessDecision:
        """Update brightness state and return a Decision."""
        prev = replace(self.state)
        prev_cur = float(prev.brightness_cur)
        prev_tgt = float(prev.brightness_target)
        prev_fsm = prev.fade_start_mono
        prev_fsv = float(prev.fade_start_val)

        desired_raw = compute_desired_brightness(now_mono, shared)
        desired = float(desired_raw)
        reason = "hold"

        # DIM forces desired to 0.0 (v1 behavior)
        if DISPLAY_PM_ENABLE and disp_state == "DIM":
            if desired != 0.0:
                reason = "dim_forced"
            desired = 0.0

        bcur = float(self.state.brightness_cur)
        btgt = float(self.state.brightness_target)

        # Immediate brighten (motion detected / light ON)
        if desired > bcur + 1e-6:
            bcur = desired
            btgt = desired
            self.state.fade_start_mono = None
            self.state.fade_start_val = bcur
            reason = "snap_up"

        # Fade down (no motion / light OFF / dark)
        elif desired < bcur - 1e-6:
            # Start or restart fade if target changes
            if (btgt != desired) or (self.state.fade_start_mono is None):
                btgt = desired
                self.state.fade_start_mono = float(now_mono)
                self.state.fade_start_val = bcur
                reason = "start_fade"
            else:
                reason = "fading"

            fade_sec = max(PIR_FADE_SEC, BH1750_FADE_SEC)
            t = (float(now_mono) - float(self.state.fade_start_mono)) / max(0.001, float(fade_sec))
            if t >= 1.0:
                bcur = btgt
                self.state.fade_start_mono = None
                reason = "fade_done"
            else:
                bcur = float(self.state.fade_start_val) + (btgt - float(self.state.fade_start_val)) * float(t)

        # Commit
        self.state.brightness_cur = float(bcur)
        self.state.brightness_target = float(btgt)

        decision = BrightnessDecision(
            prev_cur=prev_cur,
            prev_target=prev_tgt,
            prev_fade_start_mono=prev_fsm,
            prev_fade_start_val=prev_fsv,
            state=replace(self.state),
            desired=float(desired),
            reason=reason,
            disp_state=str(disp_state),
        )

        # Fire hook when something changed materially
        changed = (
            abs(decision.prev_cur - decision.state.brightness_cur) > 1e-6
            or abs(decision.prev_target - decision.state.brightness_target) > 1e-6
            or decision.prev_fade_start_mono != decision.state.fade_start_mono
            or reason != "hold"
        )
        if changed and self._on_transition is not None:
            try:
                self._on_transition(decision, disp_state=disp_state, lux=lux)
            except Exception:
                pass

        return decision

    def snapshot(self) -> BrightnessState:
        return replace(self.state)
