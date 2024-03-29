import os
import paramiko
from datetime import datetime

destination_path = '/home/alex/rig1/projects/pc/rover/world_model/data/'

def send_file(host, username, password, local_file, remote_file):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password)
    sftp = ssh.open_sftp()
    sftp.put(local_file, remote_file)
    sftp.close()
    ssh.close()

for filename in ['servo.npy', 'depth.npy']:
    print(datetime.now(), 'Sending', filename)
    send_file(
        host='192.168.1.23',
        username=os.environ.get('SFTP_USER',''),
        password=os.environ.get('SFTP_PASSWORD',''),
        local_file=filename,
        remote_file=destination_path+filename
        )

print(datetime.now(), 'files sent')