"""
HUD overlay renderer for video composer.
Draws retro-futuristic servo + track state indicator.
"""

import math
import cv2
import numpy as np
import yaml
from pathlib import Path


def load_hud_config(path: str = None) -> dict:
    if path is None:
        path = str(Path(__file__).parent / "hud_config.yaml")
    with open(path) as f:
        return yaml.safe_load(f)["hud"]


def _t(color):
    """Config color list to BGR tuple."""
    return tuple(int(c) for c in color)


def _draw_rounded_rect(img, x, y, w, h, r, color, thickness=1, fill=False):
    """Draw a rounded rectangle."""
    r = min(r, w // 2, h // 2)
    if fill:
        # Fill body
        cv2.rectangle(img, (x + r, y), (x + w - r, y + h), color, -1)
        cv2.rectangle(img, (x, y + r), (x + w, y + h - r), color, -1)
        # Fill corners
        cv2.ellipse(img, (x + r, y + r), (r, r), 180, 0, 90, color, -1)
        cv2.ellipse(img, (x + w - r, y + r), (r, r), 270, 0, 90, color, -1)
        cv2.ellipse(img, (x + w - r, y + h - r), (r, r), 0, 0, 90, color, -1)
        cv2.ellipse(img, (x + r, y + h - r), (r, r), 90, 0, 90, color, -1)
    else:
        # Outline
        cv2.line(img, (x + r, y), (x + w - r, y), color, thickness)
        cv2.line(img, (x + r, y + h), (x + w - r, y + h), color, thickness)
        cv2.line(img, (x, y + r), (x, y + h - r), color, thickness)
        cv2.line(img, (x + w, y + r), (x + w, y + h - r), color, thickness)
        cv2.ellipse(img, (x + r, y + r), (r, r), 180, 0, 90, color, thickness)
        cv2.ellipse(img, (x + w - r, y + r), (r, r), 270, 0, 90, color, thickness)
        cv2.ellipse(img, (x + w - r, y + h - r), (r, r), 0, 0, 90, color, thickness)
        cv2.ellipse(img, (x + r, y + h - r), (r, r), 90, 0, 90, color, thickness)


def _draw_track(overlay, cx, cy, velocity, cfg, color_cfg):
    """Draw a single track indicator. velocity: + forward, - backward, 0 stopped."""
    tw = cfg["width"]
    th = cfg["height"]
    cr = cfg["corner_radius"]
    x = cx - tw // 2
    y = cy - th // 2

    primary = _t(color_cfg["color_primary"])
    accent = _t(color_cfg["color_accent"])
    dim = _t(color_cfg["color_dim"])
    negative = _t(color_cfg["color_negative"])
    bg = _t(color_cfg["color_bg"])

    # Background fill
    _draw_rounded_rect(overlay, x, y, tw, th, cr, bg, fill=True)

    speed = abs(velocity)
    forward = velocity >= 0

    # Speed lines inside the track
    if speed > 0.005:
        color = accent if forward else negative
        n_lines = max(1, int(speed * cfg["max_lines"]))
        line_t = cfg["line_thickness"]

        # Lines region (inside the rounded rect with some padding)
        pad = cr + 2
        region_top = y + pad
        region_bot = y + th - pad
        region_h = region_bot - region_top

        if n_lines > 0 and region_h > 0:
            spacing = region_h / (n_lines + 1)
            # Diagonal angle: forward = /, backward = \
            slant = 6 if forward else -6

            for j in range(n_lines):
                ly = int(region_top + spacing * (j + 1))
                x1 = x + 4
                x2 = x + tw - 4
                cv2.line(overlay, (x1 + slant, ly), (x2 - slant, ly),
                         color, line_t, cv2.LINE_AA)

        # Direction arrow at center
        arrow_y = cy
        arrow_sz = 6
        if forward:
            pts = np.array([[cx, arrow_y - arrow_sz],
                            [cx - arrow_sz, arrow_y + arrow_sz],
                            [cx + arrow_sz, arrow_y + arrow_sz]])
        else:
            pts = np.array([[cx, arrow_y + arrow_sz],
                            [cx - arrow_sz, arrow_y - arrow_sz],
                            [cx + arrow_sz, arrow_y - arrow_sz]])
        cv2.polylines(overlay, [pts], True, color, 1, cv2.LINE_AA)
    else:
        # Stopped indicator: small dash
        cv2.line(overlay, (cx - 5, cy), (cx + 5, cy), dim, 1, cv2.LINE_AA)

    # Outline
    outline_color = accent if speed > 0.005 else dim
    _draw_rounded_rect(overlay, x, y, tw, th, cr, outline_color, thickness=1)

    # Speed label below
    label = f"{velocity:+.2f}"
    font = cv2.FONT_HERSHEY_SIMPLEX
    fs = color_cfg["font_scale"]
    ft = color_cfg["font_thickness"]
    (lw, lh), _ = cv2.getTextSize(label, font, fs, ft)
    lx = cx - lw // 2
    ly_pos = y + th + lh + 6
    text_color = accent if speed > 0.005 else dim
    cv2.putText(overlay, label, (lx, ly_pos), font, fs, text_color, ft, cv2.LINE_AA)


def _draw_servo(overlay, cx, cy, angle, target, cfg, color_cfg):
    """Draw servo angle indicator. angle: 0-180 degrees."""
    radius = cfg["radius"]
    needle_len = cfg["needle_length"]
    primary = _t(color_cfg["color_primary"])
    accent = _t(color_cfg["color_accent"])
    dim = _t(color_cfg["color_dim"])
    bg = _t(color_cfg["color_bg"])

    # Arc background (semicircle, 0=right, 180=left)
    # Draw arc: 0° is at 3 o'clock in OpenCV, we want 0° servo = right
    # Servo 0° = right, 90° = center/up, 180° = left
    # Map to OpenCV: servo angle → drawing angle (180 - servo for left-right flip)
    arc_center = (cx, cy)

    # Background filled semicircle
    cv2.ellipse(overlay, arc_center, (radius, radius), 0, 180, 360, bg, -1)

    # Arc outline
    cv2.ellipse(overlay, arc_center, (radius, radius), 0, 180, 360,
                dim, cfg["arc_thickness"], cv2.LINE_AA)

    # Tick marks at 0, 45, 90, 135, 180
    for tick_deg in [0, 45, 90, 135, 180]:
        rad = math.radians(180 + tick_deg)  # map servo 0→right, 180→left
        x1 = int(cx + (radius - cfg["tick_length"]) * math.cos(rad))
        y1 = int(cy + (radius - cfg["tick_length"]) * math.sin(rad))
        x2 = int(cx + radius * math.cos(rad))
        y2 = int(cy + radius * math.sin(rad))
        tick_color = primary if tick_deg == 90 else dim
        cv2.line(overlay, (x1, y1), (x2, y2), tick_color, 1, cv2.LINE_AA)

    # Target angle indicator (thin line)
    if target is not None:
        tgt_rad = math.radians(180 + target)
        tx = int(cx + (needle_len - 4) * math.cos(tgt_rad))
        ty = int(cy + (needle_len - 4) * math.sin(tgt_rad))
        cv2.line(overlay, (cx, cy), (tx, ty), dim, 1, cv2.LINE_AA)

    # Needle (current angle)
    needle_rad = math.radians(180 + angle)
    nx = int(cx + needle_len * math.cos(needle_rad))
    ny = int(cy + needle_len * math.sin(needle_rad))

    # Needle body — wedge shape
    perp_rad = needle_rad + math.pi / 2
    base_w = 4
    bx1 = int(cx + base_w * math.cos(perp_rad))
    by1 = int(cy + base_w * math.sin(perp_rad))
    bx2 = int(cx - base_w * math.cos(perp_rad))
    by2 = int(cy - base_w * math.sin(perp_rad))
    pts = np.array([[nx, ny], [bx1, by1], [bx2, by2]])
    cv2.fillPoly(overlay, [pts], accent, cv2.LINE_AA)
    cv2.polylines(overlay, [pts], True, accent, 1, cv2.LINE_AA)

    # Center dot
    cv2.circle(overlay, (cx, cy), 3, primary, -1, cv2.LINE_AA)

    # Angle label below
    deviation = angle - 90
    label = f"{deviation:+.0f}"
    font = cv2.FONT_HERSHEY_SIMPLEX
    fs = color_cfg["font_scale"]
    ft = color_cfg["font_thickness"]
    (lw, lh), _ = cv2.getTextSize(label, font, fs, ft)
    lx = cx - lw // 2
    ly_pos = cy + lh + 6
    cv2.putText(overlay, label, (lx, ly_pos), font, fs, accent, ft, cv2.LINE_AA)


def draw_hud(frame: np.ndarray, servo_state: dict, cfg: dict) -> np.ndarray:
    """Draw the full HUD overlay on the frame.

    servo_state keys: servo_angle, servo_target, left_speed, left_dir,
                      right_speed, right_dir
    """
    img_h, img_w = frame.shape[:2]

    tc = cfg["track"]
    sc = cfg["servo"]
    gap = cfg["gap"]
    my = cfg["margin_y"]

    # Compute signed velocities
    # Left track (index 0): forward when dir=0
    ls = servo_state.get("left_speed", 0)
    ld = servo_state.get("left_dir", 0)
    left_vel = ls if ld == 0 else -ls

    # Right track (index 1): forward when dir=1
    rs = servo_state.get("right_speed", 0)
    rd = servo_state.get("right_dir", 0)
    right_vel = rs if rd == 1 else -rs

    servo_angle = servo_state.get("servo_angle", 90)
    servo_target = servo_state.get("servo_target", None)

    # Layout: [left_track] [gap] [servo] [gap] [right_track]
    total_w = tc["width"] + gap + sc["radius"] * 2 + gap + tc["width"]
    total_h = max(tc["height"], sc["radius"]) + 24  # extra for labels

    # Position
    position = cfg.get("position", "left")
    if position == "center":
        panel_x = (img_w - total_w) // 2
    else:
        panel_x = cfg.get("margin_x", 30)
    panel_y = img_h - my - total_h

    # Create overlay for alpha blending
    overlay = frame.copy()

    # Panel background
    panel_pad = 12
    cv2.rectangle(overlay,
                  (panel_x - panel_pad, panel_y - panel_pad),
                  (panel_x + total_w + panel_pad, panel_y + total_h + panel_pad),
                  _t(cfg["color_bg"]), -1)

    # Blend background
    alpha = cfg["panel_alpha"]
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

    # Element centers (vertical center of panel, with track bottoms aligned)
    track_cy = panel_y + total_h // 2 - 6
    servo_cy = panel_y + sc["radius"] + 2

    # Color config for sub-drawing functions
    color_cfg = {k: cfg[k] for k in cfg if k.startswith("color_")}
    color_cfg["font_scale"] = cfg["font_scale"]
    color_cfg["font_thickness"] = cfg["font_thickness"]

    # Left track
    lt_cx = panel_x + tc["width"] // 2
    _draw_track(frame, lt_cx, track_cy, left_vel, tc, color_cfg)

    # Servo
    servo_cx = panel_x + tc["width"] + gap + sc["radius"]
    _draw_servo(frame, servo_cx, servo_cy, servo_angle, servo_target, sc, color_cfg)

    # Right track
    rt_cx = panel_x + tc["width"] + gap + sc["radius"] * 2 + gap + tc["width"] // 2
    _draw_track(frame, rt_cx, track_cy, right_vel, tc, color_cfg)

    return frame
