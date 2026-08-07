# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
import time
import gpiod

CHIP = "/dev/gpiochip0"
LINE_OFFSET = 17

print("SR501 test (libgpiod v2)")
print("Waiting for motion...  Ctrl+C to stop")

with gpiod.request_lines(
    CHIP,
    consumer="sr501-test",
    config={
        LINE_OFFSET: gpiod.LineSettings(
            direction=gpiod.line.Direction.INPUT
        )
    }
) as req:
    while True:
        val = req.get_value(LINE_OFFSET)
        print("DETECTED" if val else "no motion")
        time.sleep(0.5)

