import pyrealsense2 as rs
import numpy as np
import time

pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.depth,width=1280,height=720)
pipeline.start(config)

start_time = time.time()
i = 0
images = None
while True:
	frames = pipeline.wait_for_frames()
	depth = frames.get_depth_frame()
	if not depth:
		continue
	new_image = np.asanyarray(depth.get_data( ))
	if images is None:
		images = np.array([new_image])
	else:
		images = np.append(images, new_image, axis=0)
	i += 1
	if (time.time() - start_time > 3):
		break
print('images collected:', i, np.array(images).shape)
pipeline.stop()
