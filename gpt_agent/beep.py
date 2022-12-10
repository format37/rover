import os
# beep linux
os.system('play -nq -t alsa synth {} sine {}'.format(0.1, 1000))
