import asyncio
from fastapi import FastAPI
from adafruit_servokit import ServoKit
import math
from threading import Lock

app = FastAPI()
kit = ServoKit(channels=16, address=0x42)
head_servo = kit.servo[0]
current_angle = 90
servo_lock = Lock()

async def smooth_move(servo, start_angle, end_angle, duration, steps=200):
    for i in range(steps + 1):
        t = i / steps
        angle = start_angle + (end_angle - start_angle) * (math.sin(t * math.pi - math.pi/2) + 1) / 2
        servo.angle = angle
        await asyncio.sleep(duration / steps)

@app.get("/move")
async def move_head(goal: float):
    global current_angle
    if not 0 <= goal <= 1:
        return {"error": "Goal must be between 0 and 1"}
    target_angle = (1 - goal) * 180
    with servo_lock:
        await smooth_move(head_servo, current_angle, target_angle, duration=2)
        current_angle = target_angle
    return {"status": "success", "angle": target_angle}