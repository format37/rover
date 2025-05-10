import asyncio
from adafruit_servokit import ServoKit
import math
from threading import Lock
import time

# Initialize servo kit
kit = ServoKit(channels=16, address=0x42)
head_servo = kit.servo[0]
current_goal = 90  # Initial goal angle in degrees (0 to 180)
servo_lock = Lock()

async def smooth_move(servo, duration=2, steps_per_second=100):
    """
    Continuously move the servo toward the current_goal, adapting to goal updates.
    duration: Approximate time to move from one extreme to another (seconds).
    steps_per_second: Number of steps per second for smooth movement.
    """
    global current_goal
    print(f"# Moving to goal: {current_goal}")
    last_angle = servo.angle if servo.angle is not None else 90
    step_duration = 1 / steps_per_second
    initialized = False

    while True:
        with servo_lock:
            if not initialized:
                initialized = True
                print(f"# Initialized")
            # Get the current goal and calculate the step size
            target_angle = current_goal
            # Calculate step size based on remaining distance and duration
            max_step = abs(target_angle - last_angle) / (duration * steps_per_second)
            # Move toward the target by a small step
            if last_angle < target_angle:
                next_angle = min(last_angle + max_step, target_angle)
            else:
                next_angle = max(last_angle - max_step, target_angle)
            # Apply sine easing for smoothness
            t = (next_angle - last_angle) / (target_angle - last_angle) if target_angle != last_angle else 1
            eased_angle = last_angle + (target_angle - last_angle) * (math.sin(t * math.pi - math.pi/2) + 1) / 2
            servo.angle = eased_angle
            last_angle = eased_angle
        await asyncio.sleep(step_duration)

def update_goal(new_goal):
    """
    Update the current goal angle (between 0 and 1, mapped to 0-180 degrees).
    Can be called from anywhere in the script or externally.
    """
    global current_goal
    if not 0 <= new_goal <= 1:
        print(f"Error: Goal {new_goal} must be between 0 and 1")
        return
    with servo_lock:
        current_goal = (1 - new_goal) * 180
    print(f"Updated goal to {current_goal} degrees")

async def main():
    # Start the smooth movement task in the background
    move_task = asyncio.create_task(smooth_move(head_servo))

    # Simulate goal updates (up to 3 times per second)
    try:
        while True:
            # Example: Update goal every 0.333 seconds (3 Hz)
            update_goal(0.0)  # Move to 180 degrees
            await asyncio.sleep(3)
            update_goal(0.5)  # Move to 90 degrees
            await asyncio.sleep(3)
            update_goal(1.0)  # Move to 0 degrees
            await asyncio.sleep(3)
    except KeyboardInterrupt:
        print("Stopping...")
        move_task.cancel()
        with servo_lock:
            head_servo.angle = None  # Reset servo
        await asyncio.sleep(0.1)

if __name__ == "__main__":
    asyncio.run(main())