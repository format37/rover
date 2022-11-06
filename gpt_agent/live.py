import logging
from datetime import datetime as dt
import json
import openai
import pyrealsense2 as rs
import numpy as np
import requests
from datetime import datetime as dt
from PIL import Image
import time
from adafruit_servokit import ServoKit


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
      max_tokens=50,
      top_p=1,
      frequency_penalty=0,
      presence_penalty=0.6,
      stop=stop_words
    )))


def camera_capture_single_nondepth_image():
	pipeline = rs.pipeline()
	config = rs.config()
	config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
	pipeline.start(config)
	frames = pipeline.wait_for_frames()
	color_frame = frames.get_color_frame()
	color_image = np.asanyarray(color_frame.get_data())
	pipeline.stop()
	return color_image


def move_head(kit, answer, last_head_position):
    head_delay = 0.01
    print(answer)
    if '[I look ahead]' in answer:
        new_head_position = 90
    elif '[I look to the left]' in answer:
        new_head_position = 180
    elif '[I look to the rigth]' in answer:
        new_head_position = 0
    else:
        logging.info(str(dt.now())+': Unknown action: '+answer)
        last_head_position = move_head(kit, '[I look ahead]', last_head_position)
        exit()
    min_pos = min(last_head_position, new_head_position)
    max_pos = max(last_head_position, new_head_position)
    print(answer, last_head_position, new_head_position)
    print(min_pos, max_pos)
    for i in range(min_pos, max_pos):
        if last_head_position < new_head_position:
            kit.servo[0].angle = i
        else:
            kit.servo[0].angle = max_pos+min_pos-i
        time.sleep(head_delay)
    last_head_position = new_head_position
    return new_head_position


def main():
    life_length = 3
    total_tokens = 0

    # read prompt from json file
    with open('prompt.json', 'r') as f:
        config = json.load(f)
        prompt_file = config['prompt_file']
        stop_words = config['stop_words']
    with open(prompt_file, 'r') as f:
        prompt = f.read()

    # Head servo
    kit = ServoKit(channels=16, address=0x42)
    last_head_position = 90
    head_delay = 3

    while life_length>0:
        # Look to the world        
        color_image = camera_capture_single_nondepth_image()
        # convert to jpeg
        img = Image.fromarray(color_image, 'RGB')
        path = 'color.jpg'
        img.save(path)

        # Describe the world
        url = 'http://192.168.1.102:20000/request'
        files = {'file': open(path, 'rb')}
        start_time = dt.now()
        print(start_time)
        logging.info(str(start_time)+': Sending image to server')
        r = requests.post(url, files=files)
        description = json.loads(r.text)['description']
        # remove first two symbols from description
        description = description[2:]
        # remove last 2 symbols from description
        description = description[:-2]
        end_time = dt.now()
        logging.info(str(end_time)+': Image description: '+description)
        logging.info(str(end_time)+': Received response from server')
        logging.info(str(end_time - start_time)+': Time taken to send image and receive response')
        prompt += '\n'+'I see: '+description+'\n'

        # Thinking about reaction
        logging.info(str(dt.now())+' call openai generator')
        davinchi_response = text_davinci(str(prompt), stop_words)
        answer = davinchi_response['choices'][0]['text']
        logging.info(str(dt.now())+' openai answer: ['+str(answer)+']')
        tokens_spent = int(davinchi_response['usage']['total_tokens'])
        total_tokens += tokens_spent
        logging.info(str(dt.now())+' Tokens spent: <<=[ '+str(tokens_spent)+' ]==>>')
        prompt = prompt + answer

        logging.info(str(dt.now())+': Prompt: '+prompt)

        # Doing the reaction
        # if not '[Do nothing]' in answer:
        last_head_position = move_head(kit, answer, last_head_position)

        life_length -= 1
        logging.info(str(dt.now())+': Life length: '+str(life_length))

    # final movement
    move_head(kit, '[I look ahead]', last_head_position)


if __name__ == '__main__':
    main()
