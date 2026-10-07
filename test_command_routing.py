import unittest
from contextlib import ExitStack
from unittest.mock import mock_open, patch

import co_brain


class CommandRoutingTests(unittest.TestCase):
    def run_command(self, text):
        file = mock_open(read_data=text)
        file.return_value.read.side_effect = [text, KeyboardInterrupt()]
        with ExitStack() as stack:
            stack.enter_context(patch("builtins.open", file))
            for name in (
                "handle_task_command", "handle_system_command", "handle_tool_command",
                "handle_extension_command", "run_registered_tool", "handle_project_command",
                "handle_forge_command", "_pop_tool_offer", "pop_capability_gap",
            ):
                stack.enter_context(patch.object(co_brain, name, return_value=None))
            stack.enter_context(patch.object(co_brain, "should_propose_extension", return_value=False))
            stack.enter_context(patch.object(co_brain, "set_voice_state"))
            stack.enter_context(patch.object(co_brain, "clear_file"))
            stack.enter_context(patch.object(co_brain, "_extend_follow_up_window"))
            brain = stack.enter_context(patch.object(co_brain, "Main_Brain", return_value="Here are my functions."))
            speak = stack.enter_context(patch.object(co_brain, "speak"))
            schedule = stack.enter_context(patch.object(co_brain, "input_manage"))
            with self.assertRaises(KeyboardInterrupt):
                co_brain.check_inputs()
            return brain, speak, schedule

    def test_tell_me_about_functions_gets_a_spoken_answer(self):
        brain, speak, schedule = self.run_command("sarah tell me about some of your basic functions")
        brain.assert_called_once_with("tell me about some of your basic functions")
        speak.assert_called_once_with("Here are my functions.")
        schedule.assert_not_called()

    def test_timed_reminder_keeps_schedule_route(self):
        brain, speak, schedule = self.run_command("sara tell me to take a break at 11:30 p.m.")
        schedule.assert_called_once_with("tell me to take a break at 11:30PM")
        brain.assert_not_called()
        speak.assert_not_called()


if __name__ == "__main__":
    unittest.main()
