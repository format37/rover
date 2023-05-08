import logging
import json
import requests
from adafruit_servokit import ServoKit
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
import cv2
from rover import (
    camera_capture_single_nondepth_image,
    realsense_depth_median,
    extract_answer
)
from PIL import Image
import base64
from datetime import datetime as dt


def main():

    # enable logging
    logging.basicConfig(level=logging.INFO)

    life_length = 1

    """# Tracks init
    logging.info('Init tracks')
    i2c_bus = busio.I2C(SCL, SDA)
    pca = [
        PCA9685(i2c_bus,address=0x40),
        PCA9685(i2c_bus,address=0x41)
        ]

    # Head servo
    logging.info('Init head servo')
    kit = ServoKit(channels=16, address=0x42)
    last_head_position = 90"""

    # Read prompt.txt
    with open('prompt.txt', 'r') as f:
        prompt = f.read()

    # Read settings
    with open('settings.json') as f:
        settings = json.load(f)
        minigpt4_server = settings['minigpt4_server'] + '/'

    logging.info('Starting rover life...')
    while life_length>0:
        # === See: Look to the world
        logging.info('Capturing RGB image...')
        color_image = camera_capture_single_nondepth_image()
        # normalize image to overcome low light
        color_image = cv2.normalize(color_image, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        # convert to jpeg
        img = Image.fromarray(color_image, 'RGB')
        path = 'color.jpg'
        img.save(path)
        
        # === Obstruction distance
        logging.info('Calculating obstruction distance...')
        obstruction_distance = realsense_depth_median()
        obstruction_distance = round(obstruction_distance, 2)
        logging.info('Obstruction distance: '+str(obstruction_distance))
        
        # === Describe the world
        with open(path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
        # base64_image = cv2.imencode('.jpg', color_image)[1].tostring()
        payload = {
                "data": [
                    f"data:image/jpeg;base64,{base64_image}",
                    "vision",
                    None
                ]
            }
        url = minigpt4_server + "run/upload_image"
        logging.info(' Uploading image to MiniGPT-4: '+str(url))
        response = requests.post(url, json=payload)
        data = response.json()["data"]
        logging.info('Sending prompt to MiniGPT-4...')
        response = requests.post(minigpt4_server + "run/ask_question", json={
                "data": [
                    prompt,
                    [["Hi","Hello"],["1 + 1","2"]],
                    None,
                ]
            }).json()
        data = response["data"]
        logging.info('Waiting for MiniGPT-4 answer...')
        response = requests.post(minigpt4_server + "run/get_answer", json={
                "data": [
                    [["hi","Hello"],["1 + 1","2"]],
                    None,
                    None,
                    1,
                    0.1,
                    8000,
                ]
            }).json()
        data = response["data"]
        reaction = extract_answer(data)
        reaction = reaction.replace('<br>','')
        logging.info('MiniGPT-4 answer: '+str(reaction))
        # actions = 

        
        
        """logging.info('== see: '+description)
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

        """
        life_length -= 1
        logging.info(str(dt.now())+': Life length: '+str(life_length))
    # final_movement(kit, prompt, last_head_position, total_tokens)


if __name__ == '__main__':
    main()
