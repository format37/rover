import asyncio
import time
import numpy as np

# camera
import pyrealsense2 as rs

# Head servo
from adafruit_servokit import ServoKit

# Tracks Adafruit PWM
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
# Tracks TB6560-V2
import RPi.GPIO as gpio


cam_ready = False
servo_activity = False
tracks_ready = False
servo_angle = 100

async def move_head():

	global servo_activity
	global servo_angle	

	delay = 0.1
	kit = ServoKit(channels=16, address=0x42)
	print('servo ready')	
	servo_activity = True
	while cam_ready == False:		
		await asyncio.sleep(delay)
	print('servo start')
	for servo_angle in range(100,180):
		kit.servo[0].angle = servo_angle
		await asyncio.sleep(delay)

	for i in range(0,180):
		servo_angle = 180 - i
		kit.servo[0].angle = servo_angle
		await asyncio.sleep(delay)

	for servo_angle in range(0,100):
		kit.servo[0].angle = servo_angle
		await asyncio.sleep(delay)

	servo_activity = False
	print('servo stop')


async def move_tracks():

	global tracks_ready

	def set(track,speed,direction):
		if speed>0:
			frequency = speed*2300
			direction = direction*0xffff
			pca[track].frequency = int(frequency)
			pca[track].channels[1].duty_cycle = int(direction)
			pca[track].channels[0].duty_cycle = 0x7fff  #go
		else:
			pca[track].channels[0].duty_cycle = 0       #stop

	print('Tracks init')
	i2c_bus = busio.I2C(SCL, SDA)
	pca = [
		PCA9685(i2c_bus,address=0x40),
		PCA9685(i2c_bus,address=0x41)
		]
	for i in range(0,2):
		pca[i].frequency = 60
		pca[i].channels[0].duty_cycle = 0
		pca[i].channels[1].duty_cycle = 0xffff
	tracks_ready = True

	print('Tracks start')
	set(track = 0, speed = 1, direction = 0)
	set(track = 1, speed = 1, direction = 0)
	await asyncio.sleep(1)
	set(track = 0, speed = 0, direction = 0)
	set(track = 1, speed = 0, direction = 0)
	print('Tracks stop')

async def camera_capture():
	
	global cam_ready

	pipeline = rs.pipeline()
	config = rs.config()
	#config.enable_stream(rs.stream.depth,width=1280,height=720) # FPS = 30
	#config.enable_stream(rs.stream.depth,width=640,height=480) # FPS = 60
	config.enable_stream(rs.stream.depth, 424, 240, rs.format.z16, 30) # FPS = 90
	align = rs.align(rs.stream.color) # new
	pipeline.start(config)
	depth_images = None
	
	servo_states = []
	start_time = time.time()
	i = 0
	delay = 0.1
	cam_ready = True	
	print('camera ready')	
	while servo_activity == False:
		await asyncio.sleep(delay)
	print('camera start')
	
	while True:
		
		if servo_activity == False:
			break
		
		# save angle
		servo_states.append(servo_angle)
		
		# save image
		frames = pipeline.wait_for_frames()
		aligned_frames = align.process(frames) # new
		#depth = frames.get_depth_frame()
		depth = aligned_frames.get_depth_frame()
		if not depth:
			continue
		time_diff = time.time() - start_time
		new_depth_image = np.array([np.asanyarray(depth.get_data( ))])		
		if depth_images is None:
			depth_images = new_depth_image
		else:
			depth_images = np.append(depth_images, new_depth_image, axis=0)
		
		await asyncio.sleep(delay)

	pipeline.stop()

	print('camera saving', np.array(depth_images).shape, 'images')
	np.save('servo.npy', np.array(servo_states))
	np.save('depth.npy', depth_images)
	print('camera saved')


def main():

	loop = asyncio.get_event_loop()
	loop.run_until_complete(
		asyncio.gather(
			#move_head(),
			#camera_capture(),
			move_tracks()
			)
		)
	loop.close()
    

if __name__ == '__main__':
	main()