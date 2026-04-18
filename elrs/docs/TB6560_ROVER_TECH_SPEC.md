# TB6560 Stepper Rover — Technical Specification

## System Overview

Tracked rover with two NEMA17 stepper motors, differential steering (skid-steer),
controlled via ExpressLRS radio link, driven by Raspberry Pi Zero W v1.1.

```
ELRS TX (radio) ─── air ───► ELRS RX
                                │ CRSF @ 420kbaud
                                ▼
                         RPi Zero W v1.1
                          │           │
                     GPIO step/dir  GPIO step/dir
                          │           │
                    ┌─────┴─────┐ ┌───┴───────┐
                    │ TB6560 #1 │ │ TB6560 #2  │
                    └─────┬─────┘ └───┬────────┘
                          │           │
                    Left NEMA17  Right NEMA17
```

Power: 4S1P Li-ion → TB6560 direct + buck converter → 5V rail

---

## Hardware Specifications

### Raspberry Pi Zero W v1.1

| Parameter          | Value                              |
|--------------------|------------------------------------|
| SoC                | BCM2835, ARM11 single-core 1GHz    |
| RAM                | 512MB                              |
| GPIO               | 40-pin header, 3.3V logic          |
| UART               | PL011 (ttyAMA0) + mini-UART (ttyS0) |
| OS                 | Raspberry Pi OS Lite (32-bit)      |

**UART setup for CRSF:**

- PL011 must be freed from Bluetooth: add `dtoverlay=disable-bt` to `/boot/config.txt`
- Disable serial console: `sudo raspi-config` → Interface → Serial → No console, Yes hardware
- PL011 base clock: 48MHz → max baud = 48MHz/16 = 3MHz
- CRSF baud 420000: divisor = 48000000 / (16 × 420000) = 7.143 → fractional error ~0.66% — within CRSF tolerance

### BL-TB6560 V2.0 Stepper Driver

| Parameter              | Value                                    |
|------------------------|------------------------------------------|
| Motor supply (VMA)     | 10–35V DC (recommended 12–16V for NEMA17)|
| Logic supply (VDD)     | 4.5–5.5V (onboard regulator from VMA)    |
| Max phase current      | 3A (set via DIP switches)                |
| Microstepping          | Full, 1/2, 1/8, 1/16                     |
| Max STEP frequency     | **15 kHz** (limited by 6N137 optocoupler)|
| Input logic level      | **5V** (optocoupler LED, 330Ω onboard)   |
| STEP optocoupler       | 6N137 (high-speed)                       |
| DIR/EN optocoupler     | PC817 or 4N35                            |

**Control pinout (accent terminal block):**

| Pin | Label | Function            | Signal type                |
|-----|-------|---------------------|----------------------------|
| 1   | CLK+  | STEP pulse input    | Rising-edge triggered      |
| 2   | CLK-  | STEP ground/return  | Connect to common GND      |
| 3   | CW+   | Direction input     | HIGH = CW, LOW = CCW       |
| 4   | CW-   | Direction ground    | Connect to common GND      |
| 5   | EN+   | Enable input        | LOW = enabled, HIGH = off  |
| 6   | EN-   | Enable ground       | Connect to common GND      |

### NEMA17 Stepper Motors

| Parameter            | Typical value         |
|----------------------|-----------------------|
| Steps/rev            | 200 (1.8°/step)       |
| Rated current        | 1.2–1.7A/phase        |
| Rated voltage        | 2.5–4.2V (irrelevant with chopper driver) |
| Holding torque       | 0.4–0.5 Nm            |

### Power System

| Rail         | Source              | Voltage range     | Consumers                       |
|--------------|---------------------|-------------------|---------------------------------|
| Motor power  | 4S1P Li-ion direct  | 12.0–16.8V        | TB6560 ×2 → NEMA17 ×2          |
| 5V logic     | LM2596 buck from 4S | 5.0V ±2%          | RPi Zero W, ELRS RX, FPV cam   |

---

## Critical Issue: 3.3V → 5V Level Shifting

**RPi GPIO outputs 3.3V. TB6560 optocouplers expect 5V.**

The TB6560 has 330Ω series resistors on each input. The 6N137 optocoupler LED has
~1.2V forward voltage and needs ≥5mA to trigger reliably.

At 3.3V: I = (3.3 − 1.2) / 330 = **6.4mA** → marginal, right at threshold.
At 5.0V: I = (5.0 − 1.2) / 330 = **11.5mA** → comfortable.

**3.3V MAY work but is unreliable**, especially at high step frequencies (15kHz)
where the 6N137 needs clean edges. Temperature drift worsens this.

### Recommended solution: NPN transistor level shifter (simplest)

Per channel (4 total: 2× STEP, 2× DIR):

```
RPi GPIO (3.3V) ──[1kΩ]──► Base ┐
                                  │ 2N2222 / BC547
                          GND ──► Emitter
                                  │
              5V ──[330Ω]────────► Collector ──► TB6560 CLK+ or CW+
                                                 TB6560 CLK- or CW- ──► GND
```

Note: signal is INVERTED (GPIO HIGH → collector LOW). Handle in software
by inverting the pulse logic, or use two transistors per channel for
non-inverting buffer. For STEP pulses, inversion doesn't matter — the TB6560
triggers on edges. For DIR, just swap CW/CCW mapping in code.

**Alternative:** Dedicated level shifter board (TXB0108, 4-channel bi-directional).
Cleaner but adds another module. For a rover with only 4 signals, the transistor
approach is simpler and more robust.

**EN pins:** Directly tie EN+ to GND (always enabled) or control via another
level-shifted GPIO if you want motor standby.

---

## Timing Analysis: Can RPi Zero W Afford the Required Frequency?

### Step frequency requirements for rover

| Microstepping | Steps/rev | Max RPM target | Required freq |
|---------------|-----------|----------------|---------------|
| Full step     | 200       | 300 RPM        | 1,000 Hz      |
| 1/2 step      | 400       | 300 RPM        | 2,000 Hz      |
| 1/8 step      | 1,600     | 300 RPM        | 8,000 Hz      |
| 1/16 step     | 3,200     | 300 RPM        | 16,000 Hz     |

**TB6560 hard limit: 15 kHz** (6N137 optocoupler).

At 1/16 microstepping, 300 RPM requires 16kHz — right at the limit.
**Recommendation: use 1/8 microstepping** → 8kHz max, well within all limits.

### pigpio DMA capability on Pi Zero W

| Method           | Max reliable freq | Jitter       | Notes                    |
|------------------|-------------------|--------------|--------------------------|
| RPi.GPIO toggle  | <5 kHz            | 50–200μs     | Unusable for steppers    |
| pigpio software  | ~25 kHz           | <5μs         | DMA-based, CPU-independent|
| pigpio hardware  | >1 MHz            | <1μs         | GPIO12/18 only (2 ch)    |

**pigpio DMA wave generation at 8kHz: trivially achievable.** The DMA engine
runs independently of the CPU, so CRSF parsing in Python doesn't affect
step timing. Two independent frequencies on two pins — confirmed supported.

### CRSF parsing overhead

| Parameter        | Value                |
|------------------|----------------------|
| CRSF frame size  | 26 bytes max         |
| Frame rate       | 50–500 Hz (matches ELRS packet rate) |
| Baud rate        | 420,000              |
| Parse time       | <1ms per frame in Python |
| CPU budget       | ~5–15% of single core at 150Hz |

**Verdict: RPi Zero W can handle both CRSF parsing and dual stepper control
simultaneously without issues.** The DMA engine handles step pulses; the CPU
handles CRSF parsing and speed/direction mapping. These are decoupled.

---

## GPIO Pin Assignment

| RPi GPIO | BCM Pin | Function         | Wire to              |
|----------|---------|------------------|-----------------------|
| GPIO14   | TXD     | (unused or telemetry back to ELRS) | — |
| GPIO15   | RXD     | CRSF receive     | ELRS RX TX pin        |
| GPIO18   | PWM0    | STEP left motor  | TB6560 #1 CLK+ (via level shifter) |
| GPIO12   | PWM1    | STEP right motor | TB6560 #2 CLK+ (via level shifter) |
| GPIO23   | —       | DIR left motor   | TB6560 #1 CW+ (via level shifter)  |
| GPIO24   | —       | DIR right motor  | TB6560 #2 CW+ (via level shifter)  |
| GND      | —       | Common ground    | TB6560 CLK-/CW-/EN-, ELRS GND      |

GPIO18 and GPIO12 are the two hardware PWM channels — ideal for step pulses.

---

## Software Architecture

```
┌─────────────────────────────────────────────┐
│              Python main loop               │
│                                             │
│  ┌──────────┐    ┌────────────────────────┐ │
│  │ CRSF     │    │ Motor Controller       │ │
│  │ Parser   │───►│                        │ │
│  │ (pyserial│    │ ch1 (throttle) ──┐     │ │
│  │ 420kbaud)│    │ ch2 (steering) ──┤     │ │
│  └──────────┘    │                  ▼     │ │
│                  │ Differential mixer:    │ │
│                  │  left  = throttle + st │ │
│                  │  right = throttle - st │ │
│                  │         │         │    │ │
│                  │    set_freq(L) set_freq(R)│
│                  └────────────────────────┘ │
│                         │                   │
│  ┌──────────────────────┴──────────────────┐│
│  │ pigpio daemon (C, DMA)                  ││
│  │ GPIO18: HW PWM → step pulses left      ││
│  │ GPIO12: HW PWM → step pulses right     ││
│  │ GPIO23: write → DIR left               ││
│  │ GPIO24: write → DIR right              ││
│  └─────────────────────────────────────────┘│
└─────────────────────────────────────────────┘
```

### Key modules

1. **crsf_parser.py** — reads UART, parses CRSF frames, extracts channel values (988–2012μs → normalized -1.0 to +1.0)
2. **mixer.py** — differential drive mixing: converts (throttle, steering) → (left_speed, right_speed, left_dir, right_dir)
3. **motor_driver.py** — translates speed 0.0–1.0 → step frequency 0–8000Hz via pigpio hardware PWM; sets DIR pins
4. **failsafe.py** — monitors CRSF link quality; if no valid frame for >500ms, ramp motors to zero
5. **main.py** — event loop tying it all together

### Differential mixer logic

```python
def mix(throttle: float, steering: float) -> tuple:
    """
    throttle: -1.0 (full reverse) to +1.0 (full forward)
    steering: -1.0 (full left) to +1.0 (full right)
    returns: (left_speed, left_dir, right_speed, right_dir)
    """
    left  = throttle + steering
    right = throttle - steering

    # Clamp to [-1.0, 1.0]
    left  = max(-1.0, min(1.0, left))
    right = max(-1.0, min(1.0, right))

    left_dir  = 1 if left >= 0 else 0
    right_dir = 1 if right >= 0 else 0

    left_speed  = abs(left)
    right_speed = abs(right)

    return left_speed, left_dir, right_speed, right_dir
```

### pigpio motor control

```python
import pigpio

STEP_LEFT  = 18   # HW PWM channel 0
STEP_RIGHT = 12   # HW PWM channel 1
DIR_LEFT   = 23
DIR_RIGHT  = 24

MAX_FREQ = 8000   # Hz, 1/8 microstepping, ~300 RPM

pi = pigpio.pi()

def set_motor(speed: float, direction: int, step_pin: int, dir_pin: int):
    """
    speed: 0.0 to 1.0
    direction: 0 or 1
    """
    pi.write(dir_pin, direction)

    if speed < 0.01:
        pi.hardware_PWM(step_pin, 0, 0)  # stop
    else:
        freq = int(speed * MAX_FREQ)
        pi.hardware_PWM(step_pin, freq, 500000)  # 50% duty cycle
```

---

## DIP Switch Recommendations for TB6560

For rover use with NEMA17 (1.5A rated) at 4S voltage:

| Switch    | Setting | Purpose                                   |
|-----------|---------|-------------------------------------------|
| Current   | 1.2–1.5A| Match motor rating, prevent overheating   |
| Microstep | 1/8     | Balance: smooth motion vs. frequency budget|
| Decay     | 25%     | Good for low-speed torque (rover speeds)  |
| Stop current| 50%   | Hold torque when stopped on incline       |

---

## Dependencies

```
# System packages
sudo apt install python3-pip pigpio python3-pigpio

# Enable pigpio daemon at boot
sudo systemctl enable pigpiod
sudo systemctl start pigpiod

# Python packages
pip3 install pyserial
```

### /boot/config.txt additions

```
# Free PL011 UART from Bluetooth
dtoverlay=disable-bt

# Disable serial console (also do via raspi-config)
enable_uart=1
```

---

## Risk Register

| Risk                        | Impact | Mitigation                              |
|-----------------------------|--------|-----------------------------------------|
| 3.3V marginal for optocoupler| Motor misses steps | NPN level shifter (4 transistors) |
| CRSF link loss              | Runaway rover | Failsafe: stop motors after 500ms timeout |
| Pi kernel panic / freeze    | Total loss of control | Watchdog timer (`bcm2835_wdt`) auto-reboots |
| Stepper overheating         | Motor damage | Set current DIP to rated value, add heatsinks |
| Single-core CPU overload    | Missed CRSF frames | pigpio DMA decouples step gen from CPU |
| 6N137 freq limit at 15kHz  | Max speed cap | Use 1/8 microstepping (8kHz max) |
