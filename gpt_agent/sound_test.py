# https://www.waveshare.com/wiki/Audio_Card_for_Jetson_Nano
import os
import logging

logger = logging.getLogger(__name__)

# beep linux
# os.system('play -nq -t alsa synth {} sine {}'.format(0.1, 1000))

# Recording
# arecord -D plughw:2,0 -f S16_LE -r 48000 -c 2 test.wav
logger.info('Recording 5 seconds...')
os.system('arecord test.wav --device=sysdefault:CARD=Device -f S16_LE -r 48000 -c 2 --duration=5')

# Playing
logger.info('Playing')
os.system('aplay test.wav --device=plughw:CARD=Device,DEV=0')
