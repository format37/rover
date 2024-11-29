import time
import numpy as np
import pyrealsense2 as rs
import cv2
from PIL import Image
import matplotlib.pyplot as plt

def camera_capture():
    # Initialize RealSense pipeline
    pipeline = rs.pipeline()
    config = rs.config()
    
    # Configure streams - lower resolution for better performance
    config.enable_stream(rs.stream.depth, 1280, 720, rs.format.z16, 30) # Up to 90 fps
    config.enable_stream(rs.stream.color, 1920, 1080, rs.format.bgr8, 30) # Up to 30 fps
    
    # Configure depth filters
    dec_filter = rs.decimation_filter()
    spat_filter = rs.spatial_filter()
    temp_filter = rs.temporal_filter()
    
    # Start streaming
    profile = pipeline.start(config)
    depth_sensor = profile.get_device().first_depth_sensor()
    depth_scale = depth_sensor.get_depth_scale()
    
    # Create align object
    align = rs.align(rs.stream.color)
    
    print('camera start')
    
    try:
        # Wait for a coherent pair of frames
        for i in range(30):  # Wait for auto-exposure to stabilize
            pipeline.wait_for_frames()
            
        frames = pipeline.wait_for_frames()
        aligned_frames = align.process(frames)
        
        depth_frame = aligned_frames.get_depth_frame()
        color_frame = aligned_frames.get_color_frame()
        
        if not depth_frame or not color_frame:
            raise RuntimeError("Could not acquire frames")
            
        # Apply filters to depth
        filtered_depth = depth_frame
        for filter in [dec_filter, spat_filter, temp_filter]:
            filtered_depth = filter.process(filtered_depth)
            
        # Convert frames to numpy arrays
        depth_image = np.asanyarray(filtered_depth.get_data())
        color_image = np.asanyarray(color_frame.get_data())
        
        # Convert BGR to RGB for color image
        color_image_rgb = cv2.cvtColor(color_image, cv2.COLOR_BGR2RGB)
        
        # Save color image using PIL
        color_pil = Image.fromarray(color_image_rgb)
        color_pil.save('color_frame.jpg')
        
        # Process and save depth image using matplotlib
        plt.imsave('depth_frame_gray.png', depth_image, cmap='gray')
        
        # # Save raw numpy arrays
        # np.save('depth_image.npy', depth_image)
        # np.save('color_image.npy', color_image)
        
        # Create colormap version of depth
        depth_colormap = cv2.applyColorMap(
            cv2.convertScaleAbs(depth_image, alpha=0.03),
            cv2.COLORMAP_JET
        )
        cv2.imwrite('depth_frame_colormap.jpg', depth_colormap)
        
        print('Images saved:')
        print(' - color_frame.jpg (RGB color image)')
        print(' - depth_frame_gray.png (Grayscale depth visualization)')
        print(' - depth_frame_colormap.jpg (Colored depth visualization)')
        print(' - depth_image.npy (Raw depth data)')
        print(' - color_image.npy (Raw color data)')
        
    finally:
        pipeline.stop()

def main():
    camera_capture()

if __name__ == '__main__':
    main()