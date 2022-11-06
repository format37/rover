import pyrealsense2 as rs
import numpy as np
import time


def camera_capture_single_nondepth_image():
	pipeline = rs.pipeline()
	config = rs.config()
	config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
	pipeline.start(config)
	frames = pipeline.wait_for_frames()
	color_frame = frames.get_color_frame()
	color_image = np.asanyarray(color_frame.get_data())
	pipeline.stop()
	return color_image


def main():
	# read image and save to file
	color_image = camera_capture_single_nondepth_image()
	np.save('color.npy', color_image)


if __name__ == '__main__':
	main()
