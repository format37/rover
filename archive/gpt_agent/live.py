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
import cv2
import os


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
      engine="text-davinci-003",
      prompt=prompt,
      temperature=0.8,
      max_tokens=60,
      top_p=1,
      frequency_penalty=0.5,
      presence_penalty=0,
      stop=stop_words
    )))


def camera_capture_single_nondepth_image():
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(
        stream_type = rs.stream.color,
        width = 1920,
        height = 1080,
        format = rs.format.bgr8,
        framerate = 15
        )
    pipeline.start(config)
    frames = pipeline.wait_for_frames()
    color_frame = frames.get_color_frame()
    color_image = np.asanyarray(color_frame.get_data())
    pipeline.stop()
    return color_image


def realsense_depth_median():
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(
        stream_type = rs.stream.depth,
        width = 1280,
        height = 720
        )
    pipeline.start(config)
    frames = pipeline.wait_for_frames()
    depth_frame = frames.get_depth_frame()
    depth_image = np.asanyarray(depth_frame.get_data())
    pipeline.stop()
    return np.median(depth_image)


def move_head(kit, answer, last_head_position):
    head_delay = 0.01
    logging.info('Move head cmd: '+answer)
    if 'look ahead' in answer:
        new_head_position = 90
        logging.info('HEAD: Looking ahead.')
    elif 'look left' in answer:
        new_head_position = 180
        logging.info('HEAD: Looking left.')
    elif 'look right' in answer:
        new_head_position = 0
        logging.info('HEAD: Looking right.')
    else:
        new_head_position = 90
        logging.info('HEAD: No head movement. Looking ahead.')

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
    logging.info('Move tracks cmd: '+answer)
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


def final_movement(kit, prompt, last_head_position, total_tokens):
    move_head(kit, '[look ahead]', last_head_position)
    logging.info('Life log:\n*'+prompt+'*')
    logging.info('Total tokens spent: '+str(total_tokens))


def prompt_json_short(prompt):
    # find position of last {
    last_bracket = prompt.rfind('{')
    # remove all after last { including { and put to proto
    proto = prompt[:last_bracket-1]
    # find latest comma
    last_comma = proto.rfind(',')
    # remove last comma
    proto = proto[:last_comma]
    latest_phrase = 'Here are my latest interaction batches in machine readable json format:'
    # find the final position of the latest_phrase
    latest_phrase_final_pos = proto.rfind(latest_phrase)+len(latest_phrase)
    # remove all before the latest_phrase including the latest_phrase
    proto = proto[latest_phrase_final_pos:]
    logging.info('Proto JSON: '+str(proto+'\n]'))
    return proto+'\n]'


def prompt_json_full(prompt):
    latest_phrase = 'Here are my latest interaction batches in machine readable json format:'
    # find the final position of the latest_phrase
    latest_phrase_final_pos = prompt.rfind(latest_phrase)+len(latest_phrase)
    # remove all before the latest_phrase including the latest_phrase
    logging.info('Prompt JSON: '+str(prompt[latest_phrase_final_pos:]))
    return prompt[latest_phrase_final_pos:]


def remove_closers(prompt):
    # find position of last ]
    last_bracket = prompt.rfind(']')
    # remove all after last ] including ] and put to proto
    proto = prompt[:last_bracket-1]
    return proto


def tts(tts_text, filename='tts.wav'):
    # Read settings
    with open('settings.json') as f:
        settings = json.load(f)
        tts_server = settings['tts_server']
    # https://cloud.google.com/text-to-speech/docs/voices
    # https://cloud.google.com/text-to-speech
    logging.info('tts: '+tts_text)
    data = {
        'text':tts_text,
        'language':'en-US',
        'model':'en-US-Neural2-I',
        'speed':1
    }
    response = requests.post(tts_server+'/inference', json=data)
    logging.info('Response: '+str(response.status_code))
    # Save response as audio file
    with open(filename, "wb") as f:
        f.write(response.content)
    logging.info('File saved: '+filename)
    # Convert
    os.system('ffmpeg -y -i '+filename+' -ar 48000 -ab 768k '+filename)
    # Play
    os.system('aplay '+filename+' --device=plughw:CARD=Device,DEV=0')


def main():
    life_length = 10
    total_tokens = 0

    # read prompt from json file
    with open('prompt.json', 'r') as f:
        config = json.load(f)
        prompt_file = config['prompt_file']
        # stop_words = config['stop_words']
        stop_words = ['"']
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
        # === See: Look to the world
        color_image = camera_capture_single_nondepth_image()
        # normalize image to overcome low light
        color_image = cv2.normalize(color_image, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        # convert to jpeg
        img = Image.fromarray(color_image, 'RGB')
        path = 'color.jpg'
        img.save(path)
        # === Obstruction distance
        obstruction_distance = realsense_depth_median()
        obstruction_distance = round(obstruction_distance, 2)
        logging.info('Obstruction distance: '+str(obstruction_distance))

        # === Describe the world
        # Read settings
        with open('settings.json') as f:
            settings = json.load(f)
            image2text_server = settings['image2text_server']
        url = image2text_server+'/request'
        files = {'file': open(path, 'rb')}
        r = requests.post(url, files=files)
        description = json.loads(r.text)['description']
        # remove first two symbols from description
        description = description[2:]
        # remove last 2 symbols from description
        description = description[:-2]
        
        logging.info('== see: '+description)
        prompt += '\n'+'        "see": "'+description+'",'
        logging.info('== obstruction distance: '+str(obstruction_distance))
        prompt += '\n'+'        "obstruction_distance": '+str(obstruction_distance)+','
        
        # === Think
        prompt += '\n'+'        "my_thoughs": "'
        stop_words = ['"']
        davinchi_response = text_davinci(str(prompt), stop_words)
        answer = davinchi_response['choices'][0]['text']
        logging.info('Think openai answer: '+str(answer))
        tokens_spent = int(davinchi_response['usage']['total_tokens'])
        total_tokens += tokens_spent
        logging.info('Tokens spent: <<=[ '+str(tokens_spent)+' ]==>>')
        prompt = prompt + answer

        # === Speech
        prompt += '",'+'\n'+'        "my_speech": "'
        stop_words = ['"']
        davinchi_response = text_davinci(str(prompt), stop_words)
        answer = davinchi_response['choices'][0]['text']
        logging.info('Think openai answer: '+str(answer))
        tokens_spent = int(davinchi_response['usage']['total_tokens'])
        total_tokens += tokens_spent
        logging.info('Tokens spent: <<=[ '+str(tokens_spent)+' ]==>>')
        prompt = prompt + answer
        if len(str(answer).replace('"','')):
            tts(answer)
        
        # === Action
        stop_words = ['"']
        prompt += '",'+'\n'+'        "my_action": ["'
        davinchi_response = text_davinci(str(prompt), stop_words)
        answer = davinchi_response['choices'][0]['text']
        logging.info('Action openai answer: '+str(answer))
        tokens_spent = int(davinchi_response['usage']['total_tokens'])
        total_tokens += tokens_spent
        logging.info('Tokens spent: <<=[ '+str(tokens_spent)+' ]==>>')
        prompt = prompt + answer + '"]}]'

        if total_tokens>30000:
            # if True:
            final_movement(kit, prompt, last_head_position, total_tokens)
            logging.info('Tokens limit reached. Exit.')
            exit()
        # logging.info('Prompt: **'+prompt+'**')
        # try:
        res = prompt_json_full(prompt)
        # answer = str(json.loads(res))

        life_log_json = json.loads(res)
        my_action = str(life_log_json[-1]['my_action'])

        # === Reaction: Move tracks
        move_tracks(pca, my_action)

        # === Reaction: Head direction
        last_head_position = move_head(kit, my_action, last_head_position)

        # === prepare log for continuation
        prompt = remove_closers(prompt)+'\n},\n    {'

        life_length -= 1
        logging.info(str(dt.now())+': Life length: '+str(life_length))
    final_movement(kit, prompt, last_head_position, total_tokens)


if __name__ == '__main__':
    main()
