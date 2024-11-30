# tts_server.py
from flask import Flask, request, send_file
import pyttsx3
import tempfile
import os

class TextToSpeech:
    def __init__(self):
        # Initialize the text-to-speech engine
        self.engine = pyttsx3.init()
        
        # Get default voice properties
        self.voices = self.engine.getProperty('voices')
        
        # Set default properties
        self.engine.setProperty('rate', 150)    # Speaking rate (words per minute)
        self.engine.setProperty('volume', 1.0)  # Volume (0.0 to 1.0)
        
        # Default to first available voice
        if self.voices:
            self.engine.setProperty('voice', self.voices[0].id)

    def list_voices(self):
        """Print all available voices"""
        print("\nAvailable voices:")
        for idx, voice in enumerate(self.voices):
            print(f"{idx}: {voice.name} ({voice.id}) - {voice.languages}")

    def set_voice(self, voice_index):
        """Set voice by index"""
        if 0 <= voice_index < len(self.voices):
            self.engine.setProperty('voice', self.voices[voice_index].id)
            return True
        return False

    def set_rate(self, rate):
        """Set speaking rate"""
        self.engine.setProperty('rate', rate)

    def set_volume(self, volume):
        """Set volume"""
        self.engine.setProperty('volume', min(max(0.0, volume), 1.0))

    def speak(self, text, save_to_file=None):
        """Convert text to speech"""
        if save_to_file:
            self.engine.save_to_file(text, save_to_file)
            self.engine.runAndWait()
            print(f"Audio saved to: {save_to_file}")
        else:
            self.engine.say(text)
            self.engine.runAndWait()

app = Flask(__name__)
tts = TextToSpeech()

@app.route('/synthesize', methods=['POST'])
def synthesize_speech():
    if 'text' not in request.form:
        return {'error': 'No text provided'}, 400
    
    text = request.form['text']
    
    # Create a temporary file
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
        temp_path = temp_file.name
    
    try:
        # Generate speech
        tts.speak(text, save_to_file=temp_path)
        
        # Send the file
        response = send_file(
            temp_path,
            mimetype='audio/wav',
            as_attachment=True,
            download_name='speech.wav'
        )
        
        # Delete the temp file after sending
        @response.call_on_close
        def cleanup():
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
        return response
        
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return {'error': str(e)}, 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)