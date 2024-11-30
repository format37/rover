import requests
import json
from pathlib import Path
import logging

def load_config(config_path: str) -> dict:
        """
        Load configuration from JSON file
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            Config object with settings
        """
        config_file = Path(config_path)
        if config_file.exists():
            logger.info(f"Loading configuration from {config_path}")
            try:
                with open(config_file, 'r') as f:
                    config_data = json.load(f)
                return config_data
            except Exception as e:
                logger.warning(f"Error loading config: {e}. Using defaults.")
                return None
        else:
            logger.warning(f"Config file {config_path} not found. Using defaults.")
            return None

def text_to_speech(text, server_url='http://localhost:5000/synthesize', output_file='speech.wav'):
    """
    Send text to the TTS server and save the returned audio file
    
    Args:
        text (str): Text to convert to speech
        server_url (str): URL of the TTS server
        output_file (str): Path where to save the audio file
    """
    try:
        # Send POST request to server
        response = requests.post(
            server_url,
            data={'text': text},
            stream=True
        )
        
        # Check if request was successful
        response.raise_for_status()
        
        # Save the audio file
        with open(output_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        print(f"Audio saved to: {output_file}")
        
    except requests.exceptions.RequestException as e:
        print(f"Error communicating with server: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                print(f"Server error: {e.response.json()['error']}")
            except:
                print(f"Server returned status code: {e.response.status_code}")

# Example usage
if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    config = load_config("config.json")
    tts_api_url = config['tts_api_url']
    text = "Hello, this is a test of the text-to-speech server."
    text_to_speech(text, server_url=tts_api_url)