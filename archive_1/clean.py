import RPi.GPIO as gpio
DIR = 11
STEP = 13
EN=15
gpio.setmode(gpio.BOARD)
gpio.setup(DIR, gpio.OUT)
gpio.setup(STEP, gpio.OUT)
gpio.setup(EN, gpio.OUT)
print("Cleaning up!")
gpio.cleanup()
