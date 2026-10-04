import unittest
from unittest.mock import patch

from NetHyTechSTT.turn_taking import UtteranceBuffer
from TextToSpeech import Fast_DF_TTS as speech


class TurnTakingTests(unittest.TestCase):
    def test_saras_speech_is_not_submitted_during_or_after_playback(self):
        buffer = UtteranceBuffer(0.9)
        self.assertIsNone(buffer.update("would you like me to launch it", 1, True))
        self.assertIsNone(buffer.update("would you like me to launch it", 3, True))
        self.assertIsNone(buffer.update("would you like me to launch it", 10, False))
        self.assertIsNone(buffer.update("yes please", 11, False))
        self.assertEqual(buffer.update("yes please", 12, False), "yes please")

    def test_new_words_restart_the_settle_timer(self):
        buffer = UtteranceBuffer(0.9)
        self.assertIsNone(buffer.update("build", 0, False))
        self.assertIsNone(buffer.update("build an app", 0.8, False))
        self.assertIsNone(buffer.update("build an app", 1, False))
        self.assertEqual(buffer.update("build an app", 2, False), "build an app")

    def test_stop_command_can_interrupt_speech_once(self):
        buffer = UtteranceBuffer(0.9)
        self.assertEqual(buffer.update("sara stop", 0, True, True), "sara stop")
        self.assertIsNone(buffer.update("sara stop", 1, True, True))

    def test_empty_text_is_never_submitted(self):
        self.assertIsNone(UtteranceBuffer(0.9).update("  ", 10, False))

    def test_speech_gate_is_active_through_playback_and_echo_grace(self):
        with (
            patch.object(speech, "_SPEECH_FINISHED_AT", 10),
            patch.object(speech.time, "monotonic", return_value=10.5),
        ):
            self.assertTrue(speech.speech_input_paused())
        with (
            patch.object(speech, "_SPEECH_FINISHED_AT", 10),
            patch.object(speech.time, "monotonic", return_value=12),
        ):
            self.assertFalse(speech.speech_input_paused())


if __name__ == "__main__":
    unittest.main()
