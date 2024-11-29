# Goal oriented robot
The core concept revolves around infinite, sequential JSON prompting that can generate thoughts, speech, and actions through GPT-like models while leveraging Image2Text and STT models for world perception.  
<p align="center">
  <img src="https://github.com/format37/rover/blob/master/assets/rover.drawio.png" alt="Concept">
</p><br>
<b>Requirements</b><br>
* <a href="https://github.com/format37/MiniGPT-4">MiniGPT-4</a><br>
<b>Status</b><br>
Prototyping<br><br>
<b>Hardware</b><br>
Jetson Nano 4GB<br>
<hr>
<b>Previous revisions</b>
<p align="center">
  <a href="https://youtu.be/f6Nfc5jzEi0">YouTube</a>
    <img src="https://i9.ytimg.com/vi/f6Nfc5jzEi0/mq1.jpg?sqp=CMjwnYoG&rs=AOn4CLCXwUplQjQcZZcBIdK3yu3a80Qf7w" alt="Realsense tank async depth capture python">
  </a>
</p>
<p align="center">
  <img src="https://github.com/format37/rover/blob/master/images/back.jpg" alt="back">
  <img src="https://github.com/format37/rover/blob/master/images/right.jpg" alt="right">
  <img src="https://github.com/format37/rover/blob/master/images/front.jpg" alt="front">
</p>
<b>Settings</b>

To configure CPU and others, go there:
```
sudo nano /etc/nvpmodel.conf
```
### Installation
* Pyaudio
```
sudo apt-get install portaudio19-dev python3-dev python3-pip
python3 -m pip install pyaudio
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