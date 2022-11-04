import time
from adafruit_servokit import ServoKit

# servo init
kit = ServoKit(channels=16, address=0x42)

delay = 0.01
print('90,180')
for i in range(90,180):
	kit.servo[1].angle = i
	time.sleep(delay)

print('0,180')
for i in range(0,180):
        kit.servo[1].angle = 180-i
        time.sleep(delay)

print('0,90')
for i in range(0,90):
        kit.servo[1].angle = i
        time.sleep(delay)

print('stop')
