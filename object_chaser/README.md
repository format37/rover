# Installation
```
sudo apt-get install python3-setuptools python3-pip libjpeg-dev zlib1g-dev
```
# YOLO server
```
cd ~/projects/rover/object_chaser/server/
python3.6 yolo_server.py
```
# Servo server
```
cd ~/projects/rover/object_chaser/client/
uvicorn servo_server:app --host 0.0.0.0 --port 5000
```
# 