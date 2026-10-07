import datetime
import re
import time

import pywhatkit as kit

from TextToSpeech.Fast_DF_TTS import speak
from version import WAKE_WORD_PATTERN


CONTACTS = {"anubhav": "+919606348280"}
MAX_MESSAGE_LENGTH = 1000


def _read_input():
    with open("input.txt", "r", encoding="utf-8-sig") as file:
        return file.read().strip().casefold()


def _without_wake_word(text):
    return re.sub(WAKE_WORD_PATTERN, "", text).strip()


def _wait_for_response(previous):
    while True:
        response = _read_input()
        if response and response != previous:
            return _without_wake_word(response)
        time.sleep(0.1)


def send_msg_wa():
    previous = _read_input()
    speak("WhatsApp is ready for one supported contact, Anubhav. Say send to Anubhav, or cancel message.")
    response = _wait_for_response(previous)
    response = response.rstrip(".,!? ")
    if response in {"cancel message", "cancel"}:
        speak("I cancelled the WhatsApp message.")
        return
    if not response.startswith("send to "):
        speak("I couldn't identify the recipient. No message was sent.")
        return

    contact_name = response.removeprefix("send to ").strip()
    phone_number = CONTACTS.get(contact_name)
    if phone_number is None:
        speak("That contact is not in SARA's supported contact list. No message was sent.")
        return

    previous = _read_input()
    speak("What message would you like to send?")
    response = _wait_for_response(previous)
    if not response.startswith("message is "):
        speak("I didn't receive a message in the expected format. No message was sent.")
        return
    message = response.removeprefix("message is ").strip()
    if not message or len(message) > MAX_MESSAGE_LENGTH:
        speak(f"Messages must contain 1 to {MAX_MESSAGE_LENGTH} characters. No message was sent.")
        return

    previous = _read_input()
    speak(f"Review the message for {contact_name.title()}: {message}. Say confirm send to send it, or cancel message.")
    confirmation = _wait_for_response(previous).rstrip(".,!? ")
    if confirmation != "confirm send":
        speak("I cancelled the WhatsApp message. Nothing was sent.")
        return

    send_time = datetime.datetime.now() + datetime.timedelta(minutes=1)
    kit.sendwhatmsg(phone_number, message, send_time.hour, send_time.minute)
    speak(f"WhatsApp accepted the message for {contact_name.title()}.")
