#!/usr/bin/env python3
#Adafruit PWM
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
#TB6560-V2
import RPi.GPIO as gpio
#realsence
import pyrealsense2 as rs

def my_range(start, end, step):
	res	= []
	while start < end:
		res.append(start)
		start += step
	return res

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
#config.enable_stream(rs.stream.depth,width=640,height=480)
config.enable_stream(rs.stream.depth,width=1280,height=720)
pipeline.start(config)

while True:
	frames = pipeline.wait_for_frames()
	depth = frames.get_depth_frame()
	if not depth: continue

	coverage = [0]*64
	left = 0
	right= 0
	earth= 0
	#for y in range(0,480):
	#for y in my_range(0,480,10):
	for y in my_range(0,720,20):
		#for x in range(0,320):
		#for x in my_range(0,320,10):
		for x in my_range(0,640,20):
			#print(x)
			dp = depth.get_distance(x, y)
			left += dp
			#if y>350: earth += dp
			if y>520: earth += dp
		#for x in range(320,640):
		#for x in my_range(320,640,10):
		for x in my_range(640,1280,20):
			dp = depth.get_distance(x, y)
			right += dp
			if y>520: earth += dp
	lr = left+right
	if lr/100<10 or earth/100>4:
		set(track = 0, speed = 1, direction = 0)
		set(track = 1, speed = 1, direction = 0)
	else:
		set(track = 0, speed = round(right/lr,1), direction = 0)
		set(track = 1, speed = round(left/lr,1), direction = 1)
	print(lr/100,earth/100)

pipeline.stop()
