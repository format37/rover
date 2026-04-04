"""Detection server — async inference cache decoupling YOLO from the control loop.

Runs its own tight inference loop (frame → YOLO → depth → cache) and exposes
the last result instantly via GET /detection, so the client control loop is no
longer blocked by YOLO latency.

Port: 8090
Startup order: camera_server → yolo_server → track_api → detection_server → client
"""
import asyncio
import sys
import os
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Optional

import aiohttp
import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI

# Config lives in the client directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'client'))
from config import (
    CAMERA_SERVER_URL, YOLO_URL,
    DETECTION_CONFIDENCE_MIN, CAMERA_FOV,
    DEPTH_BBOX_SHRINK,
)

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(name)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()


@dataclass
class Detection:
    label: str
    confidence: float
    bbox: List[int]               # [x, y, w, h] pixels
    centroid_x_norm: float        # 1 - (bbox_cx / frame_width); 0.5 = center
    distance: Optional[float]     # meters; None if depth unavailable
    relative_position_deg: Optional[float]  # angular offset from rover forward axis


@dataclass
class DetectionResult:
    timestamp: float              # time.time() when inference completed
    frame_ts: str                 # X-Timestamp from camera server
    detections: List[Detection] = field(default_factory=list)


_cache: DetectionResult = DetectionResult(timestamp=0.0, frame_ts='')
_cache_lock: asyncio.Lock = asyncio.Lock()
_loop_fps: float = 0.0
_last_result_age_ms: float = 0.0
_cache_has_detections: bool = False


async def _inference_loop() -> None:
    global _cache, _loop_fps, _last_result_age_ms, _cache_has_detections
    fps_window: List[float] = []

    async with aiohttp.ClientSession() as session:
        while True:
            loop_start = time.time()

            # 1. Fetch frame from camera server
            try:
                async with session.get(f"{CAMERA_SERVER_URL}/frame") as resp:
                    if resp.status != 200:
                        continue
                    image_data = await resp.read()
                    frame_ts = resp.headers.get('X-Timestamp', '')
            except Exception as e:
                logger.warning(f"Frame fetch failed: {e}")
                continue

            # Decode JPEG to get frame width for centroid normalisation
            arr = np.frombuffer(image_data, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                continue
            frame_width = img.shape[1]

            # 2. YOLO inference
            try:
                async with session.post(
                        f"{YOLO_URL}/detect/",
                        data={'file': image_data}) as resp:
                    if resp.status != 200:
                        continue
                    yolo_result = await resp.json()
            except Exception as e:
                logger.warning(f"YOLO inference failed: {e}")
                continue

            # 3. Process detections above confidence threshold
            detections: List[Detection] = []
            for d in yolo_result.get('detections', []):
                if d['confidence'] < DETECTION_CONFIDENCE_MIN:
                    continue

                bbox = d['bbox']  # [x, y, w, h]
                centroid_x = bbox[0] + bbox[2] / 2.0
                centroid_x_norm = 1.0 - (centroid_x / frame_width)

                # Depth at shrunk bbox
                distance: Optional[float] = None
                try:
                    async with session.post(
                            f"{CAMERA_SERVER_URL}/distance",
                            json={"bbox": bbox, "shrink": DEPTH_BBOX_SHRINK},
                            timeout=aiohttp.ClientTimeout(total=0.5)) as resp:
                        if resp.status == 200:
                            dist_data = await resp.json()
                            distance = dist_data.get('distance')
                except Exception as e:
                    logger.warning(f"Depth query failed: {e}")

                # Angular offset of object from rover forward axis (pixel-based only).
                # positive = right of rover forward, negative = left.
                # Convention: centroid_x_norm is inverted (1 - raw), so
                #   centroid_x_norm < 0.5 → target right of center → positive deg.
                relative_position_deg = (0.5 - centroid_x_norm) * CAMERA_FOV

                detections.append(Detection(
                    label=d['label'],
                    confidence=d['confidence'],
                    bbox=bbox,
                    centroid_x_norm=centroid_x_norm,
                    distance=distance,
                    relative_position_deg=relative_position_deg,
                ))

            # 4. Write to cache
            new_result = DetectionResult(
                timestamp=time.time(),
                frame_ts=frame_ts,
                detections=detections,
            )
            async with _cache_lock:
                _cache = new_result

            # Update loop stats (5-second rolling window)
            fps_window.append(loop_start)
            cutoff = loop_start - 5.0
            fps_window = [t for t in fps_window if t >= cutoff]
            _loop_fps = (len(fps_window) - 1) / 5.0 if len(fps_window) > 1 else 0.0
            _last_result_age_ms = (time.time() - new_result.timestamp) * 1000
            _cache_has_detections = bool(detections)


@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(_inference_loop())


@app.get("/detection")
async def get_detection():
    """Return last cached detection result instantly (no I/O, microsecond latency)."""
    async with _cache_lock:
        result = _cache
    return {
        "timestamp": result.timestamp,
        "frame_ts": result.frame_ts,
        "detections": [asdict(d) for d in result.detections],
    }


@app.get("/status")
async def get_status():
    return {
        "running": True,
        "loop_fps": round(_loop_fps, 1),
        "last_result_age_ms": round(_last_result_age_ms, 1),
        "cache_has_detections": _cache_has_detections,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8090)
