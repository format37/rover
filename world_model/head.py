import time
from adafruit_servokit import ServoKit

# servo init
kit = ServoKit(channels=16, address=0x42)

print('start')
delay = 0.1
for i in range(100,180):
	kit.servo[0].angle = i
	time.sleep(delay)

for i in range(0,180):
        kit.servo[0].angle = 180-i
        time.sleep(delay)

for i in range(0,100):
        kit.servo[0].angle = i
        time.sleep(delay)

print('stop')
