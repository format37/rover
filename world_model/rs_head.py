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

head_rotation_map = rotation_map(start_position=95, end_position=170, steps=300)
start_time = time.time()
i = 0
images = None
while True:
	frames = pipeline.wait_for_frames()
	depth = frames.get_depth_frame()
	if not depth:
		continue
	time_diff = time.time() - start_time
	new_image = np.array([np.asanyarray(depth.get_data( )), time_diff])
	if images is None:
		images = new_image
	else:
		images = np.append(images, new_image, axis=0)
	
	if (time_diff > 3):
		break
	kit.servo[0].angle = head_rotation_map[int(time_diff*100)]
	print(head_rotation_map[int(time_diff*100)])
	i += 1

print('images collected:', np.array(images).shape)
time.sleep(3)
for i in range(0,(170-95)):
	kit.servo[0].angle = 170-i
	time.sleep(0.03)

pipeline.stop()
print('saving..')
np.save('session.npy', images)
print('saved')
time.sleep(1)
print('exit', 170-i)
