import asyncio
import logging
from contextlib import AsyncExitStack
from mech_controls import RobotController
from camera_controls import CameraController
from llm_client import create_llm_client
from speech_synthesis import TTSGenerator
import json

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger = logging.getLogger(__name__)

    # Use AsyncExitStack to manage multiple async context managers
    async with AsyncExitStack() as stack:
        try:
            # Initialize all controllers within the stack
            logger.info("Initializing robot controller...")
            mech = await stack.enter_async_context(RobotController())
            
            logger.info("Initializing camera controller...")
            camera = await stack.enter_async_context(CameraController(output_dir='camera_output'))
            
            # Initialize LLM client based on configuration
            logger.info("Initializing LLM client...")
            llm_client = create_llm_client(config_path="config.json")
            
            # Start the client if it's Ollama (OpenAI client doesn't need starting)
            if hasattr(llm_client, 'start'):
                await llm_client.start()
                # Ensure cleanup on exit for Ollama client
                stack.push_async_callback(llm_client.stop)
            
            logger.info("Initializing TTS client...")
            # tts_client = TTSClient(config_path="config.json")
            tts_client = TTSGenerator()

            # counter = 0
            max_iterations = -1  # Maximum number of iterations before exiting

            logger.info("Starting main control loop...")
            # for counter in range(max_iterations):
            while max_iterations != 0:
                # logger.info(f"\nIteration {counter + 1}/{max_iterations}")
                logger.info(f"\nIteration {abs(max_iterations)}")
                
                # Capture image
                await camera.capture_and_save(save_raw=False)
                
                # Process image and get response
                response = await llm_client.process_image("camera_output/color_frame.jpg")
                
                # Log the response components
                logger.info(f"Наблюдение: {response.get('наблюдение', '')}")
                logger.info(f"Чувства: {response.get('чувства', '')}")
                logger.info(f"Мысли: {response.get('мысли', '')}")
                logger.info(f"Речь: {response.get('речь', '')}")
                
                # Save chat history
                llm_client.save_chat_history()

                # Handle speech synthesis
                if speech_text := response.get('речь'):
                    logger.info("Synthesizing speech...")
                    await tts_client.synthesize_and_play(speech_text)

                # Handle head movement
                if "движения" in response:
                    if "голова" in response["движения"]:
                        new_head_angle = response["движения"]["голова"]
                        try:
                            logger.info(f"Moving head to angle: {new_head_angle}")
                            await mech.smooth_head_move(mech.current_head_angle, new_head_angle)
                            mech.current_head_angle = new_head_angle
                        except Exception as e:
                            logger.error(f"Error during head movement: {e}")

                    # Handle track movement
                    if "гусеницы" in response["движения"]:
                        tracks = response["движения"]["гусеницы"]
                        left_track = tracks.get("левый", 0)
                        right_track = tracks.get("правый", 0)
                        duration = tracks.get("длительность", 1.0)
                        
                        if left_track != 0 or right_track != 0:
                            logger.info(f"Moving tracks - Left: {left_track}, Right: {right_track}, Duration: {duration}")
                            await mech.move_tracks(left_track, right_track, duration)
                        else:
                            logger.debug("Skipping track movement as both tracks are set to 0")
                        

                    # # Handle track movement
                    # if "left_track" in response["movement"] and "right_track" in response["movement"]:
                    #     try:
                    #         left_track = response["movement"]["left_track"].get("direction", 0)
                    #         right_track = response["movement"]["right_track"].get("direction", 0)
                    #         duration = response["movement"].get("duration", 1.0)  # Default 1 second if not specified
                            
                    #         logger.info(f"Moving tracks - Left: {left_track}, Right: {right_track}, Duration: {duration}")
                    #         await mech.move_tracks(left_track, right_track, duration)
                    #     except Exception as e:
                    #         logger.error(f"Error during track movement: {e}")

                    # Add delay between iterations
                    # logger.info("Waiting for next iteration...")
                    # await asyncio.sleep(15)  # 15 second delay between requests

                    # counter += 1
                    # if counter >= max_iterations:
                    #     logger.info("Reached maximum iterations, exiting main loop")
                    #     break
            max_iterations -= 1

        except Exception as e:
            logger.error(f"Critical error in main function: {e}")
            raise

        finally:
            logger.info("Cleaning up and shutting down...")
            # AsyncExitStack will handle cleanup of entered context managers

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt, shutting down...")
    except Exception as e:
        print(f"Fatal error: {e}")
        raise
