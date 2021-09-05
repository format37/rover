import pyrealsense2 as rs

pipeline = rs.pipeline()
config = rs.config()
#config.enable_stream(rs.stream.depth, 256, 144, rs.format.z16, 90)
config.enable_stream(rs.stream.depth,width=640,height=480)
pipeline.start(config)

while True:
	frames = pipeline.wait_for_frames()
	depth = frames.get_depth_frame()
	if not depth: continue

	coverage = [0]*64
	#for y in range(480):
	left = 0
	right= 0
	for y in range(350):
		for x in range(0,320):		left  += depth.get_distance(x, y)
		for x in range(320,640):	right += depth.get_distance(x, y)
	lr = left+right	
	print(left/lr,right/lr,lr/10000)
	#if lr/10000<10: stop
	#exit()
