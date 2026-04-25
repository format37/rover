#!/usr/bin/env python3
"""
Direct one-channel-per-motor stepper control from the ELRS receiver.

Mapping (Mode 2 / AETR by default):
    throttle ch (right-stick Y, default ch2) → motor 0 (left)
    steer    ch (right-stick X, default ch1) → motor 1 (right)

For each channel independently:
     989µs → full reverse
    1500µs → stop (inside ±DEADBAND_US)
    2012µs → full forward

Step frequency scales linearly with stick deflection up to MAX_FREQ.
Direction pin flips on the side the stick crosses center.

Safety:
    Failsafe stops both motors if no valid RC frame for FAILSAFE_TIMEOUT.
    Ctrl-C and any exception path stops motors before exit.

Hardware (per elrs/docs/TB6560_ROVER_TECH_SPEC.md):
    GPIO18 → TB6560 #1 CLK+  (STEP motor 0 / left)
    GPIO12 → TB6560 #2 CLK+  (STEP motor 1 / right)
    GPIO23 → TB6560 #1 CW+   (DIR  motor 0)
    GPIO24 → TB6560 #2 CW+   (DIR  motor 1)
    GPIO15 ← ELRS RX TX (CRSF @ 420 kbaud, /dev/serial0)

Pre-reqs:
    sudo systemctl start pigpiod
    /dev/serial0 readable by user (see elrs/crsf-rx-test.py header for udev rule)
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

# --- Stepper pins (match tb6560-direct-demo.py) ---
STEP_LEFT = 18      # motor 0
STEP_RIGHT = 12     # motor 1
DIR_LEFT = 23
DIR_RIGHT = 24

# NPN level shifter inverts DIR — same as the demo.
DIR_INVERTED = True
FORWARD_LEFT = 1
FORWARD_RIGHT = 0

# --- Speed mapping ---
MAX_FREQ = 4000     # Hz at full deflection (matches demo's STEP_FREQ)
MIN_FREQ = 200      # Hz floor when commanded > 0 (avoids sub-stall regime)
DEADBAND_US = 30    # ±µs around 1500 → motor stopped
HALF_RANGE_US = 500 # 989..1500..2012 → ~500 µs each side
DUTY_CYCLE = 500000 # pigpio 50% duty

# --- Safety ---
FAILSAFE_TIMEOUT = 0.5  # seconds without RC → stop
PRINT_INTERVAL = 0.2    # 5 Hz status

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


def channel_to_motor(us: int) -> tuple[float, bool]:
    """Return (speed 0..1, want_forward). Inside deadband → (0.0, True)."""
    delta = us - 1500
    if abs(delta) < DEADBAND_US:
        return 0.0, True
    speed = min(1.0, abs(delta) / HALF_RANGE_US)
    return speed, delta > 0


def apply_dir(level: int) -> int:
    return 1 - level if DIR_INVERTED else level


def set_motor(pi, step_pin: int, dir_pin: int, motor_forward: int,
              speed: float, want_forward: bool) -> int:
    """Returns step frequency actually applied (0 if stopped)."""
    if speed <= 0.0:
        pi.hardware_PWM(step_pin, 0, 0)
        return 0
    logical = motor_forward if want_forward else (1 - motor_forward)
    pi.write(dir_pin, apply_dir(logical))
    freq = max(MIN_FREQ, int(speed * MAX_FREQ))
    pi.hardware_PWM(step_pin, freq, DUTY_CYCLE)
    return freq


def stop_motors(pi):
    pi.hardware_PWM(STEP_LEFT, 0, 0)
    pi.hardware_PWM(STEP_RIGHT, 0, 0)


def main():
    pi = pigpio.pi()
    if not pi.connected:
        sys.exit("pigpiod not running — sudo systemctl start pigpiod")
    for pin in (STEP_LEFT, STEP_RIGHT, DIR_LEFT, DIR_RIGHT):
        pi.set_mode(pin, pigpio.OUTPUT)
    stop_motors(pi)

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

    print(f"thr=ch{CH_THROTTLE}→motor0(left)  steer=ch{CH_STEER}→motor1(right)  "
          f"failsafe={int(FAILSAFE_TIMEOUT*1000)}ms  max={MAX_FREQ}Hz  "
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
                spd_thr, fwd_thr = channel_to_motor(thr_us)
                spd_str, fwd_str = channel_to_motor(steer_us)
                f_left = set_motor(pi, STEP_LEFT, DIR_LEFT, FORWARD_LEFT,
                                   spd_thr, fwd_thr)
                f_right = set_motor(pi, STEP_RIGHT, DIR_RIGHT, FORWARD_RIGHT,
                                    spd_str, fwd_str)
            else:
                stop_motors(pi)
                thr_us = steer_us = 1500
                spd_thr = spd_str = 0.0
                fwd_thr = fwd_str = True
                f_left = f_right = 0

            if now - last_print >= PRINT_INTERVAL:
                dt = now - last_print
                age = (now - last_rc_time) * 1000 if last_rc_time else 9999
                state = "OK     " if link_alive else "FAILSAFE"
                print(
                    f"[{state}] "
                    f"thr={thr_us:4d}µs {'F' if fwd_thr else 'R'} {f_left:4d}Hz | "
                    f"steer={steer_us:4d}µs {'F' if fwd_str else 'R'} {f_right:4d}Hz | "
                    f"rc={frames_rc/dt:4.1f}/s LQ={last_lq if last_lq is not None else '--'} "
                    f"age={age:5.0f}ms",
                    flush=True,
                )
                frames_rc = 0
                last_print = now

    except KeyboardInterrupt:
        pass
    finally:
        stop_motors(pi)
        ser.close()
        pi.stop()


if __name__ == "__main__":
    main()
