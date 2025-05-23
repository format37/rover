import requests
import time
import os
import argparse
import asyncio
from tqdm import tqdm
from camera_controls import CameraController
import cv2
from adafruit_servokit import ServoKit
from threading import Lock
import logging
import aiohttp
from tqdm import tqdm

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

current_goal = 90
servo_lock = Lock()

# Global bar for goal progress
bar = None

async def smooth_move(servo, duration=1, steps_per_second=100):
    global current_goal
    # logger.info(f"# Moving to goal: {current_goal}")
    last_angle = servo.angle if servo.angle is not None else 90
    step_duration = 1 / steps_per_second
    while True:
        with servo_lock:
            target_angle = current_goal
            max_step = abs(target_angle - last_angle) / (duration * steps_per_second)
            if last_angle < target_angle:
                next_angle = min(last_angle + max_step, target_angle)
            else:
                next_angle = max(last_angle - max_step, target_angle)
            # logger.info(f"Setting servo angle to {next_angle:.2f}")
            servo.angle = next_angle
            last_angle = next_angle
        await asyncio.sleep(step_duration)

def update_goal(new_goal):
    global current_goal, bar
    # logger.info(f"# Updating goal to {new_goal}")
    if not 0 <= new_goal <= 1:
        print(f"Error: Goal {new_goal} must be between 0 and 1")
        return
    with servo_lock:
        current_goal = (1 - new_goal) * 180
    # Update the bar if it exists
    if bar is not None:
        bar.n = int(new_goal * 100)
        bar.refresh()
    # logger.info(f"Updated goal to {current_goal} degrees")

async def process_camera_feed(server_url, output_dir='.', enable_depth=False):
    print(f"Processing camera feed, sending requests to server (infinite loop, Ctrl+C to stop)")
    url = f"{server_url}/detect/"
    server_times = []
    start_time = time.time()
    request_count = 0
    async with CameraController(output_dir=output_dir, enable_depth=enable_depth) as camera:
        async with aiohttp.ClientSession() as session:
            try:
                while True:
                    depth_image, color_image = await camera.get_frames()
                    # if request_count == 0 or request_count == num_requests - 1:
                    #     await camera.save_frames(depth_image, color_image)
                    _, img_encoded = cv2.imencode('.jpg', color_image)
                    image_data = img_encoded.tobytes()
                    async with session.post(url, data={'file': image_data}) as response:
                        if response.status == 200:
                            result = await response.json()
                            server_times.append(result['processing_time'])
                            person_detections = [d for d in result['detections'] if d['label'] == 'person']
                            if person_detections:
                                best_person = max(person_detections, key=lambda d: d['confidence'])
                                x_middle = best_person['bbox'][0] + best_person['bbox'][2] / 2
                                x_normalized = x_middle / color_image.shape[1]
                                update_goal(x_normalized)
                            annotated_image = color_image.copy()
                            for detection in result['detections']:
                                x, y, w, h = detection['bbox']
                                cv2.rectangle(annotated_image, (x, y), (x + w, y + h), (0, 255, 0), 2)
                                x_middle = detection['bbox'][0] + detection['bbox'][2] / 2
                                x_normalized = x_middle / color_image.shape[1]
                                label = f"({x_normalized:.2f}, {color_image.shape[1]}, {detection['bbox']}) {detection['label']}"
                                cv2.putText(annotated_image, label, (x, y - 10), 
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
                            # os.makedirs(output_dir, exist_ok=True)
                            # cv2.imwrite(f"{output_dir}/annotated_image_{request_count}.jpg", annotated_image)
                        else:
                            print(f"Error: {response.status}, {await response.text()}")
                    request_count += 1
            except KeyboardInterrupt:
                print("\nInterrupted by user.")
    total_time = time.time() - start_time
    fps = request_count / total_time if total_time > 0 else 0
    return fps, total_time, server_times

async def main():
    global bar
    server_url = 'http://localhost:8765'
    output_dir = 'camera_output'
    enable_depth = False

    logger.info("Initializing servo")
    kit = ServoKit(channels=16, address=0x42)
    head_servo = kit.servo[0]
    head_servo.angle = 90

    # Initialize tqdm bar for goal (0 to 1, 100 steps)
    bar = tqdm(total=100, desc='Goal', position=0, leave=True, bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt}')
    bar.n = 0
    bar.refresh()

    logger.info("Starting smooth servo movement task")
    move_task = asyncio.create_task(smooth_move(head_servo))
    try:
        logger.info(f"Starting camera feed")
        fps, total_time, server_times = await process_camera_feed(
            server_url,
            output_dir,
            enable_depth
        )
        logger.info("\nPerformance Metrics:")
        logger.info(f"Total time: {total_time:.2f} seconds")
        logger.info(f"Average FPS: {fps:.2f}")
    except Exception as e:
        logger.error(f"Error: {str(e)}")
    finally:
        move_task.cancel()
        with servo_lock:
            head_servo.angle = None
        if bar is not None:
            bar.close()
        await asyncio.sleep(0.1)

if __name__ == "__main__":
    asyncio.run(main())