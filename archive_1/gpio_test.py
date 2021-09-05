import sys

import Jetson.GPIO as GPIO
import time

def stepperTurnOff():
    GPIO.output(stepper_pin_a, GPIO.LOW)
    GPIO.output(stepper_pin_b, GPIO.LOW)
    GPIO.output(stepper_pin_c, GPIO.LOW)
    GPIO.output(stepper_pin_d, GPIO.LOW)

def stepperSet(stepperCurrentLevel):
    GPIO.output(stepper_pin_a, stepperLevels[stepperCurrentLevel][0])
    GPIO.output(stepper_pin_b, stepperLevels[stepperCurrentLevel][1])
    GPIO.output(stepper_pin_c, stepperLevels[stepperCurrentLevel][2])
    GPIO.output(stepper_pin_d, stepperLevels[stepperCurrentLevel][3])

stepper_pin_a = 11
stepper_pin_b = 12
stepper_pin_c = 15
stepper_pin_d = 16

GPIO.setmode(GPIO.BOARD)
GPIO.setup(stepper_pin_a, GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(stepper_pin_b, GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(stepper_pin_c, GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(stepper_pin_d, GPIO.OUT, initial=GPIO.HIGH)

stepperTurnOff()
stepperCurrentLevel=0

hi=GPIO.HIGH
lo=GPIO.LOW
stepperLevels=[
  [hi,lo,lo,lo],
  [hi,lo,hi,lo],
  [lo,lo,hi,lo],
  [lo,hi,hi,lo],
  [lo,hi,lo,lo],
  [lo,hi,lo,hi],
  [lo,lo,lo,hi],
  [hi,lo,lo,hi]
];

#main
print("input command:")
print("0 - exit")
print("1 - left")
print("2 - right")
cmd=int(input())
while cmd!=0:
	for i in range(500):
		stepperSet(stepperCurrentLevel)
		if cmd==1:
			stepperCurrentLevel-=1
		else:
			stepperCurrentLevel+=1
		if stepperCurrentLevel>7:
			stepperCurrentLevel=0
		else:
			if stepperCurrentLevel<0:
				stepperCurrentLevel=7
		time.sleep(0.005)
	#print(encoder_position_current)
	stepperTurnOff()
	cmd=int(input())
print("cleanup")
GPIO.cleanup()
