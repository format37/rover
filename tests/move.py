from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
import time

speed = 0.05
delay = 3

RAMP_STEPS = 15
RAMP_TIME = 0.4  # seconds for full ramp up or down

def set_track(track, spd, direction):
    if spd > 0:
        frequency = spd * 2300
        direction = direction * 0xffff
        pca[track].frequency = int(frequency)
        pca[track].channels[1].duty_cycle = int(direction)
        pca[track].channels[0].duty_cycle = 0x7fff  # go
    else:
        pca[track].channels[0].duty_cycle = 0       # stop

def ramp(from_spd, to_spd, dir0, dir1):
    for i in range(RAMP_STEPS + 1):
        s = from_spd + (to_spd - from_spd) * i / RAMP_STEPS
        set_track(0, s, dir0)
        set_track(1, s, dir1)
        time.sleep(RAMP_TIME / RAMP_STEPS)

def move(dir0, dir1):
    ramp(0, speed, dir0, dir1)
    time.sleep(delay)
    ramp(speed, 0, dir0, dir1)
    set_track(0, 0, 0)
    set_track(1, 0, 0)
    print('stop')

# tracks init
i2c_bus = busio.I2C(SCL, SDA)
pca = [
    PCA9685(i2c_bus, address=0x40),
    PCA9685(i2c_bus, address=0x41)
]

for i in range(0, 2):
    pca[i].frequency = 60
    pca[i].channels[0].duty_cycle = 0
    pca[i].channels[1].duty_cycle = 0xffff

print('start')
print(f'speed={speed}  |  w/s/a/d=move, sp=<val>=set speed, x=exit')

cmd = ''
while cmd != 'x':
    cmd = input('cmd: ').strip()
    if cmd == 'w':
        # forward
        move(0, 1)
    elif cmd == 's':
        # backward
        move(1, 0)
    elif cmd == 'd':
        # rotate left
        move(0, 0)
    elif cmd == 'a':
        # rotate right
        move(1, 1)
    elif cmd.startswith('sp='):
        try:
            speed = float(cmd[3:])
            print(f'speed={speed}')
        except ValueError:
            print('invalid speed')
