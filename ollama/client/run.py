import asyncio
import logging
from mech_controls import RobotController
from camera_controls import CameraController
from ollama_client import OllamaClient
import base64
import requests
import json

def append_response_to_text_file(response: dict, output_path: str):
    with open(output_path, "a") as f:
        f.write(json.dumps(response, indent=2))
        f.write("\n\n")

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    mech = RobotController()
    camera = CameraController(output_dir='camera_output')

    # await mech.look_right()
    # await mech.look_center(0)
    # await mech.look_left()
    # await mech.look_center(180)
    
    # await mech.move_forward()
    # await mech.turn_left()
    # await mech.turn_right()
    # await mech.move_backward()

    # try:
    #     await camera.start()
    #     await camera.capture_and_save(save_raw=False)
    # finally:
    #     await camera.stop()

    # Create client
    client = OllamaClient(config_path="config.json")
    last_head_angle = 90
    counter = 0
    while True:
        # Process image
        response = await client.process_image("camera_output/color_frame.jpg")
        print(f"type: {type(response)}")
        print(f"Response:\n{response}")
        append_response_to_text_file(response, "response_log.txt")
        new_head_angle = await client.get_head_angle(response)
        if new_head_angle is not None:
            print(f"new_head_angle: {new_head_angle}")
            await mech.smooth_head_move(last_head_angle, new_head_angle)
            last_head_angle = new_head_angle
        else:
            print("Could not get new_head_angle")
        counter += 1
        if counter >= 5:
            break
    await mech.smooth_head_move(last_head_angle, 90)

if __name__ == '__main__':
    asyncio.run(main())
