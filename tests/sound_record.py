import pyaudio
import wave

# Set the audio parameters
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 48000
CHUNK = 1024
RECORD_SECONDS = 5
WAVE_OUTPUT_FILENAME = "output.wav"

# Initialize PyAudio
audio = pyaudio.PyAudio()

# Find the index of the audio card
device_index = None
for i in range(audio.get_device_count()):
    dev = audio.get_device_info_by_index(i)
    if 'Device' in dev['name']:
        device_index = dev['index']
        print(f'[{i}] Device found: {dev["name"]}')
        break

if device_index is None:
    raise ValueError("Audio card not found.")

# Open the microphone stream
stream = audio.open(format=FORMAT, channels=CHANNELS,
                    rate=RATE, input=True,
                    input_device_index=device_index,
                    frames_per_buffer=CHUNK)

print("Recording...")

# Initialize an empty list to store the recorded audio frames
frames = []

# Record audio for the specified duration
for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
    data = stream.read(CHUNK)
    frames.append(data)

print("Recording finished.")

# Stop and close the microphone stream
stream.stop_stream()
stream.close()
audio.terminate()

# Save the recorded audio as a WAV file
wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
wf.setnchannels(CHANNELS)
wf.setsampwidth(audio.get_sample_size(FORMAT))
wf.setframerate(RATE)
wf.writeframes(b''.join(frames))
wf.close()