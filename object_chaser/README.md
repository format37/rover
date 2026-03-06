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
## Client (head tracking only)
```
cd ~/projects/rover/object_chaser/client/
python3.8 client.py --label person
```

## Client (body follow - head tracking + body rotation)
```
cd ~/projects/rover/object_chaser/client/
python3.8 body_follow.py --label person
```