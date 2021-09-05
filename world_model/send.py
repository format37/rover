import os
import paramiko
import datetime

destination_path = '/home/alex/rig1/projects/pc/rover/world_model/data/session.npy'

def send_file(host, username, password, local_file, remote_file):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password)
    sftp = ssh.open_sftp()
    sftp.put(local_file, remote_file)
    sftp.close()
    ssh.close()

print(datetime.now(), 'Sending..')
send_file(
    host='192.168.1.23',
    username=os.environ.get('SFTP_USER',''),
    password=os.environ.get('SFTP_PASSWORD',''),
    local_file='session.npy',
    remote_file=destination_path
    )
print(datetime.now(), 'Session file sent to:', destination_path)