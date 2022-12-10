import requests
import logging
import json
import os

logger = logging.getLogger(__name__)

def tts(tts_text, filename):
    # Read settings
    with open('settings.json') as f:
        settings = json.load(f)
        tts_server = settings['tts_server']

    # data={'text': tts_text}
    # request_str = json.dumps(data)
    # https://cloud.google.com/text-to-speech/docs/voices
    # https://cloud.google.com/text-to-speech
    logger.info('tts: '+tts_text)
    data = {
        'text':tts_text,
        'language':'en-US',
        'model':'en-US-Neural2-F',
        'speed':1
    }
    response = requests.post(tts_server+'/inference', json=data)
    # Save response as audio file
    with open(filename, "wb") as f:
        f.write(response.content)
    logger.info('File saved: '+filename)

def main():
    filename = 'test.wav'
    # Transcribe
    tts('Hello world', filename)
    # Play
    os.system('aplay '+filename+' --device=plughw:CARD=Device,DEV=0')


if __name__ == '__main__':
    main()
