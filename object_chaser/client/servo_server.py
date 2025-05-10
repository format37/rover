import logging
import time
import math
from flask import Flask, request
from adafruit_servokit import ServoKit
from threading import Lock

app = Flask(__name__)
kit = None
head_servo = None
current_angle = 90  # Initial angle (center)
servo_lock = Lock()

def smooth_move(servo, start_angle, end_angle, duration, steps=200):
    for i in range(steps + 1):
        t = i / steps
        # Ease in-out using sine function
        angle = start_angle + (end_angle - start_angle) * (math.sin(t * math.pi - math.pi/2) + 1) / 2
        servo.angle = angle
        time.sleep(duration / steps)

@app.route('/move', methods=['GET'])
def move_head():
    global current_angle
    try:
        goal = float(request.args.get('goal'))
        if not 0 <= goal <= 1:
            return {"error": "Goal must be between 0 and 1"}, 400
        
        # Map goal (0 to 1) to angle (180 to 0)
        target_angle = (1 - goal) * 180
        
        with servo_lock:
            logging.info(f'Moving head from {current_angle:.1f} to {target_angle:.1f} degrees')
            smooth_move(head_servo, current_angle, target_angle, duration=2)
            current_angle = target_angle
        
        return {"status": "success", "angle": target_angle}, 200
    except ValueError:
        return {"error": "Invalid goal value"}, 400
    except Exception as e:
        logging.error(f"Error moving servo: {str(e)}")
        return {"error": f"Server error: {str(e)}"}, 500

def main():
    global kit, head_servo
    # Enable logging
    logging.basicConfig(level=logging.INFO)

    # Servo init
    logging.info('Init servo')
    kit = ServoKit(channels=16, address=0x42)
    head_servo = kit.servo[0]
    head_servo.angle = current_angle  # Set initial position

    # Start Flask server
    logging.info('Starting server')
    app.run(host='0.0.0.0', port=5000)

if __name__ == '__main__':
    main()