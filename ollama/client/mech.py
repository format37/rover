import logging
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
import time
import math
from adafruit_servokit import ServoKit

class RobotController:
    def __init__(self, default_speed=0.1):
        self.default_speed = default_speed
        self.init_logging()
        self.init_tracks()
        self.init_servo()

    def init_logging(self):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def init_tracks(self):
        self.logger.info('Initializing tracks')
        i2c_bus = busio.I2C(SCL, SDA)
        self.pca = [
            PCA9685(i2c_bus, address=0x40),
            PCA9685(i2c_bus, address=0x41)
        ]
        
        for pca in self.pca:
            pca.frequency = 60
            pca.channels[0].duty_cycle = 0  # Stop
            pca.channels[1].duty_cycle = 0xffff  # Default direction

    def init_servo(self):
        self.logger.info('Initializing servo')
        self.servo_kit = ServoKit(channels=16, address=0x42)
        self.head_servo = self.servo_kit.servo[0]

    def set_track(self, track, speed, direction):
        if speed > 0:
            frequency = speed * 2300
            direction_value = direction * 0xffff
            self.pca[track].frequency = int(frequency)
            self.pca[track].channels[1].duty_cycle = int(direction_value)
            self.pca[track].channels[0].duty_cycle = 0x7fff  # Go
        else:
            self.pca[track].channels[0].duty_cycle = 0  # Stop

    def smooth_move_head(self, start_angle, end_angle, duration=2, steps=200):
        """Move the robot's head smoothly from start_angle to end_angle"""
        self.logger.info(f'Moving head smoothly from {start_angle} to {end_angle} degrees')
        
        for i in range(steps + 1):
            t = i / steps
            # Ease in-out using sine function
            angle = start_angle + (end_angle - start_angle) * (math.sin(t * math.pi - math.pi/2) + 1) / 2
            self.head_servo.angle = angle
            time.sleep(duration / steps)

    def move_tracks(self, left_direction, right_direction, speed=None):
        """Move tracks with specified directions and speed"""
        if speed is None:
            speed = self.default_speed
        
        direction_text = {
            (1, 1): "forward",
            (0, 0): "backward",
            (0, 1): "turn right",
            (1, 0): "turn left"
        }
        movement = direction_text.get((left_direction, right_direction), "custom movement")
        self.logger.info(f'Tracks {movement}')
        
        self.set_track(0, speed, left_direction)
        self.set_track(1, speed, right_direction)

    def stop_tracks(self):
        """Stop all track movement"""
        self.logger.info('Stopping tracks')
        self.set_track(0, 0, 1)
        self.set_track(1, 0, 1)

    def execute_movement_sequence(self):
        # Turn left
        self.logger.info('Starting left turn sequence')
        self.move_tracks(1, 1)  # Forward
        self.smooth_move_head(90, 180)  # Look left

        # Turn right
        self.logger.info('Starting right turn sequence')
        self.move_tracks(0, 0)  # Backward
        self.smooth_move_head(180, 0)  # Look right

        # Move forward
        self.logger.info('Starting forward sequence')
        self.move_tracks(0, 1)  # Turn
        self.smooth_move_head(0, 90)  # Look forward

        # Move backward briefly
        self.logger.info('Moving backward briefly')
        self.move_tracks(0, 0)  # Backward
        time.sleep(1)  # Backward movement duration

        # Return head to center
        self.smooth_move_head(90, 90)

        # Stop
        self.stop_tracks()
        self.logger.info('Movement sequence completed')

def main():
    robot = RobotController()
    robot.execute_movement_sequence()

if __name__ == '__main__':
    main()