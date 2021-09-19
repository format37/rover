import pyrealsense2 as rs
import numpy as np
import time
from adafruit_servokit import ServoKit
import asyncio

cam_ready = False
servo_activity = False
servo_angle = 100

"""def rotation_map(start_position, end_position, steps):	
	multiplier = (end_position - start_position) / steps
	rot_map = dict()
	for i in range(0, steps):
		rot_map[i] = start_position + i * multiplier
	return rot_map"""


async def move_head():

	global servo_activity
	global servo_angle	

	delay = 0.1
	kit = ServoKit(channels=16, address=0x42)
	print('servo ready')	
	servo_activity = True
	while cam_ready == False:		
		await asyncio.sleep(delay)
		print('servo: cam_ready', cam_ready)
	print('servo start')
	for servo_angle in range(100,180):
			kit.servo[0].angle = servo_angle
			print('servo_angle', servo_angle)
			await asyncio.sleep(delay)

	for servo_angle in range(0,180):
			kit.servo[0].angle = 180-servo_angle
			print('servo_angle', 180-servo_angle)
			await asyncio.sleep(delay)

	for servo_angle in range(0,100):
			kit.servo[0].angle = servo_angle
			print('servo_angle', servo_angle)
			await asyncio.sleep(delay)

	servo_activity = False
	print('servo stop')


async def camera_capture():
	
	global cam_ready

	pipeline = rs.pipeline()
	config = rs.config()
	#config.enable_stream(rs.stream.depth,width=1280,height=720) # FPS = 30
	#config.enable_stream(rs.stream.depth,width=640,height=480) # FPS = 60
	config.enable_stream(rs.stream.depth,width=424,height=240) # FPS = 90
	pipeline.start(config)
	depth_images = None
	
	servo_states = []
	start_time = time.time()
	i = 0
	delay = 1
	cam_ready = True	
	print('camera ready')	
	while servo_activity == False:
		await asyncio.sleep(delay)
		print('cam: servo_activity', servo_activity)
	print('camera start')
	while True:
		if not servo_activity:
			break
		frames = pipeline.wait_for_frames()
		depth = frames.get_depth_frame()
		if not depth:
			continue
		time_diff = time.time() - start_time
		new_depth_image = np.array([np.asanyarray(depth.get_data( ))])
		if depth_images is None:
			depth_images = new_depth_image
		else:
			depth_images = np.append(depth_images, new_depth_image, axis=0)

	pipeline.stop()

	print('camera saving', np.array(depth_images).shape, 'images')
	np.save('servo.npy', np.array(servo_states))
	np.save('depth.npy', depth_images)
	print('camera saved')


def main():

	loop = asyncio.get_event_loop()
	loop.run_until_complete(asyncio.gather(move_head(), camera_capture()))
	loop.close()
    

if __name__ == '__main__':
	main()
