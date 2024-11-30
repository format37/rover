import asyncio
import logging
from mech_controls import RobotController
from camera_controls import CameraController
from ollama_client import OllamaClient
from speech_synthesis import TTSClient
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
    # Initialize motoric and sensory controllers
    mech = RobotController()
    camera = CameraController(output_dir='camera_output')
    await camera.start()
    llm_client = OllamaClient(config_path="config.json")
    tts_client = TTSClient(config_path="config.json")
    track_speed = 0.05


    last_head_angle = 90
    counter = 0
    while True:
        
        # Capture image
        await camera.capture_and_save(save_raw=False)
        
        # Process image and get response
        response = await llm_client.process_image("camera_output/color_frame.jpg")
        print(f"type: {type(response)}")
        print(f"Response:\n{response}")
        append_response_to_text_file(response, "response_log.txt")
        
        # Pronounce speech from response
        try:
            text_to_speech = response['speech']
            if len(text_to_speech):
                await tts_client.synthesize_and_play(text_to_speech)
        except KeyError:
            print("No speech in response")

        # Move head
        new_head_angle = await llm_client.get_head_angle(response)
        if new_head_angle is not None:
            print(f"new_head_angle: {new_head_angle}")
            await mech.smooth_head_move(last_head_angle, new_head_angle)
            last_head_angle = new_head_angle
        else:
            print("Could not get new_head_angle")

        # Move tracks
        left_track_active = False
        right_track_active = False
        if 'left_track' in response:
            if "direction" in response['left_track']:
                direction_left = response['left_track']['direction']
                left_track_active = True
        if 'right_track' in response:
            if "direction" in response['right_track']:
                direction_right = response['right_track']['direction']
                direction_right = 1 if direction_right == 0 else 0 # Reverse direction
                right_track_active = True
        if left_track_active and right_track_active:
            await asyncio.gather(
                mech.smooth_track_set(0, track_speed, 1),
                mech.smooth_track_set(1, track_speed, 0)
            )
            await asyncio.sleep(2.0)
            await mech.stop()

        counter += 1
        if counter >= 5:
            break
    await camera.stop()
    await mech.smooth_head_move(last_head_angle, 90)

if __name__ == '__main__':
    asyncio.run(main())
