#!/usr/bin/env python3
"""
Robust servo control API for Jetson Nano with smooth movement.
Uses simple threading approach instead of async for better stability.
"""

import json
import time
import threading
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from adafruit_servokit import ServoKit
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
import requests as http_requests
import uvicorn

class ServoController:
    def __init__(self, channel: int = 0, address: int = 0x42):
        """Initialize servo controller with smooth movement capability"""
        self.kit = ServoKit(channels=16, address=address)
        self.servo = self.kit.servo[channel]
        
        # Movement state
        self.current_angle = 90.0  # Current actual position
        self.target_angle = 90.0   # Target position to move to
        self.is_running = False
        self.movement_thread = None
        
        # Movement parameters
        self.step_size = 1.0      # Degrees per step
        self.step_delay = 0.02    # Seconds between steps (50 steps/second)
        
        # Thread synchronization
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        
        # Initialize servo to center position
        self.servo.angle = self.current_angle
        print(f"Servo initialized at {self.current_angle} degrees")
    
    def start_movement_thread(self):
        """Start the smooth movement thread"""
        if self.is_running:
            return
        
        self._stop_event.clear()
        self.movement_thread = threading.Thread(target=self._movement_loop, daemon=True)
        self.movement_thread.start()
        self.is_running = True
        print("Movement thread started")
    
    def stop_movement_thread(self):
        """Stop the smooth movement thread"""
        if not self.is_running:
            return
        
        self._stop_event.set()
        if self.movement_thread and self.movement_thread.is_alive():
            self.movement_thread.join(timeout=1.0)
        self.is_running = False
        print("Movement thread stopped")
    
    def _movement_loop(self):
        """Main movement loop - runs in separate thread"""
        print("Movement loop started")
        
        while not self._stop_event.is_set():
            moved = False
            
            with self._lock:
                # Calculate distance to target
                distance = self.target_angle - self.current_angle
                
                if abs(distance) > 0.5:  # Only move if more than 0.5 degrees away
                    # Calculate next step
                    if distance > 0:
                        step = min(self.step_size, distance)
                    else:
                        step = max(-self.step_size, distance)
                    
                    # Update position
                    self.current_angle += step
                    
                    # Ensure within bounds
                    self.current_angle = max(0, min(180, self.current_angle))
                    
                    # Move servo
                    try:
                        self.servo.angle = self.current_angle
                        moved = True
                    except Exception as e:
                        print(f"Servo movement error: {e}")
            
            # Sleep between steps
            time.sleep(self.step_delay)
        
        print("Movement loop ended")
    
    def set_target(self, angle: float) -> dict:
        """Set new target angle (0-180 degrees)"""
        # Validate input
        if not 0 <= angle <= 180:
            raise ValueError(f"Angle must be between 0 and 180, got {angle}")
        
        with self._lock:
            old_target = self.target_angle
            self.target_angle = float(angle)
        
        # Start movement thread if not running
        if not self.is_running:
            self.start_movement_thread()
        
        return {
            "previous_target": old_target,
            "new_target": self.target_angle,
            "current_position": self.current_angle,
            "status": "moving" if abs(self.target_angle - self.current_angle) > 0.5 else "arrived"
        }
    
    def get_status(self) -> dict:
        """Get current servo status"""
        with self._lock:
            distance = abs(self.target_angle - self.current_angle)
            
        return {
            "current_position": round(self.current_angle, 1),
            "target_position": round(self.target_angle, 1),
            "distance_to_target": round(distance, 1),
            "status": "moving" if distance > 0.5 else "arrived",
            "thread_running": self.is_running
        }
    
    def set_speed(self, steps_per_second: float) -> dict:
        """Adjust movement speed"""
        if not 1 <= steps_per_second <= 200:
            raise ValueError("Steps per second must be between 1 and 200")
        
        with self._lock:
            self.step_delay = 1.0 / steps_per_second
        
        return {
            "steps_per_second": steps_per_second,
            "step_delay": self.step_delay
        }

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
        self.pca = [
            PCA9685(i2c_bus, address=left_address),
            PCA9685(i2c_bus, address=right_address),
        ]
        for p in self.pca:
            p.frequency = 60
            p.channels[0].duty_cycle = 0
            p.channels[1].duty_cycle = 0xFFFF
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
            track_logger.info(f"TrackController.Move: left_speed={left_speed:.3f} dir={left_dir}  "
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
        return {"status": "ok"}


class StateLogger:
    """Logs servo angle and track state at ~10Hz to a JSONL file."""

    CAMERA_SERVER_URL = "http://localhost:8080"
    SAMPLE_INTERVAL = 0.1  # 10Hz

    def __init__(self, servo: ServoController, tracks: Optional['TrackController']):
        self.servo = servo
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

            with self.servo._lock:
                servo_angle = round(self.servo.current_angle, 1)
                servo_target = round(self.servo.target_angle, 1)

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
                "servo_angle": servo_angle,
                "servo_target": servo_target,
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
class ServoMoveRequest(BaseModel):
    angle: float = Field(..., ge=0, le=180, description="Target angle in degrees (0-180)")

class ServoMoveNormalizedRequest(BaseModel):
    position: float = Field(..., ge=0, le=1, description="Target position normalized (0-1)")

class ServoSpeedRequest(BaseModel):
    steps_per_second: float = Field(..., ge=1, le=200, description="Movement speed in steps per second")

class TrackMoveRequest(BaseModel):
    left_speed: float = Field(..., ge=0, le=1, description="Left track speed 0-1")
    left_dir: int = Field(..., ge=0, le=1, description="Left track direction (0 or 1)")
    right_speed: float = Field(..., ge=0, le=1, description="Right track speed 0-1")
    right_dir: int = Field(..., ge=0, le=1, description="Right track direction (0 or 1)")
    duration: float = Field(0, ge=0, le=10, description="Auto-stop after seconds (0=manual stop)")

class TrackRotateRequest(BaseModel):
    speed: float = Field(..., ge=0, le=1, description="Rotation speed 0-1")
    direction: int = Field(..., ge=0, le=1, description="Rotation direction: 0=right, 1=left")
    duration: float = Field(0, ge=0, le=10, description="Auto-stop after seconds (0=manual stop)")

# Initialize controllers
servo_controller = None
track_controller = None
state_logger = None

# FastAPI app
app = FastAPI(
    title="Servo Control API",
    description="REST API for smooth servo motor control",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    """Initialize servo and track controllers on startup"""
    global servo_controller, track_controller, state_logger
    try:
        servo_controller = ServoController(channel=0, address=0x42)
        servo_controller.start_movement_thread()
        print("Servo controller initialized successfully")
    except Exception as e:
        print(f"Failed to initialize servo controller: {e}")
        raise
    try:
        track_controller = TrackController(left_address=0x40, right_address=0x41)
        print("Track controller initialized successfully")
    except Exception as e:
        print(f"Failed to initialize track controller: {e}")
        print("Track endpoints will be unavailable")
    state_logger = StateLogger(servo_controller, track_controller)
    state_logger.start()

@app.on_event("shutdown")
async def shutdown_event():
    """Clean shutdown"""
    global servo_controller, track_controller, state_logger
    if state_logger:
        state_logger.stop()
    if track_controller:
        track_controller.stop()
        print("Track controller stopped")
    if servo_controller:
        servo_controller.stop_movement_thread()
        print("Servo controller stopped")

@app.get("/")
async def root():
    """API information"""
    return {
        "message": "Servo Control API",
        "version": "1.0.0",
        "endpoints": {
            "GET /status": "Get current servo status",
            "POST /move": "Move servo to angle (0-180 degrees)",
            "POST /move_normalized": "Move servo to normalized position (0-1)",
            "POST /speed": "Set movement speed",
            "POST /stop": "Stop movement and hold position"
        }
    }

@app.get("/status")
async def get_status():
    """Get current servo status"""
    if not servo_controller:
        raise HTTPException(status_code=500, detail="Servo controller not initialized")
    
    return servo_controller.get_status()

@app.post("/move")
async def move_servo(request: ServoMoveRequest):
    """Move servo to specific angle (0-180 degrees)"""
    if not servo_controller:
        raise HTTPException(status_code=500, detail="Servo controller not initialized")
    
    try:
        result = servo_controller.set_target(request.angle)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Servo control error: {e}")

@app.post("/move_normalized")
async def move_servo_normalized(request: ServoMoveNormalizedRequest):
    """Move servo to normalized position (0=0°, 1=180°)"""
    if not servo_controller:
        raise HTTPException(status_code=500, detail="Servo controller not initialized")
    
    try:
        # Convert normalized position to angle
        angle = request.position * 180.0
        result = servo_controller.set_target(angle)
        result["normalized_position"] = request.position
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Servo control error: {e}")

@app.post("/speed")
async def set_speed(request: ServoSpeedRequest):
    """Set movement speed in steps per second"""
    if not servo_controller:
        raise HTTPException(status_code=500, detail="Servo controller not initialized")
    
    try:
        result = servo_controller.set_speed(request.steps_per_second)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Speed control error: {e}")

@app.post("/stop")
async def stop_servo():
    """Stop movement and hold current position"""
    if not servo_controller:
        raise HTTPException(status_code=500, detail="Servo controller not initialized")
    
    try:
        with servo_controller._lock:
            servo_controller.target_angle = servo_controller.current_angle
        
        return {
            "message": "Movement stopped",
            "position": servo_controller.current_angle
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stop error: {e}")

@app.post("/tracks/move")
async def move_tracks(request: TrackMoveRequest):
    """Move both tracks independently"""
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
    """Rotate body in place"""
    if not track_controller:
        raise HTTPException(status_code=500, detail="Track controller not initialized")
    try:
        track_controller.rotate(request.speed, request.direction, request.duration)
        return {"message": "rotating", "direction": request.direction, "duration": request.duration}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Track error: {e}")

@app.post("/tracks/stop")
async def stop_tracks():
    """Stop both tracks"""
    if not track_controller:
        raise HTTPException(status_code=500, detail="Track controller not initialized")
    try:
        track_controller.stop()
        return {"message": "tracks stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Track error: {e}")

if __name__ == "__main__":
    print("Starting Servo Control API Server...")
    print("Access API documentation at: http://localhost:8000/docs")
    print("API endpoints will be available at: http://localhost:8000")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
