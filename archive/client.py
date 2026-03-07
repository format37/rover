import requests
import time
import os
import argparse
import asyncio
from tqdm import tqdm
import cv2
import logging
import aiohttp
import numpy as np

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

servo_api_url = 'http://localhost:8000'
camera_server_url = 'http://localhost:8080'

# Global bar for goal progress
bar = None
last_servo_update_time = None


def update_goal(new_goal):
    global bar, last_servo_update_time
    logger.info(f"# Updating goal to {new_goal}")
    if not 0 <= new_goal <= 1:
        print(f"Error: Goal {new_goal} must be between 0 and 1")
        return
    now = time.monotonic()
    if last_servo_update_time is not None:
        elapsed = now - last_servo_update_time
        if elapsed < 2.0:
            logger.info(f"Skipping servo update; only {elapsed:.2f}s since last command")
            return
    # Convert normalized position (0-1) to absolute target angle (like old current_goal)
    # target_angle = (1 - new_goal) * 180  # 0=left(180°), 1=right(0°)
    target_angle = new_goal * 180 # 0=right(0°), 1=left(180°)

    try:
        # Send absolute target to servo API (let servo API handle smooth movement)
        response = requests.post(f"{servo_api_url}/move",
                               json={"angle": target_angle},
                               timeout=0.1)
        if response.status_code != 200:
            logger.warning(f"Servo API error: {response.status_code}")
        last_servo_update_time = now
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to update servo: {e}")
        last_servo_update_time = now

    # Update the bar if it exists
    if bar is not None:
        bar.n = int(new_goal * 100)
        bar.refresh()
    # logger.info(f"Updated goal to {target_angle} degrees")
    # time.sleep(2) # Debugging delay to avoid too rapid commands

async def process_camera_feed(server_url, label='person'):
    print(f"Processing camera feed, tracking label='{label}' (infinite loop, Ctrl+C to stop)")
    url = f"{server_url}/detect/"
    server_times = []
    start_time = time.time()
    request_count = 0
    async with aiohttp.ClientSession() as session:
        try:
            while True:
                # Fetch latest frame from camera server
                async with session.get(f"{camera_server_url}/frame") as frame_resp:
                    if frame_resp.status != 200:
                        logger.warning(f"Camera server error: {frame_resp.status}")
                        await asyncio.sleep(0.1)
                        continue
                    image_data = await frame_resp.read()

                async with session.post(url, data={'file': image_data}) as response:
                    if response.status == 200:
                        result = await response.json()
                        server_times.append(result['processing_time'])
                        label_detections = [d for d in result['detections'] if d['label'] == label]
                        if label_detections:
                            best_person = max(label_detections, key=lambda d: d['confidence'])

                            # Decode JPEG to get image dimensions
                            img_array = np.frombuffer(image_data, dtype=np.uint8)
                            color_image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                            img_width = color_image.shape[1]

                            x_middle = best_person['bbox'][0] + best_person['bbox'][2] / 2
                            x_normalized = x_middle / img_width
                            x_normalized = 1-x_normalized  # Invert: 0=right, 1=left
                            logger.info(f"Best person detection: {best_person}, x_normalized={x_normalized:.2f}")

                            servo_range = 180
                            response = requests.get(f"{servo_api_url}/status", timeout=0.1)
                            if response.status_code == 200:
                                status = response.json()
                                current_servo_angle = status.get('current_position')
                                logger.info(f"Current servo angle: {current_servo_angle}")
                                servo_status = status.get('status')
                                logger.info(f"Servo status: {servo_status}")
                            else:
                                logger.warning(f"Failed to get servo status: {response.status_code}")
                                logger.warning(f"Response content: {response.content}")
                                current_servo_angle = 90  # Default to center if error
                            fov = 87  # Realsense D435 horizontal FOV
                            camera_offset = (x_normalized - 0.5) * fov
                            logger.info(f"Camera FOV: {fov}, offset from center (degrees): {camera_offset:.2f}")
                            if abs(camera_offset) > 10:  # Only update if offset is significant
                                new_goal_angle = current_servo_angle + camera_offset
                                logger.info(f"New goal before clamp (degrees): {new_goal_angle:.2f}")
                                new_goal_angle = max(0, min(servo_range, new_goal_angle))
                                if new_goal_angle != current_servo_angle + camera_offset:
                                    logger.info(
                                        f"New goal clamped to servo range 0-{servo_range} degrees: {new_goal_angle:.2f}"
                                    )
                                new_goal = new_goal_angle / servo_range
                                logger.info(f"New goal (normalized 0-1): {new_goal:.2f}")

                                if servo_status == 'moving':
                                    logger.info("Servo is currently moving, skipping goal update to avoid overload")
                                else:
                                    update_goal(new_goal)

                    else:
                        print(f"Error: {response.status}, {await response.text()}")
                request_count += 1
        except KeyboardInterrupt:
            print("\nInterrupted by user.")
    total_time = time.time() - start_time
    fps = request_count / total_time if total_time > 0 else 0
    return fps, total_time, server_times

async def servo_set_speed(steps_per_second):
    try:
        response = requests.post(f"{servo_api_url}/speed",
                                 json={"steps_per_second": steps_per_second},
                                 timeout=0.1)
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Servo speed set: {result}")
        else:
            logger.warning(f"Failed to set servo speed: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Error setting servo speed: {e}")

async def main():
    global bar
    parser = argparse.ArgumentParser(description='Object chaser client - head tracking')
    parser.add_argument('--label', type=str, default='person', help='YOLO label to track (default: person)')
    args = parser.parse_args()

    server_url = 'http://localhost:8765'

    logger.info("Initializing servo via API")
    try:
        # Initialize servo to center position via API
        response = requests.post(f"{servo_api_url}/move",
                               json={"angle": 90},
                               timeout=2.0)
        if response.status_code == 200:
            logger.info("Servo initialized to center position")
        else:
            logger.error(f"Failed to initialize servo: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Cannot connect to servo API: {e}")
        logger.error("Make sure servo_api.py is running on localhost:8000")
        return

    # Initialize tqdm bar for goal (0 to 1, 100 steps)
    bar = tqdm(total=100, desc='Goal', position=0, leave=True, bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt}')
    bar.n = 0
    bar.refresh()

    await servo_set_speed(200)  # Set speed to 90 steps/sec

    try:
        logger.info(f"Starting camera feed, tracking '{args.label}'")
        fps, total_time, server_times = await process_camera_feed(
            server_url,
            label=args.label,
        )
        logger.info("\nPerformance Metrics:")
        logger.info(f"Total time: {total_time:.2f} seconds")
        logger.info(f"Average FPS: {fps:.2f}")
    except Exception as e:
        logger.error(f"Error: {str(e)}")
    finally:
        # Stop servo movement via API
        try:
            requests.post(f"{servo_api_url}/stop", timeout=1.0)
            logger.info("Servo stopped")
        except requests.exceptions.RequestException:
            logger.warning("Could not stop servo via API")

        if bar is not None:
            bar.close()
        await asyncio.sleep(0.1)

if __name__ == "__main__":
    asyncio.run(main())