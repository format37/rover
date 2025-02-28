import requests
import time
import os
import argparse
from tqdm import tqdm

def process_images(image_path, server_url, num_requests=10):
    """
    Send multiple image requests to the YOLO server and calculate performance metrics.
    
    Args:
        image_path: Path to the image file
        server_url: URL of the YOLO server
        num_requests: Number of requests to send
    
    Returns:
        tuple: (average FPS, total time, server processing times)
    """
    # Verify the image exists
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")
    
    # Open the image file
    with open(image_path, 'rb') as img_file:
        image_data = img_file.read()
    
    # Prepare for requests
    url = f"{server_url}/detect/"
    server_times = []
    
    # Start timing
    start_time = time.time()
    
    # Send requests
    for _ in tqdm(range(num_requests), desc="Sending requests"):
        files = {'file': ('image.jpg', image_data, 'image/jpeg')}
        
        response = requests.post(url, files=files)
        
        if response.status_code == 200:
            result = response.json()
            server_times.append(result['processing_time'])
            
            # Optional: Print detections for the first request
            if len(server_times) == 1:
                print("\nDetections in first image:")
                for i, detection in enumerate(result['detections']):
                    print(f"  {i+1}. {detection['label']} "
                          f"(Confidence: {detection['confidence']:.2f})")
        else:
            print(f"Error: {response.status_code}, {response.text}")
    
    # Calculate performance metrics
    total_time = time.time() - start_time
    fps = num_requests / total_time
    
    return fps, total_time, server_times

def main():
    parser = argparse.ArgumentParser(description='YOLO Detection Client')
    parser.add_argument('--image', default='photo.jpg', help='Path to the image file')
    parser.add_argument('--server', default='http://localhost:8765', help='YOLO server URL')
    parser.add_argument('--count', type=int, default=10, help='Number of requests to send')
    
    args = parser.parse_args()
    
    try:
        print(f"Sending {args.count} requests with image: {args.image}")
        fps, total_time, server_times = process_images(
            args.image, args.server, args.count
        )
        
        # Print performance metrics
        print("\nPerformance Metrics:")
        print(f"Total time: {total_time:.2f} seconds")
        print(f"Average FPS: {fps:.2f}")
        print(f"Average server processing time: {sum(server_times)/len(server_times):.3f} seconds")
        print(f"Min processing time: {min(server_times):.3f} seconds")
        print(f"Max processing time: {max(server_times):.3f} seconds")
        
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main() 