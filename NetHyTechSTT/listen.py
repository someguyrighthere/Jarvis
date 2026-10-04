from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from os import getcwd
from webdriver_manager.chrome import ChromeDriverManager
from pathlib import Path
import sys
import time
from NetHyTechSTT.turn_taking import UtteranceBuffer
from TextToSpeech.Fast_DF_TTS import is_stop_command, speech_input_paused

VOICE_STATE_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
VOICE_STATE_PATH = VOICE_STATE_ROOT / "voice_state.txt"

# The recognition page updates its #output element continuously while the user is still
# talking (interim results). Only treat the text as a finished utterance once it stops
# changing for this long, so Sara doesn't jump in on half-finished sentences.
UTTERANCE_SETTLE_SECONDS = 0.9


def set_voice_state(state):
    try:
        VOICE_STATE_PATH.write_text(state, encoding="utf-8")
    except OSError:
        pass
website = "https://allorizenproject1.netlify.app/"
Recog_File = f"{getcwd()}\\input.txt"


def create_driver():
    chrome_options = Options()
    chrome_options.add_argument("--use-fake-ui-for-media-stream")
    chrome_options.add_argument("--headless=new")
    service = Service(ChromeDriverManager().install())
    browser = webdriver.Chrome(service=service, options=chrome_options)
    browser.get(website)
    return browser


def listen():
    print("Support in Youtube @NetHyTech")
    set_voice_state("LISTENING")
    driver = None
    try:
        driver = create_driver()
        start_button = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, 'startButton')))
        start_button.click()
        print("Listening...")
        utterances = UtteranceBuffer(UTTERANCE_SETTLE_SECONDS)
        while True:
            output_element = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, 'output')))
            current_text = output_element.text.strip()
            utterance = utterances.update(
                current_text,
                time.monotonic(),
                speech_input_paused(),
                stop_command=is_stop_command(current_text),
            )
            if utterance is not None:
                with open(Recog_File, "w", encoding="utf-8") as file:
                    file.write(utterance.lower())
                    print("User:", utterance)
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("Process interrupted by user.")
    except Exception as e:
        print("An error occurred:", e)
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception as e:
                print("Could not close speech recognition browser:", e)
        set_voice_state("IDLE")