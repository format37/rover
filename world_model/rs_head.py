import pyrealsense2 as rs
import numpy as np
import time
from adafruit_servokit import ServoKit
import asyncio

cam_ready = False
servo_activity = False
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


async def camera_capture():
	
	global cam_ready

	pipeline = rs.pipeline()
	config = rs.config()
	#config.enable_stream(rs.stream.depth,width=1280,height=720) # FPS = 30
	#config.enable_stream(rs.stream.depth,width=640,height=480) # FPS = 60
	config.enable_stream(rs.stream.depth,width=424,height=240, rs.format.z16, 30) # FPS = 90
	rs.align(rs.stream.color) # new
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
		aligned_frames = self.align.process(frames) # new
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
	loop.run_until_complete(asyncio.gather(move_head(), camera_capture()))
	loop.close()
    

if __name__ == '__main__':
	main()