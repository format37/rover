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
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685


# enable logging
logging.basicConfig(level=logging.INFO)


def text_davinci(prompt, stop_words):
    # read token from file openai.token
    with open('openai.token', 'r') as f:
        token = f.read()
        # remove newline character
        token = token[:-1]

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
    # config.enable_stream(rs.stream, 0, 1920, 1080, rs.format.bgr8, 30)
    # config.enable_stream(rs.stream, 640, 480, rs.format.bgr8, 30)
    # optimize for low light
    config.enable_stream(
        stream_type = rs.stream.color,
        width = 1920,
        height = 1080,
        format = rs.format.rgba8,
        framerate = 30
        )
    # config.enable_stream(rs.stream, 0, 1920, 1080, rs.format.bgr8, 30)
    pipeline.start(config)
    frames = pipeline.wait_for_frames()
    color_frame = frames.get_color_frame()
    color_image = np.asanyarray(color_frame.get_data())
    pipeline.stop()
    return color_image


def move_head(kit, answer, last_head_position):
    head_delay = 0.01
    logging.info('Move head cmd: '+answer)
    if 'look ahead' in answer:
        new_head_position = 90
    elif 'look left' in answer:
        new_head_position = 180
    elif 'look right' in answer:
        new_head_position = 0
    else:
        logging.info('No head movement')
        return last_head_position
        # logging.info('Error. Unknown action: <<=['+answer+']=>>')
        # last_head_position = move_head(kit, '[look ahead]', last_head_position)
        # exit()
    min_pos = min(last_head_position, new_head_position)
    max_pos = max(last_head_position, new_head_position)
    for i in range(min_pos, max_pos):
        if last_head_position < new_head_position:
            kit.servo[0].angle = i
        else:
            kit.servo[0].angle = max_pos+min_pos-i
        time.sleep(head_delay)
    last_head_position = new_head_position
    return new_head_position


def set_track(pca, track, speed, direction):
	if speed>0:
		frequency = speed*2300
		direction = direction*0xffff
		pca[track].frequency = int(frequency)
		pca[track].channels[1].duty_cycle = int(direction)
		pca[track].channels[0].duty_cycle = 0x7fff  #go
	else:
		pca[track].channels[0].duty_cycle = 0       #stop


def move_tracks(pca, answer):
    default_speed = 0.07
    delay = 4
    if 'move ahead' in answer:
        # tracks go front
        set_track(pca, track = 0, speed = default_speed, direction = 0)
        set_track(pca, track = 1, speed = default_speed, direction = 1)
    elif 'move backward' in answer:
        # tracks go back
        set_track(pca, track = 0, speed = default_speed, direction = 1)
        set_track(pca, track = 1, speed = default_speed, direction = 0)
    elif 'turn right' in answer:
        # tracks go left
        set_track(pca, track = 0, speed = default_speed, direction = 0)
        set_track(pca, track = 1, speed = default_speed, direction = 0)
    elif 'turn left' in answer:
        # tracks go right
        set_track(pca, track = 0, speed = default_speed, direction = 1)
        set_track(pca, track = 1, speed = default_speed, direction = 1)
    else:
        logging.info('No track movement')
        return

    time.sleep(delay)
    # stop
    set_track(pca, track = 0, speed = 0, direction = 0)
    set_track(pca, track = 1, speed = 0, direction = 0)


def main():
    life_length = 2
    total_tokens = 0

    # read prompt from json file
    with open('prompt.json', 'r') as f:
        config = json.load(f)
        prompt_file = config['prompt_file']
        stop_words = config['stop_words']
    with open(prompt_file, 'r') as f:
        prompt = f.read()

    # Tracks init
    i2c_bus = busio.I2C(SCL, SDA)
    pca = [
        PCA9685(i2c_bus,address=0x40),
        PCA9685(i2c_bus,address=0x41)
        ]

    # Head servo
    kit = ServoKit(channels=16, address=0x42)
    last_head_position = 90

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
        r = requests.post(url, files=files)
        description = json.loads(r.text)['description']
        # remove first two symbols from description
        description = description[2:]
        # remove last 2 symbols from description
        description = description[:-2]
        logging.info('I see: '+description)
        prompt += '\n'+'I see: '+description+'\n'

        # Thinking about reaction
        davinchi_response = text_davinci(str(prompt), stop_words)
        answer = davinchi_response['choices'][0]['text']
        # replace the '\n' symbol
        answer = answer.replace('\n', '')
        logging.info('Openai answer: ['+str(answer)+']')
        tokens_spent = int(davinchi_response['usage']['total_tokens'])
        total_tokens += tokens_spent
        logging.info('Tokens spent: <<=[ '+str(tokens_spent)+' ]==>>')
        prompt = prompt + answer
        if total_tokens>10000:
            logging.info('Tokens limit reached. Exit.')
            exit()

        # Reaction: Move tracks
        move_tracks(pca, answer)

        # Reaction: Head direction
        last_head_position = move_head(kit, answer, last_head_position)

        life_length -= 1
        logging.info(str(dt.now())+': Life length: '+str(life_length))

    # final movement
    move_head(kit, '[look ahead]', last_head_position)
    logging.info('Life log:\n'+prompt)
    logging.info('Total tokens spent: '+str(total_tokens))


if __name__ == '__main__':
    main()
