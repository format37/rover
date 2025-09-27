# Installation
```
sudo apt-get install python3-setuptools python3-pip libjpeg-dev zlib1g-dev
```
# Running
To run the Object chaser u need to run 3 processes simultaneously:
* Yolo server
* Servo server
* Client
## YOLO server
```
cd ~/projects/rover/object_chaser/server/
python3.6 yolo_server.py
```
## Servo server
```
cd ~/projects/rover/object_chaser/server/
python3.8 servo_api.py
```
## Client
```
cd ~/projects/rover/object_chaser/client/
python3.8 client.py
```