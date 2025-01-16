import cv2
import matplotlib.pyplot as plt
from ultralytics import YOLO
from tqdm import tqdm
import torch

# Check if CUDA (GPU) is available
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"Using GPU: {torch.cuda.get_device_name(0)}")
    
# Load the pre-trained YOLO11 model with progress bar
with tqdm(total=1, desc="Loading YOLO model") as pbar:
    model = YOLO("yolo11n.pt")  # Replace with the path to your model file if necessary
    # Move model to GPU if available
    model.to('cuda' if torch.cuda.is_available() else 'cpu')
    pbar.update(1)

# Load the image
image_path = "photo.jpg"  # Replace with your image path
img = cv2.imread(image_path)

# Perform object detection with progress bar
with tqdm(total=1, desc="Processing image") as pbar:
    results = model(img)
    pbar.update(1)

# Iterate over detected objects
for result in results:
    for box in result.boxes:
        # Check if the detected object is a person (class ID for 'person' is typically 0)
        if int(box.cls[0]) == 0:
            # Extract bounding box coordinates
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            confidence = box.conf[0]
            print(f"Person detected (confidence: {confidence:.2f})")
            print(f"Bounding box coordinates:")
            print(f"  Top-left: ({x1}, {y1})")
            print(f"  Bottom-right: ({x2}, {y2})")
            print(f"  Width: {x2 - x1}")
            print(f"  Height: {y2 - y1}")
            print("-" * 40)

# Optional visualization code
SHOW_VISUALIZATION = False  # Set to True to enable visualization

if SHOW_VISUALIZATION:
    # Draw bounding boxes on the image
    for result in results:
        for box in result.boxes:
            if int(box.cls[0]) == 0:  # Only draw boxes for persons
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                confidence = box.conf[0]
                
                # Draw rectangle and confidence text
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(img, f"Person: {confidence:.2f}", 
                           (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 
                           0.5, (0, 255, 0), 2)
    
    # Display the image
    plt.figure(figsize=(12, 8))
    plt.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    plt.axis('off')
    plt.show()
