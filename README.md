### Jetson Nano
1. **Download the Jetson Nano image**
[Download and flash from ubuntu](https://qengineering.eu/install-opencv-on-jetson-nano.html)  
Flashing is available by RMB on image file and select SD.
2. **Check CUDA**
Clone the repo and check opencv cuda
```

```

3. **Check yolo with CUDA**
```
mkdir ~/projects
cd ~/projects
git clone https://github.com/format37/yolov5-opencv-cpp-python.git
git clone https://github.com/format37/rover.git
cd rover/object_chaser
cp ../../yolov5-opencv-cpp-python/sample.mp4 ./
cp ../../yolov5-opencv-cpp-python/config_files ./
python3 yolo_test.py cuda
python3 opencv_cuda_test.py
```
4. **Check torch
```
python3 torch_cuda_test.py
```

```
git clone https://github.com/format37/rover.git
cd rover/object_chaser
python3 cuda_test.py
```
Based on the (following repo)[https://github.com/otamajakusi/yolov5-opencv-cpp-python] I've prepared a test script which need to run in GUI:
```
sh download_yolo_model.sh
python3 yolo_test.py
```

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

1.b **Python**
First upgrade may take couple of hours. Need to press Y multiple times.
Automatically restart Docker daemon: Y
Upgrade and reboot:
```
sudo apt update && sudo apt upgrade -y
sudo reboot now
```
Install Python:
```
sudo apt-get install nano
sudo apt install python3.8 -y
sudo update-alternatives --install /usr/bin/python python /usr/bin/python3.8 1
sudo update-alternatives --install /usr/bin/python3 python /usr/bin/python3.8 1
sudo ln -s /usr/bin/python3.8 /usr/bin/python
```

2. **Mount nvcc**
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
3. **Prepare pytorch for cuda**
Since Jetson Nano is [limited by JetPack4](https://forums.developer.nvidia.com/t/pytorch-for-jetson/72048) we have to install torch-1.10 to have access to Jetson's GPU and the latest available for Jetson Nano YOLO version is YOLOv3.
You need to download the coresponding whl to your jetson from the [pytorch list whl](https://forums.developer.nvidia.com/t/pytorch-for-jetson/72048). Idk why the classic wget downloading thw wrong whl. Downloading from the web page is fine.
```
python3
>>> import torch
>>> print(torch.__version__)
>>> print(torch.cuda.is_available())
```

4. **Prepare OpenCV for CDNN**
[YOLOv5 with OpenCV on Jetson Nano](https://i7y.org/en/yolov5-with-opencv-on-jetson-nano)
I've noticed that OpenCV works with python3.8 So we have to check CUDNN availability after installation.  
Install package:
```
sudo apt-get update
sudo apt-get install -y \
    build-essential \
    cmake \
    git \
    gfortran \
    libatlas-base-dev \
    libavcodec-dev \
    libavformat-dev \
    libavresample-dev \
    libcanberra-gtk3-module \
    libdc1394-22-dev \
    libeigen3-dev \
    libglew-dev \
    libgstreamer-plugins-base1.0-dev \
    libgstreamer-plugins-good1.0-dev \
    libgstreamer1.0-dev \
    libgtk-3-dev \
    libjpeg-dev \
    libjpeg8-dev \
    libjpeg-turbo8-dev \
    liblapack-dev \
    liblapacke-dev \
    libopenblas-dev \
    libpng-dev \
    libpostproc-dev \
    libswscale-dev \
    libtbb-dev \
    libtbb2 \
    libtesseract-dev \
    libtiff-dev \
    libv4l-dev \
    libxine2-dev \
    libxvidcore-dev \
    libx264-dev \
    pkg-config \
    python3.8-dev \
    python3-numpy \
    python3-matplotlib \
    python3-pip \
    qv4l2 \
    v4l-utils \
    v4l2ucp \
    zlib1g-dev \
    nvidia-cuda \
    nvidia-cudnn8
```
Next, install the python3.8 package. The key point is to uninstall the pre-installed opencv package and python3 numpy and install the python3.8 numpy.
```
apt list --installed | grep -i opencv | awk -F/ '{print $1}'| xargs sudo apt purge -y
sudo python3 -m pip install -U pip
sudo python3 -m pip uninstall -y numpy
sudo python3.8 -m pip install -U pip
sudo python3.8 -m pip install setuptools
sudo python3.8 -m pip install numpy
```
Clone OpenCV.
```
git clone --depth 1 --branch 4.6.0 https://github.com/opencv/opencv.git
git clone --depth 1 --branch 4.6.0 https://github.com/opencv/opencv_contrib.git
```
Set CMAKFLAGS.
```
CMAKEFLAGS="
        -D BUILD_EXAMPLES=OFF
        -D BUILD_opencv_python2=OFF
        -D BUILD_opencv_python3=ON
        -D CMAKE_BUILD_TYPE=RELEASE
        -D CMAKE_INSTALL_PREFIX=/usr/local
        -D CUDA_ARCH_BIN=5.3,6.2,7.2
        -D CUDA_ARCH_PTX=
        -D CUDA_FAST_MATH=ON
        -D CUDNN_VERSION='8.0'
        -D EIGEN_INCLUDE_PATH=/usr/include/eigen3 
        -D ENABLE_NEON=ON
        -D OPENCV_DNN_CUDA=ON
        -D OPENCV_ENABLE_NONFREE=ON
        -D OPENCV_EXTRA_MODULES_PATH=../../opencv_contrib/modules
        -D OPENCV_GENERATE_PKGCONFIG=ON
        -D WITH_CUBLAS=ON
        -D WITH_CUDA=ON
        -D WITH_CUDNN=ON
        -D WITH_GSTREAMER=ON
        -D WITH_LIBV4L=ON
        -D WITH_OPENGL=ON
        -D INSTALL_PYTHON_EXAMPLES=ON
        -D PYTHON3_EXECUTABLE=python3.8
        -D PYTHON3_INCLUDE_PATH=$(python3.8 -c "from distutils.sysconfig import get_python_inc; print(get_python_inc())")
        -D PYTHON3_PACKAGES_PATH=$(python3.8 -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")
        -D PYTHON3_LIBRARY=/usr/lib/aarch64-linux-gnu/libpython3.8.so"
```
Build & install. Jetson Nano core number 4 is specified as make -j$(nproc), it builds fine in my environment. if you want to run with another OpenCV version other than 4.6.0, please refer to Please refer to [this link](https://qengineering.eu/install-opencv-4.5-on-jetson-nano.html).
```
cd opencv
mkdir build
cd build
cmake ${CMAKEFLAGS} ..
```
The following commands takes about 2 hours and 40 minutes..
```
make -j$(nproc)
sudo make install
```
Update the Dynamic Linker's Cache
```
sudo ldconfig -v
```
Check cuda
```
print(cv2.getBuildInformation())
print(cv2.cuda.getCudaEnabledDeviceCount())
```
5. **YOLO5 running**
```
git clone https://github.com/otamajakusi/yolov5-opencv-cpp-python.git
cd yolov5-opencv-cpp-python
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



