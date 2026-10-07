import wmi
from TextToSpeech.Fast_DF_TTS import speak

def set_brightness_windows(percentage):
    if not isinstance(percentage, int) or isinstance(percentage, bool) or not 0 <= percentage <= 100:
        raise ValueError("Brightness must be a whole percentage between 0 and 100.")
    try:
        w = wmi.WMI(namespace='wmi')
        brightness_methods = w.WmiMonitorBrightnessMethods()[0]
        brightness_methods.WmiSetBrightness(int(percentage), 0)
        speak(f"Brightness set to {percentage}%")
    except Exception as e:
        speak(f"Error: {e}")
