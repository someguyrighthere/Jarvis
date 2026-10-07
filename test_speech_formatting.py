import unittest
from unittest.mock import Mock, patch

from TextToSpeech import Fast_DF_TTS as speech


class SpeechFormattingTests(unittest.TestCase):
    def test_asterisks_are_removed_before_piper(self):
        with patch.object(speech, "_speak_with_piper") as piper:
            speech.Co_speak("**Hello**, *welcome*.\n* **Weather**\n  * Time")
        piper.assert_called_once_with("Hello, welcome.\nWeather\n  Time")

    def test_plain_text_and_punctuation_are_preserved(self):
        text = "It's 12:30. CPU: 25%; temperature: 48 C."
        with patch.object(speech, "_speak_with_piper") as piper:
            speech.Co_speak(text)
        piper.assert_called_once_with(text)

    def test_fallback_also_receives_clean_text(self):
        speaker = Mock()
        with (
            patch.object(speech, "_speak_with_piper", side_effect=RuntimeError("Unavailable")),
            patch.object(speech.platform, "system", return_value="Windows"),
            patch.object(speech.pythoncom, "CoInitialize"),
            patch.object(speech.pythoncom, "CoUninitialize"),
            patch.object(speech.win32com.client, "Dispatch", return_value=speaker),
            patch.object(speech, "_speak_with_sapi") as sapi,
        ):
            speech.Co_speak("**Hello**")
        sapi.assert_called_once_with(speaker, "Hello")

    def test_formatting_only_text_does_not_generate_audio(self):
        with patch.object(speech, "_speak_with_piper") as piper:
            speech.Co_speak("***")
        piper.assert_not_called()


if __name__ == "__main__":
    unittest.main()
