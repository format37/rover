#!/usr/bin/env python3
"""
Track control API for Jetson Nano.
Drives left and right PCA9685 boards via I2C.
"""

import json
import time
import threading
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
import requests as http_requests
import uvicorn
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent / 'client'))
from config import TRACK_MAX_DURATION

import logging
track_logger = logging.getLogger("tracks")
track_logger.setLevel(logging.INFO)
_track_handler = logging.StreamHandler()
_track_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
track_logger.addHandler(_track_handler)


class TrackController:
    """Controller for tank tracks via PCA9685 boards"""

    def __init__(self, left_address: int = 0x40, right_address: int = 0x41):
        i2c_bus = busio.I2C(SCL, SDA)
        for attempt in range(5):
            try:
                self.pca = [
                    PCA9685(i2c_bus, address=left_address),
                    PCA9685(i2c_bus, address=right_address),
                ]
                for p in self.pca:
                    p.frequency = 60
                    p.channels[0].duty_cycle = 0
                    p.channels[1].duty_cycle = 0xFFFF
                break
            except OSError as e:
                if attempt == 4:
                    raise
                print(f"Track I2C init attempt {attempt + 1} failed: {e}, retrying in 1s")
                time.sleep(1.0)
        self._lock = threading.Lock()
        self._stop_timer = None
        self.left_speed = 0.0
        self.left_dir = 0
        self.right_speed = 0.0
        self.right_dir = 0
        print("Track controller initialized")

    def _set_track(self, track: int, speed: float, direction: int):
        """Set individual track. speed 0-1, direction 0 or 1."""
        if speed > 0:
            frequency = speed * 2300
            dir_val = direction * 0xFFFF
            self.pca[track].frequency = int(frequency)
            self.pca[track].channels[1].duty_cycle = int(dir_val)
            self.pca[track].channels[0].duty_cycle = 0x7FFF  # go
        else:
            self.pca[track].channels[0].duty_cycle = 0  # stop

    def move(
            self,
            left_speed: float,
            left_dir: int,
            right_speed: float,
            right_dir: int,
            duration: float = 0):
        """Track movement function.

        Directions use native convention: 1=forward, 0=backward for both tracks.
        Left track hardware direction is inverted internally (mirrored on chassis).
        """
        with self._lock:
            if self._stop_timer is not None:
                self._stop_timer.cancel()
                self._stop_timer = None
            hw_left_dir = 0 if left_dir else 1  # Invert left track: mirrored on chassis
            self._set_track(0, left_speed, hw_left_dir)   # pca[0] = 0x40 = left
            self._set_track(1, right_speed, right_dir)     # pca[1] = 0x41 = right
            track_logger.info(f"TrackController.Move: left_speed={left_speed:.3f} dir={left_dir} ({hw_left_dir}) "
                              f"right_speed={right_speed:.3f} dir={right_dir}")
            self.left_speed = left_speed
            self.left_dir = left_dir
            self.right_speed = right_speed
            self.right_dir = right_dir
        if duration > 0:
            self._stop_timer = threading.Timer(duration, self.stop)
            self._stop_timer.start()

    def rotate(self, speed: float, direction: int, duration: float = 0):
        """Rotate body in place. direction: 0=right, 1=left.

        Right: left forward (1) + right backward (0).
        Left:  left backward (0) + right forward (1).
        """
        self.move(speed, 1 - direction, speed, direction, duration)

    def stop(self):
        with self._lock:
            if self._stop_timer is not None:
                self._stop_timer.cancel()
                self._stop_timer = None
            self._set_track(0, 0, 0)
            self._set_track(1, 0, 0)
            self.left_speed = 0.0
            self.right_speed = 0.0
            track_logger.info("HW stop: both tracks stopped")

    def get_status(self) -> dict:
        with self._lock:
            return {
                "left_speed": self.left_speed,
                "left_dir": self.left_dir,
                "right_speed": self.right_speed,
                "right_dir": self.right_dir,
            }


class StateLogger:
    """Logs track state at ~10Hz to a JSONL file."""

    CAMERA_SERVER_URL = "http://localhost:8080"
    SAMPLE_INTERVAL = 0.1  # 10Hz

    def __init__(self, tracks: Optional['TrackController']):
        self.tracks = tracks
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._log_file = None

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._thread.join(timeout=2)
        if self._log_file:
            self._log_file.close()

    def _resolve_log_path(self) -> Optional[str]:
        """Query camera server for servo log directory."""
        try:
            resp = http_requests.get(f"{self.CAMERA_SERVER_URL}/session", timeout=2.0)
            if resp.status_code == 200:
                servo_dir = resp.json().get("servo_dir")
                if servo_dir:
                    return f"{servo_dir}/state.jsonl"
        except Exception:
            pass
        return None

    def _run(self):
        # Wait for camera server to come up (it may start after servo_api)
        log_path = None
        for _ in range(60):
            if self._stop_event.is_set():
                return
            log_path = self._resolve_log_path()
            if log_path:
                break
            time.sleep(1)

        if not log_path:
            print("StateLogger: camera server not available, logging disabled")
            return

        self._log_file = open(log_path, "a")
        print(f"StateLogger: logging to {log_path}")

        while not self._stop_event.is_set():
            now = datetime.now()
            timestamp = now.strftime("%Y%m%d_%H%M%S") + f"_{now.microsecond:06d}"

            left_speed = 0.0
            left_dir = 0
            right_speed = 0.0
            right_dir = 0
            if self.tracks:
                with self.tracks._lock:
                    left_speed = self.tracks.left_speed
                    left_dir = self.tracks.left_dir
                    right_speed = self.tracks.right_speed
                    right_dir = self.tracks.right_dir

            entry = {
                "timestamp": timestamp,
                "left_speed": left_speed,
                "left_dir": left_dir,
                "right_speed": right_speed,
                "right_dir": right_dir,
            }
            self._log_file.write(json.dumps(entry) + "\n")
            self._log_file.flush()

            self._stop_event.wait(self.SAMPLE_INTERVAL)

        print("StateLogger: stopped")


# API Models
class TrackMoveRequest(BaseModel):
    left_speed: float = Field(..., ge=0, le=1, description="Left track speed 0-1")
    left_dir: int = Field(..., ge=0, le=1, description="Left track direction (0 or 1)")
    right_speed: float = Field(..., ge=0, le=1, description="Right track speed 0-1")
    right_dir: int = Field(..., ge=0, le=1, description="Right track direction (0 or 1)")
    duration: float = Field(0, ge=0, le=TRACK_MAX_DURATION, description="Auto-stop after seconds (0=manual stop)")

class TrackRotateRequest(BaseModel):
    speed: float = Field(..., ge=0, le=1, description="Rotation speed 0-1")
    direction: int = Field(..., ge=0, le=1, description="Rotation direction: 0=right, 1=left")
    duration: float = Field(0, ge=0, le=TRACK_MAX_DURATION, description="Auto-stop after seconds (0=manual stop)")

# Controllers
track_controller = None
state_logger = None

# FastAPI app
app = FastAPI(
    title="Track Control API",
    description="REST API for tank track control",
    version="2.0.0"
)

@app.on_event("startup")
async def startup_event():
    global track_controller, state_logger
    try:
        track_controller = TrackController(left_address=0x40, right_address=0x41)
        print("Track controller initialized successfully")
    except Exception as e:
        print(f"Failed to initialize track controller: {e}")
        raise
    state_logger = StateLogger(track_controller)
    state_logger.start()

@app.on_event("shutdown")
async def shutdown_event():
    global track_controller, state_logger
    if state_logger:
        state_logger.stop()
    if track_controller:
        track_controller.stop()
        print("Track controller stopped")

@app.get("/status")
async def get_status():
    if not track_controller:
        raise HTTPException(status_code=500, detail="Track controller not initialized")
    return track_controller.get_status()

@app.post("/tracks/move")
async def move_tracks(request: TrackMoveRequest):
    if not track_controller:
        raise HTTPException(status_code=500, detail="Track controller not initialized")
    try:
        track_controller.move(request.left_speed, request.left_dir,
                              request.right_speed, request.right_dir,
                              request.duration)
        return {"message": "tracks moving", "duration": request.duration}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Track error: {e}")

@app.post("/tracks/rotate")
async def rotate_tracks(request: TrackRotateRequest):
    if not track_controller:
        raise HTTPException(status_code=500, detail="Track controller not initialized")
    try:
        track_controller.rotate(request.speed, request.direction, request.duration)
        return {"message": "rotating", "direction": request.direction, "duration": request.duration}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Track error: {e}")

@app.post("/tracks/stop")
async def stop_tracks():
    if not track_controller:
        raise HTTPException(status_code=500, detail="Track controller not initialized")
    try:
        track_controller.stop()
        return {"message": "tracks stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Track error: {e}")

if __name__ == "__main__":
    print("Starting Track Control API Server...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
