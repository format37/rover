#!/usr/bin/env python3
"""
CRSF receive sanity check — confirms the Pi is hearing the ELRS receiver.

Wiring (per elrs/docs/TB6560_ROVER_TECH_SPEC.md):
    ELRS RX  TX pin  → RPi GPIO15 / RXD  (/dev/serial0)
    ELRS RX  GND     → RPi GND
    ELRS RX  5V      → 5V rail

Pi setup (one-time):
    /boot/config.txt:  dtoverlay=disable-bt   and   enable_uart=1
    raspi-config → Interface → Serial → console: No, hardware: Yes
    sudo systemctl disable --now serial-getty@ttyAMA0.service

What this prints:
    bytes/s and valid-frame/s (link is alive if both > 0 and frames/s ≈ 50–500)
    Right-stick channels in microseconds (988..2012) with a live bar.
    Mode 2 / AETR: ch1 = aileron (right-stick X = steering),
                   ch2 = elevator (right-stick Y = throttle).
    Override the channel mapping below if your radio uses TAER or a custom mix.
"""

import time
import sys
import serial

PORT = "/dev/serial0"
BAUD = 420000

# 1-indexed CRSF channels for the right stick.
CH_STEER = 1     # right-stick X — aileron in AETR
CH_THROTTLE = 2  # right-stick Y — elevator in AETR

CRSF_SYNC = 0xC8           # also accept 0xEE (handset) just in case
CRSF_TYPE_RC = 0x16        # RC channels packed (16 ch × 11 bit)
CRSF_TYPE_LINK = 0x14      # link statistics


def crc8_dvb_s2(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0xD5) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def unpack_channels(buf: bytes) -> list[int]:
    """22 bytes → 16 channels of 11 bits, LSB-first."""
    bits = 0
    nbits = 0
    out = []
    for b in buf:
        bits |= b << nbits
        nbits += 8
        while nbits >= 11:
            out.append(bits & 0x7FF)
            bits >>= 11
            nbits -= 11
    return out


def to_us(v: int) -> int:
    return round((v - 992) * 5 / 8 + 1500)


def bar(us: int, width: int = 21) -> str:
    """Visual stick position bar from 988µs (left) to 2012µs (right)."""
    span = 2012 - 988
    pos = round((us - 988) / span * (width - 1))
    pos = max(0, min(width - 1, pos))
    cells = ['-'] * width
    cells[width // 2] = '|'   # center marker (1500µs)
    cells[pos] = 'o'
    return '[' + ''.join(cells) + ']'


def main():
    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.05)
    except serial.SerialException as e:
        sys.exit(f"open {PORT} failed: {e}")

    buf = bytearray()
    bytes_in = 0
    frames_rc = 0
    frames_link = 0
    last_chans = [992] * 16
    last_lq = None
    last_print = time.monotonic()

    tty = sys.stdout.isatty()
    line_end = "" if tty else "\n"
    line_prefix = "\r" if tty else ""

    print(f"listening on {PORT} @ {BAUD} baud — Ctrl-C to stop")
    print(f"showing right stick: steer=ch{CH_STEER}  throttle=ch{CH_THROTTLE}")
    try:
        while True:
            chunk = ser.read(64)
            if chunk:
                buf.extend(chunk)
                bytes_in += len(chunk)

            # Resync: drop bytes until buf starts with a known sync byte.
            while buf and buf[0] not in (CRSF_SYNC, 0xEE):
                buf.pop(0)
            if len(buf) < 4:
                pass
            else:
                length = buf[1]
                # CRSF frame = sync + length + (length bytes: type + payload + crc)
                total = length + 2
                if length < 2 or length > 62:
                    buf.pop(0)
                elif len(buf) >= total:
                    frame = bytes(buf[:total])
                    payload = frame[2:-1]    # type + data
                    crc_rx = frame[-1]
                    if crc8_dvb_s2(payload) == crc_rx:
                        ftype = payload[0]
                        if ftype == CRSF_TYPE_RC and len(payload) == 1 + 22:
                            last_chans = unpack_channels(payload[1:])
                            frames_rc += 1
                        elif ftype == CRSF_TYPE_LINK and len(payload) >= 1 + 10:
                            # uplink LQ is byte index 2 of the link-stats payload
                            last_lq = payload[1 + 2]
                            frames_link += 1
                        del buf[:total]
                    else:
                        buf.pop(0)   # bad CRC, slide forward and resync

            now = time.monotonic()
            if now - last_print >= 0.1:
                dt = now - last_print
                steer_us = to_us(last_chans[CH_STEER - 1])
                thr_us = to_us(last_chans[CH_THROTTLE - 1])
                lq = f"{last_lq:>3}" if last_lq is not None else " --"
                print(
                    f"{line_prefix}"
                    f"{bytes_in/dt:5.0f}B/s rc={frames_rc/dt:5.1f}/s LQ={lq}  "
                    f"steer={steer_us:4d}µs {bar(steer_us)}  "
                    f"thr={thr_us:4d}µs {bar(thr_us)}",
                    end=line_end, flush=True,
                )
                bytes_in = frames_rc = frames_link = 0
                last_print = now
    except KeyboardInterrupt:
        pass
    finally:
        if tty:
            print()       # close the in-place line cleanly
        ser.close()


if __name__ == "__main__":
    main()
