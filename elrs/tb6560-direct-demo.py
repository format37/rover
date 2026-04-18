#!/usr/bin/env python3
"""
TB6560 dual-stepper demo: front / back / left / right, 1 second each.

Hardware (per elrs/docs/TB6560_ROVER_TECH_SPEC.md):
    GPIO18 → TB6560 #1 CLK+  (STEP left)   via NPN level shifter to 5V
    GPIO12 → TB6560 #2 CLK+  (STEP right)  via NPN level shifter to 5V
    GPIO23 → TB6560 #1 CW+   (DIR  left)   via NPN level shifter to 5V
    GPIO24 → TB6560 #2 CW+   (DIR  right)  via NPN level shifter to 5V
    EN+ pins tied to GND (always enabled) or unused.
    Common GND between RPi, both TB6560s, and 5V rail.

Requires: pigpiod running (`sudo systemctl start pigpiod`).
"""

import time
import pigpio

# --- Pin assignment ---
STEP_LEFT  = 18   # hardware PWM0
STEP_RIGHT = 12   # hardware PWM1
DIR_LEFT   = 23
DIR_RIGHT  = 24

# --- Motion parameters ---
STEP_FREQ    = 4000   # Hz — ~150 RPM @ 1/8 microstep (well under 8kHz limit)
DUTY_CYCLE   = 500000 # pigpio scale: 500000 = 50%
MOVE_SECONDS = 1.0

# NPN transistor level shifter inverts DIR (see tech spec §Critical Issue).
# If wired through a single NPN per DIR line, set to True; with a direct 5V
# buffer (or two-transistor non-inverting shifter) set to False.
DIR_INVERTED = True

# Convention: forward = physical track motion that propels rover forward.
# Because the two motors are mounted mirror-image on left/right tracks, the
# "forward" DIR level is opposite on the two sides. Flip these if the demo
# moves backward on your build.
FORWARD_LEFT  = 1
FORWARD_RIGHT = 0


def apply_dir(level: int) -> int:
    return 1 - level if DIR_INVERTED else level


def set_motor(pi, step_pin: int, dir_pin: int, dir_level: int, freq: int):
    pi.write(dir_pin, apply_dir(dir_level))
    pi.hardware_PWM(step_pin, freq, DUTY_CYCLE if freq > 0 else 0)


def stop(pi):
    pi.hardware_PWM(STEP_LEFT, 0, 0)
    pi.hardware_PWM(STEP_RIGHT, 0, 0)


def drive(pi, left_dir: int, right_dir: int, seconds: float = MOVE_SECONDS):
    set_motor(pi, STEP_LEFT,  DIR_LEFT,  left_dir,  STEP_FREQ)
    set_motor(pi, STEP_RIGHT, DIR_RIGHT, right_dir, STEP_FREQ)
    time.sleep(seconds)
    stop(pi)


def main():
    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("pigpiod not running — start it with: sudo systemctl start pigpiod")

    for pin in (STEP_LEFT, STEP_RIGHT, DIR_LEFT, DIR_RIGHT):
        pi.set_mode(pin, pigpio.OUTPUT)

    try:
        print("FRONT"); drive(pi, FORWARD_LEFT,      FORWARD_RIGHT)
        time.sleep(0.3)
        print("BACK");  drive(pi, 1 - FORWARD_LEFT,  1 - FORWARD_RIGHT)
        time.sleep(0.3)
        print("LEFT (CCW)");  drive(pi, 1 - FORWARD_LEFT, FORWARD_RIGHT)
        time.sleep(0.3)
        print("RIGHT (CW)");  drive(pi, FORWARD_LEFT,     1 - FORWARD_RIGHT)
    finally:
        stop(pi)
        pi.stop()


if __name__ == "__main__":
    main()
