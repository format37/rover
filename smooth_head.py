import logging
import time
import math
from adafruit_servokit import ServoKit

def smooth_move(servo, start_angle, end_angle, duration, steps=200):
    for i in range(steps + 1):
        t = i / steps
        # Ease in-out using sine function
        angle = start_angle + (end_angle - start_angle) * (math.sin(t * math.pi - math.pi/2) + 1) / 2
        servo.angle = angle
        time.sleep(duration / steps)

def main():
    # enable logging
    logging.basicConfig(level=logging.INFO)

    # servo init
    logging.info('Init servo')
    kit = ServoKit(channels=16, address=0x42)

    # head servo
    head_servo = kit.servo[0]

    # Move head right
    logging.info('head right')
    smooth_move(head_servo, 90, 0, duration=2)

    # Move head front
    logging.info('head front')
    smooth_move(head_servo, 0, 90, duration=2)

    # Move head left
    logging.info('head left')
    smooth_move(head_servo, 90, 180, duration=2)

    # Move head front
    logging.info('head front')
    smooth_move(head_servo, 0, 90, duration=2)

if __name__ == '__main__':
    main()
