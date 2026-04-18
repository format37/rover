"""Wiring diagram: RPi Zero W → 2N2222A level shifters → TB6560 stepper drivers.

Clean schematic with manual boxes and power flag labels.
Usage:
    python3 wiring-diagram.py --save          # SVG
    python3 wiring-diagram.py --save --png    # PNG at 200 dpi
"""

import schemdraw
import schemdraw.elements as elm
import sys


def box(d, x, y, w, h, label="", sublabel="", lw=2):
    """Rectangle from (x,y) with size (w,h), centered label."""
    d.add(elm.Line().at((x, y)).to((x + w, y)).linewidth(lw))
    d.add(elm.Line().at((x + w, y)).to((x + w, y + h)).linewidth(lw))
    d.add(elm.Line().at((x + w, y + h)).to((x, y + h)).linewidth(lw))
    d.add(elm.Line().at((x, y + h)).to((x, y)).linewidth(lw))
    cx, cy = x + w / 2, y + h / 2
    if label and sublabel:
        d.add(elm.Label().at((cx, cy + 0.35)).label(label, loc="center"))
        d.add(elm.Label().at((cx, cy - 0.35)).label(sublabel, loc="center"))
    elif label:
        d.add(elm.Label().at((cx, cy)).label(label, loc="center"))


def channel(d, x, y, gpio, sig):
    """GPIO dot → 1 kΩ → 2N2222A NPN.  Returns (collector, emitter) coords."""
    d.add(elm.Dot().at((x, y)))
    d.add(elm.Label().at((x - 0.15, y)).label(gpio, loc="left"))
    R = d.add(elm.Resistor().right().at((x, y)).label("1 kΩ", loc="top"))
    Q = d.add(elm.BjtNpn().right().anchor("base").at(R.end))
    mid_y = (Q.collector[1] + Q.emitter[1]) / 2
    d.add(elm.Label().at((Q.collector[0] + 0.55, mid_y)).label(sig, loc="right"))
    return tuple(Q.collector), tuple(Q.emitter)


def wire_to_pin(d, col_xy, pin_xy, jx):
    """Route collector → TB6560 pin via L-bend at x=jx."""
    cx, cy = col_xy
    px, py = pin_xy
    # Up from collector
    d.add(elm.Line().at((cx, cy)).to((cx, py + 0.5)))
    # Right to junction x
    d.add(elm.Line().at((cx, py + 0.5)).to((jx, py + 0.5)))
    # Down to pin y
    d.add(elm.Line().at((jx, py + 0.5)).to((jx, py)))
    # Right to pin
    d.add(elm.Line().at((jx, py)).to((px, py)))


def emi_gnd(d, emi_xy, rail_y, route_x=None):
    """Emitter → GND rail, optionally routed via route_x to avoid overlaps."""
    ex, ey = emi_xy
    if route_x is not None and route_x != ex:
        d.add(elm.Line().at((ex, ey)).to((route_x, ey)).color("seagreen"))
        d.add(elm.Line().at((route_x, ey)).to((route_x, rail_y)).color("seagreen"))
        d.add(elm.Dot().at((route_x, rail_y)).color("seagreen"))
    else:
        d.add(elm.Line().at((ex, ey)).to((ex, rail_y)).color("seagreen"))
        d.add(elm.Dot().at((ex, rail_y)).color("seagreen"))


def power_flag(d, pin_xy, label="5V", side="left"):
    """Small power flag: short stub + label, no long wires."""
    px, py = pin_xy
    stub = 0.5
    if side == "left":
        d.add(elm.Line().at((px, py)).to((px - stub, py)).color("orangered"))
        d.add(elm.Label().at((px - stub - 0.1, py)).label(label, loc="left")
              .color("orangered"))
    else:
        d.add(elm.Line().at((px, py)).to((px + stub, py)).color("orangered"))
        d.add(elm.Label().at((px + stub + 0.1, py)).label(label, loc="right")
              .color("orangered"))


def build() -> schemdraw.Drawing:
    d = schemdraw.Drawing(unit=2.2)
    d.config(fontsize=10)

    # ── layout ──
    RPI_X, RPI_W    = 0.5, 2.8
    RPI_RIGHT       = RPI_X + RPI_W
    CH_X            = 4.0
    TB_X, TB_W      = 11.0, 3.0
    TB_H            = 4.2
    G1, G2          = 3.5, -3.5          # group centres
    CS              = 2.6                 # STEP↔DIR spacing
    RAIL_GND        = -7.0

    # ── RPi block ──
    rpi_top = G1 + CS / 2 + 1.0
    rpi_bot = G2 - CS / 2 - 1.0
    box(d, RPI_X, rpi_bot, RPI_W, rpi_top - rpi_bot,
        label="RPi Zero W", sublabel="3.3 V logic")

    # ── GND rail ──
    d.add(elm.Line().at((CH_X - 0.5, RAIL_GND))
          .to((TB_X + TB_W + 0.5, RAIL_GND))
          .color("seagreen").linewidth(2.5))
    d.add(elm.Label()
          .at(((CH_X + TB_X + TB_W) / 2, RAIL_GND - 0.5))
          .label("GND (common — RPi, buck converter, TB6560)", loc="center")
          .color("seagreen"))

    # ════════════════════════════
    # GROUP 1 — Left motor
    # ════════════════════════════
    s1y, d1y = G1 + CS / 2, G1 - CS / 2

    c1c, c1e = channel(d, CH_X, s1y, "GPIO18", "STEP L")
    c2c, c2e = channel(d, CH_X, d1y, "GPIO23", "DIR  L")

    # RPi → channel wires
    for y in (s1y, d1y):
        d.add(elm.Line().at((RPI_RIGHT, y)).to((CH_X, y)))
        d.add(elm.Dot().at((RPI_RIGHT, y)))

    # TB6560 #1 block
    box(d, TB_X, G1 - TB_H / 2, TB_W, TB_H,
        label="TB6560 #1", sublabel="Left motor")

    # pins
    tb1 = {
        "CLK+": (TB_X, G1 + 1.3),
        "CLK−": (TB_X, G1 + 0.45),
        "CW+":  (TB_X, G1 - 0.45),
        "CW−":  (TB_X, G1 - 1.3),
    }
    for name, (px, py) in tb1.items():
        d.add(elm.Dot().at((px, py)))
        d.add(elm.Label().at((px - 0.15, py)).label(name, loc="left"))

    # collector wires → minus-pins
    wire_to_pin(d, c1c, tb1["CLK−"], jx=8.8)
    wire_to_pin(d, c2c, tb1["CW−"],  jx=9.5)

    # 5V power flags on plus-pins (no long wires!)
    power_flag(d, tb1["CLK+"], "5V")
    power_flag(d, tb1["CW+"],  "5V")

    # emitters → GND
    emi_gnd(d, c1e, RAIL_GND, route_x=7.8)
    emi_gnd(d, c2e, RAIL_GND, route_x=8.2)

    # ════════════════════════════
    # GROUP 2 — Right motor
    # ════════════════════════════
    s2y, d2y = G2 + CS / 2, G2 - CS / 2

    c3c, c3e = channel(d, CH_X, s2y, "GPIO12", "STEP R")
    c4c, c4e = channel(d, CH_X, d2y, "GPIO24", "DIR  R")

    for y in (s2y, d2y):
        d.add(elm.Line().at((RPI_RIGHT, y)).to((CH_X, y)))
        d.add(elm.Dot().at((RPI_RIGHT, y)))

    box(d, TB_X, G2 - TB_H / 2, TB_W, TB_H,
        label="TB6560 #2", sublabel="Right motor")

    tb2 = {
        "CLK+": (TB_X, G2 + 1.3),
        "CLK−": (TB_X, G2 + 0.45),
        "CW+":  (TB_X, G2 - 0.45),
        "CW−":  (TB_X, G2 - 1.3),
    }
    for name, (px, py) in tb2.items():
        d.add(elm.Dot().at((px, py)))
        d.add(elm.Label().at((px - 0.15, py)).label(name, loc="left"))

    wire_to_pin(d, c3c, tb2["CLK−"], jx=8.8)
    wire_to_pin(d, c4c, tb2["CW−"],  jx=9.5)

    power_flag(d, tb2["CLK+"], "5V")
    power_flag(d, tb2["CW+"],  "5V")

    emi_gnd(d, c3e, RAIL_GND, route_x=7.8)
    emi_gnd(d, c4e, RAIL_GND, route_x=8.2)

    # ── dashed separator ──
    d.add(elm.Line().at((RPI_RIGHT + 0.5, 0)).to((TB_X + TB_W + 0.5, 0))
          .linestyle("--").color("lightgray").linewidth(0.4))

    # ── notes ──
    d.add(elm.Label().at((8.0, RAIL_GND - 1.5)).label(
        "Common anode:  5V → CLK+/CW+ → 330Ω (onboard) → opto LED → "
        "CLK−/CW− → collector → GND",
        loc="center"))
    d.add(elm.Label().at((8.0, RAIL_GND - 2.1)).label(
        "Ib = (3.3−0.7)/1kΩ = 2.6 mA → saturated → "
        "Ic = (5−1.2−0.2)/330Ω = 10.9 mA  ✓",
        loc="center"))

    return d


if __name__ == "__main__":
    drawing = build()
    if "--save" in sys.argv:
        fmt = "png" if "--png" in sys.argv else "svg"
        out = f"wiring-diagram.{fmt}"
        drawing.save(out, dpi=200)
        print(f"Saved: {out}")
    else:
        drawing.draw()