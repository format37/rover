import requests
import logging
import json
import os

logger = logging.getLogger(__name__)

def tts(tts_text, filename='tts.wav'):
    # Read settings
    with open('settings.json') as f:
        settings = json.load(f)
        tts_server = settings['tts_server']
    # https://cloud.google.com/text-to-speech/docs/voices
    # https://cloud.google.com/text-to-speech
    logger.info('tts: '+tts_text)
    data = {
        'text':tts_text,
        'language':'en-US',
        'model':'en-US-Neural2-I',
        'speed':1
    }
    response = requests.post(tts_server+'/inference', json=data)
    logger.info('Response: '+str(response.status_code))
    # Save response as audio file
    with open(filename, "wb") as f:
        f.write(response.content)
    logger.info('File saved: '+filename)
    # Convert
    os.system('ffmpeg -y -i '+filename+' -ar 48000 -ab 768k '+filename)
    # Play
    os.system('aplay '+filename+' --device=plughw:CARD=Device,DEV=0')


def main():
    # Transcribe
    tts('Hi, glad to meet you')


if __name__ == '__main__':
    main()
