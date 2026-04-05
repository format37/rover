#!/usr/bin/env python3
"""
Camera server: captures RealSense frames at 30fps, saves to disk, serves latest
frame and depth-based distance queries to clients via FastAPI.
"""

import argparse
import json
import threading
import time
import queue
import shutil
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import cv2
import numpy as np
import pyrealsense2 as rs
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
import uvicorn


# Estimates for initial frame limit (recalculated after RECALC_AFTER_FRAMES)
ESTIMATED_RGB_SIZE = 150_000       # ~150KB per JPEG at quality 85, 848×480
ESTIMATED_DEPTH_SIZE = 820_000     # ~820KB per .npy (848×480 uint16)
DISK_HEADROOM = 100_000_000        # Reserve 100MB free
RECALC_AFTER_FRAMES = 30           # Recalculate frame limit from actual sizes

# Cliff detection: sample the bottom CLIFF_BOTTOM_FRAC of the depth frame.
# If the median depth of valid pixels there exceeds CLIFF_DEPTH_THRESHOLD metres
# (floor is farther away than expected → edge/cliff), or too few valid pixels
# are returned (surface out of range), a cliff is reported.
CLIFF_BOTTOM_FRAC = 0.30       # Bottom 30% of rows to sample
CLIFF_DEPTH_THRESHOLD = 0.8    # Metres; floor closer than this is normal ground
CLIFF_VALID_FRAC_MIN = 0.10    # Fraction of region pixels that must be valid


class DistanceRequest(BaseModel):
    bbox: List[float] = Field(..., min_length=4, max_length=4, description="[x, y, w, h]")
    shrink: float = Field(0.2, ge=0, le=0.49, description="Shrink bbox fraction per side")


class CameraManager:
    def __init__(self, session_dir: str = "sessions", jpeg_quality: int = 85,
                 frame_limit: Optional[int] = None, save_depth: bool = True):
        self.jpeg_quality = jpeg_quality
        self.depth_saving_enabled: bool = save_depth
        self.session_base = Path(session_dir).resolve()

        # Create session folder
        self.session_start = datetime.now()
        session_name = self.session_start.strftime("%Y%m%d_%H%M%S")
        self.session_path = self.session_base / session_name
        self.rgb_dir = self.session_path / "rgb"
        self.depth_dir = self.session_path / "depth"
        self.yolo_dir = self.session_path / "yolo"
        self.servo_dir = self.session_path / "servo"
        for d in (self.rgb_dir, self.depth_dir, self.yolo_dir, self.servo_dir):
            d.mkdir(parents=True, exist_ok=True)

        # Frame limit
        if frame_limit is not None:
            self.frame_limit = frame_limit
        else:
            self.frame_limit = self._compute_frame_limit()
        print(f"Frame limit: {self.frame_limit}")

        # Shared state
        self._lock = threading.Lock()
        self.latest_color_image: Optional[np.ndarray] = None
        self.latest_depth_image: Optional[np.ndarray] = None
        self.latest_jpeg: Optional[bytes] = None
        self.latest_timestamp: str = ""
        self.depth_scale: float = 0.0
        self.frame_count: int = 0
        self.saving_active: bool = False
        self.capture_fps: float = 0.0
        self.cliff_detected: bool = False

        # Write queue — large enough to buffer ~2s of capture at 60fps
        self._write_queue: queue.Queue = queue.Queue(maxsize=120)

        # RealSense setup
        self.pipeline = rs.pipeline()
        rs_config = rs.config()
        rs_config.enable_stream(rs.stream.color, 848, 480, rs.format.bgr8, 60)
        rs_config.enable_stream(rs.stream.depth, 848, 480, rs.format.z16, 60)
        profile = self.pipeline.start(rs_config)

        self.depth_scale = profile.get_device().first_depth_sensor().get_depth_scale()
        self.align = rs.align(rs.stream.color)
        self.filters = {
            'decimation': rs.decimation_filter(),
            'spatial': rs.spatial_filter(),
            'temporal': rs.temporal_filter(),
        }

        # Stabilize auto-exposure
        print("Stabilizing auto-exposure...")
        for _ in range(30):
            self.pipeline.wait_for_frames()

        # Threads
        self._stop_event = threading.Event()
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._capture_thread.start()
        self._writer_thread.start()

        # Write session metadata (start time)
        self._session_meta_path = self.session_path / "session.json"
        self._session_meta = {
            "session_start": self.session_start.isoformat(),
            "session_end": None,
        }
        self._session_meta_path.write_text(json.dumps(self._session_meta, indent=2))
        print(f"Camera server started. Session: {self.session_path}")

    def _compute_frame_limit(self) -> int:
        self.session_base.mkdir(parents=True, exist_ok=True)
        available = shutil.disk_usage(self.session_base).free
        budget = available - DISK_HEADROOM
        depth_size = ESTIMATED_DEPTH_SIZE if self.depth_saving_enabled else 0
        est_frame_size = ESTIMATED_RGB_SIZE + depth_size
        return max(100, int(budget / est_frame_size))

    def _make_timestamp(self) -> str:
        now = datetime.now()
        return now.strftime("%Y%m%d_%H%M%S") + f"_{now.microsecond:06d}"

    def _capture_loop(self):
        print("Capture thread started")
        fps_counter = 0
        fps_timer = time.monotonic()

        while not self._stop_event.is_set():
            try:
                frames = self.pipeline.wait_for_frames(timeout_ms=1000)
            except RuntimeError:
                continue

            try:
                aligned = self.align.process(frames)
            except RuntimeError as e:
                print(f"Align error (skipping frame): {e}")
                continue

            depth_frame = aligned.get_depth_frame()
            color_frame = aligned.get_color_frame()
            if not depth_frame or not color_frame:
                continue

            # Apply depth filters
            filtered_depth = depth_frame
            try:
                for f in self.filters.values():
                    filtered_depth = f.process(filtered_depth)
            except RuntimeError as e:
                print(f"Depth filter error (skipping frame): {e}")
                continue

            color_image = np.asanyarray(color_frame.get_data())
            depth_image = np.asanyarray(filtered_depth.get_data())

            # JPEG encode
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
            ok, jpeg_buf = cv2.imencode('.jpg', color_image, encode_params)
            if not ok:
                continue
            jpeg_bytes = jpeg_buf.tobytes()

            timestamp = self._make_timestamp()
            cliff = self._detect_cliff(depth_image)

            with self._lock:
                self.latest_color_image = color_image
                self.latest_depth_image = depth_image
                self.latest_jpeg = jpeg_bytes
                self.latest_timestamp = timestamp
                self.cliff_detected = cliff
                saving = self.saving_active
                count = self.frame_count

            # Enqueue for saving
            if saving:
                depth_to_save = depth_image if self.depth_saving_enabled else None
                try:
                    self._write_queue.put_nowait((timestamp, jpeg_bytes, depth_to_save))
                except queue.Full:
                    pass  # Drop frame from saving, never block capture

            # FPS tracking
            fps_counter += 1
            now = time.monotonic()
            elapsed = now - fps_timer
            if elapsed >= 2.0:
                with self._lock:
                    self.capture_fps = fps_counter / elapsed
                fps_counter = 0
                fps_timer = now

        print("Capture thread stopped")

    def _recalc_frame_limit(self):
        """Recalculate frame limit from actual file sizes on disk."""
        rgb_files = list(self.rgb_dir.glob("*.jpg"))
        if not rgb_files:
            return
        total_rgb = sum(f.stat().st_size for f in rgb_files)
        avg_rgb = total_rgb / len(rgb_files)

        avg_depth = 0
        if self.depth_saving_enabled:
            depth_files = list(self.depth_dir.glob("*.npy"))
            if depth_files:
                total_depth = sum(f.stat().st_size for f in depth_files)
                avg_depth = total_depth / len(depth_files)

        avg_frame = avg_rgb + avg_depth
        available = shutil.disk_usage(self.session_base).free
        budget = available - DISK_HEADROOM
        new_limit = self.frame_count + max(100, int(budget / avg_frame))

        print(f"Frame limit recalculated: {self.frame_limit} -> {new_limit} "
              f"(avg frame {avg_frame/1000:.0f}KB: rgb {avg_rgb/1000:.0f}KB + depth {avg_depth/1000:.0f}KB)")
        self.frame_limit = new_limit

    def _writer_loop(self):
        print("Writer thread started")
        recalc_done = False
        while not self._stop_event.is_set():
            try:
                item = self._write_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            timestamp, jpeg_bytes, depth_array = item

            # Write RGB JPEG
            rgb_path = self.rgb_dir / f"{timestamp}.jpg"
            rgb_path.write_bytes(jpeg_bytes)

            # Write depth .npy if provided
            if depth_array is not None:
                depth_path = self.depth_dir / f"{timestamp}.npy"
                np.save(str(depth_path), depth_array)

            with self._lock:
                self.frame_count += 1

                # Recalculate frame limit from actual sizes after first N frames
                if not recalc_done and self.frame_count >= RECALC_AFTER_FRAMES:
                    self._recalc_frame_limit()
                    recalc_done = True

                if self.frame_count >= self.frame_limit:
                    self.saving_active = False
                    print(f"Frame limit reached ({self.frame_limit}), saving stopped")

        print("Writer thread stopped")

    def _detect_cliff(self, depth_image: np.ndarray) -> bool:
        """Return True if the lower portion of the depth frame suggests a cliff.

        Samples the bottom CLIFF_BOTTOM_FRAC rows. If valid pixels are too
        sparse or their median distance exceeds CLIFF_DEPTH_THRESHOLD, the
        rover is likely at an edge.
        """
        h = depth_image.shape[0]
        y_start = int(h * (1.0 - CLIFF_BOTTOM_FRAC))
        region = depth_image[y_start:, :]
        valid = region[region > 0]
        if len(valid) < region.size * CLIFF_VALID_FRAC_MIN:
            return True  # too few valid readings → surface out of range
        median_m = float(np.median(valid)) * self.depth_scale
        return median_m > CLIFF_DEPTH_THRESHOLD

    def get_distance(self, bbox: List[float], shrink: float = 0.2) -> Optional[float]:
        with self._lock:
            depth_image = self.latest_depth_image
            color_image = self.latest_color_image
            scale = self.depth_scale

        if depth_image is None:
            print("get_distance: no depth image")
            return None

        depth_h, depth_w = depth_image.shape[:2]

        # Scale bbox from color space to depth space
        x, y, w, h = bbox
        if color_image is not None:
            color_h, color_w = color_image.shape[:2]
            if color_w != depth_w or color_h != depth_h:
                sx = depth_w / color_w
                sy = depth_h / color_h
                x, y, w, h = x * sx, y * sy, w * sx, h * sy

        x, y, w, h = int(x), int(y), int(w), int(h)

        margin_x = int(w * shrink)
        margin_y = int(h * shrink)
        x1 = max(0, x + margin_x)
        y1 = max(0, y + margin_y)
        x2 = min(depth_w, x + w - margin_x)
        y2 = min(depth_h, y + h - margin_y)

        # Fallback to unshrunk bbox if shrunk region is empty
        if x2 <= x1 or y2 <= y1:
            print(f"get_distance: shrunk bbox empty, using full bbox")
            x1 = max(0, x)
            y1 = max(0, y)
            x2 = min(depth_w, x + w)
            y2 = min(depth_h, y + h)

        # Fallback to center point if bbox still empty
        if x2 <= x1 or y2 <= y1:
            cx = max(0, min(depth_w - 1, x + w // 2))
            cy = max(0, min(depth_h - 1, y + h // 2))
            print(f"get_distance: bbox out of bounds, using center ({cx},{cy})")
            val = int(depth_image[cy, cx])
            if val > 0:
                return float(val) * scale
            return None

        region = depth_image[y1:y2, x1:x2]
        valid = region[region > 0]
        if len(valid) == 0:
            # Expand to full bbox
            region_full = depth_image[max(0, y):min(depth_h, y+h),
                                      max(0, x):min(depth_w, x+w)]
            valid = region_full[region_full > 0]
            if len(valid) == 0:
                print(f"get_distance: all zeros in region [{x1}:{x2},{y1}:{y2}]")
                return None
            print(f"get_distance: shrunk region all zeros, used full bbox")

        return float(np.median(valid)) * scale

    def shutdown(self):
        print("Shutting down camera manager...")
        self._stop_event.set()
        self._capture_thread.join(timeout=3)
        self._writer_thread.join(timeout=3)
        self.pipeline.stop()

        # Write session end time
        self._session_meta["session_end"] = datetime.now().isoformat()
        self._session_meta_path.write_text(json.dumps(self._session_meta, indent=2))
        print("Camera manager stopped")


# --- FastAPI app ---

camera_manager: Optional[CameraManager] = None


@asynccontextmanager
async def lifespan(app):
    global camera_manager
    camera_manager = CameraManager(
        session_dir=cli_args.session_dir,
        jpeg_quality=cli_args.jpeg_quality,
        frame_limit=cli_args.frame_limit,
        save_depth=not cli_args.no_save_depth,
    )
    yield
    if camera_manager:
        camera_manager.shutdown()


app = FastAPI(title="Camera Server", version="1.0.0", lifespan=lifespan)


@app.get("/frame")
async def get_frame():
    if not camera_manager:
        raise HTTPException(status_code=500, detail="Camera not initialized")

    with camera_manager._lock:
        jpeg = camera_manager.latest_jpeg
        timestamp = camera_manager.latest_timestamp
        frame_count = camera_manager.frame_count
        session_path = str(camera_manager.session_path)
        saving = camera_manager.saving_active

    if jpeg is None:
        raise HTTPException(status_code=503, detail="No frame captured yet")

    return Response(
        content=jpeg,
        media_type="image/jpeg",
        headers={
            "X-Timestamp": timestamp,
            "X-Frame-Number": str(frame_count),
            "X-Session-Path": session_path,
            "X-Saving-Active": str(saving),
        },
    )


@app.post("/distance")
async def get_distance(req: DistanceRequest):
    if not camera_manager:
        raise HTTPException(status_code=500, detail="Camera not initialized")

    distance = camera_manager.get_distance(req.bbox, req.shrink)
    with camera_manager._lock:
        timestamp = camera_manager.latest_timestamp

    return {"distance": distance, "timestamp": timestamp}


@app.get("/cliff")
async def get_cliff():
    if not camera_manager:
        raise HTTPException(status_code=500, detail="Camera not initialized")

    with camera_manager._lock:
        return {
            "cliff": camera_manager.cliff_detected,
            "timestamp": camera_manager.latest_timestamp,
        }


@app.get("/session")
async def get_session():
    if not camera_manager:
        raise HTTPException(status_code=500, detail="Camera not initialized")

    with camera_manager._lock:
        return {
            "session_path": str(camera_manager.session_path),
            "yolo_dir": str(camera_manager.yolo_dir),
            "servo_dir": str(camera_manager.servo_dir),
            "frame_count": camera_manager.frame_count,
            "frame_limit": camera_manager.frame_limit,
            "saving_active": camera_manager.saving_active,
            "depth_scale": camera_manager.depth_scale,
        }


@app.get("/status")
async def get_status():
    if not camera_manager:
        raise HTTPException(status_code=500, detail="Camera not initialized")

    with camera_manager._lock:
        return {
            "status": "running",
            "capture_fps": round(camera_manager.capture_fps, 1),
            "frame_count": camera_manager.frame_count,
            "frame_limit": camera_manager.frame_limit,
            "saving_active": camera_manager.saving_active,
            "depth_scale": camera_manager.depth_scale,
        }


@app.post("/start-saving")
async def start_saving():
    if not camera_manager:
        raise HTTPException(status_code=500, detail="Camera not initialized")

    with camera_manager._lock:
        if camera_manager.saving_active:
            return {"message": "already saving", "frame_count": camera_manager.frame_count}
        camera_manager.saving_active = True

    print("Saving activated via /start-saving")
    return {"message": "saving started", "frame_limit": camera_manager.frame_limit}


@app.post("/depth-saving")
async def set_depth_saving(enabled: bool):
    if not camera_manager:
        raise HTTPException(status_code=500, detail="Camera not initialized")

    camera_manager.depth_saving_enabled = enabled
    return {"depth_saving": enabled}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RealSense camera server")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--session-dir", type=str, default="sessions",
                        help="Base directory for session folders")
    parser.add_argument("--jpeg-quality", type=int, default=85)
    parser.add_argument("--frame-limit", type=int, default=None,
                        help="Override dynamic frame limit")
    parser.add_argument("--no-save-depth", action="store_true",
                        help="Disable depth saving (saves disk space; depth still used for distance queries)")
    cli_args = parser.parse_args()

    print(f"Starting Camera Server on port {cli_args.port}...")
    uvicorn.run(app, host="0.0.0.0", port=cli_args.port, log_level="info")
