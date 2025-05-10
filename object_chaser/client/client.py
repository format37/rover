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

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

current_goal = 90  # Initial goal angle in degrees (0 to 180)
servo_lock = Lock()

async def smooth_move(servo, duration=2, steps_per_second=100):
    """
    Continuously move the servo toward the current_goal, adapting to goal updates.
    duration: Approximate time to move from one extreme to another (seconds).
    steps_per_second: Number of steps per second for smooth movement.
    """
    global current_goal
    logger.info(f"# Moving to goal: {current_goal}")
    last_angle = servo.angle if servo.angle is not None else 90
    step_duration = 1 / steps_per_second

    while True:
        with servo_lock:
            target_angle = current_goal
            # Calculate step size based on remaining distance and duration
            max_step = abs(target_angle - last_angle) / (duration * steps_per_second)
            # Move toward the target by a small step
            if last_angle < target_angle:
                next_angle = min(last_angle + max_step, target_angle)
            else:
                next_angle = max(last_angle - max_step, target_angle)
            servo.angle = next_angle
            last_angle = next_angle
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
    logger.info(f"Updated goal to {current_goal} degrees")

async def process_camera_feed(server_url, output_dir='.', enable_depth=False, num_requests=10):
    """
    Capture images from camera and send to the YOLO server for processing.
    
    Args:
        server_url: URL of the YOLO server
        output_dir: Directory to save captured images
        enable_depth: Whether to enable depth capture
        num_requests: Number of requests to send
    
    Returns:
        tuple: (average FPS, total time, server processing times)
    """
    print(f"Processing camera feed, sending {num_requests} requests to server")
    
    # Prepare for requests
    url = f"{server_url}/detect/"
    server_times = []
    
    # Start timing
    start_time = time.time()
    
    async with CameraController(output_dir=output_dir, enable_depth=enable_depth) as camera:
        # Send requests
        for i in tqdm(range(num_requests), desc="Sending requests"):
            # Capture frame from camera
            depth_image, color_image = await camera.get_frames()
            
            # Save the current frame if it's the first or last request
            if i == 0 or i == num_requests - 1:
                await camera.save_frames(depth_image, color_image)
            
            # Convert color image to JPEG format in memory
            _, img_encoded = cv2.imencode('.jpg', color_image)
            image_data = img_encoded.tobytes()
            
            # Send to server
            files = {'file': ('image.jpg', image_data, 'image/jpeg')}
            
            response = requests.post(url, files=files)
            
            if response.status_code == 200:
                result = response.json()
                server_times.append(result['processing_time'])
                
                # --- New logic: Find the person with highest confidence and update goal ---
                person_detections = [d for d in result['detections'] if d['label'] == 'person']
                if person_detections:
                    best_person = max(person_detections, key=lambda d: d['confidence'])
                    x_middle = best_person['bbox'][0] + best_person['bbox'][2] / 2
                    x_normalized = x_middle / color_image.shape[1]
                    update_goal(x_normalized)
                    logger.info(f"Updated goal to person with confidence {best_person['confidence']:.2f} at x_normalized={x_normalized:.2f}")
                # --- End new logic ---
                
                # Create a copy of the image for drawing bounding boxes
                annotated_image = color_image.copy()
                
                # Print detections for the first request
                if i == 0:
                    print("\nDetections in first image:")
                    for j, detection in enumerate(result['detections']):
                        # Calculate middle point on x-axis
                        x_middle = detection['bbox'][0] + detection['bbox'][2] / 2
                        # Calculate normalized position (0 to 1)
                        x_normalized = x_middle / color_image.shape[1]
                        rectangle_area = detection['bbox'][2] * detection['bbox'][3]
                        print(f"  {j+1}. {detection['label']} "
                              f"(Confidence: {detection['confidence']:.2f}, "
                              f"X-middle: {x_middle:.2f}, Position: {x_normalized:.2f}, "
                              f"Square: {rectangle_area:.2f}) of {color_image.shape[1]}")
                
                # Draw bounding boxes on the image
                for detection in result['detections']:
                    # Extract bounding box coordinates
                    x, y, w, h = detection['bbox']
                    
                    # Draw rectangle
                    cv2.rectangle(annotated_image, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    
                    # Add label with confidence
                    x_middle = detection['bbox'][0] + detection['bbox'][2] / 2
                    x_normalized = x_middle / color_image.shape[1]
                    # label = f"{detection['label']}: {detection['confidence']:.2f} ({x_normalized:.2f}) of {color_image.shape[1]}"
                    label = f"({x_normalized:.2f}, {color_image.shape[1]}, {detection['bbox']}) {detection['label']}"
                    cv2.putText(annotated_image, label, (x, y - 10), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
                
                # Save the annotated image
                os.makedirs(output_dir, exist_ok=True)
                cv2.imwrite(f"{output_dir}/annotated_image_{i}.jpg", annotated_image)
            else:
                print(f"Error: {response.status_code}, {response.text}")
    
    # Calculate performance metrics
    total_time = time.time() - start_time
    fps = num_requests / total_time
    
    return fps, total_time, server_times

async def async_main(args):
    """Async main function to handle camera operations"""
    try:
        # Initialize servo kit and head_servo here
        logger.info("Initializing servo")
        kit = ServoKit(channels=16, address=0x42)
        head_servo = kit.servo[0]
        head_servo.angle = 90  # Set to a safe initial position

        # Start the smooth movement task in the background
        logger.info("Starting smooth servo movement task")
        move_task = asyncio.create_task(smooth_move(head_servo))

        logger.info(f"Sending {args.count} requests from camera feed")
        fps, total_time, server_times = await process_camera_feed(
            args.server, 
            args.output_dir, 
            args.enable_depth, 
            args.count
        )
        
        # Print performance metrics
        logger.info("\nPerformance Metrics:")
        logger.info(f"Total time: {total_time:.2f} seconds")
        logger.info(f"Average FPS: {fps:.2f}")
        logger.info(f"Average server processing time: {sum(server_times)/len(server_times):.3f} seconds")
        logger.info(f"Min processing time: {min(server_times):.3f} seconds")
        logger.info(f"Max processing time: {max(server_times):.3f} seconds")
        logger.info(f"Annotated images saved to: {os.path.abspath(args.output_dir)}")
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")

    finally:
        move_task.cancel()
        with servo_lock:
            head_servo.angle = None  # Reset servo
        await asyncio.sleep(0.1)

def main():
    parser = argparse.ArgumentParser(description='YOLO Detection Client')
    parser.add_argument('--server', default='http://localhost:8765', help='YOLO server URL')
    parser.add_argument('--count', type=int, default=10, help='Number of requests to send')
    parser.add_argument('--use_camera', action='store_true', default=True, help='Use camera feed instead of static image')
    parser.add_argument('--output_dir', default='camera_output', help='Directory to save camera images')
    parser.add_argument('--enable_depth', action='store_true', help='Enable depth capture (for RealSense camera)')
    
    args = parser.parse_args()
    
    # Run async main for camera operations
    asyncio.run(async_main(args))
        
if __name__ == "__main__":
    main()