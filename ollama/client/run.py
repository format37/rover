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
        # try:
        while True:
            # Capture image
            await camera.capture_and_save(save_raw=False)
            
            # Process image and get response
            response = await llm_client.process_image("camera_output/color_frame.jpg")
            print(f"Response:\n{json.dumps(response, indent=2)}")
            
            # Save chat history
            llm_client.save_chat_history("chat_history.json")
            
            # Add delay to ensure previous request is fully completed
            await asyncio.sleep(15)  # 15 second delay between requests
            
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
            try:
                movement = response.get('movement', {})
                left_track = movement.get('left_track', {})
                right_track = movement.get('right_track', {})
                
                if 'duration' in response:
                    duration = response['duration']
                else:
                    duration = 2.0

                if 'velocity' in left_track:
                    left_velocity = left_track['velocity']
                else:
                    left_velocity = 0.0
                if 'velocity' in right_track:
                    right_velocity = right_track['velocity']
                else:
                    right_velocity = 0.0
                if abs(left_velocity) + abs(right_velocity) > 0 and duration > 0:
                    await mech.move_tracks(left_velocity, right_velocity, duration)
                else:
                    logging.info("No track movement required")
                    
            except Exception as e:
                logging.error(f"Skipping track movement due to JSON parse error: {e}")

            counter += 1
            print(f"Counter: {counter}")
            if counter >= 5:
                print("Exiting main loop due to the end of the session")
                break

        # except Exception as e:
        #     logging.error(f"Error in main loop: {e}")
        #     raise

if __name__ == '__main__':
    asyncio.run(main())
