#!/usr/bin/env python3
#ROS
import rospy
from std_msgs.msg import String
from geometry_msgs.msg import Twist
#Adafruit PWM
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
#TB6560-V2
import RPi.GPIO as gpio

def callback(data):
	global pca
	i=0
	x=data.linear.x*2300
	y=data.angular.z*2300
	steppers=[
		( int(y)-int(x)  ),
		( -int(y)-int(x) )
		]
	
	frequency	= [
		abs(steppers[0]),
		abs(steppers[1])
		]
		
	direction_forward=[
		0xffff,
		0
		]
	direction_backward=[
		0,
		0xffff
		]
	
	for i in range (0,2):
		if frequency[i]>=60:
			pca[i].frequency = frequency[i]
		
		if frequency[i]>=60:
			pca[i].channels[0].duty_cycle = 0x7fff	#go
		else:
			pca[i].channels[0].duty_cycle = 0		#stop
			
		if steppers[i]>=60:
			pca[i].channels[1].duty_cycle = direction_forward[i]		#Dir+
		if steppers[i]<=-60:
			pca[i].channels[1].duty_cycle = direction_backward[i]		#dir-
		'''
		if abs(data_R)>=60:
			pca[i].channels[2].duty_cycle = 0x7fff	#R go
		else:
			pca[i].channels[2].duty_cycle = 0		#R stop

		if (data_L>=60 and data_R<=-60) or (data_R>=60 and data_L<=-60):
			if data_L<=-60:
				pca[i].channels[3].duty_cycle = 0		#R dir-
			if data_L>=60:
				pca[i].channels[3].duty_cycle = 0x7fff	#R Dir+
		else:
			if data_L<=-60:
				pca[i].channels[3].duty_cycle = 0x7fff	#R dir+
			if data_L>=60:
				pca[i].channels[3].duty_cycle = 0		#R Dir-
		'''
def listener():
	rospy.init_node('rover_node', anonymous=True)
	rospy.Subscriber('cmd_vel', Twist, callback)
	rospy.spin()

if __name__ == '__main__':
	i2c_bus = busio.I2C(SCL, SDA)	
	pca = [
		PCA9685(i2c_bus,address=0x40),
		PCA9685(i2c_bus,address=0x41)
		]
	for i in range(0,2):
		pca[i].frequency = 60
		pca[i].channels[0].duty_cycle = 0
		pca[i].channels[1].duty_cycle = 0xffff
		pca[i].channels[3].duty_cycle = 0
		pca[i].channels[4].duty_cycle = 0xffff
	print('start')
	listener()