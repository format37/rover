# Rover wiring diagram

RPi Zero W → 2N2222A NPN level shifters → TB6560 stepper drivers, plus ELRS
receiver on UART. See `wiring-diagram.py` for the schematic source.

## Header pin map (current)

| Function          | RPi GPIO | Header pin | Notes                          |
|-------------------|----------|------------|--------------------------------|
| ELRS TX → RPi RX  | GPIO15   | 10         | CRSF data in (required)        |
| ELRS RX ← RPi TX  | GPIO14   | 8          | Telemetry back (optional)      |
| STEP left         | GPIO18   | 12         | PWM0 (hardware PWM)            |
| STEP right        | GPIO12   | 32         | PWM1 (hardware PWM)            |
| DIR left          | GPIO23   | 16         | Through NPN level shifter      |
| DIR right         | GPIO24   | 18         | Through NPN level shifter      |
| 5V to ELRS        | 5V       | 2 or 4     |                                |
| GND (common)      | GND      | 6          | RPi / buck / TB6560 share rail |

ELRS wiring is **crossed**: ELRS TX → RPi RXD, ELRS RX ← RPi TXD.

## TB6560 channel topology

Each motor-control line goes through a 2N2222A in common-emitter:

```
GPIO ── 1 kΩ ── B
                E ── GND
                C ── TB6560 CLK− or CW−   (5V on CLK+/CW+ via opto + 330 Ω)
```

- Ib = (3.3 − 0.7) / 1 kΩ ≈ 2.6 mA → saturated
- Ic = (5 − 1.2 − 0.2) / 330 Ω ≈ 10.9 mA ✓
- **Single-NPN inverts the signal** — `DIR_INVERTED` in the demo script
  compensates.

## Proposed additions (transistor-switched outputs)

Three new NPN channels, same topology as DIR L/R. All three drive the
transistor base via 1 kΩ; the load sits between 5 V and the collector
(active-high logic from the RPi side, transistor-ON pulls the load line to
GND).

| Function                     | RPi GPIO | Header pin | Boot state | Transistor                          |
|------------------------------|----------|------------|------------|-------------------------------------|
| TB6560 EN (both drivers)     | GPIO25   | 22         | LOW (off)  | 2N2222A                             |
| Camera + VTX power           | GPIO22   | 15         | LOW (off)  | 2N2222A (MOSFET later for O4 Pro)   |
| Aux output (laser, …)        | GPIO27   | 13         | LOW (off)  | 2N2222A                             |

### Why these pins

- All three are in the GPIO9–27 range → default **LOW at boot**, so the loads
  stay off until firmware asserts them. Critical for motor EN (no twitch at
  startup), camera (clean power sequence), and laser (safety).
- All three are free — no UART, I²C, SPI, or in-use PWM conflict.
- GPIO25 (pin 22) is adjacent to GPIO24 (pin 18) → keeps the EN trace next to
  the existing DIR cluster, easy fan-out to both TB6560 EN− inputs.
- GPIO22 (pin 15) and GPIO27 (pin 13) sit on the same header side as the
  motor-control bank, keeping the level-shifter board compact.

### Camera channel sizing

**Current build — Foxeer Mini Predator 5 + analog VTX (lowest-power mode):**
camera ~150 mA, 25 mW VTX ~50–100 mA → ~250 mA total. Well within the 2N2222A
envelope. Add a 10 Ω in series with the 5V feed to soften VTX inrush.

**Future — DJI O4 Air Unit Pro:** runs at 7.4–26.4 V, ~1–1.5 A peak. The
2N2222A is not adequate; swap to a logic-level MOSFET (likely high-side
P-channel, since the load runs from pack voltage rather than 5 V). Pin choice
stays GPIO22 — only the switching device changes. Revisit MOSFET selection
when the O4 Pro arrives.

### TB6560 EN wiring (single line, both drivers)

TB6560 EN is active-low: drive EN− to GND to **enable**. Wire one transistor's
collector to **both** EN− pins (driver #1 and driver #2 in parallel); EN+ on
each driver goes to 5 V.

```
GPIO25 ── 1 kΩ ── B(2N2222A)
                  E ── GND
                  C ──┬── TB6560 #1 EN−
                      └── TB6560 #2 EN−
TB6560 #1 EN+ ── 5V
TB6560 #2 EN+ ── 5V
```

GPIO25 HIGH → transistor ON → EN− pulled to GND → **drivers enabled**.
GPIO25 LOW (boot default) → transistor OFF → EN− floats high via opto →
**drivers disabled**.

### Control logic (firmware side)

Each output is the AND of an ELRS channel (mapped to a switch) and an optional
software gate:

```
motor_en_out  =  elrs_switch_motors  AND  software_wants_motion
camera_out    =  elrs_switch_camera
aux_out       =  elrs_switch_aux
```

The motor channel adds the software gate so the rover can drop EN when idle
(saves driver heat and stepper holding current) even while the radio switch is
left in the "armed" position.
