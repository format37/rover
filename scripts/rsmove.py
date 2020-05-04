#!/usr/bin/env python3
#Adafruit PWM
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
#TB6560-V2
import RPi.GPIO as gpio
#realsence
import pyrealsense2 as rs

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
print('start')

pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.depth,width=640,height=480)
pipeline.start(config)

while True:
	frames = pipeline.wait_for_frames()
	depth = frames.get_depth_frame()
	if not depth: continue

	coverage = [0]*64
	left = 0
	right= 0
	earth= 0
	for y in range(480):
		for x in range(0,320):
			dp = depth.get_distance(x, y)
			left += dp
			if y>350: earth += dp
		for x in range(320,640):
			dp = depth.get_distance(x, y)
			right += dp
			if y>350: earth += dp
	lr = left+right
	if lr/10000<10 or earth/10000>5:
		set(track = 0, speed = 1, direction = 0)
		set(track = 1, speed = 1, direction = 0)
	else:
		set(track = 0, speed = round(right/lr,1), direction = 0)
		set(track = 1, speed = round(left/lr,1), direction = 1)
