#!/usr/bin/env python3
"""
Robust servo control API for Jetson Nano with smooth movement.
Uses simple threading approach instead of async for better stability.
"""

import time
import threading
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from adafruit_servokit import ServoKit
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

# API Models
class ServoMoveRequest(BaseModel):
    angle: float = Field(..., ge=0, le=180, description="Target angle in degrees (0-180)")

class ServoMoveNormalizedRequest(BaseModel):
    position: float = Field(..., ge=0, le=1, description="Target position normalized (0-1)")

class ServoSpeedRequest(BaseModel):
    steps_per_second: float = Field(..., ge=1, le=200, description="Movement speed in steps per second")

# Initialize servo controller
servo_controller = None

# FastAPI app
app = FastAPI(
    title="Servo Control API",
    description="REST API for smooth servo motor control",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    """Initialize servo controller on startup"""
    global servo_controller
    try:
        servo_controller = ServoController(channel=0, address=0x42)
        servo_controller.start_movement_thread()
        print("Servo controller initialized successfully")
    except Exception as e:
        print(f"Failed to initialize servo controller: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Clean shutdown"""
    global servo_controller
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
