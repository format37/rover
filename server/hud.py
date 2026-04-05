"""
HUD overlay renderer for video composer.
Draws retro-futuristic track state + per-frame top-down depth projection.
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
        cv2.rectangle(img, (x + r, y), (x + w - r, y + h), color, -1)
        cv2.rectangle(img, (x, y + r), (x + w, y + h - r), color, -1)
        cv2.ellipse(img, (x + r, y + r), (r, r), 180, 0, 90, color, -1)
        cv2.ellipse(img, (x + w - r, y + r), (r, r), 270, 0, 90, color, -1)
        cv2.ellipse(img, (x + w - r, y + h - r), (r, r), 0, 0, 90, color, -1)
        cv2.ellipse(img, (x + r, y + h - r), (r, r), 90, 0, 90, color, -1)
    else:
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

    accent = _t(color_cfg["color_accent"])
    dim = _t(color_cfg["color_dim"])
    negative = _t(color_cfg["color_negative"])
    bg = _t(color_cfg["color_bg"])

    # Background fill
    _draw_rounded_rect(overlay, x, y, tw, th, cr, bg, fill=True)

    speed = abs(velocity)
    forward = velocity >= 0

    speed_min = cfg.get("speed_min", 0.0)
    speed_max = cfg.get("speed_max", 1.0)
    if speed > 0.005:
        speed_norm = min(1.0, max(0.0, (speed - speed_min) / (speed_max - speed_min)))
    else:
        speed_norm = 0.0

    if speed > 0.005:
        color = accent if forward else negative
        n_lines = max(1, round(speed_norm * cfg["max_lines"]))
        line_t = cfg["line_thickness"]

        pad = cr + 2
        region_top = y + pad
        region_bot = y + th - pad
        region_h = region_bot - region_top

        if n_lines > 0 and region_h > 0:
            spacing = region_h / (n_lines + 1)
            slant = 6 if forward else -6
            for j in range(n_lines):
                ly = int(region_top + spacing * (j + 1))
                cv2.line(overlay, (x + 4 + slant, ly), (x + tw - 4 - slant, ly),
                         color, line_t, cv2.LINE_AA)

        # Direction arrow
        arrow_sz = 6
        if forward:
            pts = np.array([[cx, cy - arrow_sz],
                            [cx - arrow_sz, cy + arrow_sz],
                            [cx + arrow_sz, cy + arrow_sz]])
        else:
            pts = np.array([[cx, cy + arrow_sz],
                            [cx - arrow_sz, cy - arrow_sz],
                            [cx + arrow_sz, cy - arrow_sz]])
        cv2.polylines(overlay, [pts], True, color, 1, cv2.LINE_AA)
    else:
        cv2.line(overlay, (cx - 5, cy), (cx + 5, cy), dim, 1, cv2.LINE_AA)

    outline_color = accent if speed > 0.005 else dim
    _draw_rounded_rect(overlay, x, y, tw, th, cr, outline_color, thickness=1)

    # Speed label below
    label = f"{velocity:+.2f}"
    font = cv2.FONT_HERSHEY_SIMPLEX
    fs = color_cfg["font_scale"]
    ft = color_cfg["font_thickness"]
    (lw, lh), _ = cv2.getTextSize(label, font, fs, ft)
    text_color = accent if speed > 0.005 else dim
    cv2.putText(overlay, label, (cx - lw // 2, y + th + lh + 6),
                font, fs, text_color, ft, cv2.LINE_AA)


def _draw_depth_map(frame, cx, cy, depth_image, cfg, color_cfg):
    """Top-down depth projection: rover at bottom-center, obstacles project upward.

    Renders onto a local canvas then blits to frame — range rings and all other
    elements are naturally clipped to the widget boundary, never bleeding into
    adjacent track indicators.
    """
    size = cfg.get("size", 150)
    max_range_m = cfg.get("max_range_m", 4.0)
    stop_dist_m = cfg.get("stop_dist_m", 0.7)
    hfov_deg = cfg.get("hfov_deg", 87.0)
    step = cfg.get("subsample", 6)

    accent = _t(color_cfg["color_accent"])
    dim = _t(color_cfg["color_dim"])
    bg = _t(color_cfg["color_bg"])
    negative = _t(color_cfg["color_negative"])

    # Local canvas — all drawing stays within [0, size)
    canvas = np.full((size, size, 3), bg, dtype=np.uint8)

    # Rover at bottom-center of canvas (local coordinates)
    ox = size // 2
    oy = size - 10
    scale = (size - 14) / max_range_m  # pixels per meter

    # FOV cone lines
    hfov_half = math.radians(hfov_deg / 2)
    cone_len = int(max_range_m * scale)
    lx = int(ox - cone_len * math.sin(hfov_half))
    rx = int(ox + cone_len * math.sin(hfov_half))
    ty = oy - cone_len
    cv2.line(canvas, (ox, oy), (lx, ty), dim, 1, cv2.LINE_AA)
    cv2.line(canvas, (ox, oy), (rx, ty), dim, 1, cv2.LINE_AA)

    # Distance rings + labels — cv2 clips ellipses to canvas bounds automatically
    font = cv2.FONT_HERSHEY_SIMPLEX
    for d_m in [1.0, 2.0, 3.0, 4.0]:
        if d_m > max_range_m:
            continue
        r_px = int(d_m * scale)
        cv2.ellipse(canvas, (ox, oy), (r_px, r_px), 0, 180, 360, dim, 1, cv2.LINE_AA)
        lbl_x = ox + r_px + 2
        if lbl_x < size - 12:
            cv2.putText(canvas, f"{d_m:.0f}m", (lbl_x, oy - 2),
                        font, 0.3, dim, 1, cv2.LINE_AA)

    # Stop distance ring (warning color)
    stop_r = int(stop_dist_m * scale)
    if stop_r > 0:
        cv2.ellipse(canvas, (ox, oy), (stop_r, stop_r), 0, 180, 360,
                    negative, 1, cv2.LINE_AA)
        lbl_x = ox + stop_r + 2
        lbl_y = oy - stop_r // 2
        if lbl_x < size - 10 and lbl_y > 8:
            cv2.putText(canvas, f"{stop_dist_m:.1f}m", (lbl_x, lbl_y),
                        font, 0.3, negative, 1, cv2.LINE_AA)

    # Depth point cloud projection
    if depth_image is not None:
        dep_h, dep_w = depth_image.shape[:2]
        hfov_rad = math.radians(hfov_deg)

        # Sample middle 50% of rows (avoids ceiling noise and floor clutter)
        row_start = dep_h // 4
        row_end = dep_h * 3 // 4
        ys_idx = np.arange(row_start, row_end, step)
        xs_idx = np.arange(0, dep_w, step)
        gx, gy = np.meshgrid(xs_idx, ys_idx)

        d_mm = depth_image[gy, gx].astype(np.float32)
        valid = d_mm > 0
        d_m_arr = d_mm[valid] / 1000.0

        px_norm = gx[valid].astype(np.float32) / dep_w - 0.5
        ha = px_norm * hfov_rad

        x_w = d_m_arr * np.sin(ha)
        z_w = d_m_arr * np.cos(ha)

        map_x = (ox + x_w * scale).astype(np.int32)
        map_y = (oy - z_w * scale).astype(np.int32)

        # Clip to canvas bounds
        in_b = (map_x >= 0) & (map_x < size) & (map_y >= 0) & (map_y < size)
        map_x = map_x[in_b]
        map_y = map_y[in_b]
        d_f = d_m_arr[in_b]

        t = np.clip(d_f / max_range_m, 0.0, 1.0)
        canvas[map_y, map_x, 0] = (accent[0] * (1 - t) + dim[0] * t).astype(np.uint8)
        canvas[map_y, map_x, 1] = (accent[1] * (1 - t) + dim[1] * t).astype(np.uint8)
        canvas[map_y, map_x, 2] = (accent[2] * (1 - t) + dim[2] * t).astype(np.uint8)

    # Rover marker (filled triangle pointing forward/up)
    rover_pts = np.array([[ox, oy - 7], [ox - 5, oy + 1], [ox + 5, oy + 1]])
    cv2.fillPoly(canvas, [rover_pts], accent)

    # Widget border
    _draw_rounded_rect(canvas, 0, 0, size, size, 4, dim, thickness=1)

    # Blit canvas to frame — hard clip, nothing bleeds outside this region
    x0 = cx - size // 2
    y0 = cy - size // 2
    frame[y0:y0 + size, x0:x0 + size] = canvas


def draw_hud(frame: np.ndarray, track_state: dict, depth_image, cfg: dict,
             elapsed_sec: float = None) -> np.ndarray:
    """Draw HUD overlay: [left_track] [depth_map] [right_track].

    track_state keys: left_speed, left_dir, right_speed, right_dir
    depth_image: raw uint16 depth numpy array (mm units) or None
    elapsed_sec: seconds since session start (shown as timer when session_timer enabled)
    """
    img_h, img_w = frame.shape[:2]

    tc = cfg["track"]
    dmc = cfg["depth_map"]
    gap = cfg["gap"]
    my = cfg["margin_y"]

    ls = track_state.get("left_speed", 0)
    ld = track_state.get("left_dir", 0)
    left_vel = ls if ld == 1 else -ls

    rs = track_state.get("right_speed", 0)
    rd = track_state.get("right_dir", 0)
    right_vel = rs if rd == 1 else -rs

    dm_size = dmc.get("size", 150)
    total_w = tc["width"] + gap + dm_size + gap + tc["width"]
    total_h = max(tc["height"], dm_size) + 24  # extra for speed labels below tracks

    position = cfg.get("position", "center")
    if position == "center":
        panel_x = (img_w - total_w) // 2
    else:
        panel_x = cfg.get("margin_x", 30)
    panel_y = img_h - my - total_h

    # Panel background with alpha blend
    overlay = frame.copy()
    panel_pad = 12
    cv2.rectangle(overlay,
                  (panel_x - panel_pad, panel_y - panel_pad),
                  (panel_x + total_w + panel_pad, panel_y + total_h + panel_pad),
                  _t(cfg["color_bg"]), -1)
    cv2.addWeighted(overlay, cfg["panel_alpha"], frame, 1 - cfg["panel_alpha"], 0, frame)

    # Vertical center: align tracks and depth map
    dm_cy = panel_y + dm_size // 2
    track_cy = dm_cy

    color_cfg = {k: cfg[k] for k in cfg if k.startswith("color_")}
    color_cfg["font_scale"] = cfg["font_scale"]
    color_cfg["font_thickness"] = cfg["font_thickness"]

    # Depth map first (canvas-clipped) — then tracks drawn on top
    dm_cx = panel_x + tc["width"] + gap + dm_size // 2
    _draw_depth_map(frame, dm_cx, dm_cy, depth_image, dmc, color_cfg)

    lt_cx = panel_x + tc["width"] // 2
    _draw_track(frame, lt_cx, track_cy, left_vel, tc, color_cfg)

    rt_cx = panel_x + tc["width"] + gap + dm_size + gap + tc["width"] // 2
    _draw_track(frame, rt_cx, track_cy, right_vel, tc, color_cfg)

    # Session timer
    if elapsed_sec is not None and cfg.get("session_timer", True):
        mins, secs = divmod(int(elapsed_sec), 60)
        hrs, mins = divmod(mins, 60)
        timer_text = f"{hrs:d}:{mins:02d}:{secs:02d}"
        font = cv2.FONT_HERSHEY_SIMPLEX
        fs = cfg["font_scale"]
        ft = cfg["font_thickness"]
        accent = _t(cfg["color_accent"])
        (tw, th), _ = cv2.getTextSize(timer_text, font, fs, ft)
        tx = panel_x + total_w - tw
        ty = panel_y - panel_pad - 6
        cv2.putText(frame, timer_text, (tx, ty), font, fs, accent, ft, cv2.LINE_AA)

    return frame
