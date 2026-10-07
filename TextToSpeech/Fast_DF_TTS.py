import requests # pip install requests
import os
from typing import Union # pip install typing
import sys
import threading
import platform
import tempfile
import wave
from pathlib import Path
import ctypes
import re
import time
from version import WAKE_WORD_PATTERN
from avatar_bridge import audio_envelope, publish_speech
from speech_gestures import plan_gestures

VOICE_STATE_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
VOICE_STATE_PATH = VOICE_STATE_ROOT / "voice_state.txt"
_SPEECH_STOP = threading.Event()
_SPEECH_LOCK = threading.Lock()
_SPEAKING = threading.Event()
_SPEECH_FINISHED_AT = float("-inf")
SPEECH_ECHO_GRACE_SECONDS = 1.0
_MCI_ALIAS = "jarvis_speech"
PIPER_VOICE_NAME = "en_GB-alba-medium"
PIPER_MODEL_NAME = f"{PIPER_VOICE_NAME}.onnx"
PIPER_CONFIG_NAME = f"{PIPER_MODEL_NAME}.json"
PIPER_MODEL_DIRECTORY = (
    VOICE_STATE_ROOT / "models" / "piper"
    if getattr(sys, "frozen", False)
    else Path(os.getenv("LOCALAPPDATA", Path.home())) / "JARVIS" / "models" / "piper"
)
PIPER_MODEL_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/"
    "en/en_GB/alba/medium"
)
_PIPER_VOICE = None
_PIPER_LOCK = threading.Lock()


def set_voice_state(state: str):
    try:
        VOICE_STATE_PATH.write_text(state, encoding="utf-8")
    except OSError:
        pass


def stop_speaking():
    _SPEECH_STOP.set()
    if platform.system() == "Windows":
        try:
            ctypes.windll.winmm.mciSendStringW(f"stop {_MCI_ALIAS}", None, 0, None)
        except (AttributeError, OSError):
            pass


def speech_input_paused():
    return _SPEAKING.is_set() or time.monotonic() - _SPEECH_FINISHED_AT < SPEECH_ECHO_GRACE_SECONDS


def is_stop_command(text: str) -> bool:
    query = text.strip().lower()
    query = re.sub(WAKE_WORD_PATTERN, "", query).strip()
    query = re.sub(r"[.!?]+$", "", query).strip()
    return query in {
        "stop", "stop talking", "stop speaking", "be quiet", "quiet",
        "silence", "cancel speech", "stop audio", "please stop talking",
        "please stop speaking", "stop talking please", "stop speaking please",
    }


def _play_audio(audio_path: str, message: str = ""):
    try:
        levels = audio_envelope(audio_path)
    except (OSError, ValueError, wave.Error) as error:
        print(f"Avatar audio analysis failed: {error}")
        levels = []
    gestures = plan_gestures(message, len(levels) * 0.04, levels)
    if platform.system() != "Windows":
        publish_speech(levels, "audio", gestures=gestures)
        try:
            playsound(audio_path)
        finally:
            publish_speech([], "idle")
        return

    winmm = ctypes.windll.winmm

    def send(command: str, output=None):
        return winmm.mciSendStringW(command, output, len(output) if output else 0, None)

    if send(f'open "{audio_path}" alias {_MCI_ALIAS}'):
        raise RuntimeError("Could not open audio for playback")
    try:
        if send(f"play {_MCI_ALIAS}"):
            raise RuntimeError("Could not start audio playback")
        publish_speech(levels, "audio", gestures=gestures)
        while not _SPEECH_STOP.is_set():
            mode = ctypes.create_unicode_buffer(32)
            if send(f"status {_MCI_ALIAS} mode", mode) or mode.value != "playing":
                break
            _SPEECH_STOP.wait(0.05)
    finally:
        publish_speech([], "idle")
        send(f"stop {_MCI_ALIAS}")
        send(f"close {_MCI_ALIAS}")


def _speak_with_sapi(speaker, message: str):
    if _SPEECH_STOP.is_set():
        return
    publish_speech([], "sapi")
    speaker.Speak(message, 1)
    while not _SPEECH_STOP.is_set() and speaker.Status.RunningState == 2:
        _SPEECH_STOP.wait(0.05)
    if _SPEECH_STOP.is_set():
        speaker.Speak("", 3)


def _download_piper_file(filename: str, maximum_size: int):
    destination = PIPER_MODEL_DIRECTORY / filename
    if destination.is_file() and destination.stat().st_size:
        return destination

    PIPER_MODEL_DIRECTORY.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with requests.get(
            f"{PIPER_MODEL_URL}/{filename}",
            stream=True,
            timeout=(10, 120),
        ) as response:
            response.raise_for_status()
            downloaded = 0
            with tempfile.NamedTemporaryFile(
                dir=PIPER_MODEL_DIRECTORY,
                prefix=f"{filename}.",
                suffix=".part",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    downloaded += len(chunk)
                    if downloaded > maximum_size:
                        raise ValueError(f"The Piper voice file {filename} exceeds its size limit.")
                    temporary_file.write(chunk)
        if downloaded == 0:
            raise ValueError(f"The Piper voice file {filename} was empty.")
        temporary_path.replace(destination)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()
    return destination


def _load_piper_voice():
    global _PIPER_VOICE
    if _PIPER_VOICE is not None:
        return _PIPER_VOICE

    with _PIPER_LOCK:
        if _PIPER_VOICE is None:
            model_path = _download_piper_file(PIPER_MODEL_NAME, 150 * 1024 * 1024)
            _download_piper_file(PIPER_CONFIG_NAME, 1024 * 1024)
            from piper import PiperVoice

            _PIPER_VOICE = PiperVoice.load(str(model_path))
    return _PIPER_VOICE


def _speak_with_piper(message: str):
    voice = _load_piper_voice()
    audio_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as audio_file:
            audio_path = audio_file.name
        with wave.open(audio_path, "wb") as wav_file:
            voice.synthesize_wav(message, wav_file)
        if not _SPEECH_STOP.is_set():
            _play_audio(audio_path, message)
    finally:
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)

if platform.system() == "Windows":
    import win32com.client
    import pythoncom
    from playsound import playsound
else:
    try:
        from playsound import playsound
    except:
        playsound = None

SAPI_VOICE_NAMES = ("Jenny", "Sonia", "Zira", "Hazel", "Susan", "Heera", "Eva")

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
        if _SPEECH_STOP.is_set():
            break
        sys.stdout.write(char)
        sys.stdout.flush()
        if _SPEECH_STOP.wait(0.050):
            break
    print()

def Co_speak(message: str, voice: str = "Matthew", folder: str = "", extension: str = ".mp3") -> Union[None,str]:
    message = re.sub(r"(?m)^([ \t]*)\*+[ \t]+", r"\1", message).replace("*", "")
    if not message.strip():
        return None
    try:
        _speak_with_piper(message)
    except Exception as e:
        print(f"Piper speech error: {e}")
        if platform.system() == "Windows":
            try:
                pythoncom.CoInitialize()
                try:
                    speaker = win32com.client.Dispatch("SAPI.SpVoice")
                    speaker.Rate = -1
                    speaker.Volume = 100
                    _speak_with_sapi(speaker, message)
                finally:
                    pythoncom.CoUninitialize()
            except Exception as fallback_error:
                print(f"Fallback audio error: {fallback_error}")
    return None

def speak(text):
    global _SPEECH_FINISHED_AT
    with _SPEECH_LOCK:
        _SPEECH_STOP.clear()
        _SPEAKING.set()
        set_voice_state("SPEAKING")
        try:
            t1 = threading.Thread(target=Co_speak,args=(text,))
            t2 = threading.Thread(target=print_animated_message,args=(text,))
            t1.start()
            t2.start()
            t1.join()
            t2.join()
        finally:
            publish_speech([], "idle")
            _SPEECH_FINISHED_AT = time.monotonic()
            _SPEAKING.clear()
            set_voice_state("IDLE")


#c