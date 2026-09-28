import pyautogui as gui
import subprocess
import time
import os

def open_App(text):
    app_name = text.strip().lower()
    known_apps = {
        "chrome": os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Google", "Chrome", "Application", "chrome.exe"),
        "google chrome": os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Google", "Chrome", "Application", "chrome.exe"),
    }
    app_path = known_apps.get(app_name, text.strip())

    if os.path.isfile(app_path):
        subprocess.Popen([app_path])
        return

    try:
        subprocess.Popen(app_path)
    except OSError:
        gui.press("win")
        time.sleep(0.2)
        gui.write(text.strip())
        time.sleep(0.2)
        gui.press("enter")


def close_App(text):
    app_name = text.lower().replace("close", "").replace("shut down", "").strip()
    app_name = app_name.replace("application", "").replace("app", "").strip()
    process_names = {
        "chrome": "chrome.exe",
        "google chrome": "chrome.exe",
        "edge": "msedge.exe",
        "microsoft edge": "msedge.exe",
        "firefox": "firefox.exe",
        "spotify": "spotify.exe",
        "notepad": "notepad.exe",
        "calculator": "calculatorapp.exe",
        "code": "code.exe",
        "visual studio code": "code.exe",
    }
    process_name = process_names.get(app_name)
    if not process_name:
        gui.hotkey("alt", "f4")
        return False

    result = subprocess.run(
        ["taskkill", "/IM", process_name, "/T"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0