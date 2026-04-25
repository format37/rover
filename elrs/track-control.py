#!/usr/bin/env python3
"""
Differential ("tank") track control from a single ELRS right-stick.

Stick mapping (Mode 2 / AETR):
    Y axis (CH_THROTTLE, default ch2): forward / backward
    X axis (CH_STEER,    default ch1): turn right / left

Differential mixer:
    left  = throttle + steering   (clamped to [-1, 1])
    right = throttle - steering

Resulting behaviour:
    stick up         → both tracks forward                → rover forward
    stick down       → both tracks backward               → rover backward
    stick left       → left back,    right forward        → spin CCW in place
    stick right      → left forward, right back           → spin CW  in place
    diagonal         → blend of forward + spin            → arc

Failsafe stops both tracks if no valid RC frame arrives within FAILSAFE_TIMEOUT.

Hardware: see elrs/docs/TB6560_ROVER_TECH_SPEC.md.
Pre-reqs: pigpiod running, /dev/serial0 readable (see crsf-rx-test.py header).
"""

import time
import sys
import serial
import pigpio

# --- CRSF / serial ---
PORT = "/dev/serial0"
BAUD = 420000

CH_STEER = 1       # 1-indexed
CH_THROTTLE = 2

CRSF_SYNC = 0xC8
CRSF_HANDSET = 0xEE
CRSF_TYPE_RC = 0x16
CRSF_TYPE_LINK = 0x14

# --- Stepper pins (match tb6560-direct-demo.py / stepper-control.py) ---
STEP_LEFT = 18      # PWM channel 0
STEP_RIGHT = 13     # PWM channel 1
DIR_LEFT = 23
DIR_RIGHT = 24

DIR_INVERTED = True
FORWARD_LEFT = 1
FORWARD_RIGHT = 0

# --- Speed mapping ---
MAX_FREQ = 4000     # Hz at full deflection
MIN_FREQ = 200      # Hz floor when commanded > 0
DEADBAND_US = 30    # ±µs around 1500 → axis treated as 0
HALF_RANGE_US = 500
DUTY_CYCLE = 500000

# --- Safety ---
FAILSAFE_TIMEOUT = 0.5
PRINT_INTERVAL = 0.2
BUF_HARD_LIMIT = 4096


def _build_crc8_table():
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = ((crc << 1) ^ 0xD5) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
        table.append(crc)
    return tuple(table)

CRC8 = _build_crc8_table()


def crc8_dvb_s2(data) -> int:
    crc = 0
    for b in data:
        crc = CRC8[crc ^ b]
    return crc


def unpack_channels(buf22) -> list[int]:
    bits = 0
    nbits = 0
    out = []
    for b in buf22:
        bits |= b << nbits
        nbits += 8
        while nbits >= 11:
            out.append(bits & 0x7FF)
            bits >>= 11
            nbits -= 11
    return out


def to_us(v: int) -> int:
    return round((v - 992) * 5 / 8 + 1500)


def channel_to_signed(us: int) -> float:
    """µs → signed [-1, 1]. Inside ±DEADBAND_US returns exactly 0.0."""
    delta = us - 1500
    if abs(delta) < DEADBAND_US:
        return 0.0
    val = delta / HALF_RANGE_US
    return max(-1.0, min(1.0, val))


def apply_dir(level: int) -> int:
    return 1 - level if DIR_INVERTED else level


def set_track(pi, step_pin: int, dir_pin: int, motor_forward: int,
              signed_speed: float) -> int:
    """signed_speed ∈ [-1, 1]. Returns applied step Hz (signed for direction)."""
    if signed_speed == 0.0:
        pi.hardware_PWM(step_pin, 0, 0)
        return 0
    want_forward = signed_speed > 0
    logical = motor_forward if want_forward else (1 - motor_forward)
    pi.write(dir_pin, apply_dir(logical))
    freq = max(MIN_FREQ, int(abs(signed_speed) * MAX_FREQ))
    pi.hardware_PWM(step_pin, freq, DUTY_CYCLE)
    return freq if want_forward else -freq


def stop_tracks(pi):
    pi.hardware_PWM(STEP_LEFT, 0, 0)
    pi.hardware_PWM(STEP_RIGHT, 0, 0)


def main():
    pi = pigpio.pi()
    if not pi.connected:
        sys.exit("pigpiod not running — sudo systemctl start pigpiod")
    for pin in (STEP_LEFT, STEP_RIGHT, DIR_LEFT, DIR_RIGHT):
        pi.set_mode(pin, pigpio.OUTPUT)
    stop_tracks(pi)

    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.01)
    except serial.SerialException as e:
        pi.stop()
        sys.exit(f"open {PORT} failed: {e}")

    buf = bytearray()
    last_chans = [992] * 16
    last_lq = None
    last_rc_time = 0.0
    last_print = time.monotonic()
    frames_rc = 0

    print(f"track-control  thr=ch{CH_THROTTLE}  steer=ch{CH_STEER}  "
          f"max={MAX_FREQ}Hz  failsafe={int(FAILSAFE_TIMEOUT*1000)}ms  "
          f"deadband=±{DEADBAND_US}µs")

    try:
        while True:
            n = ser.in_waiting
            chunk = ser.read(n) if n else ser.read(1)
            if chunk:
                buf.extend(chunk)

            i = 0
            blen = len(buf)
            while i < blen:
                b = buf[i]
                if b != CRSF_SYNC and b != CRSF_HANDSET:
                    i += 1
                    continue
                if i + 4 > blen:
                    break
                length = buf[i + 1]
                if length < 2 or length > 62:
                    i += 1
                    continue
                total = length + 2
                if i + total > blen:
                    break
                pstart = i + 2
                pend = i + total - 1
                if crc8_dvb_s2(buf[pstart:pend]) == buf[pend]:
                    ftype = buf[pstart]
                    plen = pend - pstart
                    if ftype == CRSF_TYPE_RC and plen == 23:
                        last_chans = unpack_channels(buf[pstart + 1:pend])
                        last_rc_time = time.monotonic()
                        frames_rc += 1
                    elif ftype == CRSF_TYPE_LINK and plen >= 11:
                        last_lq = buf[pstart + 3]
                    i += total
                else:
                    i += 1

            if i:
                del buf[:i]
            if len(buf) > BUF_HARD_LIMIT:
                buf.clear()

            now = time.monotonic()
            link_alive = (now - last_rc_time) < FAILSAFE_TIMEOUT

            if link_alive:
                thr_us = to_us(last_chans[CH_THROTTLE - 1])
                steer_us = to_us(last_chans[CH_STEER - 1])
                throttle = channel_to_signed(thr_us)
                steering = channel_to_signed(steer_us)
                left  = max(-1.0, min(1.0, throttle + steering))
                right = max(-1.0, min(1.0, throttle - steering))
                f_left = set_track(pi, STEP_LEFT,  DIR_LEFT,  FORWARD_LEFT,  left)
                f_right = set_track(pi, STEP_RIGHT, DIR_RIGHT, FORWARD_RIGHT, right)
            else:
                stop_tracks(pi)
                thr_us = steer_us = 1500
                throttle = steering = 0.0
                left = right = 0.0
                f_left = f_right = 0

            if now - last_print >= PRINT_INTERVAL:
                dt = now - last_print
                age = (now - last_rc_time) * 1000 if last_rc_time else 9999
                state = "OK     " if link_alive else "FAILSAFE"
                print(
                    f"[{state}] "
                    f"thr={thr_us:4d} steer={steer_us:4d} "
                    f"→ L={left:+5.2f}({f_left:+5d}Hz)  R={right:+5.2f}({f_right:+5d}Hz)  "
                    f"rc={frames_rc/dt:4.1f}/s LQ={last_lq if last_lq is not None else '--'} "
                    f"age={age:5.0f}ms",
                    flush=True,
                )
                frames_rc = 0
                last_print = now

    except KeyboardInterrupt:
        pass
    finally:
        stop_tracks(pi)
        ser.close()
        pi.stop()


if __name__ == "__main__":
    main()
