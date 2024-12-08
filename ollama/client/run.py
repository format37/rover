import asyncio
import logging
from contextlib import AsyncExitStack
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

    # Use AsyncExitStack to manage multiple async context managers
    async with AsyncExitStack() as stack:
        # Initialize all controllers within the stack
        mech = await stack.enter_async_context(RobotController())
        camera = await stack.enter_async_context(CameraController(output_dir='camera_output'))
        
        # Initialize other components
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
            
            # Save chat history
            llm_client.save_chat_history("chat_history.json")
            
            # Handle speech synthesis
            try:
                text_to_speech = response['speech']
                if len(text_to_speech):
                    await tts_client.synthesize_and_play(text_to_speech)
            except KeyError:
                print("No speech in response")

            # Handle duration
            duration = response.get('duration', 2.0)

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
            velocity_left = 0.0
            velocity_right = 0.0
            
            if 'left_track' in response:
                velocity_left = response['left_track'].get('velocity', 0.0)
                left_track_active = 'velocity' in response['left_track']
                
            if 'right_track' in response:
                velocity_right = response['right_track'].get('velocity', 0.0)
                right_track_active = 'velocity' in response['right_track']
            
            if left_track_active and right_track_active:
                await mech.move_tracks(velocity_left, velocity_right, 2)
                await asyncio.sleep(2.0)
                await mech.stop()

            counter += 1
            if counter >= 5:
                break

        # No need for explicit cleanup - AsyncExitStack handles it automatically

if __name__ == '__main__':
    asyncio.run(main())