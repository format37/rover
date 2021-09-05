#!/usr/bin/env python3
import time
#Adafruit PWM
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
#TB6560-V2
import RPi.GPIO as gpio

def set(track,speed,direction):
	if speed>0:
		frequency = speed*2300
		direction = direction*0xffff
		pca[track].frequency = int(frequency)
		pca[track].channels[1].duty_cycle = int(direction)
		pca[track].channels[0].duty_cycle = 0x7fff  #go
	else:
		pca[track].channels[0].duty_cycle = 0       #stop

i2c_bus = busio.I2C(SCL, SDA)
pca = [
	PCA9685(i2c_bus,address=0x40),
	PCA9685(i2c_bus,address=0x41)
	]

for i in range(0,2):
	pca[i].frequency = 60
	pca[i].channels[0].duty_cycle = 0
	pca[i].channels[1].duty_cycle = 0xffff
print('stop')
set(track = 0, speed = 0, direction = 0)
set(track = 1, speed = 0, direction = 0)
print('ok')
