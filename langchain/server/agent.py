import requests

rover_address = '192.168.100.17'

def test_api():
    url = f'http://{rover_address}:5000/test'
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        print('Server response:')
        print(data)
    else:
        print(f'Request failed with status code: {response.status_code}')

if __name__ == '__main__':
    test_api()