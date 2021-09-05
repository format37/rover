import pyrealsense2 as rs
import numpy as np
import time
from adafruit_servokit import ServoKit

def rotation_map(start_position, end_position, steps):	
	multiplier = (end_position - start_position) / steps
	rot_map = dict()
	for i in range(0, steps):
		rot_map[i] = start_position + i * multiplier
	return rot_map

def action(servo_states, depth_images, lenght, servo_start, servo_end):
	head_rotation_map = rotation_map(
		start_position=servo_start, 
		end_position=servo_end, 
		steps=int(lenght*100)
		)
	start_time = time.time()
	i = 0	
	while True:
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
		if (time_diff < lenght):
			current_servo_state = head_rotation_map[int(time_diff*100)]
			kit.servo[0].angle = current_servo_state	
		servo_states.append(current_servo_state)
		if (time_diff > lenght):
			break	
		i += 1
	return servo_states, depth_images

# init
kit = ServoKit(channels=16, address=0x42)
pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.depth,width=1280,height=720)
pipeline.start(config)
depth_images = None
servo_states = []

for i in range(10):
	# look left
	servo_states, depth_images = action(servo_states, depth_images, 1, 90, 180)
	# look right
	servo_states, depth_images = action(servo_states, depth_images, 2, 180, 0)
	# look front
	servo_states, depth_images = action(servo_states, depth_images, 1, 0, 90)

print('images collected:', np.array(depth_images).shape)
"""
# look front
for i in range(0,(180-90)):
	kit.servo[0].angle = 180-i
	time.sleep(0.03)
"""
pipeline.stop()

print('saving..')
np.save('servo.npy', np.array(servo_states))
np.save('depth.npy', depth_images)
print('saved')
