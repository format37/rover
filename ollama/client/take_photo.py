import time
import numpy as np
import pyrealsense2 as rs

# cam_ready = False

def camera_capture():
	
	# global cam_ready
	pipeline = rs.pipeline()
	config = rs.config()
	#config.enable_stream(rs.stream.depth,width=1280,height=720) # FPS = 30
	#config.enable_stream(rs.stream.depth,width=640,height=480) # FPS = 60
	config.enable_stream(rs.stream.depth, 424, 240, rs.format.z16, 30) # FPS = 90
	align = rs.align(rs.stream.color) # new
	pipeline.start(config)
	depth_images = None
	
	# servo_states = []
	start_time = time.time()
	# i = 0
	delay = 0.1
	# cam_ready = True	
	# print('camera ready')	
	# while servo_activity == False:
	# 	await asyncio.sleep(delay)
	print('camera start')
	
	while True:
		
		# if servo_activity == False:
		# 	break
		
		# save angle
		# servo_states.append(servo_angle)
		
		# save image
		frames = pipeline.wait_for_frames()
		aligned_frames = align.process(frames) # new
		# depth = frames.get_depth_frame()
		depth = aligned_frames.get_depth_frame()
		if not depth:
			continue
		# time_diff = time.time() - start_time
		new_depth_image = np.array([np.asanyarray(depth.get_data( ))])		
		if depth_images is None:
			depth_images = new_depth_image
		else:
			depth_images = np.append(depth_images, new_depth_image, axis=0)
		
		# await asyncio.sleep(delay)
		time.sleep(delay)
		# break
		if np.array(depth_images).shape[0] > 0:
			break

	pipeline.stop()

	print('camera saving', np.array(depth_images).shape, 'images')
	# np.save('servo.npy', np.array(servo_states))
	# np.save('depth.npy', depth_images)
	print('camera saved')


def main():
	camera_capture()
    

if __name__ == '__main__':
	main()