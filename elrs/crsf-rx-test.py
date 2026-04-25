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

Output:
    Once per second:
        B/s   rc-frames/s   link-frames/s   LQ   steer-µs   thr-µs   bad_crc
    Mode 2 / AETR: ch1 = right-stick X (steering), ch2 = right-stick Y (throttle).
    Override CH_STEER / CH_THROTTLE below for TAER or custom mixes.
"""

import time
import sys
import serial

PORT = "/dev/serial0"
BAUD = 420000

CH_STEER = 1     # 1-indexed
CH_THROTTLE = 2

CRSF_SYNC = 0xC8
CRSF_HANDSET = 0xEE
CRSF_TYPE_RC = 0x16        # RC channels packed (16 ch × 11 bit)
CRSF_TYPE_LINK = 0x14      # link statistics

PRINT_INTERVAL = 0.1       # seconds — 10 Hz status output
BUF_HARD_LIMIT = 4096      # bytes — drop and resync if we ever exceed this


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
    """22 bytes → 16 channels of 11 bits, LSB-first."""
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


def main():
    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.01)
    except serial.SerialException as e:
        sys.exit(f"open {PORT} failed: {e}")

    buf = bytearray()
    bytes_in = 0
    frames_rc = 0
    frames_link = 0
    bad_crc = 0
    overflows = 0
    last_chans = [992] * 16
    last_lq = None
    last_print = time.monotonic()

    print(f"listening on {PORT} @ {BAUD} baud — Ctrl-C to stop")
    print(f"right stick: steer=ch{CH_STEER}  throttle=ch{CH_THROTTLE}")

    try:
        while True:
            # Read everything currently available (or block briefly for the next byte).
            n = ser.in_waiting
            chunk = ser.read(n) if n else ser.read(1)
            if chunk:
                buf.extend(chunk)
                bytes_in += len(chunk)

            # Drain ALL complete frames in this pass. Advance an index — never pop(0).
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
                total = length + 2          # full frame size incl. sync+length
                if i + total > blen:
                    break                   # frame not yet complete
                pstart = i + 2              # type byte
                pend = i + total - 1        # crc byte
                if crc8_dvb_s2(buf[pstart:pend]) == buf[pend]:
                    ftype = buf[pstart]
                    plen = pend - pstart    # type + data
                    if ftype == CRSF_TYPE_RC and plen == 23:
                        last_chans = unpack_channels(buf[pstart + 1:pend])
                        frames_rc += 1
                    elif ftype == CRSF_TYPE_LINK and plen >= 11:
                        # CRSF link stats: [type, ulRSSI1, ulRSSI2, ulLQ, ulSNR, ...]
                        last_lq = buf[pstart + 3]
                        frames_link += 1
                    i += total
                else:
                    bad_crc += 1
                    i += 1

            if i:
                del buf[:i]

            # Safety net: if anything ever lets the buffer grow unbounded, blow it away.
            if len(buf) > BUF_HARD_LIMIT:
                buf.clear()
                overflows += 1

            now = time.monotonic()
            if now - last_print >= PRINT_INTERVAL:
                dt = now - last_print
                steer_us = to_us(last_chans[CH_STEER - 1])
                thr_us = to_us(last_chans[CH_THROTTLE - 1])
                lq = last_lq if last_lq is not None else "--"
                print(
                    f"B/s={bytes_in/dt:5.0f}  rc={frames_rc/dt:5.1f}/s  "
                    f"link={frames_link/dt:4.1f}/s  LQ={lq}  "
                    f"steer={steer_us:4d}µs  thr={thr_us:4d}µs  "
                    f"bad_crc={bad_crc}  buf={len(buf)}  ovf={overflows}",
                    flush=True,
                )
                bytes_in = frames_rc = frames_link = bad_crc = 0
                last_print = now

    except KeyboardInterrupt:
        pass
    finally:
        ser.close()


if __name__ == "__main__":
    main()
