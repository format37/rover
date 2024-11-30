import asyncio
import logging
from mech_controls import RobotController
from camera_controls import CameraController
import base64
import requests
import json

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    mech = RobotController()

    await mech.look_right()
    await mech.look_center(0)
    await mech.look_left()
    await mech.look_center(180)
    
    await mech.move_forward()
    await mech.turn_left()
    await mech.turn_right()
    await mech.move_backward()

    # Create and use camera controller
    camera = CameraController(output_dir='camera_output')
    try:
        await camera.start()
        await camera.capture_and_save(save_raw=False)
    finally:
        await camera.stop()

if __name__ == '__main__':
    asyncio.run(main())