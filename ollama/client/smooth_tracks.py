import logging
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
import time
import math

def set(pca, track, speed, direction):
    """Original set function for complete stop"""
    if speed > 0:
        frequency = speed * 2300
        direction = direction * 0xffff
        pca[track].frequency = int(frequency)
        pca[track].channels[1].duty_cycle = int(direction)
        pca[track].channels[0].duty_cycle = 0x7fff  # go
    else:
        pca[track].channels[0].duty_cycle = 0  # stop

def smooth_set(pca, track, target_speed, direction, duration=1.0, steps=50):
    """
    Smoothly adjust track speed using sine-based easing
    """
    MIN_FREQ = 60  # Minimum frequency to prevent division by zero
    direction_value = direction * 0xffff
    
    # Set initial state
    pca[track].frequency = MIN_FREQ
    pca[track].channels[1].duty_cycle = int(direction_value)
    
    for i in range(steps + 1):
        t = i / steps
        # Ease in-out using sine function
        current_speed = target_speed * (math.sin(t * math.pi - math.pi/2) + 1) / 2
        
        if current_speed > 0:
            # Scale frequency between MIN_FREQ and target frequency
            frequency = MIN_FREQ + (current_speed * 2300)
            pca[track].channels[0].duty_cycle = 0x7fff  # go
        else:
            frequency = MIN_FREQ
            pca[track].channels[0].duty_cycle = 0  # stop
            
        pca[track].frequency = int(frequency)
        time.sleep(duration / steps)

def smooth_stop(pca, track, current_speed, direction, duration=1.0, steps=50):
    """
    Smoothly stop the track
    """
    MIN_FREQ = 60  # Minimum frequency
    direction_value = direction * 0xffff
    
    for i in range(steps + 1):
        t = i / steps
        # Ease out using sine function
        speed = current_speed * (math.cos(t * math.pi/2))  # Gradually decrease to 0
        
        if speed > 0:
            frequency = MIN_FREQ + (speed * 2300)
            pca[track].frequency = int(frequency)
            pca[track].channels[1].duty_cycle = int(direction_value)
            pca[track].channels[0].duty_cycle = 0x7fff
        
        time.sleep(duration / steps)
    
    # Use the original set function for the final stop
    set(pca, track=track, speed=0, direction=direction)

def main():
    # enable logging
    logging.basicConfig(level=logging.INFO)

    default_speed = 0.05
    
    # tracks init
    logging.info('Init tracks')
    i2c_bus = busio.I2C(SCL, SDA)
    pca = [
        PCA9685(i2c_bus, address=0x40),
        PCA9685(i2c_bus, address=0x41)
    ]

    for i in range(0, 2):
        pca[i].frequency = 60  # Set initial minimum frequency
        pca[i].channels[0].duty_cycle = 0
        pca[i].channels[1].duty_cycle = 0xffff

    delay = 2

    # tracks go left with smooth start
    logging.info('tracks go left')
    smooth_set(pca, track=0, target_speed=default_speed, direction=1)
    smooth_set(pca, track=1, target_speed=default_speed, direction=1)
    time.sleep(delay)
    
    # smooth stop before direction change
    smooth_stop(pca, track=0, current_speed=default_speed, direction=1)
    smooth_stop(pca, track=1, current_speed=default_speed, direction=1)

    # tracks go right
    logging.info('tracks go right')
    smooth_set(pca, track=0, target_speed=default_speed, direction=0)
    smooth_set(pca, track=1, target_speed=default_speed, direction=0)
    time.sleep(delay)
    
    # smooth stop before direction change
    smooth_stop(pca, track=0, current_speed=default_speed, direction=0)
    smooth_stop(pca, track=1, current_speed=default_speed, direction=0)

    # tracks go front
    logging.info('tracks go front')
    smooth_set(pca, track=0, target_speed=default_speed, direction=0)
    smooth_set(pca, track=1, target_speed=default_speed, direction=1)
    time.sleep(delay)
    
    # smooth stop before direction change
    smooth_stop(pca, track=0, current_speed=default_speed, direction=0)
    smooth_stop(pca, track=1, current_speed=default_speed, direction=1)

    # tracks go back
    logging.info('tracks go back')
    smooth_set(pca, track=0, target_speed=default_speed, direction=1)
    smooth_set(pca, track=1, target_speed=default_speed, direction=0)
    time.sleep(delay)
    
    # final smooth stop
    logging.info('tracks stop')
    smooth_stop(pca, track=0, current_speed=default_speed, direction=1)
    smooth_stop(pca, track=1, current_speed=default_speed, direction=0)
    logging.info('done')

if __name__ == '__main__':
    main()