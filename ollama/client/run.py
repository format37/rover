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
    llm_client = OllamaClient(config_path="config.json")
    tts_client = TTSClient(config_path="config.json")


    last_head_angle = 90
    counter = 0
    while True:
        
        # Capture image
        try:
            await camera.start()
            await camera.capture_and_save(save_raw=False)
        finally:
            await camera.stop()
        
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
        counter += 1
        if counter >= 5:
            break
    await mech.smooth_head_move(last_head_angle, 90)

if __name__ == '__main__':
    asyncio.run(main())
