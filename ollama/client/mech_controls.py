import logging
import time
import math
import asyncio
import weakref
import atexit
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
    
    # Class-level set to track active instances
    _instances = weakref.WeakSet()
    
    @classmethod
    def _cleanup_all(cls):
        """Class method to cleanup all active robot instances"""
        for instance in cls._instances:
            try:
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                if loop.is_running():
                    loop.create_task(instance._cleanup())
                else:
                    loop.run_until_complete(instance._cleanup())
            except Exception as e:
                instance.logger.error(f"Error during cleanup: {e}")
    
    def __init__(self, 
                 servo_channels: int = 16,
                 servo_address: int = 0x42,
                 track_addresses: Tuple[int, int] = (0x40, 0x41),
                 head_servo_channel: int = 0):
        """Initialize robot controller"""
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
            
        # Store current head angle
        self.current_head_angle = 90
        self._is_running = True
        
        # Register instance for cleanup
        self._instances.add(self)
        atexit.register(self.__class__._cleanup_all)

    async def _cleanup(self):
        """Internal cleanup method"""
        if self._is_running:
            try:
                self.logger.info("Performing robot cleanup...")
                # Stop all tracks
                await self.stop()
                # Return head to center position
                await self.smooth_head_move(self.current_head_angle, 90)
                self._is_running = False
                self.logger.info("Robot cleanup completed")
            except Exception as e:
                self.logger.error(f"Error during cleanup: {e}")

    def __del__(self):
        """Destructor to ensure cleanup when object is garbage collected"""
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            if loop.is_running():
                loop.create_task(self._cleanup())
            else:
                loop.run_until_complete(self._cleanup())
        except Exception as e:
            self.logger.error(f"Error during destructor cleanup: {e}")

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self._cleanup()

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

    async def move_tracks(self, left_speed: float, right_speed: float, duration: float = 2.0):
        # Move robot tracks
        # left_speed: Speed of left track (-1.0 to 1.0)
        # right_speed: Speed of right track (-1.0 to 1.0)
        left_direction = 0 if left_speed >= 0 else 1
        right_direction = 0 if right_speed < 0 else 1
        left_speed = abs(left_speed * 0.1)
        right_speed = abs(right_speed * 0.1)
        await asyncio.gather(
            self.smooth_track_set(0, left_speed, left_direction),
            self.smooth_track_set(1, right_speed, right_direction)
        )

        await asyncio.sleep(duration)
        await asyncio.gather(
            self.smooth_track_stop(0, left_speed, left_direction),
            self.smooth_track_stop(1, right_speed, right_direction)
        )

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

    async def stop(self, speed: float = 0.05):
        """Stop all tracks"""
        self.logger.info('Stopping')
        await asyncio.gather(
            self.smooth_track_stop(0, speed, 1),
            self.smooth_track_stop(1, speed, 0)
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

    await robot.move_tracks(1, 1, 2)
    await robot.move_tracks(-1, -1, 2)
    await robot.move_tracks(1, -1, 2)
    await robot.move_tracks(-1, 1, 2)

if __name__ == '__main__':
    asyncio.run(main())
    