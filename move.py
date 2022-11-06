from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
import time

default_speed = 0.05
delay = 3

def set_track(track,speed,direction):
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
cmd = ''
while cmd != 'x':
	cmd = input('cmd: ')
	if cmd == 'w':
		# tracks go front
		set_track(track = 0, speed = default_speed, direction = 0)
		set_track(track = 1, speed = default_speed, direction = 1)
	elif cmd == 's':
		# tracks go back
		set_track(track = 0, speed = default_speed, direction = 1)
		set_track(track = 1, speed = default_speed, direction = 0)
	elif cmd == 'd':
		# tracks go left
		set_track(track = 0, speed = default_speed, direction = 0)
		set_track(track = 1, speed = default_speed, direction = 0)
	elif cmd == 'a':
		# tracks go right
		set_track(track = 0, speed = default_speed, direction = 1)
		set_track(track = 1, speed = default_speed, direction = 1)

	time.sleep(delay)
	# stop
	set_track(track = 0, speed = 0, direction = 0)
	set_track(track = 1, speed = 0, direction = 0)
	print('stop')
