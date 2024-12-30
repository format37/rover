import requests
import json
from pathlib import Path
from typing import Optional
import asyncio
import os

class TTSGenerator:
    def __init__(self, base_url: str = 'http://localhost:5000'):
        self.base_url = base_url.rstrip('/')
        self.tts_endpoint = f"{self.base_url}/tts"

    def generate_speech(
        self, 
        text: str, 
        output_path: str = 'output.wav',
        language: str = 'ru',
        reference_file: str = 'asmr_0.wav'
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
        success = self.synthesize(text, output_file)
        if success:
            return self.play_audio(output_file)
        return False

async def main():
    generator = TTSGenerator()
    text = "Так, кажется кому-то пора помыть посуду"
    await generator.synthesize_and_play(text)

if __name__ == "__main__":
    asyncio.run(main())
