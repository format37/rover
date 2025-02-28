import requests
import time
import os
import argparse
import asyncio
from tqdm import tqdm
from camera_controls import CameraController
import cv2

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
                        print(f"  {j+1}. {detection['label']} "
                              f"(Confidence: {detection['confidence']:.2f}, "
                              f"X-middle: {x_middle:.2f}, Position: {x_normalized:.2f}) of {color_image.shape[1]}")
                
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
                    label = f"({x_normalized:.2f}, {color_image.shape[1]}, {detection['bbox']})"
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

def process_images(image_path, server_url, output_dir='.', num_requests=10):
    """
    Send multiple image requests to the YOLO server and calculate performance metrics.
    
    Args:
        image_path: Path to the image file
        server_url: URL of the YOLO server
        output_dir: Directory to save annotated images
        num_requests: Number of requests to send
    
    Returns:
        tuple: (average FPS, total time, server processing times)
    """
    print(f"Processing image: {image_path}")
    # Verify the image exists
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")
    
    # Open the image file
    with open(image_path, 'rb') as img_file:
        image_data = img_file.read()
    
    # Load the original image for annotation
    original_image = cv2.imread(image_path)
    if original_image is None:
        raise ValueError(f"Could not read image: {image_path}")
    
    # Prepare for requests
    url = f"{server_url}/detect/"
    server_times = []
    
    # Start timing
    start_time = time.time()
    
    # Send requests
    for i in tqdm(range(num_requests), desc="Sending requests"):
        files = {'file': ('image.jpg', image_data, 'image/jpeg')}
        
        response = requests.post(url, files=files)
        
        if response.status_code == 200:
            result = response.json()
            server_times.append(result['processing_time'])
            
            # Create a copy of the image for drawing bounding boxes
            annotated_image = original_image.copy()
            
            # Print detections for the first request
            if i == 0:
                print("\nDetections in first image:")
                for j, detection in enumerate(result['detections']):
                    # Calculate middle point on x-axis
                    x_middle = (detection['bbox'][0] + detection['bbox'][2]) / 2
                    # Get image width from the original image
                    image_width = original_image.shape[1]
                    # Calculate normalized position (0 to 1)
                    x_normalized = x_middle / image_width
                    print(f"  {j+1}. {detection['label']} "
                          f"(Confidence: {detection['confidence']:.2f}, "
                          f"X-middle: {x_middle:.2f}, Position: {x_normalized:.2f})")
            
            # Draw bounding boxes on the image
            for detection in result['detections']:
                # Extract bounding box coordinates
                x, y, w, h = detection['bbox']
                
                # Draw rectangle
                cv2.rectangle(annotated_image, (x, y), (x + w, y + h), (0, 255, 0), 2)
                
                # Add label with confidence
                label = f"{detection['label']}: {detection['confidence']:.2f}"
                cv2.putText(annotated_image, label, (x, y - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
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
        print(f"Sending {args.count} requests from camera feed")
        fps, total_time, server_times = await process_camera_feed(
            args.server, 
            args.output_dir, 
            args.enable_depth, 
            args.count
        )
        
        # Print performance metrics
        print("\nPerformance Metrics:")
        print(f"Total time: {total_time:.2f} seconds")
        print(f"Average FPS: {fps:.2f}")
        print(f"Average server processing time: {sum(server_times)/len(server_times):.3f} seconds")
        print(f"Min processing time: {min(server_times):.3f} seconds")
        print(f"Max processing time: {max(server_times):.3f} seconds")
        print(f"Annotated images saved to: {os.path.abspath(args.output_dir)}")
        
    except Exception as e:
        print(f"Error: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description='YOLO Detection Client')
    parser.add_argument('--image', help='Path to the image file (for static mode)')
    parser.add_argument('--server', default='http://localhost:8765', help='YOLO server URL')
    parser.add_argument('--count', type=int, default=10, help='Number of requests to send')
    parser.add_argument('--use_camera', action='store_true', default=True, help='Use camera feed instead of static image')
    parser.add_argument('--output_dir', default='camera_output', help='Directory to save camera images')
    parser.add_argument('--enable_depth', action='store_true', help='Enable depth capture (for RealSense camera)')
    
    args = parser.parse_args()
    
    try:
        if args.image:
            # If image is provided, override the use_camera setting
            args.use_camera = False
            print(f"Sending {args.count} requests with image: {args.image}")
            fps, total_time, server_times = process_images(
                args.image, args.server, args.output_dir, args.count
            )
        elif args.use_camera:
            # Run async main for camera operations
            asyncio.run(async_main(args))
        else:
            print("Error: Either --image must be specified or --use_camera must be enabled")
            return
            
        # Print performance metrics
        if not args.use_camera:  # Only print metrics here for image mode
            print("\nPerformance Metrics:")
            print(f"Total time: {total_time:.2f} seconds")
            print(f"Average FPS: {fps:.2f}")
            print(f"Average server processing time: {sum(server_times)/len(server_times):.3f} seconds")
            print(f"Min processing time: {min(server_times):.3f} seconds")
            print(f"Max processing time: {max(server_times):.3f} seconds")
            print(f"Annotated images saved to: {os.path.abspath(args.output_dir)}")
        
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main() 