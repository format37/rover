import time
from adafruit_servokit import ServoKit

# servo init
kit = ServoKit(channels=16, address=0x42)

def move_head(answer, last_head_position):
        head_delay = 0.1
        print(answer)
        if answer == 'Look front':
                new_head_position = 0
        elif answer == 'Look left':
                new_head_position = 180
        elif answer == 'Look right':
                new_head_position = 90
        min_pos = min(last_head_position, new_head_position)
        max_pos = max(last_head_position, new_head_position)
        for i in range(min_pos, max_pos):
                if last_head_position < new_head_position:
                        kit.servo[0].angle = i
                else:
                        kit.servo[0].angle = max_pos-i
                time.sleep(head_delay*(max_pos-min_pos)/90)
        last_head_position = new_head_position
        return new_head_position

# delay = 0.01
"""print('90,180')
for i in range(90,180):
	kit.servo[0].angle = i
	time.sleep(delay)

print('0,180')
for i in range(0,180):
        kit.servo[0].angle = 180-i
        time.sleep(delay)

print('0,90')
for i in range(0,90):
        kit.servo[0].angle = i
        time.sleep(delay)
"""
last_head_position = 90
last_head_position = move_head('Look left', last_head_position)
last_head_position = move_head('Look front', last_head_position)
# last_head_position = move_head('Look right', last_head_position)
# last_head_position = move_head('Look left', last_head_position)
# last_head_position = move_head('Look right', last_head_position)
# last_head_position = move_head('Look front', last_head_position)

print('stop')
