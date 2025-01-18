import cv2
import matplotlib.pyplot as plt
from ultralytics import YOLO
from tqdm import tqdm
import torch
import time
# import os
import sys

class ObjectDetector:
    def __init__(self, model_path="yolov3.pt", num_runs=10, show_prints=False, show_viz=False):
        self.num_runs = num_runs
        self.show_detailed_prints = show_prints
        self.show_visualization = show_viz
        self._init_cuda()
        self._load_model(model_path)
    
    def _init_cuda(self):
        """Initialize CUDA if available"""
        self.cuda_available = torch.cuda.is_available()
        print(f"CUDA available: {self.cuda_available}")
        if self.cuda_available:
            print(f"Using GPU: {torch.cuda.get_device_name(0)}")
    
    def _load_model(self, model_path):
        """Load YOLO model with progress bar"""
        with tqdm(total=1, desc="Loading YOLO model (YOLOv3)"):
            self.model = YOLO(model_path)  # Validate that 'yolov3.pt' is at the correct path
            self.model.to('cuda' if self.cuda_available else 'cpu')
    
    def process_image(self, image_path):
        """Process image and perform object detection"""
        self.img = cv2.imread(image_path)
        total_time = 0
        
        with tqdm(total=self.num_runs, desc="Processing image"):
            for _ in range(self.num_runs):
                start_time = time.time()
                results = self.model(self.img)
                run_time = time.time() - start_time
                total_time += run_time
                
                self._process_results(results)
    
        self._print_metrics(total_time)
        
        if self.show_visualization:
            self._visualize_results(results)
    
    def _process_results(self, results):
        """Process detection results"""
        for result in results:
            for box in result.boxes:
                if int(box.cls[0]) == 0:  # person detection
                    if self.show_detailed_prints:
                        self._print_detection_details(box)
    
    def _print_detection_details(self, box):
        """Print detailed detection information"""
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        confidence = box.conf[0]
        print(f"Person detected (confidence: {confidence:.2f})")
        print(f"Bounding box coordinates:")
        print(f"  Top-left: ({x1}, {y1})")
        print(f"  Bottom-right: ({x2}, {y2})")
        print(f"  Width: {x2 - x1}")
        print(f"  Height: {y2 - y1}")
        print("-" * 40)
    
    def _print_metrics(self, total_time):
        """Print performance metrics"""
        avg_time = total_time / self.num_runs
        fps = 1 / avg_time
        print("\nPerformance Metrics:")
        print(f"Total time: {total_time:.2f} seconds")
        print(f"Average time per frame: {avg_time:.3f} seconds")
        print(f"FPS: {fps:.2f}")
    
    def _visualize_results(self, results):
        """Visualize detection results"""
        for result in results:
            for box in result.boxes:
                if int(box.cls[0]) == 0:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    confidence = box.conf[0]
                    
                    cv2.rectangle(self.img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(self.img, f"Person: {confidence:.2f}", 
                              (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 
                              0.5, (0, 255, 0), 2)
        
        plt.figure(figsize=(12, 8))
        plt.imshow(cv2.cvtColor(self.img, cv2.COLOR_BGR2RGB))
        plt.axis('off')
        plt.show()

def main():
    # Configuration parameters
    MODEL_PATH = "yolov3.pt"
    IMAGE_PATH = "photo.jpg"
    
    # Get number of runs from command line argument, default to 10 if not provided
    NUM_RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    
    SHOW_DETAILED_PRINTS = False
    SHOW_VISUALIZATION = False
    
    # Initialize and run detector
    detector = ObjectDetector(
        model_path=MODEL_PATH,
        num_runs=NUM_RUNS,
        show_prints=SHOW_DETAILED_PRINTS,
        show_viz=SHOW_VISUALIZATION
    )
    detector.process_image(IMAGE_PATH)

if __name__ == "__main__":
    main()
