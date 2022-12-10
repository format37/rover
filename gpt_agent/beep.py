# https://www.waveshare.com/wiki/Audio_Card_for_Jetson_Nano
import os
# beep linux
# os.system('play -nq -t alsa synth {} sine {}'.format(0.1, 1000))

# Recording
# arecord -D plughw:2,0 -f S16_LE -r 48000 -c 2 test.wav
os.system('arecord --device=plughw:CARD=Device,DEV=0 -f S16_LE -r 48000 -c 2 test.wav')
# Playing
os.system('aplay test.wav --device=plughw:CARD=Device,DEV=0')
