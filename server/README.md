Server should be runned with python3.6 to access to Jetson GPU.
```
cd ~/projects
git clone https://github.com/format37/yolov5-opencv-cpp-python.git
cd rover/object_chaser/server
cp -r ../../../yolov5-opencv-cpp-python/config_files ./
python3.6 -m pip install -r requirements.txt
python3.6 yolo_server.py
```