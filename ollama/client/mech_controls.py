import logging
import time
import math
import asyncio
from typing import Optional, Tuple
from dataclasses import dataclass
from adafruit_servokit import ServoKit
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685

@dataclass
class TrackConfig:
    """Configuration for track controls"""
    min_frequency: int = 60
    max_frequency: int = 2300
    forward_duty: int = 0xffff
    stop_duty: int = 0
    go_duty: int = 0x7fff

class RobotController:
    """Unified controller for robot's head servo and tracks"""
    
    def __init__(self, 
                 servo_channels: int = 16,
                 servo_address: int = 0x42,
                 track_addresses: Tuple[int, int] = (0x40, 0x41),
                 head_servo_channel: int = 0):
        """
        Initialize robot controller
        
        Args:
            servo_channels: Number of servo channels
            servo_address: I2C address for servo controller
            track_addresses: Tuple of I2C addresses for left and right track controllers
            head_servo_channel: Channel number for head servo
        """
        self.logger = logging.getLogger(__name__)
        self.track_config = TrackConfig()
        
        # Initialize servo
        self.logger.info('Initializing servo controller')
        self.servo_kit = ServoKit(channels=servo_channels, address=servo_address)
        self.head_servo = self.servo_kit.servo[head_servo_channel]
        
        # Initialize tracks
        self.logger.info('Initializing track controllers')
        i2c_bus = busio.I2C(SCL, SDA)
        self.track_controllers = [
            PCA9685(i2c_bus, address=addr) for addr in track_addresses
        ]
        
        # Initialize track controllers with base frequency
        for controller in self.track_controllers:
            controller.frequency = self.track_config.min_frequency
            controller.channels[0].duty_cycle = 0
            controller.channels[1].duty_cycle = self.track_config.forward_duty

    async def smooth_head_move(self, 
                             start_angle: float, 
                             end_angle: float, 
                             duration: float = 2.0,
                             steps: int = 200) -> None:
        """
        Smoothly move head servo from start to end angle
        
        Args:
            start_angle: Starting angle in degrees
            end_angle: Ending angle in degrees
            duration: Time to complete movement in seconds
            steps: Number of intermediate steps
        """
        if start_angle == end_angle:
            return
        self.logger.info(f'Moving head from {start_angle}° to {end_angle}°')
        step_delay = duration / steps
        
        for i in range(steps + 1):
            t = i / steps
            # Ease in-out using sine function
            angle = start_angle + (end_angle - start_angle) * (
                math.sin(t * math.pi - math.pi/2) + 1) / 2
            self.head_servo.angle = angle
            await asyncio.sleep(step_delay)

    async def smooth_track_set(self,
                             track: int,
                             target_speed: float,
                             direction: int,
                             duration: float = 1.0,
                             steps: int = 50) -> None:
        """
        Smoothly set track speed
        
        Args:
            track: Track index (0 or 1)
            target_speed: Target speed (0.0 to 1.0)
            direction: Direction (0 or 1)
            duration: Time to reach target speed in seconds
            steps: Number of intermediate steps
        """
        direction_value = direction * self.track_config.forward_duty
        controller = self.track_controllers[track]
        step_delay = duration / steps
        
        # Set initial state
        controller.frequency = self.track_config.min_frequency
        controller.channels[1].duty_cycle = direction_value
        
        for i in range(steps + 1):
            t = i / steps
            current_speed = target_speed * (math.sin(t * math.pi - math.pi/2) + 1) / 2
            
            if current_speed > 0:
                frequency = self.track_config.min_frequency + (
                    current_speed * self.track_config.max_frequency)
                controller.channels[0].duty_cycle = self.track_config.go_duty
            else:
                frequency = self.track_config.min_frequency
                controller.channels[0].duty_cycle = self.track_config.stop_duty
                
            controller.frequency = int(frequency)
            await asyncio.sleep(step_delay)

    async def smooth_track_stop(self,
                              track: int,
                              current_speed: float,
                              direction: int,
                              duration: float = 1.0,
                              steps: int = 50) -> None:
        """
        Smoothly stop track
        
        Args:
            track: Track index (0 or 1)
            current_speed: Current speed (0.0 to 1.0)
            direction: Current direction (0 or 1)
            duration: Time to complete stop in seconds
            steps: Number of intermediate steps
        """
        direction_value = direction * self.track_config.forward_duty
        controller = self.track_controllers[track]
        step_delay = duration / steps
        
        for i in range(steps + 1):
            t = i / steps
            speed = current_speed * math.cos(t * math.pi/2)
            
            if speed > 0:
                frequency = self.track_config.min_frequency + (
                    speed * self.track_config.max_frequency)
                controller.frequency = int(frequency)
                controller.channels[1].duty_cycle = direction_value
                controller.channels[0].duty_cycle = self.track_config.go_duty
            
            await asyncio.sleep(step_delay)
        
        # Final stop
        controller.channels[0].duty_cycle = self.track_config.stop_duty

    # High-level movement methods
    async def look_left(self, duration: float = 2.0):
        """Move head to look left"""
        await self.smooth_head_move(90, 180, duration)

    async def look_right(self, duration: float = 2.0):
        """Move head to look right"""
        await self.smooth_head_move(90, 0, duration)

    async def look_center(self, current_angle: float, duration: float = 2.0):
        """Center head from current angle"""
        await self.smooth_head_move(current_angle, 90, duration)

    async def move_forward(self, speed: float = 0.05, duration: float = 2.0):
        """Move robot forward"""
        self.logger.info('Moving forward')
        await asyncio.gather(
            self.smooth_track_set(0, speed, 0),
            self.smooth_track_set(1, speed, 1)
        )
        await asyncio.sleep(duration)
        await self.stop()

    async def move_backward(self, speed: float = 0.05, duration: float = 2.0):
        """Move robot backward"""
        self.logger.info('Moving backward')
        await asyncio.gather(
            self.smooth_track_set(0, speed, 1),
            self.smooth_track_set(1, speed, 0)
        )
        await asyncio.sleep(duration)
        await self.stop()

    async def turn_left(self, speed: float = 0.05, duration: float = 2.0):
        """Turn robot left"""
        self.logger.info('Turning left')
        await asyncio.gather(
            self.smooth_track_set(0, speed, 1),
            self.smooth_track_set(1, speed, 1)
        )
        await asyncio.sleep(duration)
        await self.stop()

    async def turn_right(self, speed: float = 0.05, duration: float = 2.0):
        """Turn robot right"""
        self.logger.info('Turning right')
        await asyncio.gather(
            self.smooth_track_set(0, speed, 0),
            self.smooth_track_set(1, speed, 0)
        )
        await asyncio.sleep(duration)
        await self.stop()

    async def stop(self):
        """Stop all tracks"""
        self.logger.info('Stopping')
        await asyncio.gather(
            self.smooth_track_stop(0, 0.05, 1),
            self.smooth_track_stop(1, 0.05, 0)
        )

# Example usage
async def main():
    logging.basicConfig(level=logging.INFO)
    robot = RobotController()
    
    # Example movement sequence
    await robot.look_right()
    await robot.look_center(0)
    await robot.look_left()
    await robot.look_center(180)
    
    await robot.move_forward()
    await robot.turn_left()
    await robot.turn_right()
    await robot.move_backward()

if __name__ == '__main__':
    asyncio.run(main())
    