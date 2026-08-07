#!/usr/bin/env python3
# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
import time

PIR_GPIOCHIP = "/dev/gpiochip0"
PIR_LINE = 17            # BCM番号
POLL_SEC = 0.05          # 50ms

def main():
    import gpiod

    print("SR501 diag (libgpiod v2)")
    print(f"chip={PIR_GPIOCHIP}, line={PIR_LINE}")
    print("NOTE: SR501 needs warm-up ~30-60s after power-on.")
    print("Ctrl+C to stop\n")

    # libgpiod v2: request_lines() + get_value()
    req = gpiod.request_lines(
        PIR_GPIOCHIP,
        consumer="sr501-diag",
        config={
            PIR_LINE: gpiod.LineSettings(direction=gpiod.LineDirection.INPUT)
        },
    )

    last = None
    try:
        while True:
            v = req.get_value(PIR_LINE)  # 0/1
            if last is None or v != last:
                stamp = time.strftime("%F %T")
                print(f"{stamp} value={v}" + (" (CHANGE)" if last is not None else ""))
                last = v
            time.sleep(POLL_SEC)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            req.release()
        except Exception:
            pass

if __name__ == "__main__":
    main()

