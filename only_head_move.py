import time
from adafruit_servokit import ServoKit

# servo init
kit = ServoKit(channels=16, address=0x42)

def move_head(answer, last_head_position):
        head_delay = 0.01
        print(answer)
        if '[look ahead]' in answer:
                new_head_position = 90
        elif '[look left]' in answer:
                new_head_position = 180
        elif '[look right]' in answer:
                new_head_position = 0
        min_pos = min(last_head_position, new_head_position)
        max_pos = max(last_head_position, new_head_position)
        print(answer, last_head_position, new_head_position)
        print(min_pos, max_pos)
        for i in range(min_pos, max_pos):
                if last_head_position < new_head_position:
                        kit.servo[0].angle = i
                else:
                        kit.servo[0].angle = max_pos+min_pos-i
                time.sleep(head_delay)
        last_head_position = new_head_position
        return new_head_position

last_head_position = 90
last_head_position = move_head('[look left]', last_head_position)
last_head_position = move_head('[look right]', last_head_position)
last_head_position = move_head('[look ahead]', last_head_position)

print('stop')
