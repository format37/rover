import cv2
import time
import sys
import numpy as np
from datetime import datetime
from flask import Flask, request, jsonify
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
request_counter = 0

# Constants
INPUT_WIDTH = 640
INPUT_HEIGHT = 640
SCORE_THRESHOLD = 0.2
NMS_THRESHOLD = 0.4
CONFIDENCE_THRESHOLD = 0.4

# Model and classes are loaded once on startup
is_cuda = len(sys.argv) > 1 and sys.argv[1] == "cpu"  # Default to CUDA unless CPU is specified
net = None
class_list = []

def build_model(is_cuda):
    net = cv2.dnn.readNet("config_files/yolov5s.onnx")
    if is_cuda:
        logger.info("Running on CPU")
        net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
    else:
        logger.info("Attempting to use CUDA")
        net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
        net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA_FP16)
    return net

def load_classes():
    classes = []
    with open("config_files/classes.txt", "r") as f:
        classes = [cname.strip() for cname in f.readlines()]
    return classes

def detect(image, net):
    blob = cv2.dnn.blobFromImage(image, 1/255.0, (INPUT_WIDTH, INPUT_HEIGHT), swapRB=True, crop=False)
    net.setInput(blob)
    preds = net.forward()
    return preds

def format_yolov5(frame):
    row, col, _ = frame.shape
    _max = max(col, row)
    result = np.zeros((_max, _max, 3), np.uint8)
    result[0:row, 0:col] = frame
    return result

def wrap_detection(input_image, output_data):
    class_ids = []
    confidences = []
    boxes = []

    rows = output_data.shape[0]

    image_width, image_height, _ = input_image.shape

    x_factor = image_width / INPUT_WIDTH
    y_factor = image_height / INPUT_HEIGHT

    for r in range(rows):
        row = output_data[r]
        confidence = row[4]
        if confidence >= CONFIDENCE_THRESHOLD:
            classes_scores = row[5:]
            _, _, _, max_indx = cv2.minMaxLoc(classes_scores)
            class_id = max_indx[1]
            if (classes_scores[class_id] > SCORE_THRESHOLD):
                confidences.append(float(confidence))
                class_ids.append(class_id)

                x, y, w, h = row[0].item(), row[1].item(), row[2].item(), row[3].item() 
                left = int((x - 0.5 * w) * x_factor)
                top = int((y - 0.5 * h) * y_factor)
                width = int(w * x_factor)
                height = int(h * y_factor)
                box = [left, top, width, height]
                boxes.append(box)

    confidences = np.array(confidences).astype(np.float32)

    if len(boxes) > 0:
        indexes = cv2.dnn.NMSBoxes(boxes, confidences, CONFIDENCE_THRESHOLD, NMS_THRESHOLD)
    else:
        indexes = []

    result_class_ids = []
    result_confidences = []
    result_boxes = []

    for i in indexes:
        idx = i if isinstance(i, int) else i[0]
        result_confidences.append(confidences[idx])
        result_class_ids.append(class_ids[idx])
        result_boxes.append(boxes[idx])

    return result_class_ids, result_confidences, result_boxes

# Initialize model on startup
@app.before_first_request
def startup_event():
    global net, class_list
    logger.info("Loading YOLO model...")
    start_time = time.time()
    net = build_model(is_cuda)
    class_list = load_classes()
    logger.info(f"Model loaded in {time.time() - start_time:.2f} seconds")

@app.route('/test', methods=['GET'])
def test_endpoint():
    return jsonify({"message": "YOLO API is working!"})

@app.route('/favicon.ico', methods=['GET'])
def favicon():
    return "", 204

@app.route('/detect/', methods=['POST'])
def detect_objects():
    try:
        global request_counter, net, class_list
        request_counter += 1
        
        # Check if file exists in request
        if 'file' not in request.files:
            return jsonify({"error": "No file in request"}), 400
        
        file = request.files['file']
        
        # Read and validate the uploaded image
        file_bytes = file.read()
        nparr = np.frombuffer(file_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return jsonify({"error": "Invalid image file"}), 400
        
        logger.info(f"[{request_counter}] Processing image of shape {img.shape}")
        
        # Process with YOLO
        start_time = time.time()
        
        # Format image for YOLO
        input_image = format_yolov5(img)
        
        # Run detection
        outputs = detect(input_image, net)
        
        # Process results
        class_ids, confidences, boxes = wrap_detection(input_image, outputs[0])
        
        # Prepare response
        detections = []
        for class_id, confidence, box in zip(class_ids, confidences, boxes):
            detections.append({
                "label": class_list[class_id],
                "confidence": float(confidence),
                "bbox": box  # [x, y, width, height]
            })
        
        process_time = time.time() - start_time
        logger.info(f"Detection completed in {process_time:.3f} seconds, found {len(detections)} objects")
        
        return jsonify({
            "detections": detections,
            "processing_time": process_time
        })
        
    except Exception as e:
        logger.error(f"Error processing image: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Load the model right away instead of waiting for first request
    logger.info("Loading YOLO model...")
    start_time = time.time()
    net = build_model(is_cuda)
    class_list = load_classes()
    logger.info(f"Model loaded in {time.time() - start_time:.2f} seconds")
    
    # Run the Flask server
    app.run(host="0.0.0.0", port=8765, threaded=True)