import requests

class Movement:
    def __init__(self, rover_address, port):
        self.rover_address = rover_address
        self.port = port
        self.base_url = f'http://{rover_address}:{port}'

    def test_api(self):
        url = f'{self.base_url}/test'
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            if data['message'] == 'ok':
                print('Movement API: OK')
                return True
        else:
            print(f'Request failed with status code: {response.status_code}')
            return False

    def move_head(self, pan, tilt):
        url = f'{self.base_url}/move_head'
        data = {'pan': pan, 'tilt': tilt}
        response = requests.post(url, json=data)

        if response.status_code == 200:
            print('Head movement command sent successfully.')
        else:
            print(f'Request failed with status code: {response.status_code}')

    def move_track(self, left_speed, right_speed):
        url = f'{self.base_url}/move_track'
        data = {
            'left_speed': left_speed, 
            'right_speed': right_speed
            }
        response = requests.post(url, json=data)

        if response.status_code == 200:
            print('Track movement command sent successfully.')
        else:
            print(f'Request failed with status code: {response.status_code}')

if __name__ == '__main__':
    rover_address = '192.168.100.17'
    movement_port = 5000
    movement = Movement(rover_address, movement_port)
    movement.test_api()
    movement.move_track(1, 1)
    print('Done.')