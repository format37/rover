import requests
import json
import logging
import os
from pathlib import Path
from typing import Optional, Dict
import asyncio


class TTSClient:
    """A client for interacting with a Text-to-Speech server with audio playback capabilities."""
    
    def __init__(self, config_path: Optional[str] = None, default_server_url: str = 'http://localhost:5000/synthesize'):
        """
        Initialize the TTS client.
        
        Args:
            config_path: Path to configuration file (optional)
            default_server_url: Default TTS server URL if not specified in config
        """
        # Configure logging
        self.logger = logging.getLogger(__name__)
        self._setup_logging()
        
        # Load configuration
        self.config = self._load_config(config_path) if config_path else {}
        self.server_url = self.config.get('tts_api_url', default_server_url)
        self.audio_device = self.config.get('audio_device', 'plughw:CARD=Device,DEV=0')
        
        self.logger.info(f"Initialized TTS client with server URL: {self.server_url}")

    def _setup_logging(self) -> None:
        """Configure logging settings."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    def _load_config(self, config_path: str) -> Dict:
        """
        Load configuration from JSON file.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            Config dictionary with settings
        """
        config_file = Path(config_path)
        if config_file.exists():
            self.logger.info(f"Loading configuration from {config_path}")
            try:
                with open(config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.warning(f"Error loading config: {e}. Using defaults.")
                return {}
        else:
            self.logger.warning(f"Config file {config_path} not found. Using defaults.")
            return {}

    def synthesize(self, text: str, output_file: str = 'speech.wav') -> bool:
        """
        Send text to the TTS server and save the returned audio file.
        
        Args:
            text: Text to convert to speech
            output_file: Path where to save the audio file
            
        Returns:
            bool: True if synthesis was successful, False otherwise
        """
        self.logger.info(f"Synthesizing text: '{text}'")
        try:
            # Send POST request to server
            response = requests.post(
                self.server_url,
                data={'text': text},
                stream=True
            )
            
            # Check if request was successful
            response.raise_for_status()
            
            # Save the audio file
            with open(output_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
            self.logger.info(f"Audio saved to: {output_file}")
            return True
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error communicating with server: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    self.logger.error(f"Server error: {e.response.json()['error']}")
                except:
                    self.logger.error(f"Server returned status code: {e.response.status_code}")
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

    async def synthesize_and_play(self, text: str, output_file: str = 'speech.wav'):
        """
        Synthesize text to speech and play it immediately.
        
        Args:
            text: Text to convert to speech
            output_file: Path where to save the audio file
            
        Returns:
            bool: True if both synthesis and playback were successful
        """
        if self.synthesize(text, output_file):
            self.play_audio(output_file)


async def main():
    """Example usage of the TTSClient class."""
    # Initialize client with optional config file
    client = TTSClient("config.json")
    
    # Example 1: Synthesize and save
    text = "Hello, this is a test of the text-to-speech system."
    await client.synthesize(text, "test_output.wav")
    
    # Example 2: Synthesize and play immediately
    await client.synthesize_and_play("This text will be synthesized and played immediately.")


if __name__ == "__main__":
    asyncio.run(main())
