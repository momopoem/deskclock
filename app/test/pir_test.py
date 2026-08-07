# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
import RPi.GPIO as GPIO
import time

GPIO.setmode(GPIO.BCM)
GPIO.setup(17, GPIO.IN)

print("PIR test start")
try:
    while True:
        print(GPIO.input(17))
        time.sleep(0.5)
except KeyboardInterrupt:
    GPIO.cleanup()

