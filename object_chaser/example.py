import cv2
import matplotlib.pyplot as plt
from ultralytics import YOLO
from tqdm import tqdm

# Load the pre-trained YOLO11 model with progress bar
with tqdm(total=1, desc="Loading YOLO model") as pbar:
    model = YOLO("yolo11n.pt")  # Replace with the path to your model file if necessary
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
            # Draw rectangle around the person
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            # Add label
            confidence = box.conf[0]
            label = f"Person: {confidence:.2f}"
            cv2.putText(img, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

# Convert BGR image to RGB for displaying with matplotlib
img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
plt.imshow(img_rgb)
plt.axis('off')  # Hide axes
plt.show()
