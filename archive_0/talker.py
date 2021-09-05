# export ROS_MASTER_URI=http://ip_robot:11311
# export ROS_IP=ip_comp
import rospy
from std_msgs.msg import String
from geometry_msgs.msg import Twist

def msg_off(vel_msg):
	vel_msg = Twist()
	vel_msg.linear.x=0
	vel_msg.linear.y = 0
	vel_msg.linear.z = 0
	vel_msg.angular.x = 0
	vel_msg.angular.y = 0
	vel_msg.angular.z = 0
	return vel_msg

def talker():
	pub = rospy.Publisher('cmd_vel', Twist, queue_size=10)
	rospy.init_node('rover_node', anonymous=True)
	rate = rospy.Rate(0.5) # 10hz
	vel_msg = Twist()
	vel_msg.linear.x = 1
	vel_msg.linear.y = 1
	vel_msg.linear.z = 0
	vel_msg.angular.x = 0
	vel_msg.angular.y = 1
	vel_msg.angular.z = 0
	packet_count=1
	while not rospy.is_shutdown():
		log_msg=str(vel_msg.linear.x)+' : '+str(vel_msg.linear.y)+' s '+str(vel_msg.angular.x)+' : '+str(vel_msg.angular.y)
		rospy.loginfo(log_msg)
		pub.publish(vel_msg)
		rate.sleep()
		packet_count-=1
		if packet_count<=0:
			break
	vel_msg=msg_off(vel_msg)
	log_msg=str(vel_msg.linear.x)+' : '+str(vel_msg.linear.y)+' s '+str(vel_msg.angular.x)+' : '+str(vel_msg.angular.y)
	rospy.loginfo(log_msg)
	pub.publish(vel_msg)

if __name__ == '__main__':
	try:
		talker()
	except rospy.ROSInterruptException:
		pass

