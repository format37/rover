from abc import ABC, abstractmethod
import logging
import json
import base64
import aiohttp
import aiofiles
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
from openai import AsyncOpenAI
import os
import re

@dataclass
class BaseLLMConfig:
    """Base configuration for LLM clients"""
    model: str
    log_directory: str = "logs"
    max_history_size: int = 2
    timeout: float = 30.0
    max_response_size: int = 1024 * 1024  # 1MB
    prompt_path: str = "prompts/robot_prompt.txt"

@dataclass
class OllamaConfig(BaseLLMConfig):
    """Configuration for Ollama client"""
    ollama_api_url: str = "http://localhost:11434/api/generate"

@dataclass
class OpenAIConfig(BaseLLMConfig):
    """Configuration for OpenAI client"""
    api_key: Optional[str] = None

class BaseLLMClient(ABC):
    """Abstract base class for LLM clients"""
    
    def __init__(self, config_path: str = "config.json"):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config = self._load_config(config_path)
        self.base_prompt_template = self._load_prompt_template()
        self.chat_history = []
        
        # Create logs directory
        self.log_dir = Path(self.config.log_directory)
        self.log_dir.mkdir(exist_ok=True)

    @abstractmethod
    async def process_image(self, image_path: str, custom_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Process an image and return response"""
        pass

    @abstractmethod
    def _load_config(self, config_path: str) -> BaseLLMConfig:
        """Load configuration from file"""
        pass

    def _filter_config_data(self, config_data: Dict[str, Any], config_class: type) -> Dict[str, Any]:
        """Filter configuration data to only include fields defined in the config class"""
        from dataclasses import fields
        valid_fields = {field.name for field in fields(config_class)}
        return {k: v for k, v in config_data.items() if k in valid_fields}

    async def encode_image(self, image_path: str) -> str:
        """Encode image to base64"""
        async with aiofiles.open(image_path, "rb") as image_file:
            content = await image_file.read()
            return base64.b64encode(content).decode('utf-8')

    def _load_prompt_template(self) -> str:
        """Load prompt template from file"""
        prompt_file = Path(self.config.prompt_path)
        try:
            with open(prompt_file, 'r') as f:
                return f.read().strip()
        except Exception as e:
            self.logger.error(f"Error loading prompt template: {e}")
            raise

    async def _log_interaction(self, request_data: Dict[str, Any], response_data: Dict[str, Any], image_path: str):
        """Log interaction details"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        log_entry = {
            "timestamp": timestamp,
            "image_path": image_path,
            "request": {
                "prompt": request_data.get('prompt'),
                "model": self.config.model,
            },
            "response": response_data,
            "chat_history_length": len(self.chat_history)
        }
        
        log_file = self.log_dir / f"interaction_{timestamp}.json"
        async with aiofiles.open(log_file, 'w') as f:
            await f.write(json.dumps(log_entry, indent=2))

    def update_chat_history(self, request: Dict[str, Any], response: Dict[str, Any]):
        """Update chat history maintaining size limit"""
        self.chat_history.extend([request, response])
        max_entries = self.config.max_history_size * 2
        if len(self.chat_history) > max_entries:
            self.chat_history = self.chat_history[-max_entries:]

    def save_chat_history(self, filepath: str):
        """Save chat history to file"""
        with open(filepath, 'w') as f:
            json.dump({
                "chat_history": self.chat_history,
                "saved_at": datetime.now().isoformat(),
                "model": self.config.model
            }, f, indent=2)

    def load_chat_history(self, filepath: str):
        """Load chat history from file"""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                self.chat_history = data.get("chat_history", [])
        except Exception as e:
            self.logger.error(f"Error loading chat history: {e}")
            self.chat_history = []

class OllamaClient(BaseLLMClient):
    """Ollama-specific implementation"""
    
    def __init__(self, config_path: str = "config.json"):
        super().__init__(config_path)
        self._request_queue = asyncio.Queue()
        self._processing_lock = asyncio.Lock()
        self._request_processor_task = None

    def _load_config(self, config_path: str) -> OllamaConfig:
        config_file = Path(config_path)
        if config_file.exists():
            with open(config_file, 'r') as f:
                config_data = json.load(f)
                filtered_config = self._filter_config_data(config_data, OllamaConfig)
                return OllamaConfig(**filtered_config)
        return OllamaConfig(model="llava:34b")

    async def start(self):
        """Start request processor"""
        if self._request_processor_task is None:
            self._request_processor_task = asyncio.create_task(self._process_request_queue())

    async def stop(self):
        """Stop request processor"""
        if self._request_processor_task:
            self._request_processor_task.cancel()
            try:
                await self._request_processor_task
            except asyncio.CancelledError:
                pass
            self._request_processor_task = None

    async def process_image(self, image_path: str, custom_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Process image through Ollama"""
        future = asyncio.Future()
        await self._request_queue.put({
            'image_path': image_path,
            'prompt': custom_prompt or self._build_prompt_with_history(),
            'future': future
        })
        return await future

    async def _process_request_queue(self):
        """Process queued requests"""
        while True:
            try:
                request_data = await self._request_queue.get()
                try:
                    async with self._processing_lock:
                        response = await self._make_api_request(
                            image_path=request_data['image_path'],
                            prompt=request_data['prompt']
                        )
                    request_data['future'].set_result(response)
                except Exception as e:
                    request_data['future'].set_exception(e)
                finally:
                    self._request_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error processing request: {e}")

    async def _make_api_request(self, image_path: str, prompt: str) -> Dict[str, Any]:
        """Make Ollama API request"""
        image_base64 = await self.encode_image(image_path)
        request_data = {
            "model": self.config.model,
            "prompt": prompt,
            "images": [image_base64]
        }
        
        request_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "request",
            "image_path": image_path,
            "prompt": prompt,
            "model": self.config.model
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.ollama_api_url,
                    json=request_data,
                    timeout=self.config.timeout
                ) as response:
                    if response.status != 200:
                        raise RuntimeError(f"API request failed with status {response.status}")
                    
                    model_response = ""
                    async for line in response.content:
                        if len(model_response) > self.config.max_response_size:
                            raise RuntimeError("Response size exceeded limit")
                        
                        decoded_line = line.decode('utf-8').strip()
                        if not decoded_line:
                            continue
                        
                        json_obj = json.loads(decoded_line)
                        response_chunk = json_obj.get('response', '')
                        model_response += response_chunk
                        
                        if json_obj.get('done', False):
                            break

            clean_response = await self._clean_json_response(model_response)
            response_data = json.loads(clean_response)
            response_data["timestamp"] = datetime.now().isoformat()
            response_data["type"] = "response"
            
            await self._log_interaction(request_data, response_data, image_path)
            self.update_chat_history(request_entry, response_data)
            return response_data
            
        except Exception as e:
            error_response = {
                "timestamp": datetime.now().isoformat(),
                "type": "response",
                "error": str(e),
                "status": "failed"
            }
            self.update_chat_history(request_entry, error_response)
            await self._log_interaction(request_data, error_response, image_path)
            raise

    async def _clean_json_response(self, response: str) -> str:
        """Clean JSON response"""
        response = response.replace("```json", "").replace("```", "")
        return re.sub(r'//.*$', '', response, flags=re.MULTILINE)
    
    def _build_prompt_with_history(self) -> str:
        """Build complete prompt including chat history"""
        # Convert chat history to formatted string
        history_str = json.dumps(self.chat_history, indent=2) if self.chat_history else "[]"
        
        prompt_with_history = f"""# Your chat history is:
{history_str}
# Your system prompt:
{self.base_prompt_template}"""

        # Insert chat history into the base prompt
#         prompt_with_history = f"""You are robot. You can see, speak and move head. You have memory of your past interactions.
# Your chat history is:
# {history_str}

# The available movements are:
# - Left track: direction (0=forward, 1=backward)
# - Right track: direction (0=forward, 1=backward)
# - Head position: angle 0-180 degrees (0=full left, 90=center, 180=full right)

# Based on your memory and current observation, answer in JSON format:
# {{
#     "observations": "<describe what you see>",
#     "feelings": "<describe how you feel, considering your past experiences>",
#     "thoughts": "<describe your thinking process, referencing past events when relevant>",
#     "speech": "<what you want to say, maintaining consistency with past interactions>",
#     "movement": {{
#         "head": {{
#             "angle": <0-180>
#         }},
#         "left_track": {{
#             "direction": <0 or 1>
#         }},
#         "right_track": {{
#             "direction": <0 or 1>
#         }}
#     }}
# }}"""
        return prompt_with_history

class OpenAIClient(BaseLLMClient):
    """OpenAI-specific implementation"""
    
    def __init__(self, config_path: str = "config.json"):
        super().__init__(config_path)
        self.client = AsyncOpenAI(api_key=self.config.api_key or os.getenv('OPENAI_API_KEY'))

    def _load_config(self, config_path: str) -> OpenAIConfig:
        config_file = Path(config_path)
        if config_file.exists():
            with open(config_file, 'r') as f:
                config_data = json.load(f)
                filtered_config = self._filter_config_data(config_data, OpenAIConfig)
                return OpenAIConfig(**filtered_config)
        return OpenAIConfig(model="gpt-4-vision-preview")
    
    def _build_prompt_with_history(self) -> str:
        """Build complete prompt including chat history"""
        # Convert chat history to formatted string
        history_str = json.dumps(self.chat_history, indent=2) if self.chat_history else "[]"
        
        prompt_with_history = f"""# Your chat history is:
{history_str}
# Your system prompt:
{self.base_prompt_template}"""

#         # Insert chat history into the base prompt
#         prompt_with_history = f"""You are robot. You can see, speak and move head. You have memory of your past interactions.
# Your chat history is:
# {history_str}

# The available movements are:
# - Left track: direction (0=forward, 1=backward)
# - Right track: direction (0=forward, 1=backward)
# - Head position: angle 0-180 degrees (0=full left, 90=center, 180=full right)

# Based on your memory and current observation, answer in JSON format:
# {{
#     "observations": "<describe what you see>",
#     "feelings": "<describe how you feel, considering your past experiences>",
#     "thoughts": "<describe your thinking process, referencing past events when relevant>",
#     "speech": "<what you want to say, maintaining consistency with past interactions>",
#     "movement": {{
#         "head": {{
#             "angle": <0-180>
#         }},
#         "left_track": {{
#             "direction": <0 or 1>
#         }},
#         "right_track": {{
#             "direction": <0 or 1>
#         }}
#     }}
# }}"""
        return prompt_with_history

    async def process_image(self, image_path: str, custom_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Process image through OpenAI"""
        image_base64 = await self.encode_image(image_path)
        prompt = custom_prompt or self._build_prompt_with_history()
        
        request_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "request",
            "image_path": image_path,
            "prompt": prompt,
            "model": self.config.model
        }
        
        try:
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }],
                max_tokens=1000,
                timeout=self.config.timeout
            )
            
            response_text = response.choices[0].message.content
            self.logger.info(f"Response:\n{response_text}")
            response_data = json.loads(response_text)
            response_data["timestamp"] = datetime.now().isoformat()
            response_data["type"] = "response"
            
            await self._log_interaction(
                {"prompt": prompt, "model": self.config.model},
                response_data,
                image_path
            )
            self.update_chat_history(request_entry, response_data)
            return response_data
            
        except Exception as e:
            error_response = {
                "timestamp": datetime.now().isoformat(),
                "type": "response",
                "error": str(e),
                "status": "failed"
            }
            self.update_chat_history(request_entry, error_response)
            await self._log_interaction(
                {"prompt": prompt, "model": self.config.model},
                error_response,
                image_path
            )
            raise

def create_llm_client(config_path: str = "config.json", client_type: Optional[str] = None) -> BaseLLMClient:
    """Factory function to create appropriate LLM client"""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            if client_type is None:
                client_type = config.get('client_type', 'ollama')
    except Exception as e:
        logging.warning(f"Error reading config file: {e}. Using default client type.")
        client_type = client_type or 'ollama'
    
    if client_type.lower() == 'openai':
        return OpenAIClient(config_path)
    else:
        return OllamaClient(config_path)