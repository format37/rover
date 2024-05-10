# import requests
# import logging
# import json
import os

def main():
    filename = 'output.wav'
    # Play
    os.system('aplay '+filename+' --device=plughw:CARD=Device,DEV=0')


if __name__ == '__main__':
    main()
