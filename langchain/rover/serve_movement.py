from flask import Flask, jsonify, request
import logging
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
import time
from adafruit_servokit import ServoKit

app = Flask(__name__)

# enable logging
logging.basicConfig(level=logging.INFO)

def set(pca, track,speed,direction):
	if speed>0:
		frequency = speed*2300
		direction = direction*0xffff
		pca[track].frequency = int(frequency)
		pca[track].channels[1].duty_cycle = int(direction)
		pca[track].channels[0].duty_cycle = 0x7fff  #go
	else:
		pca[track].channels[0].duty_cycle = 0       #stop

@app.route('/test', methods=['GET'])
def test():
    return jsonify({'message': 'ok'})

@app.route('/move_track', methods=['POST'])
def move_track():
    data = request.get_json()
    left_speed = data['left_speed']
    right_speed = data['right_speed']
    default_speed = 0.1

    # tracks init
    logging.info('Init tracks')
    i2c_bus = busio.I2C(SCL, SDA)
    pca = [
        PCA9685(i2c_bus,address=0x40),
        PCA9685(i2c_bus,address=0x41)
        ]
    # # servo init
    # logging.info('Init servo')
    # kit = ServoKit(channels=16, address=0x42)
    # tracks go front
    logging.info('tracks go front')
    set(pca, track = 0, speed = default_speed, direction = 0)
    set(pca, track = 1, speed = default_speed, direction = 1)
    time.sleep(1)
    # tracks stop
    logging.info('tracks stop')
    set(pca, track = 0, speed = 0, direction = 1)
    set(pca, track = 1, speed = 0, direction = 1)

    logging.info('done')

    return jsonify({'message': 'done'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)