#!/usr/bin/env python3
"""
Differential ("tank") track control from a single ELRS right-stick.

Stick mapping (Mode 2 / AETR):
    Y axis (CH_THROTTLE, default ch2): forward / backward
    X axis (CH_STEER,    default ch1): turn right / left
    CH_CRUISE   (default ch3): signed cruise / throttle floor

Cruise (ch3) sets a continuous minimum speed the rover holds hands-off:
    ch3 = 0   → no effect, normal stick control
    ch3 > 0   → continuous forward; ch2 can add more but not go below it
    ch3 < 0   → continuous reverse; ch2 can add more but not go below it
The floor is applied to the common throttle *before* steering is mixed,
so ch1 can still differentiate the tracks to turn while cruising.

Differential mixer:
    throttle = cruise-floored ch2
    left  = throttle + steering   (clamped to [-1, 1])
    right = throttle - steering

Speed mapping:
    stick value → |x|^FREQ_EXPO curve → target step Hz in [MIN_FREQ, MAX_FREQ]
    A slew-rate limiter (ACCEL_HZ_PER_S up, DECEL_HZ_PER_S down) ramps the
    applied frequency toward the target — that ramp is what lets MAX_FREQ sit
    far above the stepper pull-in rate (~800 Hz on this build) without
    stalling from standstill. Direction reversals decelerate through zero
    first. Failsafe stops instantly, no ramp.

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

import signal
import time
import sys
import serial
import pigpio

# --- CRSF / serial ---
PORT = "/dev/serial0"
BAUD = 420000

CH_STEER = 1       # 1-indexed
CH_THROTTLE = 2
CH_CRUISE = 3      # signed cruise / throttle floor
CH_MODE = 5        # mode switch: always-on vs movement-gated EN

CRSF_SYNC = 0xC8
CRSF_HANDSET = 0xEE
CRSF_TYPE_RC = 0x16
CRSF_TYPE_LINK = 0x14

# --- Stepper pins (match tb6560-direct-demo.py / stepper-control.py) ---
STEP_LEFT = 18      # PWM channel 0
STEP_RIGHT = 13     # PWM channel 1
DIR_LEFT = 23
DIR_RIGHT = 24
STEPPER_EN = 25
EN_ACTIVE = 0       # GPIO level that enables the drivers (flip if wiring inverts)

DIR_INVERTED = True
FORWARD_LEFT = 1
FORWARD_RIGHT = 0

# --- Speed mapping ---
# MAX_FREQ is the 1/8-microstep hardware budget (TB6560 opto limit 15 kHz,
# ≈300 RPM at 8 kHz). It is reachable from standstill only because of the
# accel ramp below — without it anything past ~800 Hz stalls (pull-in limit).
# Calibrate MAX_FREQ under load at MINIMUM pack voltage (~12.0 V, near-empty
# 4S): pull-out speed scales with bus voltage, so a value that holds at
# 16.8 V will stall as the pack sags. Stall symptom: one track buzzes at
# zero torque while the other drives (hard veer); to re-sync, drop the stick
# below ~30% so the commanded frequency falls under the ~800 Hz pull-in rate.
MAX_FREQ = 8000     # Hz at full deflection
MIN_FREQ = 10       # Hz at the deadband edge — slowest commandable crawl
FREQ_EXPO = 2.0     # stick→Hz curve: 1.0 = linear, >1 = finer low-speed control
ACCEL_HZ_PER_S = 4000   # ramp-up slope; keeps starts below the pull-in limit
DECEL_HZ_PER_S = 16000  # ramp-down slope (failsafe still stops instantly)
RAMP_DT_MAX = 0.05  # s — clamp loop hiccups so one tick can't jump past pull-in
DEADBAND_US = 30    # ±µs around 1500 → axis treated as 0
HALF_RANGE_US = 500
DUTY_CYCLE = 500000
MODE_THRESHOLD_US = 1500    # CH_MODE > threshold → drivers always enabled (FIXED)

# --- Safety ---
FAILSAFE_TIMEOUT = 0.5
FAILSAFE_EN_HOLD = 1.0  # s — keep drivers energized after a failsafe stop so
                        # the pole-slip ringdown happens against the 50% stop
                        # current and the rover doesn't break loose on a grade
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
    """µs → signed [-1, 1]. Inside ±DEADBAND_US returns exactly 0.0.

    Rescaled so the deadband edge maps to 0.0 (continuous, no jump) and
    full deflection to ±1.0.
    """
    delta = us - 1500
    if abs(delta) < DEADBAND_US:
        return 0.0
    val = min(1.0, (abs(delta) - DEADBAND_US) / (HALF_RANGE_US - DEADBAND_US))
    return val if delta > 0 else -val


def signed_to_freq(signed: float) -> float:
    """Signed [-1, 1] → signed target step frequency in Hz.

    Magnitude follows MIN_FREQ + (MAX_FREQ - MIN_FREQ) * |signed|^FREQ_EXPO,
    so the whole usable band is on the stick with extra resolution down low.
    """
    if signed == 0.0:
        return 0.0
    mag = MIN_FREQ + (MAX_FREQ - MIN_FREQ) * abs(signed) ** FREQ_EXPO
    return mag if signed > 0 else -mag


def slew_freq(current: float, target: float, dt: float) -> float:
    """Slope-limit the signed step frequency.

    Magnitude rises at most ACCEL_HZ_PER_S and falls at most DECEL_HZ_PER_S
    per second; a direction change decelerates through zero first, spending
    any leftover tick time accelerating the other way.
    """
    dt = min(dt, RAMP_DT_MAX)
    if dt <= 0.0:
        return current
    if current != 0.0 and (target == 0.0 or (current > 0) != (target > 0)):
        drop = DECEL_HZ_PER_S * dt
        if abs(current) > drop:
            return current - drop if current > 0 else current + drop
        dt -= abs(current) / DECEL_HZ_PER_S
        current = 0.0
        if target == 0.0:
            return 0.0
    if abs(target) > abs(current):
        rise = ACCEL_HZ_PER_S * dt
        return min(target, current + rise) if target > 0 else max(target, current - rise)
    drop = DECEL_HZ_PER_S * dt
    return max(target, current - drop) if target > 0 else min(target, current + drop)


def apply_dir(level: int) -> int:
    return 1 - level if DIR_INVERTED else level


def set_track(pi, step_pin: int, dir_pin: int, motor_forward: int,
              freq_signed: float) -> int:
    """freq_signed: signed step Hz, already slew-limited. Returns applied Hz."""
    freq = int(round(abs(freq_signed)))
    if freq == 0:
        pi.hardware_PWM(step_pin, 0, 0)
        return 0
    want_forward = freq_signed > 0
    logical = motor_forward if want_forward else (1 - motor_forward)
    pi.write(dir_pin, apply_dir(logical))
    pi.hardware_PWM(step_pin, freq, DUTY_CYCLE)
    return freq if want_forward else -freq


def stop_tracks(pi):
    pi.hardware_PWM(STEP_LEFT, 0, 0)
    pi.hardware_PWM(STEP_RIGHT, 0, 0)


def set_enable(pi, state, current):
    """Drive STEPPER_EN only when state changes. Returns new state."""
    if state != current:
        pi.write(STEPPER_EN, EN_ACTIVE if state else 1 - EN_ACTIVE)
    return state


def main():
    # systemd sends SIGINT (KillSignal= in the unit), but make a bare SIGTERM
    # (manual kill) also run the finally-cleanup instead of dying mid-pulse.
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    pi = pigpio.pi()
    if not pi.connected:
        sys.exit("pigpiod not running — sudo systemctl start pigpiod")
    for pin in (STEP_LEFT, STEP_RIGHT, DIR_LEFT, DIR_RIGHT, STEPPER_EN):
        pi.set_mode(pin, pigpio.OUTPUT)
    pi.write(STEPPER_EN, 1 - EN_ACTIVE)
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
    en_state = False
    ramp_left = 0.0     # signed Hz currently applied to each track
    ramp_right = 0.0
    last_loop = time.monotonic()

    print(f"track-control  thr=ch{CH_THROTTLE}  steer=ch{CH_STEER}  "
          f"cruise=ch{CH_CRUISE}  "
          f"freq={MIN_FREQ}-{MAX_FREQ}Hz expo={FREQ_EXPO}  "
          f"ramp={ACCEL_HZ_PER_S}/{DECEL_HZ_PER_S}Hz/s  "
          f"failsafe={int(FAILSAFE_TIMEOUT*1000)}ms  "
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
            dt = now - last_loop
            last_loop = now
            link_alive = (now - last_rc_time) < FAILSAFE_TIMEOUT

            mode_us = to_us(last_chans[CH_MODE - 1])
            mode_fixed = mode_us > MODE_THRESHOLD_US
            if link_alive:
                thr_us = to_us(last_chans[CH_THROTTLE - 1])
                steer_us = to_us(last_chans[CH_STEER - 1])
                cruise_us = to_us(last_chans[CH_CRUISE - 1])
                throttle = channel_to_signed(thr_us)
                steering = channel_to_signed(steer_us)
                cruise = channel_to_signed(cruise_us)
                # ch3 sets a signed floor on the common throttle: the rover
                # never goes slower than `cruise` in cruise's direction.
                if cruise > 0.0:
                    throttle = max(throttle, cruise)
                elif cruise < 0.0:
                    throttle = min(throttle, cruise)
                left  = max(-1.0, min(1.0, throttle + steering))
                right = max(-1.0, min(1.0, throttle - steering))
                ramp_left = slew_freq(ramp_left, signed_to_freq(left), dt)
                ramp_right = slew_freq(ramp_right, signed_to_freq(right), dt)
                # keep EN asserted while still ramping down after stick release
                moving = (left != 0.0 or right != 0.0
                          or ramp_left != 0.0 or ramp_right != 0.0)
                en_state = set_enable(pi, mode_fixed or moving, en_state)
                f_left = set_track(pi, STEP_LEFT,  DIR_LEFT,  FORWARD_LEFT,  ramp_left)
                f_right = set_track(pi, STEP_RIGHT, DIR_RIGHT, FORWARD_RIGHT, ramp_right)
            else:
                stop_tracks(pi)
                # Hold EN briefly after losing the link (never at cold start,
                # when last_rc_time is still 0): phases stay energized while
                # the rotor rings down, then release for fail-dead behavior.
                hold = (last_rc_time > 0.0 and
                        (now - last_rc_time) < FAILSAFE_TIMEOUT + FAILSAFE_EN_HOLD)
                en_state = set_enable(pi, hold, en_state)
                throttle = steering = cruise = 0.0
                left = right = 0.0
                ramp_left = ramp_right = 0.0
                f_left = f_right = 0

            if now - last_print >= PRINT_INTERVAL:
                dt = now - last_print
                age = (now - last_rc_time) * 1000 if last_rc_time else 9999
                state = "OK     " if link_alive else "FAILSAFE"
                en = "EN" if en_state else "--"
                print(
                    f"[{state}] {en} "
                    f"ch{CH_MODE}={mode_us:4d}({'FX' if mode_fixed else 'GT'}) "
                    f"cr={cruise:+4.2f} "
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
        # Each step independently: a broken pigpiod socket in stop_tracks
        # must not skip the EN deassert (PWM would keep free-running).
        try:
            stop_tracks(pi)
        except Exception:
            pass
        try:
            pi.write(STEPPER_EN, 1 - EN_ACTIVE)
        except Exception:
            pass
        try:
            ser.close()
        except Exception:
            pass
        pi.stop()


if __name__ == "__main__":
    main()
