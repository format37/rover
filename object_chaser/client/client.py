import requests
import time
import os
import argparse
import asyncio
from tqdm import tqdm
from camera_controls import CameraController
import cv2
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

servo_api_url = 'http://localhost:8000'

# Global bar for goal progress
bar = None


def update_goal(new_goal):
    global bar
    logger.info(f"# Updating goal to {new_goal}")
    if not 0 <= new_goal <= 1:
        print(f"Error: Goal {new_goal} must be between 0 and 1")
        return
    # Convert normalized position (0-1) to absolute target angle (like old current_goal)
    target_angle = (1 - new_goal) * 180  # 0=left(180°), 1=right(0°)

    try:
        # Send absolute target to servo API (let servo API handle smooth movement)
        response = requests.post(f"{servo_api_url}/move",
                               json={"angle": target_angle},
                               timeout=0.1)
        if response.status_code != 200:
            logger.warning(f"Servo API error: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to update servo: {e}")

    # Update the bar if it exists
    if bar is not None:
        bar.n = int(new_goal * 100)
        bar.refresh()
    # logger.info(f"Updated goal to {target_angle} degrees")

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
                                x_middle = best_person['bbox'][0] + best_person['bbox'][2] / 2 # Left + width/2
                                x_normalized = x_middle / color_image.shape[1] # between 0=left and 1=right
                                
                                servo_range = 180
                                response = requests.post(f"{servo_api_url}/status", timeout=0.1)
                                if response.status_code == 200:
                                    status = response.json()
                                    current_servo_angle = status.get('current_angle')
                                    logger.info(f"Current servo angle: {current_servo_angle}")
                                else:
                                    logger.warning(f"Failed to get servo status: {response.status_code}")
                                    logger.warning(f"Response content: {response.content}")
                                    current_servo_angle = 90 # Default to center if error
                                fov = 87 # Realsense D435 horizontal FOV
                                x_normalized = x_normalized * (fov/servo_range)
                                
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