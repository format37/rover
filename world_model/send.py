import os
import paramiko

def send_file(host, username, password, local_file, remote_file):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password)
    sftp = ssh.open_sftp()
    sftp.put(local_file, remote_file)
    sftp.close()
    ssh.close()

send_file(
    host='192.168.1.23',
    username=os.environ.get('SFTP_USER',''),
    password=os.environ.get('SFTP_PASSWORD',''),
    local_file='session.npy',
    remote_file='session.npy'
    )
print('sent')