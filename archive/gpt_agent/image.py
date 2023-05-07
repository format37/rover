import pyrealsense2 as rs
import numpy as np
import requests
from datetime import datetime as dt
# imports, required for saving to jpeg
from PIL import Image


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
	# np.save('color.npy', color_image)
	# convert to jpeg
	img = Image.fromarray(color_image, 'RGB')
	img.save('color.jpg')

	path = 'color.jpg'
	url = 'http://192.168.1.102:20000/request'
	files = {'file': open(path, 'rb')}
	start_time = dt.now()
	print(start_time)
	r = requests.post(url, files=files)
	end_time = dt.now()
	print(r.text)
	print(end_time)
	print(end_time - start_time)



if __name__ == '__main__':
	main()
