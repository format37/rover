import pyrealsense2 as rs
import numpy as np
import time
from adafruit_servokit import ServoKit

def rotation_map(start_position, end_position, steps):
	multiplier = (end_position - start_position) / steps
	rot_map = dict()
	for i in range(0, steps):
		rot_map[i] = int(start_position + i * multiplier)
	return rot_map

kit = ServoKit(channels=16, address=0x42)
pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.depth,width=1280,height=720)
pipeline.start(config)

head_rotation_map = rotation_map(start_position=90, end_position=180, steps=300)
start_time = time.time()
i = 0
depth_images = None
servo_states = []
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
	current_servo_state = head_rotation_map[int(time_diff*100)]
	servo_states.append(current_servo_state)
	kit.servo[0].angle = current_servo_state	
	if (time_diff > 3):
		break
	i += 1

print('images collected:', np.array(depth_images).shape)
time.sleep(3)
for i in range(0,(180-90)):
	kit.servo[0].angle = 180-i
	time.sleep(0.03)

pipeline.stop()

print('saving..')
np.save('servo.npy', np.array(servo_states))
np.save('depth.npy', depth_images)
print('saved')
