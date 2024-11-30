import logging
import json
import base64
import aiohttp
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

@dataclass
class OllamaConfig:
    """Configuration for Ollama client"""
    model: str = "llava:34b"
    api_url: str = "http://localhost:11434/api/generate"
    prompt_path: str = "prompts/robot_prompt.txt"
    timeout: float = 30.0
    max_response_size: int = 1024 * 1024  # 1MB

class OllamaClient:
    """Async client for Ollama API interactions"""

    def __init__(self, config_path: str = "config.json"):
        """
        Initialize Ollama client
        
        Args:
            config_path: Path to configuration JSON file
        """
        self.logger = logging.getLogger(__name__)
        self.config = self._load_config(config_path)
        self.prompt_template = self._load_prompt_template()
        
    def _load_config(self, config_path: str) -> OllamaConfig:
        """
        Load configuration from JSON file
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            OllamaConfig object with settings
        """
        config_file = Path(config_path)
        if config_file.exists():
            self.logger.info(f"Loading configuration from {config_path}")
            try:
                with open(config_file, 'r') as f:
                    config_data = json.load(f)
                return OllamaConfig(**config_data)
            except Exception as e:
                self.logger.warning(f"Error loading config: {e}. Using defaults.")
                return OllamaConfig()
        else:
            self.logger.warning(f"Config file {config_path} not found. Using defaults.")
            return OllamaConfig()

    def _load_prompt_template(self) -> str:
        """
        Load prompt template from file
        
        Returns:
            Prompt template string
        """
        prompt_file = Path(self.config.prompt_path)
        try:
            with open(prompt_file, 'r') as f:
                return f.read().strip()
        except Exception as e:
            self.logger.error(f"Error loading prompt template: {e}")
            raise

    async def encode_image(self, image_path: str) -> str:
        """
        Encode image file to base64 asynchronously
        
        Args:
            image_path: Path to image file
            
        Returns:
            Base64 encoded image string
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"file://{image_path}") as response:
                    image_data = await response.read()
                    return base64.b64encode(image_data).decode('utf-8')
        except Exception as e:
            self.logger.error(f"Error encoding image: {e}")
            raise

    async def process_image(self, 
                          image_path: str,
                          custom_prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        Process image through Ollama API
        
        Args:
            image_path: Path to image file
            custom_prompt: Optional custom prompt to use instead of template
            
        Returns:
            Parsed JSON response from model
        """
        try:
            # Encode image
            image_base64 = await self.encode_image(image_path)
            
            # Prepare request payload
            payload = {
                "model": self.config.model,
                "prompt": custom_prompt or self.prompt_template,
                "images": [image_base64]
            }
            
            # Make API request
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.api_url,
                    json=payload,
                    timeout=self.config.timeout
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise RuntimeError(
                            f"API request failed with status {response.status}: {error_text}"
                        )
                    
                    # Process streaming response
                    model_response = ""
                    async for line in response.content:
                        if len(model_response) > self.config.max_response_size:
                            raise RuntimeError("Response size exceeded limit")
                            
                        decoded_line = line.decode('utf-8').strip()
                        if not decoded_line:
                            continue
                            
                        try:
                            json_obj = json.loads(decoded_line)
                            model_response += json_obj.get('response', '')
                            
                            if json_obj.get('done', False):
                                break
                        except json.JSONDecodeError as e:
                            self.logger.warning(f"Error parsing response line: {e}")
                            continue
            
            # Parse final response
            try:
                return json.loads(model_response)
            except json.JSONDecodeError as e:
                self.logger.error(f"Error parsing final response: {e}")
                raise ValueError(f"Invalid JSON response: {model_response}")
                
        except Exception as e:
            self.logger.error(f"Error processing image: {e}")
            raise

    async def validate_response(self, response: Dict[str, Any]) -> bool:
        """
        Validate response format
        
        Args:
            response: Parsed JSON response from model
            
        Returns:
            True if response is valid, False otherwise
        """
        required_fields = {'thoughts', 'speech', 'movement'}
        movement_fields = {'left_track', 'right_track', 'head'}
        track_fields = {'speed', 'direction'}
        
        try:
            # Check top-level fields
            if not all(field in response for field in required_fields):
                return False
                
            # Check movement structure
            movement = response['movement']
            if not all(field in movement for field in movement_fields):
                return False
                
            # Check track parameters
            for track in ['left_track', 'right_track']:
                track_data = movement[track]
                if not all(field in track_data for field in track_fields):
                    return False
                    
                # Validate value ranges
                speed = track_data['speed']
                direction = track_data['direction']
                if not (0 <= speed <= 100 and direction in [0, 1]):
                    return False
                    
            # Check head angle
            head_angle = movement['head']['angle']
            if not (0 <= head_angle <= 180):
                return False
                
            return True
            
        except (KeyError, TypeError) as e:
            self.logger.warning(f"Response validation failed: {e}")
            return False

async def main():
    """Example usage of OllamaClient"""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create client
    client = OllamaClient(config_path="config.json")
    
    try:
        # Process image
        response = await client.process_image("camera_output/color_frame.jpg")
        
        # Validate response
        if await client.validate_response(response):
            print("Valid response received:")
            print(json.dumps(response, indent=2))
        else:
            print("Invalid response format")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
