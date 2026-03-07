#!/usr/bin/env python3
"""
Compose video from a session: RGB frames + depth overlay on detected objects.

For each RGB frame, finds the closest YOLO detection and depth map by timestamp.
Detected objects get a depth-colormap crop placed above the RGB image with label.
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np


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


def colorize_depth(depth_crop: np.ndarray) -> np.ndarray:
    """Convert uint16 depth crop to a colormap visualization."""
    valid = depth_crop[depth_crop > 0]
    if len(valid) == 0:
        return np.zeros((*depth_crop.shape, 3), dtype=np.uint8)
    vmin, vmax = np.percentile(valid, [5, 95])
    normalized = np.clip((depth_crop.astype(float) - vmin) / max(vmax - vmin, 1), 0, 1)
    normalized = (normalized * 255).astype(np.uint8)
    # Zero depth stays black
    normalized[depth_crop == 0] = 0
    colored = cv2.applyColorMap(normalized, cv2.COLORMAP_TURBO)
    colored[depth_crop == 0] = 0
    return colored


def draw_depth_overlay(frame: np.ndarray, depth_image: np.ndarray,
                       detections: list, depth_scale: tuple) -> np.ndarray:
    """Draw depth-colormap crops above the RGB frame for each detection."""
    img_h, img_w = frame.shape[:2]
    dep_h, dep_w = depth_image.shape[:2]
    sx = dep_w / img_w
    sy = dep_h / img_h

    for det in detections:
        bbox = det["bbox"]
        label = det["label"]
        conf = det["confidence"]
        x, y, w, h = [int(v) for v in bbox]

        # Crop depth in depth coordinates
        dx1 = max(0, int(x * sx))
        dy1 = max(0, int(y * sy))
        dx2 = min(dep_w, int((x + w) * sx))
        dy2 = min(dep_h, int((y + h) * sy))
        if dx2 <= dx1 or dy2 <= dy1:
            continue

        depth_crop = depth_image[dy1:dy2, dx1:dx2]
        colored_crop = colorize_depth(depth_crop)

        # Resize depth crop to match bbox size in RGB coordinates
        overlay_w = min(w, img_w - x)
        overlay_h = min(h, img_h)
        if overlay_w <= 0 or overlay_h <= 0:
            continue
        colored_resized = cv2.resize(colored_crop, (overlay_w, overlay_h),
                                     interpolation=cv2.INTER_NEAREST)

        # Place above the bbox (or at top if not enough space)
        oy = max(0, y - overlay_h)
        ox = max(0, min(x, img_w - overlay_w))
        # Clamp
        place_h = min(overlay_h, img_h - oy)
        place_w = min(overlay_w, img_w - ox)

        # Blend: semi-transparent overlay
        alpha = 0.8
        roi = frame[oy:oy + place_h, ox:ox + place_w]
        frame[oy:oy + place_h, ox:ox + place_w] = cv2.addWeighted(
            colored_resized[:place_h, :place_w], alpha, roi, 1 - alpha, 0)

        # Border around depth overlay
        cv2.rectangle(frame, (ox, oy), (ox + place_w - 1, oy + place_h - 1),
                      (255, 255, 255), 1)

        # Label inside depth overlay
        text = f"{label} {conf:.0%}"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = max(0.4, min(place_w / 200, 1.0))
        thickness = max(1, int(font_scale * 2))
        (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
        tx = ox + 4
        ty = oy + th + 4
        # Background for text readability
        cv2.rectangle(frame, (tx - 2, ty - th - 2), (tx + tw + 2, ty + 2), (0, 0, 0), -1)
        cv2.putText(frame, text, (tx, ty), font, font_scale, (255, 255, 255), thickness)

        # Thin bbox outline on RGB
        cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 255, 255), 1)
        # Connecting lines from bbox top to depth overlay bottom
        cv2.line(frame, (ox, oy + place_h), (x, y), (255, 255, 255), 1)
        cv2.line(frame, (ox + place_w, oy + place_h), (x + w, y), (255, 255, 255), 1)

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

    # Depth cache to avoid reloading
    cached_depth_idx = -1
    cached_depth_image = None

    for i, (rgb_ts, rgb_path) in enumerate(rgb_timestamps):
        frame = cv2.imread(str(rgb_path))
        if frame is None:
            continue

        # Find closest depth
        depth_idx = find_closest(rgb_ts, depth_timestamps, args.max_depth_gap)
        depth_image = None
        if depth_idx >= 0:
            if depth_idx != cached_depth_idx:
                cached_depth_image = np.load(str(depth_timestamps[depth_idx][1]))
                cached_depth_idx = depth_idx
            depth_image = cached_depth_image

        # Find closest YOLO
        yolo_idx = find_closest(rgb_ts, yolo_entries, args.max_yolo_gap)
        if yolo_idx >= 0 and depth_image is not None:
            detections = yolo_entries[yolo_idx][1].get("detections", [])
            if detections:
                frame = draw_depth_overlay(frame, depth_image, detections,
                                           (depth_image.shape[1] / w, depth_image.shape[0] / h))

        writer.write(frame)

        if (i + 1) % 100 == 0 or i == len(rgb_timestamps) - 1:
            print(f"\r{i + 1}/{len(rgb_timestamps)} frames", end="", flush=True)

    writer.release()
    print(f"\nVideo saved: {output_path}")
    duration = rgb_timestamps[-1][0] - rgb_timestamps[0][0]
    print(f"Duration: {duration:.1f}s, {len(rgb_timestamps)} frames, {len(rgb_timestamps)/duration:.1f} actual fps")


if __name__ == "__main__":
    main()
