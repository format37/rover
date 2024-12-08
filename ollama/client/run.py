import asyncio
import logging
from contextlib import AsyncExitStack
from mech_controls import RobotController
from camera_controls import CameraController
from ollama_client import OllamaClient
from speech_synthesis import TTSClient
import json

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
        # Start the Ollama request processor
        await llm_client.start()
        # Ensure cleanup on exit
        stack.push_async_callback(llm_client.stop)
        
        tts_client = TTSClient(config_path="config.json")
        track_speed = 0.05

        last_head_angle = 90
        counter = 0
        try:
            while True:
                # Capture image
                await camera.capture_and_save(save_raw=False)
                
                # Process image and get response
                response = await llm_client.process_image("camera_output/color_frame.jpg")
                print(f"Response:\n{json.dumps(response, indent=2)}")
                
                # Save chat history
                llm_client.save_chat_history("chat_history.json")
                
                # Handle speech synthesis
                if speech_text := response.get('speech'):
                    await tts_client.synthesize_and_play(speech_text)

                # Handle head movement
                if new_head_angle := await llm_client.get_head_angle(response):
                    print(f"new_head_angle: {new_head_angle}")
                    await mech.smooth_head_move(last_head_angle, new_head_angle)
                    last_head_angle = new_head_angle
                    mech.current_head_angle = new_head_angle

                # Handle track movement
                movement = response.get('movement', {})
                left_track = movement.get('left_track', {})
                right_track = movement.get('right_track', {})
                
                if 'direction' in left_track and 'direction' in right_track:
                    await mech.move_tracks(
                        track_speed if left_track['direction'] == 0 else -track_speed,
                        track_speed if right_track['direction'] == 0 else -track_speed,
                        2
                    )
                    await asyncio.sleep(2.0)
                    await mech.stop()

                counter += 1
                if counter >= 5:
                    break

        except Exception as e:
            logging.error(f"Error in main loop: {e}")
            raise

if __name__ == '__main__':
    asyncio.run(main())
    