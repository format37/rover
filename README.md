### Jetson Nano
1. **Download the Jetson Nano image**
[Download and flash from ubuntu](https://qengineering.eu/install-opencv-on-jetson-nano.html)  
Flashing is available by RMB on image file and select SD.

2. **Check YOLOv5 OpenCV GPU**
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

3. **Check torch GPU**
```
python3 torch_cuda_test.py
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
Follow the instructions for the [Linux Distribution](https://github.com/IntelRealSense/librealsense/blob/master/doc/distribution_linux.md).
Check the realsense with GUI:
```
realsense-viewer
```
If camera works well in GUI then continue to configure python wrappers:
```bash
sudo apt-get update
sudo apt-get install -y \
    git \
    libssl-dev \
    libusb-1.0-0-dev \
    pkg-config \
    libgtk-3-dev \
    libcurl4-openssl-dev \
    libglu1-mesa-dev
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
# cmake ../ -DFORCE_RSUSB_BACKEND=ON -DBUILD_PYTHON_BINDINGS=bool:true -DPYTHON_EXECUTABLE=$(which python3) -DCMAKE_EXE_LINKER_FLAGS="-lGLU"
cmake ../ -DFORCE_RSUSB_BACKEND=ON -DBUILD_PYTHON_BINDINGS=bool:true -DBUILD_SHARED_LIBS=false -DPYTHON_EXECUTABLE=$(which python3)
```
This command sets up the build to use the RSUSB backend and includes the Python bindings for Python 3.

7. **Compile and Install**:
```bash
make -j$(nproc)
sudo make install
```
This step compiles the library and installs it on your system.

8. **Instal pyrealsense via pip**
```bash
python3 -m pip install pyrealsense2
```

9. **Check pyrealsense2**
```bash
cd ~/projects/librealsense/wrappers/python/examples
python3 opencv_viewer_example.py
```

<!-- 8. **Update the Python Path**:
```bash
# export PYTHONPATH=$PYTHONPATH:/usr/local/lib/python3.6/pyrealsense2/
# Add the correct path to PYTHONPATH
export PYTHONPATH=$PYTHONPATH:/usr/local/lib/python3.6
```
This command adds the installed `pyrealsense2` module to your Python path.

After completing these steps, you should be able to import `pyrealsense2` in your Python scripts and utilize the RealSense SDK functionalities. -->
