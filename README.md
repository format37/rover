### Requirements
* GPU with 22+ Gb of memory for ollama server
* Python managed Rover with camera as ollama client
### Server installation (PC)
```
git clone https://github.com/format37/rover.git
cd rover/ollama/server
```
* Set ollama server  
* Config your ollama to be accesible from remote client:
```
sudo nano /etc/systemd/system/ollama.service
```
Add the following line to the file
```
Environment="OLLAMA_HOST=0.0.0.0"
```
* Restart ollama service
```
sudo systemctl daemon-reload
sudo systemctl restart ollama
```
* Run ollama server
```
sudo systemctl start ollama
```

### First steps with the clean Jetson Nano Operating system
1. **SSH**
```
sudo systemctl start ssh
sudo systemctl enable ssh
```
2. **Python**
First upgrade may take couple of hours. Need to press Y multiple times.
Automatically restart Docker daemon: Y
Upgrade and reboot:
```
sudo apt update && sudo apt upgrade -y
sudo reboot now
```
Install Python:
Check that you have python3.6 installed. If you have python3.6, then you don't need to perfrom the steps of this point.
```
sudo apt-get install nano
<!-- sudo apt install python3.9 -y
sudo update-alternatives --install /usr/bin/python python /usr/bin/python3.8 1
sudo update-alternatives --install /usr/bin/python3 python /usr/bin/python3.8 1
sudo ln -s /usr/bin/python3.8 /usr/bin/python -->

sudo apt install python3.6 -y
sudo update-alternatives --install /usr/bin/python python /usr/bin/python3.6 1
sudo update-alternatives --install /usr/bin/python3 python /usr/bin/python3.6 1
sudo ln -s /usr/bin/python3.6 /usr/bin/python
sudo ln -s /usr/bin/python3.6 /usr/bin/python3

sudo apt install python3-pip -y
sudo apt-get install python3-dev python3-pip python3-setuptools
sudo apt-get install python3-distutils
python -m pip install --upgrade pip setuptools
python --version
python3 --version
```
3. **Mount nvcc**
Open your .bashrc file:
```
nano ~/.bashrc
```
Add the following lines at the end of the file:
```
export PATH=/usr/local/cuda/bin${PATH:+:${PATH}}
export LD_LIBRARY_PATH=/usr/local/cuda/lib64${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}
```
Save and exit, then run:
```
source ~/.bashrc
```
Check nvcc version
```
nvcc --version
```
Check Jetpack
```
sudo apt-cache show nvidia-jetpack
```
4. **Prepare pytorch for cuda**
Since Jetson Nano is [limited by JetPack4](https://forums.developer.nvidia.com/t/pytorch-for-jetson/72048) we have to install torch-1.10 to have access to Jetson's GPU and the latest available for Jetson Nano YOLO version is YOLOv3.
You need to download the coresponding whl to your jetson from the [pytorch list whl](https://forums.developer.nvidia.com/t/pytorch-for-jetson/72048). Idk why the classic wget downloading thw wrong whl. Downloading from the web page is fine.
```
<!-- sudo apt-get install python3-pip libopenblas-dev -y -->
python3 -m pip install torch-1.10.0-cp36-cp36m-linux_aarch64.whl
```
Check that torch is installed and that the cuda is available:
```
python3
>>> import torch
>>> print(torch.__version__)
>>> print(torch.cuda.is_available())
```

Previous tries:
```
<!-- sudo apt-get install python3-pip libopenblas-base libopenmpi-dev
git clone --recursive https://github.com/pytorch/pytorch
cd pytorch
export CMAKE_PREFIX_PATH="$(dirname $(which python))/../.." -->
```

### Client installation (Jetson Nano)
```
git clone https://github.com/format37/rover.git
cd rover/ollama/client
```
* Install requirements
```
python -m pip install -r requirements.txt
```
* Run client
```
python client.py
```
### PyAidio installation
I've used the usb audio device which works well with both speaker and mic.
```
sudo apt-get install portaudio19-dev
```
### Realsense camera installation on Jetson nano
0. Ensure that python3 is installed and defined as default python. I am using 3.8.
To install the `pyrealsense2` Python wrapper on a Jetson Nano, you need to build the Intel RealSense SDK (`librealsense`) from source, as pre-built binaries are not compatible with the ARM architecture of the Jetson Nano. This process will also install the necessary RealSense software. Here's a step-by-step guide:

1. **Update and Upgrade System Packages**:
   ```bash
   sudo apt-get update && sudo apt-get upgrade -y
   ```

2. **Install Required Dependencies**:
   ```bash
   sudo apt-get install -y git libssl-dev libusb-1.0-0-dev pkg-config libgtk-3-dev
   ```

3. **Clone the `librealsense` Repository**:
   ```bash
   git clone https://github.com/IntelRealSense/librealsense.git
   cd librealsense
   ```

4. **Set Up Udev Rules**:
   ```bash
   sudo ./scripts/setup_udev_rules.sh
   ```

5. **Create a Build Directory and Navigate Into It**:
   ```bash
   mkdir build && cd build
   ```

6. **Configure the Build with CMake**:
   ```bash
   cmake ../ -DFORCE_RSUSB_BACKEND=ON -DBUILD_PYTHON_BINDINGS=bool:true -DPYTHON_EXECUTABLE=$(which python3)
   ```
   This command sets up the build to use the RSUSB backend and includes the Python bindings for Python 3.

7. **Compile and Install**:
   ```bash
   make -j$(nproc)
   sudo make install
   ```
   This step compiles the library and installs it on your system.

8. **Update the Python Path**:
   ```bash
   export PYTHONPATH=$PYTHONPATH:/usr/local/lib/python3.6/pyrealsense2/
   ```
   This command adds the installed `pyrealsense2` module to your Python path.

After completing these steps, you should be able to import `pyrealsense2` in your Python scripts and utilize the RealSense SDK functionalities.



