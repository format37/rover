# https://www.waveshare.com/wiki/Audio_Card_for_Jetson_Nano
import os
import logging

logger = logging.getLogger(__name__)

# Recording
logger.info('Recording 5 seconds...')
os.system('arecord test.wav --device=plughw:CARD=Device,DEV=0 -f S16_LE -r 48000 --duration=4')

# Playing
logger.info('Playing')
os.system('aplay test.wav --device=plughw:CARD=Device,DEV=0')
