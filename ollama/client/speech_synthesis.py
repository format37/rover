import requests
import json
from pathlib import Path
from typing import Optional
import asyncio
import os
import logging

class TTSGenerator:
    def __init__(self, base_url: str = 'http://localhost:5000', audio_device: str = 'default'):
        self.base_url = base_url.rstrip('/')
        self.tts_endpoint = f"{self.base_url}/tts"
        self.audio_device = audio_device
        self.logger = logging.getLogger(__name__)

    def generate_speech(
        self, 
        text: str, 
        output_path: str = 'output.wav',
        language: str = 'ru',
        reference_file: str = 'kompot.wav'
    ) -> Optional[Path]:
        """
        Generate speech from text using TTS API
        
        Args:
            text: Text to convert to speech
            output_path: Path to save the output audio file
            language: Language code for TTS
            reference_file: Reference audio file for voice cloning
            
        Returns:
            Path object if successful, None if failed
        """
        payload = {
            'text': text,
            'language': language,
            'reference_file': reference_file
        }
        
        try:
            response = requests.post(
                self.tts_endpoint, 
                json=payload, 
                timeout=30
            )
            response.raise_for_status()
            
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            output_file.write_bytes(response.content)
            print(f"Audio saved successfully to: {output_file}")
            return output_file
            
        except requests.exceptions.RequestException as e:
            print(f"API request failed: {str(e)}")
        except Exception as e:
            print(f"Failed to save audio: {str(e)}")
        
        return None

    async def synthesize_and_play(self, text: str, output_file: str = 'speech.wav') -> bool:
        """
        Synthesize text to speech and play it immediately.
        
        Args:
            text: Text to convert to speech
            output_file: Path where to save the audio file
            
        Returns:
            bool: True if both synthesis and playback were successful
        """
        success = self.generate_speech(text, output_file)
        if success:
            return self.play_audio(output_file)
        return False

    def play_audio(self, filename: str) -> bool:
        """
        Play the audio file using system audio device.
        
        Args:
            filename: Path to the audio file to play
            
        Returns:
            bool: True if playback was successful, False otherwise
        """
        if not Path(filename).exists():
            self.logger.error(f"Audio file not found: {filename}")
            return False
            
        try:
            self.logger.info(f"Playing audio file: {filename}")
            command = f'aplay {filename} --device={self.audio_device}'
            exit_code = os.system(command)
            
            if exit_code == 0:
                self.logger.info("Audio playback completed successfully")
                return True
            else:
                self.logger.error(f"Audio playback failed with exit code: {exit_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error during audio playback: {e}")
            return False

async def main():
    logging.basicConfig(level=logging.INFO)
    with open('config.json') as f:
        config = json.load(f)
    generator = TTSGenerator(
        base_url=config['tts_api_url'],
        audio_device=config.get('audio_device', 'default')
    )
    text = "Так, кажется кому-то пора помыть посуду"
    await generator.synthesize_and_play(text)

if __name__ == "__main__":
    asyncio.run(main())
