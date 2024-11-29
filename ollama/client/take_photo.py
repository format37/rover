import time
import numpy as np
import pyrealsense2 as rs
import cv2  # Added for RGB image saving

def camera_capture():
    pipeline = rs.pipeline()
    config = rs.config()
    
    # Configure both depth and color streams
    config.enable_stream(rs.stream.depth, 424, 240, rs.format.z16, 30)
    config.enable_stream(rs.stream.color, 424, 240, rs.format.bgr8, 30)
    
    align = rs.align(rs.stream.color)
    pipeline.start(config)
    
    depth_images = None
    color_images = None
    
    delay = 0.1
    print('camera start')
    
    while True:
        frames = pipeline.wait_for_frames()
        aligned_frames = align.process(frames)
        
        depth_frame = aligned_frames.get_depth_frame()
        color_frame = aligned_frames.get_color_frame()
        
        if not depth_frame or not color_frame:
            continue
            
        # Process depth frame
        new_depth_image = np.array([np.asanyarray(depth_frame.get_data())])
        if depth_images is None:
            depth_images = new_depth_image
        else:
            depth_images = np.append(depth_images, new_depth_image, axis=0)
            
        # Process color frame
        new_color_image = np.array([np.asanyarray(color_frame.get_data())])
        if color_images is None:
            color_images = new_color_image
        else:
            color_images = np.append(color_images, new_color_image, axis=0)
        
        time.sleep(delay)
        
        if np.array(depth_images).shape[0] > 0:
            break

    pipeline.stop()
    
    print('camera saving', np.array(depth_images).shape, 'depth images')
    print('camera saving', np.array(color_images).shape, 'color images')
    
    # Save depth images as numpy array
    np.save('depth_images.npy', depth_images)
    
    # Save color images as both numpy array and JPEG
    np.save('color_images.npy', color_images)
    
    # Save individual frames as JPEG
    for i, color_frame in enumerate(color_images):
        cv2.imwrite(f'color_frame_{i}.jpg', color_frame)
        
    print('camera saved')

def main():
    camera_capture()

if __name__ == '__main__':
    main()