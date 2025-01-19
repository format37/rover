import cv2
print(cv2.getBuildInformation())
print(f'CUDA device count: {cv2.cuda.getCudaEnabledDeviceCount()}')
