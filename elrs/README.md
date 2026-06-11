# TB6560 stepper driver configuiration

Dual TB6560 stepper driver control from a Raspberry Pi, driving two NEMA-class
steppers for left/right tank tracks. Uses pigpio hardware PWM for jitter-free
STEP pulses.

See `docs/TB6560_ROVER_TECH_SPEC.md` for the full wiring spec and
`docs/wiring-diagram.py` for a pin diagram.

## Hardware

| RPi GPIO | TB6560 pin          | Role              |
|----------|---------------------|-------------------|
| GPIO18   | #1 CLK+ (PWM0)      | STEP left         |
| GPIO13   | #2 CLK+ (PWM1)      | STEP right        |
| GPIO23   | #1 CW+              | DIR  left         |
| GPIO24   | #2 CW+              | DIR  right        |
| GND      | #1/#2 CLK-, CW-, EN-| common ground     |

All signal lines go through an NPN level shifter to 5V (TB6560 inputs are 5V).
A single-NPN shifter inverts the signal — see `DIR_INVERTED` in the demo.

## Install

```bash
sudo apt install pigpio
sudo systemctl enable --now pigpiod

pip install -r requirements.txt
```

## Run the demo

```bash
python tb6560-direct-demo.py
```

Drives the rover forward, backward, left, right — 1 second each. If the rover
moves opposite to the label, flip `FORWARD_LEFT` / `FORWARD_RIGHT` in the
script. If one side is inverted vs the other, flip `DIR_INVERTED`.

## Troubleshooting

- **`Can't connect to pigpio at localhost(8888)`** — daemon not running.
  Start with `sudo systemctl start pigpiod` or `sudo pigpiod`.
- **`Unit pigpiod.service not found`** — package not installed.
  Run `sudo apt install pigpio`.
- **Motors hum but don't turn** — STEP frequency too high for the microstep
  setting, or TB6560 current DIP switches too low. Reduce `STEP_FREQ` or raise
  the driver current.

# ELRS connection
## RPi Zero W — Initial Setup

> **Prerequisites:** ELRS receiver Rx/Tx must be **disconnected** from RPi during setup.

### 1. Configure UART

Free the PL011 UART from Bluetooth and disable serial console:

```bash
# Disable serial console, keep hardware UART enabled
sudo raspi-config
# Interface Options → Serial Port → login shell: No → hardware: Yes

# Free PL011 from Bluetooth
echo "dtoverlay=disable-bt" | sudo tee -a /boot/firmware/config.txt
echo "enable_uart=1" | sudo tee -a /boot/firmware/config.txt

# Disable BT service
sudo systemctl disable hciuart
```

> **Note:** On Bookworm (RPi OS 2024+) configs live in `/boot/firmware/`, not `/boot/`.

### 2. Install dependencies

```bash
sudo apt update
sudo apt install -y pigpio python3-pigpio python3-serial
```

### 3. Enable pigpio daemon

```bash
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
```

### 4. Reboot

```bash
sudo reboot
```

### 5. Verify

```bash
# PL011 UART available
ls -l /dev/ttyAMA0
# Expected: crw-rw---- 1 root dialout 204, 64 ...

# pigpio running
sudo systemctl status pigpiod
# Expected: active (running)

# GPIO connectivity test
python3 -c "
import pigpio
pi = pigpio.pi()
print('Connected:', pi.connected)
print('pigpio version:', pi.get_pigpio_version())
pi.stop()
"
# Expected: Connected: True
```

## ELRS wiring
| ELRS RX pin | RPi Zero W GPIO | Physical pin |
|---|---|---|
| TX | GPIO15 (RXD) | Pin 10 |
| RX | GPIO14 (TXD) | Pin 8 |
| 5V | 5V | Pin 2 or 4 |
| GND | GND | Pin 6 |

Key detail: ELRS **TX** goes to RPi **RX** (GPIO15), and vice versa — crossed, not straight. For our rover you only strictly need one wire: ELRS TX → RPi RXD (receiving channel data). The second wire (RPi TXD → ELRS RX) is for telemetry back to your radio — nice to have for battery voltage display, but optional for v1.

# Running track control

## Stick mapping

| Channel | Role | Behaviour |
|---|---|---|
| ch1 | Steer | differential turn (left/right) |
| ch2 | Throttle | instantaneous forward/back |
| ch3 | Cruise | signed throttle **floor** — see below |
| ch5 | Mode | EN policy: FIXED (always on) vs GATED (move-only) |

**Cruise (ch3)** holds a continuous minimum speed hands-off:

- `ch3 = 0` → no effect, normal ch1/ch2 stick driving
- `ch3 > 0` → continuous forward; ch2 can add more, but pulling ch2 back
  cannot go below the ch3 level (clamped, not an override)
- `ch3 < 0` → continuous reverse, same rule

The floor is applied to the common throttle *before* steering is mixed, so
ch1 still differentiates the tracks to turn while cruising (one track may
briefly drop below the floor on sharp turns — by design, so it can steer).
Status line shows it as `cr=±x.xx`. ch3 is expected to be the
non-centering throttle stick (it holds position); a spring-centered
channel works too but won't "hold" cruise when released.

## Speed mapping

Stick deflection maps to step frequency through an expo curve, then a
slew-rate limiter ramps the *applied* frequency toward that target
(constants in `track-control.py`):

- `MIN_FREQ` (10 Hz) — slowest commandable crawl, right past the deadband
- `MAX_FREQ` (8000 Hz) — full deflection; ≈300 RPM at 1/8 microstep, under
  the TB6560's 15 kHz optocoupler limit
- `FREQ_EXPO` (2.0) — quadratic curve: half stick ≈ 2 kHz, full stick
  8 kHz, so the lower half of the stick keeps fine low-speed resolution
- `ACCEL_HZ_PER_S` (4000) / `DECEL_HZ_PER_S` (16000) — ramp slopes. The
  ramp is what makes 8 kHz reachable at all: a stepper stalls if asked to
  jump from standstill past its pull-in rate (~800 Hz on this build, the
  old hard cap). Direction reversals decelerate through zero first.
  Failsafe still cuts the step pulses instantly — no ramp-down.

Tuning on hardware: if the top end stalls under load, lower `MAX_FREQ` to
the highest frequency the motors hold at full stick; if the ramp feels
sluggish, raise `ACCEL_HZ_PER_S` (too high re-introduces start-up stalls).

## Service

`track-control.py` is **not** run manually in production — it runs as a
systemd service that starts at boot, ordered after `pigpiod`, and auto-restarts
on failure. The unit is version-controlled at `elrs/track-control.service`.

> **Path note:** the unit assumes the repo is checked out at `/home/alex/rover`
> on the Pi (the dev machine uses `~/projects/rover`). Edit
> `WorkingDirectory`/`ExecStart` in the unit if you clone elsewhere.

### Install / update the service

```bash
sudo cp elrs/track-control.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now track-control.service
```

### Operate

```bash
systemctl status track-control.service          # is it running?
sudo systemctl restart track-control.service    # after a git pull
sudo systemctl stop track-control.service        # before manual testing
journalctl -u track-control.service -f           # live status / CRSF log
```

To run the script by hand (e.g. tuning), **stop the service first** so two
processes don't fight over `/dev/serial0` and the GPIO pins:

```bash
sudo systemctl stop track-control.service
python3 track-control.py
```