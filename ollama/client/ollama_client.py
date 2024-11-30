import logging
import json
import base64
import aiohttp
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import re
from collections import deque

@dataclass
class OllamaConfig:
    """Configuration for Ollama client"""
    model: str = "llava:34b"
    ollama_api_url: str = "http://localhost:11434/api/generate"
    tts_api_url: str = "http://localhost:5000/synthesize"
    prompt_path: str = "prompts/robot_prompt.txt"
    audio_device: str = "default"
    timeout: float = 30.0
    max_response_size: int = 1024 * 1024  # 1MB
    max_history_size: int = 10  # Maximum number of chat history entries to keep

class OllamaClient:
    """Async client for Ollama API interactions with chat history support"""

    def __init__(self, config_path: str = "config.json"):
        """Initialize Ollama client with chat history support"""
        self.logger = logging.getLogger(__name__)
        self.config = self._load_config(config_path)
        self.base_prompt_template = self._load_prompt_template()
        self.chat_history = []

    def _load_config(self, config_path: str) -> OllamaConfig:
        """Load configuration from JSON file"""
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
        """Load base prompt template from file"""
        prompt_file = Path(self.config.prompt_path)
        try:
            with open(prompt_file, 'r') as f:
                return f.read().strip()
        except Exception as e:
            self.logger.error(f"Error loading prompt template: {e}")
            raise

    def _build_prompt_with_history(self) -> str:
        """Build complete prompt including chat history"""
        # Convert chat history to formatted string
        history_str = json.dumps(self.chat_history, indent=2) if self.chat_history else "[]"
        
        # Insert chat history into the base prompt
        prompt_with_history = f"""You are robot. You can see, speak and move head. You have memory of your past interactions.
Your chat history is:
{history_str}

The available movements are:
- Left track: direction (0=forward, 1=backward)
- Right track: direction (0=forward, 1=backward)
- Head position: angle 0-180 degrees (0=full left, 90=center, 180=full right)

Based on your memory and current observation, answer in JSON format:
{{
    "observations": "<describe what you see>",
    "feelings": "<describe how you feel, considering your past experiences>",
    "thoughts": "<describe your thinking process, referencing past events when relevant>",
    "speech": "<what you want to say, maintaining consistency with past interactions>",
    "movement": {{
        "head": {{
            "angle": <0-180>
        }},
        "left_track": {{
            "direction": <0 or 1>
        }},
        "right_track": {{
            "direction": <0 or 1>
        }}
    }}
}}"""
        return prompt_with_history

    def update_chat_history(self, response: Dict[str, Any]):
        """Update chat history with new response while maintaining size limit"""
        # Create history entry with relevant fields
        history_entry = {
            "observations": response.get("observations", ""),
            "feelings": response.get("feelings", ""),
            "thoughts": response.get("thoughts", ""),
            "speech": response.get("speech", ""),
            "movement": response.get("movement", {})
        }
        
        # Add new entry to history
        self.chat_history.append(history_entry)
        
        # Trim history if it exceeds max size
        if len(self.chat_history) > self.config.max_history_size:
            self.chat_history = self.chat_history[-self.config.max_history_size:]

    async def encode_image(self, image_path: str) -> str:
        """Encodes an image file to a base64 string."""
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read())
            return encoded_string.decode('utf-8')

    async def process_image(self, 
                          image_path: str,
                          custom_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Process image through Ollama API with chat history"""
        # Encode image
        image_base64 = await self.encode_image(image_path)

        print(f"# prompt:\n{custom_prompt or self._build_prompt_with_history()}")
        
        # Prepare request payload using prompt with history
        payload = {
            "model": self.config.model,
            "prompt": custom_prompt or self._build_prompt_with_history(),
            "images": [image_base64]
        }
        
        # Make API request
        async with aiohttp.ClientSession() as session:
            logging.info(f"Sending {image_path} to {self.config.ollama_api_url}")
            async with session.post(
                self.config.ollama_api_url,
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
        
        # Parse and validate final response
        try:
            self.logger.info(f"model_response:\n{model_response}")
            clean_response = await self.clean_json_response(model_response)
            parsed_response = json.loads(clean_response)
            
            # Update chat history with new response
            self.update_chat_history(parsed_response)
            
            return parsed_response
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Error parsing final response: {e}")
            raise ValueError(f"Invalid JSON response: {model_response}")

    async def clean_json_response(self, response: str) -> str:
        """Remove any markdown and comments from JSON response"""
        response = response.replace("```json", "")
        response = response.replace("```", "")
        return re.sub(r'//.*$', '', response, flags=re.MULTILINE)

    async def get_head_angle(self, response: Dict[str, Any]) -> Optional[int]:
        """Extract head angle from response with validation"""
        try:
            angle = response.get('movement', {}).get('head', {}).get('angle')
            if angle is not None:
                angle = int(angle)
                if 0 <= angle <= 180:
                    return angle
                else:
                    self.logger.warning(f"Head angle {angle} outside valid range [0-180]")
                    return 90  # Return to center if invalid
            else:
                self.logger.warning("No head angle found in response")
                return None
                
        except (TypeError, ValueError) as e:
            self.logger.warning(f"Error extracting head angle: {e}")
            return None

    def save_chat_history(self, filepath: str):
        """Save chat history to a JSON file"""
        try:
            with open(filepath, 'w') as f:
                json.dump(self.chat_history, f, indent=2)
            self.logger.info(f"Chat history saved to {filepath}")
        except Exception as e:
            self.logger.error(f"Error saving chat history: {e}")

    def load_chat_history(self, filepath: str):
        """Load chat history from a JSON file"""
        try:
            with open(filepath, 'r') as f:
                self.chat_history = json.load(f)
            self.logger.info(f"Chat history loaded from {filepath}")
        except Exception as e:
            self.logger.error(f"Error loading chat history: {e}")
            self.chat_history = []  # Reset to empty history on error

async def main():
    """Example usage of OllamaClient with chat history"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    client = OllamaClient(config_path="config.json")
    
    try:
        # Process multiple images to build up chat history
        for i in range(3):
            response = await client.process_image("camera_output/color_frame.jpg")
            print(f"\nResponse {i+1}:")
            print(json.dumps(response, indent=2))
            
        # Save chat history
        client.save_chat_history("chat_history.json")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())