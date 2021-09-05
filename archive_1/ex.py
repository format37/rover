import RPi.GPIO as GPIO
import time

port=12

GPIO.setmode(GPIO.BOARD)
GPIO.setup(port, GPIO.OUT, initial=GPIO.LOW)

try:
	while(1):
		print('hi')
		GPIO.output(port, GPIO.LOW)
		time.sleep(2)
		print('lo')
		GPIO.output(port, GPIO.HIGH)
		time.sleep(2)
except KeyboardInterrupt: # If there is a KeyboardInterrupt (when you press ctrl+c), exit the program and cleanup
    print("Cleaning up!")
    GPIO.cleanup()
