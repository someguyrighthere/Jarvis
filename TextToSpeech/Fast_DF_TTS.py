import requests # pip install requests
import os
from typing import Union # pip install typing
import sys
import time
import threading
import platform
import asyncio
import tempfile
from pathlib import Path

VOICE_STATE_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
VOICE_STATE_PATH = VOICE_STATE_ROOT / "voice_state.txt"


def set_voice_state(state: str):
    try:
        VOICE_STATE_PATH.write_text(state, encoding="utf-8")
    except OSError:
        pass

if platform.system() == "Windows":
    import win32com.client
    import pythoncom
    from playsound import playsound
else:
    try:
        from playsound import playsound
    except:
        playsound = None

try:
    import edge_tts
except ImportError:
    edge_tts = None

NEURAL_VOICE = "en-US-AriaNeural"

def generate_audio(message: str,voice : str = "Matthew"):
    url: str = f"https://api.streamelements.com/kappa/v2/speech?voice={voice}&text={{{message}}}"

    headers = {'User-Agent':'Mozilla/5.0(Maciontosh;intel Mac OS X 10_15_7)AppleWebKit/537.36(KHTML,like Gecoko)Chrome/119.0.0.0 Safari/537.36'}
    
    try:
        result = requests.get(url=url, headers=headers)
        return result.content
    except:
        return None
    
def print_animated_message(message):
    for char in message:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(0.050)  # Adjust the sleep duration for the animation speed
    print()

def Co_speak(message: str, voice: str = "Matthew", folder: str = "", extension: str = ".mp3") -> Union[None,str]:
    audio_path = None
    try:
        if edge_tts is not None and playsound is not None:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as audio_file:
                audio_path = audio_file.name
            communicate = edge_tts.Communicate(
                message,
                NEURAL_VOICE,
                rate="-10%",
                pitch="-4Hz",
            )
            asyncio.run(communicate.save(audio_path))
            playsound(audio_path)
            return None

        if platform.system() == "Windows":
            pythoncom.CoInitialize()
            try:
                speaker = win32com.client.Dispatch("SAPI.SpVoice")
                speaker.Voice = speaker.GetVoices().Item(0)
                speaker.Rate = -1
                speaker.Volume = 100
                speaker.Speak(message)
            finally:
                pythoncom.CoUninitialize()
            return None

        result_content = generate_audio(message, voice)
        file_path = os.path.join(folder, f"{voice}{extension}")
        with open(file_path, "wb") as file:
            file.write(result_content)
        playsound(file_path)
        os.remove(file_path)
        return None
    except Exception as e:
        print(f"Audio playback error: {e}")
        if platform.system() == "Windows":
            try:
                pythoncom.CoInitialize()
                try:
                    speaker = win32com.client.Dispatch("SAPI.SpVoice")
                    speaker.Speak(message)
                finally:
                    pythoncom.CoUninitialize()
            except Exception as fallback_error:
                print(f"Fallback audio error: {fallback_error}")
    finally:
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)

def speak(text):
    set_voice_state("SPEAKING")
    try:
        t1 = threading.Thread(target=Co_speak,args=(text,))
        t2 = threading.Thread(target=print_animated_message,args=(text,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    finally:
        set_voice_state("IDLE")


#c