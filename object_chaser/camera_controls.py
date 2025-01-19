import logging
import asyncio
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Tuple, List
import numpy as np
import pyrealsense2 as rs
import cv2
from PIL import Image
import matplotlib.pyplot as plt
import atexit
import weakref

@dataclass
class CameraConfig:
    """Configuration for RealSense camera streams"""
    depth_width: int = 1280
    depth_height: int = 720
    depth_fps: int = 30
    color_width: int = 1920
    color_height: int = 1080
    color_fps: int = 30
    stabilization_frames: int = 30
    depth_scale_alpha: float = 0.03
    enable_depth: bool = False  # Flag to control depth capture

class CameraController:
    """Controller for RealSense camera operations"""
    
    # Class-level set to track active instances
    _instances = weakref.WeakSet()
    
    @classmethod
    def _cleanup_all(cls):
        """Class method to cleanup all active camera instances"""
        for instance in cls._instances:
            try:
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                if loop.is_running():
                    loop.create_task(instance._cleanup())
                else:
                    loop.run_until_complete(instance._cleanup())
            except Exception as e:
                instance.logger.error(f"Error during cleanup: {e}")

    def __init__(self, output_dir: str = '.', enable_depth: bool = False):
        """
        Initialize camera controller
        
        Args:
            output_dir: Directory to save captured images
            enable_depth: Whether to enable depth capture (default: False)
        """
        self.logger = logging.getLogger(__name__)
        self.config = CameraConfig(enable_depth=enable_depth)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize RealSense components
        self.pipeline = rs.pipeline()
        self.rs_config = rs.config()
        
        # Initialize filters if depth is enabled
        self.filters = {}
        if self.config.enable_depth:
            self.filters = {
                'decimation': rs.decimation_filter(),
                'spatial': rs.spatial_filter(),
                'temporal': rs.temporal_filter()
            }
        
        self._configure_streams()
        self._is_running = False
        
        # Register instance for cleanup
        self._instances.add(self)
        atexit.register(self.__class__._cleanup_all)
        
        self.logger.info(f'Camera controller initialized (depth {"enabled" if enable_depth else "disabled"})')

    async def _cleanup(self):
        """Internal cleanup method"""
        if self._is_running:
            try:
                await self.stop()
            except Exception as e:
                self.logger.error(f"Error during cleanup: {e}")

    def __del__(self):
        """Destructor to ensure cleanup when object is garbage collected"""
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            if loop.is_running():
                loop.create_task(self._cleanup())
            else:
                loop.run_until_complete(self._cleanup())
        except Exception as e:
            self.logger.error(f"Error during destructor cleanup: {e}")

    async def __aenter__(self):
        """Async context manager entry"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self._cleanup()

    def _configure_streams(self):
        """Configure depth and color streams"""
        # Always enable color stream
        self.rs_config.enable_stream(
            rs.stream.color,
            self.config.color_width,
            self.config.color_height,
            rs.format.bgr8,
            self.config.color_fps
        )
        
        # Enable depth stream only if configured
        if self.config.enable_depth:
            self.rs_config.enable_stream(
                rs.stream.depth,
                self.config.depth_width,
                self.config.depth_height,
                rs.format.z16,
                self.config.depth_fps
            )

    async def start(self) -> None:
        """Start the RealSense pipeline"""
        self.logger.info('Starting camera pipeline')
        self.profile = self.pipeline.start(self.rs_config)
        
        if self.config.enable_depth:
            self.depth_sensor = self.profile.get_device().first_depth_sensor()
            self.depth_scale = self.depth_sensor.get_depth_scale()
            self.align = rs.align(rs.stream.color)

        # # RGB quality improvements
        # device = self.profile.get_device()
        # color_sensor = device.query_sensors()[1]  # usually index 1 is color sensor
        # # Enable auto-exposure
        # color_sensor.set_option(rs.option.enable_auto_exposure, 1)
        # # Optionally, tweak exposure compensation if available
        # color_sensor.set_option(rs.option.exposure, some_exposure_value)
        # # Adjust gain if automatic settings are not ideal
        # color_sensor.set_option(rs.option.gain, 16)
        
        self._is_running = True
        
        # Wait for auto-exposure to stabilize
        self.logger.info('Waiting for auto-exposure stabilization')
        for _ in range(self.config.stabilization_frames):
            self.pipeline.wait_for_frames()
            await asyncio.sleep(0.001)  # Allow other tasks to run

    async def stop(self) -> None:
        """Stop the RealSense pipeline"""
        if self._is_running:
            self.logger.info('Stopping camera pipeline')
            self.pipeline.stop()
            self._is_running = False

    async def get_frames(self) -> Tuple[Optional[np.ndarray], np.ndarray]:
        """
        Capture and process a set of frames
        
        Returns:
            Tuple of (depth_image, color_image) as numpy arrays
            depth_image will be None if depth capture is disabled
        """
        self.logger.info('Capturing frames')
        
        # Get frames
        frames = self.pipeline.wait_for_frames()
        
        # Process depth if enabled
        depth_image = None
        if self.config.enable_depth:
            aligned_frames = self.align.process(frames)
            depth_frame = aligned_frames.get_depth_frame()
            color_frame = aligned_frames.get_color_frame()
            
            if not depth_frame or not color_frame:
                raise RuntimeError("Could not acquire frames")
            
            # Apply filters to depth
            filtered_depth = depth_frame
            for filter_name, filter_obj in self.filters.items():
                self.logger.debug(f'Applying {filter_name} filter')
                filtered_depth = filter_obj.process(filtered_depth)
            
            depth_image = np.asanyarray(filtered_depth.get_data())
        else:
            color_frame = frames.get_color_frame()
            if not color_frame:
                raise RuntimeError("Could not acquire color frame")
        
        # Convert color frame to numpy array
        color_image = np.asanyarray(color_frame.get_data())
        
        return depth_image, color_image

    async def save_frames(self, depth_image: Optional[np.ndarray], 
                         color_image: np.ndarray,
                         save_raw: bool = False) -> None:
        """
        Save captured frames to files
        
        Args:
            depth_image: Depth image as numpy array (can be None if depth disabled)
            color_image: Color image as numpy array
            save_raw: Whether to save raw numpy arrays
        """
        self.logger.info('Saving captured frames')
        
        # Convert BGR to RGB for color image
        color_image_rgb = cv2.cvtColor(color_image, cv2.COLOR_BGR2RGB)
        
        # Save color image
        color_path = self.output_dir / 'color_frame.jpg'
        color_pil = Image.fromarray(color_image_rgb)
        color_pil.save(color_path)
        self.logger.info(f'Saved color image to {color_path}')
        
        # Save depth visualizations if depth is enabled and image is provided
        if self.config.enable_depth and depth_image is not None:
            depth_gray_path = self.output_dir / 'depth_frame_gray.png'
            plt.imsave(depth_gray_path, depth_image, cmap='gray')
            self.logger.info(f'Saved grayscale depth image to {depth_gray_path}')
            
            depth_color_path = self.output_dir / 'depth_frame_colormap.jpg'
            depth_colormap = cv2.applyColorMap(
                cv2.convertScaleAbs(depth_image, alpha=self.config.depth_scale_alpha),
                cv2.COLORMAP_JET
            )
            cv2.imwrite(str(depth_color_path), depth_colormap)
            self.logger.info(f'Saved colormap depth image to {depth_color_path}')
            
            if save_raw:
                np.save(self.output_dir / 'depth_image.npy', depth_image)
        
        if save_raw:
            np.save(self.output_dir / 'color_image.npy', color_image)
            self.logger.info('Saved raw numpy arrays')

    async def capture_and_save(self, save_raw: bool = False) -> None:
        """
        Capture frames and save them in one operation
        
        Args:
            save_raw: Whether to save raw numpy arrays
        """
        try:
            depth_image, color_image = await self.get_frames()
            await self.save_frames(depth_image, color_image, save_raw)
        except Exception as e:
            self.logger.error(f'Error during capture and save: {e}')
            raise

async def main():
    """Example usage of CameraController"""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Example with depth disabled (default)
    async with CameraController(output_dir='camera_output') as camera:
        await camera.capture_and_save(save_raw=False)
    
    # # Example with depth enabled
    # async with CameraController(output_dir='camera_output_depth', enable_depth=True) as camera:
    #     await camera.capture_and_save(save_raw=True)

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()