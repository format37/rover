import asyncio
from fastapi import FastAPI
from adafruit_servokit import ServoKit
import math
from threading import Lock
from fastapi import BackgroundTasks

app = FastAPI()
kit = ServoKit(channels=16, address=0x42)
head_servo = kit.servo[0]
current_goal = 90
servo_lock = Lock()
task = None

async def smooth_move(servo, start_angle, end_angle, duration, steps=200):
    for i in range(steps + 1):
        t = i / steps
        angle = start_angle + (end_angle - start_angle) * (math.sin(t * math.pi - math.pi/2) + 1) / 2
        servo.angle = angle
        await asyncio.sleep(duration / steps)

async def move_to_goal():
    global current_goal
    while True:
        with servo_lock:
            start_angle = head_servo.angle if head_servo.angle is not None else 90
            await smooth_move(head_servo, start_angle, current_goal, duration=2)
        await asyncio.sleep(0.1)  # Small delay to prevent tight loop

@app.on_event("startup")
async def startup_event():
    global task
    task = asyncio.create_task(move_to_goal())

@app.get("/move")
async def move_head(goal: float, background_tasks: BackgroundTasks):
    global current_goal
    if not 0 <= goal <= 1:
        return {"error": "Goal must be between 0 and 1"}
    target_angle = (1 - goal) * 180
    with servo_lock:
        current_goal = target_angle
    return {"status": "success", "angle": target_angle}