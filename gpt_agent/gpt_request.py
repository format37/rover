import logging
from datetime import datetime as dt
import json
import openai

# enable logging
logging.basicConfig(level=logging.INFO)


def text_davinci(prompt, stop_words):
    # read token from file openai.token
    with open('openai.token', 'r') as f:
        token = f.read()
        # remove newline character
        token = token[:-1]
        print(token)

    openai.api_key = token
    return json.loads(str(openai.Completion.create(
      engine="text-davinci-002",
      prompt=prompt,
      temperature=0.9,
      max_tokens=150,
      top_p=1,
      frequency_penalty=0,
      presence_penalty=0.6,
      stop=stop_words
    )))


logging.info(str(dt.now())+' call_voice.openai conversation')
# read prompt from json file
with open('prompt.json', 'r') as f:
  config = json.load(f)
  prompt = config['prompt']
  stop_words = config['stop_words']
davinchi_response = text_davinci(str(prompt), stop_words)
answer = davinchi_response['choices'][0]['text']
logging.info(str(dt.now())+' call_voice.openai conversation answer: '+str(answer))
total_tokens = davinchi_response['usage']['total_tokens']
logging.info(str(dt.now())+' call_voice.openai conversation total_tokens: '+str(total_tokens))
