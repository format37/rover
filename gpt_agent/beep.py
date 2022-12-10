import os
# beep linux
# os.system('play -nq -t alsa synth {} sine {}'.format(0.1, 1000))
os.system('aplay ru.wav --device=plughw:CARD=Device,DEV=0')
