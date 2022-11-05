from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
import time

direction = 'f'
default_speed = 0.05
delay = 2

def set(track,speed,direction):
	if speed>0:
		frequency = speed*2300
		direction = direction*0xffff
		pca[track].frequency = int(frequency)
		pca[track].channels[1].duty_cycle = int(direction)
		pca[track].channels[0].duty_cycle = 0x7fff  #go
	else:
		pca[track].channels[0].duty_cycle = 0       #stop

# tracks init
i2c_bus = busio.I2C(SCL, SDA)
pca = [
	PCA9685(i2c_bus,address=0x40),
	PCA9685(i2c_bus,address=0x41)
	]

print('start')
if direction == 'f':
	# tracks go front
	set(track = 0, speed = default_speed, direction = 0)
	set(track = 1, speed = default_speed, direction = 1)
elif direction == 'b':
	# tracks go back
	set(track = 0, speed = default_speed, direction = 1)
	set(track = 1, speed = default_speed, direction = 0)
elif direction == 'l':
	# tracks go left
	set(track = 0, speed = default_speed, direction = 0)
	set(track = 1, speed = default_speed, direction = 0)
elif direction == 'r':
	# tracks go right
	set(track = 0, speed = default_speed, direction = 1)
	set(track = 1, speed = default_speed, direction = 1)

time.sleep(delay)
# stop
set(track = 0, speed = 0, direction = 0)
set(track = 1, speed = 0, direction = 0)
print('stop')
