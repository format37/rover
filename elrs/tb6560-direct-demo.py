#!/usr/bin/env python3
"""
TB6560 dual-stepper isolation demo: drive each motor by itself, both
directions, 1 second each. If any of the four steps misbehaves while
the others work, the issue is on that side's wiring/driver — not the
mixer or radio path.

Test sequence:
    1. stepper 0 (left)  forward
    2. stepper 0 (left)  backward
    3. stepper 1 (right) forward
    4. stepper 1 (right) backward

Only one motor is energised at a time; the other is held stopped.

Hardware (per elrs/docs/TB6560_ROVER_TECH_SPEC.md):
    GPIO18 → TB6560 #1 CLK+  (STEP left  / motor 0) via NPN level shifter to 5V  (PWM0)
    GPIO13 → TB6560 #2 CLK+  (STEP right / motor 1) via NPN level shifter to 5V  (PWM1)
    GPIO23 → TB6560 #1 CW+   (DIR  left)            via NPN level shifter to 5V
    GPIO24 → TB6560 #2 CW+   (DIR  right)           via NPN level shifter to 5V
    EN+ pins tied to GND (always enabled) or unused.
    Common GND between RPi, both TB6560s, and 5V rail.

Requires: pigpiod running (`sudo systemctl start pigpiod`).
"""

import time
import pigpio

# --- Pin assignment ---
# GPIO12 and GPIO18 BOTH map to PWM channel 0, so they cannot be driven
# independently — use GPIO13 (PWM channel 1) for the right motor.
STEP_LEFT  = 18   # hardware PWM channel 0
STEP_RIGHT = 13   # hardware PWM channel 1
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


def drive_one(pi, step_pin: int, dir_pin: int, dir_level: int,
              seconds: float = MOVE_SECONDS):
    """Run one motor at STEP_FREQ; explicitly hold the other stopped."""
    other_step = STEP_RIGHT if step_pin == STEP_LEFT else STEP_LEFT
    pi.hardware_PWM(other_step, 0, 0)
    set_motor(pi, step_pin, dir_pin, dir_level, STEP_FREQ)
    time.sleep(seconds)
    stop(pi)


def main():
    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("pigpiod not running — start it with: sudo systemctl start pigpiod")

    for pin in (STEP_LEFT, STEP_RIGHT, DIR_LEFT, DIR_RIGHT):
        pi.set_mode(pin, pigpio.OUTPUT)

    try:
        print("stepper 0 (left)  FORWARD")
        drive_one(pi, STEP_LEFT,  DIR_LEFT,  FORWARD_LEFT)
        time.sleep(0.5)
        print("stepper 0 (left)  BACKWARD")
        drive_one(pi, STEP_LEFT,  DIR_LEFT,  1 - FORWARD_LEFT)
        time.sleep(0.5)
        print("stepper 1 (right) FORWARD")
        drive_one(pi, STEP_RIGHT, DIR_RIGHT, FORWARD_RIGHT)
        time.sleep(0.5)
        print("stepper 1 (right) BACKWARD")
        drive_one(pi, STEP_RIGHT, DIR_RIGHT, 1 - FORWARD_RIGHT)
    finally:
        stop(pi)
        pi.stop()


if __name__ == "__main__":
    main()
