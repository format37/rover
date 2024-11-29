import logging
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
import time
from adafruit_servokit import ServoKit

class RobotController:
    def __init__(self, default_speed=0.1, head_movement_delay=0.02):
        self.default_speed = default_speed
        self.head_movement_delay = head_movement_delay
        self.init_logging()
        self.init_tracks()
        # Uncomment to enable servo control
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

    def set_track(self, track, speed, direction):
        if speed > 0:
            frequency = speed * 2300
            direction_value = direction * 0xffff
            self.pca[track].frequency = int(frequency)
            self.pca[track].channels[1].duty_cycle = int(direction_value)
            self.pca[track].channels[0].duty_cycle = 0x7fff  # Go
        else:
            self.pca[track].channels[0].duty_cycle = 0  # Stop

    def move_head(self, start_angle, end_angle):
        """Move the robot's head from start_angle to end_angle"""
        self.logger.info(f'Moving head from {start_angle} to {end_angle} degrees')
        step = 1 if end_angle > start_angle else -1
        for angle in range(start_angle, end_angle, step):
            # Uncomment to enable servo control
            # self.servo_kit.servo[0].angle = angle
            time.sleep(self.head_movement_delay)

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
        self.move_tracks(1, 1)  # Forward
        self.move_head(90, 180)

        # Turn right
        self.move_tracks(0, 0)  # Backward
        self.move_head(180, 0)

        # Move forward
        self.move_tracks(0, 1)  # Turn
        self.move_head(0, 90)

        # Move backward briefly
        self.logger.info('Moving backward briefly')
        self.move_tracks(0, 0)  # Backward
        time.sleep(1)  # Backward movement duration

        # Stop
        self.stop_tracks()
        self.logger.info('Movement sequence completed')

def main():
    robot = RobotController()
    robot.execute_movement_sequence()

if __name__ == '__main__':
    main()