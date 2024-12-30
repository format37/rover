import base64
import json
import requests
from pathlib import Path
from typing import Optional, Dict, Any
from asyncio import sleep
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
# Configure logging with a more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('llm_client.log')
    ]
)


class LLMClient:
    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.chat_history = []
        # Set default max history size if not in config
        if 'max_history_size' not in self.config:
            self.config['max_history_size'] = 4
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        with open(config_path) as f:
            return json.load(f)

    def _load_prompt(self) -> str:
        """Load prompt from the configured prompt file and prepend chat history."""
        # Load the base prompt
        with open(self.config['prompt_path']) as f:
            base_prompt = f.read().strip()
        
        # If there's no chat history, return just the base prompt
        if not self.chat_history:
            return base_prompt
        
        # Format the chat history
        history_text = "Ваши воспоминания:\n"
        for entry in self.chat_history:
            history_text += f"- Время: {entry.get('время', 'неизвестно')}\n"
            history_text += f"  Наблюдение: {entry['наблюдение']}\n"
            history_text += f"  Чувства: {entry['чувства']}\n"
            if entry.get('мысли'): history_text += f"  Мысли: {entry['мысли']}\n"
            if entry.get('речь'): history_text += f"  Речь: {entry['речь']}\n"
            if entry.get('движения'): history_text += f"  Движения: {json.dumps(entry['движения'], ensure_ascii=False)}\n"
            history_text += "\n"
        
        # Add current time before the task
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        history_text += f"Текущее время: {current_time}\n\n"
        history_text += "Ваша задача:\n"
        
        logger.info(f"\n# Sending prompt:\n{history_text}\n{base_prompt}\n\n")
        # Combine history with base prompt
        return f"{history_text}\n{base_prompt}"

    @staticmethod
    def _encode_image_to_base64(image_path: str) -> str:
        """Encodes an image file to a base64 string."""
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read())
            return encoded_string.decode('utf-8')

    async def process_image(self, image_path: str) -> Dict[str, Any]:
        """Process an image with the LLM model."""
        # Add timestamp at the beginning of processing
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        image_base64 = self._encode_image_to_base64(image_path)
        prompt = self._load_prompt()
        
        data = {
            "model": self.config['model'],
            "prompt": prompt,
            "images": [image_base64]
        }

        response = requests.post(
            self.config['ollama_api_url'],
            json=data,
            stream=True,
            timeout=self.config['timeout']
        )

        if response.status_code != 200:
            raise Exception(f"Request failed with status {response.status_code}: {response.text}")

        model_response = ''
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                json_obj = json.loads(decoded_line)
                model_response += json_obj.get('response', '')
                if json_obj.get('done', False):
                    break
                # Small delay to allow other async operations
                await sleep(0)

        # Log the model's response
        # logger.info(f"Raw model response:\n{model_response}")
        # Find the first { and last } positions
        start = model_response.find('{')
        end = model_response.rfind('}')
        if start != -1 and end != -1:
            # Extract just the JSON part, keeping the braces
            model_response = model_response[start:end + 1]
        logger.info(f"Processed model response:\n{model_response}")
        try:
            # Parse the response as JSON and store in history
            response_data = json.loads(model_response)
            # Add timestamp to the response data
            response_data['время'] = current_time
            # Maintain max history size by removing oldest entries
            self.chat_history.append(response_data)
            if len(self.chat_history) > self.config['max_history_size']:
                self.chat_history = self.chat_history[-self.config['max_history_size']:]
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON response: {e}")
            # Clear the chat history
            self.chat_history = []
            # Fill the response with default answers
            response_data = {
                "время": current_time,
                "наблюдение": "Мне снится сон",
                "чувства": "Я отдыхаю",
                "мысли": "",
                "речь": "",
                "движения": {}
            }            
        
        return response_data

    def save_chat_history(self) -> None:
        """Save chat history to a JSON file with current date postfix."""
        filename = f"logs/chat_history_{datetime.now().strftime('%Y%m%d')}.json"
        with open(filename, 'w') as f:
            json.dump(self.chat_history, f, indent=2)

def create_llm_client(config_path: str) -> LLMClient:
    """Factory function to create an LLMClient instance."""
    return LLMClient(config_path)

async def main():
    """Test function to demonstrate usage."""
    client = create_llm_client("config.json")
    
    for i in range(5):
        logger.info(f"\nIteration {i+1}/5")
        response = await client.process_image("camera_output/color_frame.jpg")
        logger.info(f"Наблюдение: {response['наблюдение']}")
        logger.info(f"Чувства: {response['чувства']}")
        logger.info(f"Мысли: {response['мысли']}")
        logger.info(f"Речь: {response['речь']}")
        # logger.info(f"Движения: {response['движения']}")
        client.save_chat_history()
        await asyncio.sleep(1)  # Small delay between iterations
    logger.info("End of iterations")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
