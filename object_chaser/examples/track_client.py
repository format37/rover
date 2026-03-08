#!/usr/bin/env python3
"""
Remote track & servo control via servo_api server.

Controls (type command + Enter):
  w  - forward        s  - backward
  a  - rotate left    d  - rotate right
  q  - look left      e  - look right     x  - look forward
  +  - speed up       -  - speed down
  0  - stop tracks
  z  - exit

Tracks run for DURATION seconds then auto-stop (same as move.py).
Directions use native convention: 1=forward, 0=backward.
"""

import requests
import sys

SERVO_URL = 'http://localhost:8000'
DURATION = 3.0
SPEED_DEFAULT = 0.05
SPEED_STEP = 0.01
SPEED_MIN = 0.01
SPEED_MAX = 1.0
SERVO_STEP = 30  # degrees per press


def tracks_move(left_speed, left_dir, right_speed, right_dir, duration=DURATION):
    try:
        requests.post(f"{SERVO_URL}/tracks/move",
                      json={"left_speed": left_speed, "left_dir": left_dir,
                            "right_speed": right_speed, "right_dir": right_dir,
                            "duration": duration},
                      timeout=2.0)
    except requests.exceptions.RequestException as e:
        print(f"  error: {e}")


def tracks_stop():
    try:
        requests.post(f"{SERVO_URL}/tracks/stop", timeout=2.0)
    except requests.exceptions.RequestException as e:
        print(f"  error: {e}")


def servo_move(angle):
    try:
        requests.post(f"{SERVO_URL}/move",
                      json={"angle": angle}, timeout=2.0)
    except requests.exceptions.RequestException as e:
        print(f"  error: {e}")


def servo_status():
    try:
        r = requests.get(f"{SERVO_URL}/status", timeout=2.0)
        if r.status_code == 200:
            return r.json()
    except requests.exceptions.RequestException:
        pass
    return None


def main():
    speed = SPEED_DEFAULT
    print(__doc__)
    print(f"speed: {speed:.2f}")

    cmd = ''
    while cmd != 'z':
        cmd = input('cmd: ').strip()

        if cmd == 'w':
            print(f"  forward (speed={speed:.2f}, {DURATION}s)")
            tracks_move(speed, 1, speed, 1)

        elif cmd == 's':
            print(f"  backward (speed={speed:.2f}, {DURATION}s)")
            tracks_move(speed, 0, speed, 0)

        elif cmd == 'a':
            print(f"  rotate left (speed={speed:.2f}, {DURATION}s)")
            tracks_move(speed, 0, speed, 1)

        elif cmd == 'd':
            print(f"  rotate right (speed={speed:.2f}, {DURATION}s)")
            tracks_move(speed, 1, speed, 0)

        elif cmd == '0':
            print("  stop")
            tracks_stop()

        elif cmd == 'q':
            status = servo_status()
            angle = status['current_position'] if status else 90
            new_angle = min(180, angle + SERVO_STEP)
            print(f"  look left -> {new_angle:.0f}deg")
            servo_move(new_angle)

        elif cmd == 'e':
            status = servo_status()
            angle = status['current_position'] if status else 90
            new_angle = max(0, angle - SERVO_STEP)
            print(f"  look right -> {new_angle:.0f}deg")
            servo_move(new_angle)

        elif cmd == 'x':
            print("  look forward -> 90deg")
            servo_move(90)

        elif cmd == '+':
            speed = min(SPEED_MAX, speed + SPEED_STEP)
            print(f"  speed: {speed:.2f}")

        elif cmd == '-':
            speed = max(SPEED_MIN, speed - SPEED_STEP)
            print(f"  speed: {speed:.2f}")

        elif cmd == 'z':
            print("  stopping & exit")
            tracks_stop()
            servo_move(90)
            break

        elif cmd:
            print("  unknown command")


if __name__ == "__main__":
    main()
