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