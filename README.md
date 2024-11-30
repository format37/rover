### Requirements
* GPU with 22+ Gb of memory for ollama server
* Python managed Rover with camera as ollama client
### Server installation
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
### Client installation
```
git clone https://github.com/format37/rover.git
cd rover/ollama/client
```
* Install requirements
```
pip install -r requirements.txt
```
* Run client
```
python client.py
```
### PyAidio installation
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