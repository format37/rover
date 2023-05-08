import pyrealsense2 as rs
import numpy as np
import logging
import time
import os
import json

# enable logging
logging.basicConfig(level=logging.INFO)

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
    if 'photo ahead' in answer:
        new_head_position = 90
        logging.info('HEAD: Looking ahead.')
    elif 'photo left' in answer:
        new_head_position = 180
        logging.info('HEAD: Looking left.')
    elif 'photo right' in answer:
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
    elif 'move right' in answer:
        # tracks go left
        set_track(pca, track = 0, speed = default_speed, direction = 0)
        set_track(pca, track = 1, speed = default_speed, direction = 0)
    elif 'move left' in answer:
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


def extract_answer(structure):
    if not structure or not structure[0]:
        return None

    first_element = structure[0]

    if len(first_element) < 2:
        return None

    answer = first_element[1]
    return answer[-1]