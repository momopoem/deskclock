# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
from __future__ import annotations

import time

from config import *

def fetch_pir_loop(shared, stop_event):
    """Poll SR501 PIR via gpioget CLI (robust across gpiod variants).
    Updates:
      - pir_value (0/1 current)
      - pir_mono (last motion time)
    """
    if not PIR_ENABLE:
        return

    import subprocess, time, os

    chip = PIR_GPIOCHIP
    if isinstance(chip, str) and chip.startswith("/dev/"):
        chip = os.path.basename(chip)

    def read_cli():
        out = subprocess.check_output(
            ["gpioget", "-c", str(chip), str(PIR_LINE)],
            text=True,
            timeout=0.8,
            stderr=subprocess.STDOUT,
        ).strip()
        if "inactive" in out:
            return 0
        if "active" in out:
            return 1
        for ch in out:
            if ch in "01":
                return int(ch)
        raise ValueError(out)

    while not stop_event.is_set():
        try:
            v = int(read_cli())
            shared["pir_value"] = v
            if v == 1:
                nowm = time.monotonic()
                shared["pir_mono"] = nowm
                shared["activity_mono"] = nowm
            shared["pir_err"] = ""
        except Exception as e:
            shared["pir_err"] = f"PIR(gpioget): {e}"
        stop_event.wait(0.2)
