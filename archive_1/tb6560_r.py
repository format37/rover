from time import sleep
import RPi.GPIO as gpio

frequency=.0005*9
steps=100*4

#DIR=11
#STEP=13
#EN=15

DIR=37
STEP=35
EN=33

gpio.setmode(gpio.BOARD)
gpio.setup(DIR, gpio.OUT)
gpio.setup(STEP, gpio.OUT)
gpio.setup(EN, gpio.OUT)

gpio.output(DIR,gpio.HIGH)
sleep(1)
gpio.output(EN,gpio.LOW)
sleep(1)

# Main body of code
try:
    while(True):

        for x in range(steps):
            gpio.output(STEP,gpio.HIGH)
            sleep(frequency)
            gpio.output(STEP,gpio.LOW)
            sleep(frequency)

        gpio.output(EN,gpio.HIGH)
        gpio.output(DIR,gpio.LOW)
        print('low')
        sleep(1)
        gpio.output(EN,gpio.LOW)

        for x in range(steps):
            gpio.output(STEP,gpio.HIGH)
            sleep(frequency)
            gpio.output(STEP,gpio.LOW)
            sleep(frequency)

        gpio.output(EN,gpio.HIGH)
        gpio.output(DIR,gpio.HIGH)
        print('hi')
        sleep(1)
        gpio.output(EN,gpio.HIGH)

        while(True):
            a=0;

except KeyboardInterrupt: # If there is a KeyboardInterrupt (when you press ctrl+c), exit the program and cleanup
    print("ex: Cleaning up!")
    gpio.cleanup()

print("Cleaning up!")
gpio.cleanup()
