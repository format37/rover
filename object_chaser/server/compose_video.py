#!/usr/bin/env python3
"""
Compose video from a session: RGB frames + depth overlay on detected objects.

For each RGB frame, finds the closest YOLO detection and depth map by timestamp.
Detected objects get a depth-colormap crop placed above the RGB image with label.
"""

import argparse
import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import cv2
import numpy as np

from hud import load_hud_config, draw_hud


def parse_timestamp(name: str) -> float:
    """Parse filename timestamp into seconds since midnight."""
    # Format: 20260307_100125_257409
    ts = name.replace(".jpg", "").replace(".npy", "")
    parts = ts.split("_")
    # parts[0] = date, parts[1] = HHMMSS, parts[2] = microseconds
    t = parts[1]
    h, m, s = int(t[0:2]), int(t[2:4]), int(t[4:6])
    us = int(parts[2])
    return h * 3600 + m * 60 + s + us / 1_000_000


def find_closest(target_ts: float, candidates: list, max_gap: float) -> int:
    """Binary search for closest timestamp. Returns index or -1 if beyond max_gap."""
    if not candidates:
        return -1
    lo, hi = 0, len(candidates) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if candidates[mid][0] < target_ts:
            lo = mid + 1
        else:
            hi = mid
    # Check lo and lo-1
    best = lo
    if lo > 0 and abs(candidates[lo - 1][0] - target_ts) < abs(candidates[lo][0] - target_ts):
        best = lo - 1
    if abs(candidates[best][0] - target_ts) > max_gap:
        return -1
    return best


def _sample_depth(px, py, depth_image, sx, sy):
    """Sample depth value at image pixel (px, py)."""
    dep_h, dep_w = depth_image.shape[:2]
    dpx = min(dep_w - 1, max(0, int(px * sx)))
    dpy = min(dep_h - 1, max(0, int(py * sy)))
    return float(depth_image[dpy, dpx])


def _generate_adaptive_points(x1, y1, x2, y2, depth_image, sx, sy,
                              gamma=1.0, cutoff=0.0,
                              pct_near=5, pct_far=95):
    """Generate variable-density points: denser where depth is closer."""
    # LOD levels: (grid_step_divisor, closeness_threshold)
    # Level 0 (coarse): always present
    # Level 1+: only where closeness exceeds threshold
    levels = [
        (4, 0.0),    # 4x4 base — always
        (8, 0.15),   # 8x8 — mild detail
        (16, 0.35),  # 16x16 — medium
        (32, 0.55),  # 32x32 — fine
        (48, 0.75),  # 48x48 — ultra fine for very close
    ]

    w = x2 - x1
    h = y2 - y1

    # First pass: build a coarse closeness map for LOD decisions
    sample_n = 8
    depths = []
    for sy_i in range(sample_n + 1):
        for sx_i in range(sample_n + 1):
            px = x1 + w * sx_i / sample_n
            py = y1 + h * sy_i / sample_n
            d = _sample_depth(px, py, depth_image, sx, sy)
            if d > 0:
                depths.append(d)

    if not depths:
        return np.empty((0, 2)), np.empty(0), 0, 1

    d_min = np.percentile(depths, pct_near)
    d_max = np.percentile(depths, pct_far)
    d_range = max(d_max - d_min, 1)

    # Collect unique points across all LOD levels
    # Each level gets an offset (fraction of cell size) to break grid alignment
    offsets = [0.0, 0.37, 0.23, 0.41, 0.31]
    point_set = set()
    for li, (divisions, threshold) in enumerate(levels):
        cell_w = w / divisions
        cell_h = h / divisions
        off = offsets[li]
        for gy in range(divisions + 1):
            for gx in range(divisions + 1):
                px = x1 + w * gx / divisions + cell_w * off
                py = y1 + h * gy / divisions + cell_h * off
                px = min(max(px, x1), x2)
                py = min(max(py, y1), y2)
                d = _sample_depth(px, py, depth_image, sx, sy)
                if d > 0:
                    closeness = np.clip(1.0 - (d - d_min) / d_range, 0, 1)
                else:
                    closeness = 0
                if closeness < cutoff:
                    continue
                closeness = closeness ** gamma
                if closeness >= threshold:
                    key = (round(px, 1), round(py, 1))
                    point_set.add(key)

    if len(point_set) < 3:
        return np.empty((0, 2)), np.empty(0), d_min, d_range

    points = np.array(list(point_set), dtype=np.float64)
    # Sample depth at final points
    point_depths = np.array([
        _sample_depth(p[0], p[1], depth_image, sx, sy) for p in points
    ])

    return points, point_depths, d_min, d_range


def draw_depth_overlay(frame: np.ndarray, depth_image: np.ndarray,
                       detections: list, depth_scale: tuple,
                       mesh_cfg: dict = None) -> np.ndarray:
    """Draw Tron-style adaptive triangle mesh on detected objects."""
    img_h, img_w = frame.shape[:2]
    dep_h, dep_w = depth_image.shape[:2]
    sx = dep_w / img_w
    sy = dep_h / img_h

    max_displace = 30
    alpha_min = mesh_cfg.get("fill_alpha_min", 0.15) if mesh_cfg else 0.15
    alpha_max = mesh_cfg.get("fill_alpha_max", 0.40) if mesh_cfg else 0.40
    darken = mesh_cfg.get("darken", 0.5) if mesh_cfg else 0.5
    gamma = mesh_cfg.get("gamma", 1.0) if mesh_cfg else 1.0
    cutoff = mesh_cfg.get("cutoff", 0.0) if mesh_cfg else 0.0
    max_tri_area = mesh_cfg.get("max_triangle_area", 0) if mesh_cfg else 0
    pct_near = mesh_cfg.get("depth_pct_near", 5) if mesh_cfg else 5
    pct_far = mesh_cfg.get("depth_pct_far", 95) if mesh_cfg else 95

    # Build heatmap LUT from config: far → mid → near
    c_far = np.array(mesh_cfg.get("color_far", [255, 255, 255])) if mesh_cfg else np.array([255, 255, 255])
    c_mid = np.array(mesh_cfg.get("color_mid", [255, 200, 50])) if mesh_cfg else np.array([255, 200, 50])
    c_near = np.array(mesh_cfg.get("color_near", [50, 255, 80])) if mesh_cfg else np.array([50, 255, 80])
    heatmap_lut = np.zeros((256, 3), dtype=np.uint8)
    for i in range(256):
        t = i / 255.0
        if t < 0.5:
            f = t / 0.5
            heatmap_lut[i] = (c_far * (1 - f) + c_mid * f).astype(np.uint8)
        else:
            f = (t - 0.5) / 0.5
            heatmap_lut[i] = (c_mid * (1 - f) + c_near * f).astype(np.uint8)

    for det in detections:
        bbox = det["bbox"]
        label = det["label"]
        conf = det["confidence"]
        bx, by, bw, bh = [int(v) for v in bbox]

        x1 = max(0, bx)
        y1 = max(0, by)
        x2 = min(img_w, bx + bw)
        y2 = min(img_h, by + bh)
        if x2 - x1 < 20 or y2 - y1 < 20:
            continue

        # Generate adaptive point cloud
        points, point_depths, d_min, d_range = _generate_adaptive_points(
            x1, y1, x2, y2, depth_image, sx, sy, gamma, cutoff,
            pct_near, pct_far)

        if len(points) < 3:
            continue

        # Compute closeness and displaced positions
        closeness_raw = np.zeros(len(points))
        closeness = np.zeros(len(points))
        displaced = points.copy()
        for i in range(len(points)):
            d = point_depths[i]
            if d > 0:
                c = np.clip(1.0 - (d - d_min) / d_range, 0, 1)
            else:
                c = 0
            closeness_raw[i] = c
            closeness[i] = c ** gamma
            displaced[i, 1] -= closeness[i] * max_displace

        # Delaunay triangulation
        rect = (x1 - 1, y1 - max_displace - 1,
                x2 - x1 + 2, y2 - y1 + max_displace + 2)
        subdiv = cv2.Subdiv2D(rect)
        for pt in displaced:
            try:
                subdiv.insert((float(pt[0]), float(pt[1])))
            except cv2.error:
                pass

        triangles = subdiv.getTriangleList()

        # Build lookup: displaced coord → index (for closeness)
        pt_lookup = {}
        for i, pt in enumerate(displaced):
            key = (round(pt[0], 1), round(pt[1], 1))
            pt_lookup[key] = i

        # Darken bbox region
        cy1 = max(0, y1 - max_displace)
        roi = frame[cy1:y2, x1:x2].copy()
        frame[cy1:y2, x1:x2] = (roi * darken).astype(np.uint8)

        # Draw triangles
        rx1, ry1, rx2, ry2 = float(x1), float(y1 - max_displace), float(x2), float(y2)

        # Batch triangle rendering: single overlay blend instead of per-triangle mask
        color_layer = np.zeros_like(frame)
        alpha_layer = np.zeros(frame.shape[:2], dtype=np.uint8)
        wireframe = []

        for t in triangles:
            ax, ay, bxx, byy, cx, cy = t
            if (ax < rx1 or ax > rx2 or bxx < rx1 or bxx > rx2 or
                cx < rx1 or cx > rx2 or ay < ry1 or ay > ry2 or
                byy < ry1 or byy > ry2 or cy < ry1 or cy > ry2):
                continue

            # Triangle area (cross product / 2)
            if max_tri_area > 0:
                area = abs((bxx - ax) * (cy - ay) - (cx - ax) * (byy - ay)) * 0.5
                if area > max_tri_area:
                    continue

            verts_c = []
            verts_raw = []
            for vx, vy in [(ax, ay), (bxx, byy), (cx, cy)]:
                key = (round(vx, 1), round(vy, 1))
                idx = pt_lookup.get(key)
                verts_c.append(closeness[idx] if idx is not None else 0)
                verts_raw.append(closeness_raw[idx] if idx is not None else 0)

            avg_c = sum(verts_c) / 3
            if sum(verts_raw) / 3 < cutoff:
                continue
            lut_idx = min(255, max(0, int(avg_c * 255)))
            color = tuple(int(v) for v in heatmap_lut[lut_idx])

            pts = np.array([(int(ax), int(ay)), (int(bxx), int(byy)),
                            (int(cx), int(cy))], dtype=np.int32)
            alpha_byte = int((alpha_min + (alpha_max - alpha_min) * avg_c) * 255)
            cv2.fillConvexPoly(color_layer, pts, color)
            cv2.fillConvexPoly(alpha_layer, pts, alpha_byte)
            # Draw thick edges on overlay layers to seal rasterization gaps
            cv2.polylines(color_layer, [pts], True, color, 2)
            cv2.polylines(alpha_layer, [pts], True, alpha_byte, 2)
            wireframe.append((pts, color))

        # Single blend pass for all triangle fills
        mask = alpha_layer > 0
        if mask.any():
            alpha_f = alpha_layer[mask].astype(np.float32) / 255.0
            alpha_f = alpha_f[:, np.newaxis]
            frame[mask] = (
                frame[mask].astype(np.float32) * (1 - alpha_f) +
                color_layer[mask].astype(np.float32) * alpha_f
            ).astype(np.uint8)

        # Wireframe on top of fills
        for pts, color in wireframe:
            cv2.polylines(frame, [pts], True, color, 1, cv2.LINE_AA)

        # Label
        text = f"{label} {conf:.0%}"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = max(0.4, min(bw / 200, 1.0))
        thickness = max(1, int(font_scale * 2))
        (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
        tx = x1 + 4
        ty = y1 - 8 if y1 > th + 12 else y1 + th + 4
        cv2.rectangle(frame, (tx - 2, ty - th - 2), (tx + tw + 2, ty + 2),
                      (10, 15, 10), -1)
        cv2.putText(frame, text, (tx, ty), font, font_scale,
                    (120, 255, 200), thickness, cv2.LINE_AA)

    return frame


# -- Multiprocessing worker --

_worker_hud_cfg = None


def _init_worker(hud_cfg):
    global _worker_hud_cfg
    _worker_hud_cfg = hud_cfg


def _draw_debug_sources(frame, debug_info):
    """Draw source filenames/timestamps in bottom-left."""
    lines = [
        f"RGB:   {debug_info['rgb']}",
        f"Depth: {debug_info['depth']}",
        f"YOLO:  {debug_info['yolo']}",
        f"Servo: {debug_info['servo']}",
    ]
    font = cv2.FONT_HERSHEY_SIMPLEX
    fs, ft = 0.4, 1
    lh = 18
    x, y = 8, frame.shape[0] - 8 - lh * (len(lines) - 1)
    # Background
    cv2.rectangle(frame, (x - 4, y - 14), (x + 340, y + lh * (len(lines) - 1) + 6),
                  (0, 0, 0), -1)
    for i, line in enumerate(lines):
        cv2.putText(frame, line, (x, y + i * lh), font, fs,
                    (180, 180, 180), ft, cv2.LINE_AA)


def _process_frame(args):
    """Process a single frame (runs in worker process)."""
    rgb_path, depth_path, detections, servo_state, debug_info = args
    frame = cv2.imread(rgb_path)
    if frame is None:
        return None

    if depth_path is not None and detections:
        depth_image = np.load(depth_path)
        h, w = frame.shape[:2]
        mesh_cfg = _worker_hud_cfg.get("mesh") if _worker_hud_cfg else None
        frame = draw_depth_overlay(frame, depth_image, detections,
                                   (depth_image.shape[1] / w, depth_image.shape[0] / h),
                                   mesh_cfg)

    if servo_state is not None:
        frame = draw_hud(frame, servo_state, _worker_hud_cfg)

    if _worker_hud_cfg and _worker_hud_cfg.get("debug_sources"):
        _draw_debug_sources(frame, debug_info)

    return frame


def main():
    parser = argparse.ArgumentParser(description="Compose video from session data")
    parser.add_argument("session", help="Path to session directory")
    parser.add_argument("--fps", type=float, default=0,
                        help="Output video FPS (default: auto from timestamps)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output video path (default: <session>.mp4)")
    parser.add_argument("--max-depth-gap", type=float, default=2.0,
                        help="Max seconds to reuse a depth frame (default: 2.0)")
    parser.add_argument("--max-yolo-gap", type=float, default=3.0,
                        help="Max seconds to reuse a YOLO detection (default: 3.0)")
    parser.add_argument("--label", type=str, default="person",
                        help="Only show this detection label (empty=all)")
    parser.add_argument("--frame", type=str, default=None,
                        help="Render single frame from this depth file (saves PNG)")
    parser.add_argument("--workers", type=int, default=0,
                        help="Parallel workers (default: auto)")
    args = parser.parse_args()

    session = Path(args.session)
    rgb_dir = session / "rgb"
    depth_dir = session / "depth"
    yolo_file = session / "yolo" / "detections.jsonl"

    if not rgb_dir.exists():
        print(f"No rgb/ directory in {session}")
        sys.exit(1)

    # Load RGB file list sorted by timestamp
    rgb_files = sorted(rgb_dir.glob("*.jpg"))
    if not rgb_files:
        print("No RGB frames found")
        sys.exit(1)
    rgb_timestamps = [(parse_timestamp(f.stem), f) for f in rgb_files]
    print(f"RGB frames: {len(rgb_timestamps)}")

    # Load depth file list sorted by timestamp
    depth_files = sorted(depth_dir.glob("*.npy")) if depth_dir.exists() else []
    depth_timestamps = [(parse_timestamp(f.stem), f) for f in depth_files]
    print(f"Depth frames: {len(depth_timestamps)}")

    # Load YOLO detections
    yolo_entries = []
    if yolo_file.exists():
        with open(yolo_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                ts = parse_timestamp(entry["timestamp"])
                yolo_entries.append((ts, entry))
        yolo_entries.sort(key=lambda x: x[0])
    print(f"YOLO entries: {len(yolo_entries)}")

    # Load servo state
    servo_file = session / "servo" / "state.jsonl"
    servo_entries = []
    if servo_file.exists():
        with open(servo_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                ts = parse_timestamp(entry["timestamp"])
                servo_entries.append((ts, entry))
        servo_entries.sort(key=lambda x: x[0])
    print(f"Servo entries: {len(servo_entries)}")

    # Load HUD config
    hud_cfg = load_hud_config()

    # Single frame mode
    if args.frame:
        depth_name = Path(args.frame).stem
        depth_ts = parse_timestamp(depth_name)

        # Find closest RGB
        rgb_idx = find_closest(depth_ts, rgb_timestamps, 5.0)
        if rgb_idx < 0:
            print("No RGB frame found near that depth frame")
            sys.exit(1)

        rgb_path = str(rgb_timestamps[rgb_idx][1])
        depth_path = str(session / "depth" / Path(args.frame).name)

        yolo_idx = find_closest(depth_ts, yolo_entries, args.max_yolo_gap)
        detections = yolo_entries[yolo_idx][1].get("detections", []) if yolo_idx >= 0 else []
        yolo_ts = yolo_entries[yolo_idx][1].get("timestamp", "") if yolo_idx >= 0 else ""
        if args.label:
            detections = [d for d in detections if d.get("label") == args.label]

        servo_state = None
        servo_ts = ""
        if servo_entries:
            servo_idx = find_closest(depth_ts, servo_entries, 1.0)
            if servo_idx >= 0:
                servo_state = servo_entries[servo_idx][1]
                servo_ts = servo_state.get("timestamp", "")

        debug_info = {
            "rgb": Path(rgb_path).name,
            "depth": Path(depth_path).name,
            "yolo": yolo_ts or "-",
            "servo": servo_ts or "-",
        }

        print(f"RGB:   {debug_info['rgb']}")
        print(f"Depth: {debug_info['depth']}")
        print(f"YOLO:  {debug_info['yolo']}  ({len(detections)} detections)")
        print(f"Servo: {debug_info['servo']}")

        _init_worker(hud_cfg)
        frame = _process_frame((rgb_path, depth_path, detections, servo_state, debug_info))

        out_base = args.output or f"/tmp/frame_{depth_name}.png"
        out_stem = out_base.rsplit(".", 1)[0]
        cv2.imwrite(out_base, frame)
        print(f"Saved: {out_base}")

        # Debug depth heatmaps — per-bbox, matching what the mesh sees
        depth_image = np.load(depth_path)
        img_h, img_w = cv2.imread(rgb_path).shape[:2]
        dep_h, dep_w = depth_image.shape[:2]
        mesh_cfg = hud_cfg.get("mesh", {})
        gm = mesh_cfg.get("gamma", 1.0)
        co = mesh_cfg.get("cutoff", 0.0)
        pn = mesh_cfg.get("depth_pct_near", 5)
        pf = mesh_cfg.get("depth_pct_far", 95)
        dsx, dsy = dep_w / img_w, dep_h / img_h

        # Global linear heatmap (full frame, p5-p95)
        d = depth_image.astype(np.float32)
        d[d == 0] = np.nan
        d_min_g, d_max_g = np.nanpercentile(d, [5, 95])
        d_range_g = max(d_max_g - d_min_g, 1)
        linear = np.clip((d - d_min_g) / d_range_g, 0, 1)
        linear = np.nan_to_num(linear, nan=0)
        hm_linear = cv2.applyColorMap((linear * 255).astype(np.uint8), cv2.COLORMAP_TURBO)
        hm_linear[depth_image == 0] = 0

        # Draw detection bboxes on heatmaps
        for det in detections:
            bx, by, bw, bh = [int(v) for v in det["bbox"]]
            dx1, dy1 = int(bx * dsx), int(by * dsy)
            dx2, dy2 = int((bx + bw) * dsx), int((by + bh) * dsy)
            cv2.rectangle(hm_linear, (dx1, dy1), (dx2, dy2), (255, 255, 255), 1)

        out_hm = f"{out_stem}_depth.png"
        cv2.imwrite(out_hm, hm_linear)
        print(f"Saved: {out_hm}")

        # Per-bbox adjusted heatmap (gamma + cutoff + configurable percentiles)
        hm_adjusted = np.zeros_like(hm_linear)
        for det in detections:
            bx, by, bw, bh = [int(v) for v in det["bbox"]]
            dx1 = max(0, int(bx * dsx))
            dy1 = max(0, int(by * dsy))
            dx2 = min(dep_w, int((bx + bw) * dsx))
            dy2 = min(dep_h, int((by + bh) * dsy))
            region = depth_image[dy1:dy2, dx1:dx2].astype(np.float32)
            region[region == 0] = np.nan
            valid = region[~np.isnan(region)]
            if len(valid) < 10:
                continue
            d_min_b = np.percentile(valid, pn)
            d_max_b = np.percentile(valid, pf)
            d_range_b = max(d_max_b - d_min_b, 1)
            closeness = np.clip(1.0 - (region - d_min_b) / d_range_b, 0, 1)
            closeness = np.nan_to_num(closeness, nan=0)
            closeness = closeness ** gm
            closeness[closeness < co] = 0
            bbox_hm = cv2.applyColorMap((closeness * 255).astype(np.uint8), cv2.COLORMAP_TURBO)
            bbox_hm[depth_image[dy1:dy2, dx1:dx2] == 0] = 0
            hm_adjusted[dy1:dy2, dx1:dx2] = bbox_hm
            cv2.rectangle(hm_adjusted, (dx1, dy1), (dx2, dy2), (255, 255, 255), 1)
            print(f"  {det['label']}: d_range=[{d_min_b:.0f}, {d_max_b:.0f}] "
                  f"(pct {pn}-{pf})")

        out_adj = f"{out_stem}_depth_adjusted.png"
        cv2.imwrite(out_adj, hm_adjusted)
        print(f"Saved: {out_adj}")
        return

    # Output path
    output_path = args.output or str(session) + ".mp4"

    # Compute natural FPS from timestamps
    duration = rgb_timestamps[-1][0] - rgb_timestamps[0][0]
    natural_fps = len(rgb_timestamps) / duration if duration > 0 else 30
    fps = args.fps if args.fps > 0 else natural_fps
    print(f"Output FPS: {fps:.1f}")

    # Read first frame to get dimensions
    first_frame = cv2.imread(str(rgb_timestamps[0][1]))
    h, w = first_frame.shape[:2]

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (w, h))

    # Pre-compute frame processing arguments
    last_servo_state = {
        "servo_angle": 90, "servo_target": 90,
        "left_speed": 0, "left_dir": 0, "right_speed": 0, "right_dir": 0,
    }
    has_servo = bool(servo_entries)

    frame_args = []
    for rgb_ts, rgb_path in rgb_timestamps:
        depth_idx = find_closest(rgb_ts, depth_timestamps, args.max_depth_gap)
        depth_path = str(depth_timestamps[depth_idx][1]) if depth_idx >= 0 else None

        yolo_idx = find_closest(rgb_ts, yolo_entries, args.max_yolo_gap)
        detections = yolo_entries[yolo_idx][1].get("detections", []) if yolo_idx >= 0 else []
        yolo_ts = yolo_entries[yolo_idx][1].get("timestamp", "") if yolo_idx >= 0 else ""
        if args.label:
            detections = [d for d in detections if d.get("label") == args.label]

        servo_state = None
        servo_ts = ""
        if has_servo:
            servo_idx = find_closest(rgb_ts, servo_entries, 1.0)
            if servo_idx >= 0:
                last_servo_state = servo_entries[servo_idx][1]
                servo_ts = last_servo_state.get("timestamp", "")
            servo_state = dict(last_servo_state)

        debug_info = {
            "rgb": Path(rgb_path).name,
            "depth": Path(depth_path).name if depth_path else "-",
            "yolo": yolo_ts or "-",
            "servo": servo_ts or "-",
        }
        frame_args.append((str(rgb_path), depth_path, detections, servo_state, debug_info))

    # Parallel processing
    n_workers = args.workers if args.workers > 0 else min(os.cpu_count() or 4, 8)
    n_frames = len(frame_args)
    print(f"Workers: {n_workers}")
    t_start = time.time()

    with Pool(n_workers, initializer=_init_worker, initargs=(hud_cfg,)) as pool:
        for i, frame in enumerate(pool.imap(_process_frame, frame_args, chunksize=4)):
            if frame is not None:
                writer.write(frame)
            done = i + 1
            elapsed = time.time() - t_start
            speed = done / elapsed if elapsed > 0 else 0
            eta = (n_frames - done) / speed if speed > 0 else 0
            print(f"\r{done}/{n_frames} [{done*100//n_frames}%] "
                  f"{speed:.1f} fps, ETA {eta:.0f}s", end="", flush=True)

    writer.release()
    total_time = time.time() - t_start
    print(f"\nVideo saved: {output_path}")
    print(f"Duration: {duration:.1f}s, {len(rgb_timestamps)} frames, "
          f"{len(rgb_timestamps)/duration:.1f} actual fps")
    print(f"Composed in {total_time:.1f}s ({n_frames/total_time:.1f} compose fps)")


if __name__ == "__main__":
    main()
