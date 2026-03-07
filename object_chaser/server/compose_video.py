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


def _generate_adaptive_points(x1, y1, x2, y2, depth_image, sx, sy):
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

    d_min = np.percentile(depths, 5)
    d_max = np.percentile(depths, 95)
    d_range = max(d_max - d_min, 1)

    # Collect unique points across all LOD levels
    point_set = set()
    for divisions, threshold in levels:
        for gy in range(divisions + 1):
            for gx in range(divisions + 1):
                px = x1 + w * gx / divisions
                py = y1 + h * gy / divisions
                d = _sample_depth(px, py, depth_image, sx, sy)
                if d > 0:
                    closeness = np.clip(1.0 - (d - d_min) / d_range, 0, 1)
                else:
                    closeness = 0
                if closeness >= threshold:
                    # Quantize to avoid near-duplicates
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

    # Custom heatmap LUT: white (far) → lightning-blue (mid) → green (near)
    heatmap_lut = np.zeros((256, 3), dtype=np.uint8)
    # BGR anchors
    white = np.array([255, 255, 255])
    blue = np.array([255, 200, 50])    # electric/lightning blue
    green = np.array([50, 255, 80])
    for i in range(256):
        t = i / 255.0
        if t < 0.5:
            f = t / 0.5
            heatmap_lut[i] = (white * (1 - f) + blue * f).astype(np.uint8)
        else:
            f = (t - 0.5) / 0.5
            heatmap_lut[i] = (blue * (1 - f) + green * f).astype(np.uint8)

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
            x1, y1, x2, y2, depth_image, sx, sy)

        if len(points) < 3:
            continue

        # Compute closeness and displaced positions
        closeness = np.zeros(len(points))
        displaced = points.copy()
        for i in range(len(points)):
            d = point_depths[i]
            if d > 0:
                c = np.clip(1.0 - (d - d_min) / d_range, 0, 1)
            else:
                c = 0
            closeness[i] = c
            displaced[i, 1] -= c * max_displace

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

            verts_c = []
            for vx, vy in [(ax, ay), (bxx, byy), (cx, cy)]:
                key = (round(vx, 1), round(vy, 1))
                idx = pt_lookup.get(key)
                verts_c.append(closeness[idx] if idx is not None else 0)

            avg_c = sum(verts_c) / 3
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


def _process_frame(args):
    """Process a single frame (runs in worker process)."""
    rgb_path, depth_path, detections, servo_state = args
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

        servo_state = None
        if has_servo:
            servo_idx = find_closest(rgb_ts, servo_entries, 1.0)
            if servo_idx >= 0:
                last_servo_state = servo_entries[servo_idx][1]
            servo_state = dict(last_servo_state)

        frame_args.append((str(rgb_path), depth_path, detections, servo_state))

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
