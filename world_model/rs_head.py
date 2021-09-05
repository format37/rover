import pyrealsense2 as rs
import numpy as np
import time

def rotation_map(start_position, end_position, steps):
	multiplier = (end_position - start_position) / steps
	rot_map = dict()
	for i in range(0, steps):
		rot_map[i] = int(start_position + i * multiplier)
	return rot_map

pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.depth,width=1280,height=720)
pipeline.start(config)

head_rotation_map = rotation_map(start_position=95, end_position=180, steps=300)
start_time = time.time()
i = 0
images = None
while True:
	frames = pipeline.wait_for_frames()
	depth = frames.get_depth_frame()
	if not depth:
		continue
	new_image = np.array([np.asanyarray(depth.get_data( ))])
	if images is None:
		images = new_image
	else:
		images = np.append(images, new_image, axis=0)
	time_diff = time.time() - start_time
	if (time_diff > 3):
		break
	print(head_rotation_map[int(time_diff*100)])	
	i += 1

print('images collected:', i, np.array(images).shape)
pipeline.stop()
