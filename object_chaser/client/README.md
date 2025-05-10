Client should be runned with python3.8 to access to Realsense depth camera.
```
python3.8 -m pip install -r requirements.txt
python3.8 yolo_client.py
```
To run servo server:
```
uvicorn servo_server:app --host 0.0.0.0 --port 5000
```