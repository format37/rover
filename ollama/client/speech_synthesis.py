import pyttsx3
import argparse
from pathlib import Path

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

def main():
    parser = argparse.ArgumentParser(description='Text-to-Speech Converter')
    parser.add_argument('--text', '-t', help='Text to convert to speech')
    parser.add_argument('--file', '-f', help='Text file to convert to speech')
    parser.add_argument('--output', '-o', help='Output audio file (e.g., output.mp3)')
    parser.add_argument('--rate', '-r', type=int, default=150, help='Speaking rate (words per minute)')
    parser.add_argument('--volume', '-v', type=float, default=1.0, help='Volume (0.0 to 1.0)')
    parser.add_argument('--list-voices', '-l', action='store_true', help='List available voices')
    parser.add_argument('--voice', type=int, help='Voice index to use')
    
    args = parser.parse_args()
    
    tts = TextToSpeech()
    
    if args.list_voices:
        tts.list_voices()
        return

    # Set properties
    tts.set_rate(args.rate)
    tts.set_volume(args.volume)
    
    if args.voice is not None:
        if not tts.set_voice(args.voice):
            print(f"Invalid voice index: {args.voice}")
            return

    # Get text from file or command line
    text = ""
    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                text = f.read()
        except Exception as e:
            print(f"Error reading file: {e}")
            return
    elif args.text:
        text = args.text
    else:
        print("Please provide text using --text or --file argument")
        return

    # Convert to speech
    tts.speak(text, args.output)

if __name__ == "__main__":
    main()
    