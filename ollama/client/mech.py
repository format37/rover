import logging
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
# TB6560-V2
# import RPi.GPIO as gpio
import time
from adafruit_servokit import ServoKit


def set(pca, track,speed,direction):
	if speed>0:
		frequency = speed*2300
		direction = direction*0xffff
		pca[track].frequency = int(frequency)
		pca[track].channels[1].duty_cycle = int(direction)
		pca[track].channels[0].duty_cycle = 0x7fff  #go
	else:
		pca[track].channels[0].duty_cycle = 0       #stop

def main():

	# enable logging
	logging.basicConfig(level=logging.INFO)

	default_speed = 0.1

	# tracks init
	logging.info('Init tracks')
	i2c_bus = busio.I2C(SCL, SDA)
	pca = [
		PCA9685(i2c_bus,address=0x40),
		PCA9685(i2c_bus,address=0x41)
		]

	for i in range(0,2):
		pca[i].frequency = 60
		pca[i].channels[0].duty_cycle = 0
		pca[i].channels[1].duty_cycle = 0xffff

	# # servo init
	# logging.info('Init servo')
	# kit = ServoKit(channels=16, address=0x42)
	delay = 1.8

	# tracks go cw
	logging.info('tracks go left')
	set(pca, track = 0, speed = default_speed, direction = 1)
	set(pca, track = 1, speed = default_speed, direction = 1)
	time.sleep(delay)

	logging.info('tracks go right')
	set(pca, track = 0, speed = default_speed, direction = 0)
	set(pca, track = 1, speed = default_speed, direction = 0)
	time.sleep(delay)

	logging.info('tracks go front')
	set(pca, track = 0, speed = default_speed, direction = 0)
	set(pca, track = 1, speed = default_speed, direction = 1)
	time.sleep(delay)
	
	logging.info('tracks go back')
	set(pca, track = 0, speed = default_speed, direction = 1)
	set(pca, track = 1, speed = default_speed, direction = 0)
	time.sleep(delay)

	# tracks stop
	logging.info('tracks stop')
	set(pca, track = 0, speed = 0, direction = 1)
	set(pca, track = 1, speed = 0, direction = 1)
	logging.info('done')


if __name__ == '__main__':
	main()