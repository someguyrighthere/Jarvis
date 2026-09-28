import importlib
import unittest
from unittest.mock import patch

import Brain.brain as brain


class CapabilityGapTests(unittest.TestCase):
    """Sara should flag when she can't answer or act, and clear that flag once consumed."""

    def setUp(self):
        brain.pop_capability_gap()  # drain any leftover state between tests

    def test_pop_capability_gap_is_none_when_nothing_flagged(self):
        self.assertIsNone(brain.pop_capability_gap())

    def test_flagging_and_popping_returns_the_original_request_once(self):
        brain._flag_capability_gap("translate this ancient script")
        self.assertEqual(brain.pop_capability_gap(), "translate this ancient script")
        self.assertIsNone(brain.pop_capability_gap())

    def test_refusal_phrases_are_detected(self):
        refusals = [
            "I can't help with that request.",
            "I'm unable to control smart home devices.",
            "I don't have the ability to browse private files.",
            "That's outside of my capabilities right now.",
        ]
        for answer in refusals:
            with self.subTest(answer=answer):
                self.assertTrue(brain._looks_like_refusal(answer))

    def test_ordinary_answers_are_not_treated_as_refusals(self):
        self.assertFalse(brain._looks_like_refusal("Paris is the capital of France."))

    def test_final_fallback_flags_capability_gap_and_offers_a_tool(self):
        with patch.object(brain, "_ask_llm", return_value=None), \
             patch.object(brain, "search_web", return_value=[]), \
             patch.object(brain.requests, "get", side_effect=RuntimeError("offline")):
            response = brain.Main_Brain("what is the airspeed of an unladen swallow")
        self.assertIn("build a reusable tool", response)
        self.assertEqual(
            brain.pop_capability_gap(), "what is the airspeed of an unladen swallow"
        )

    def test_refusal_from_the_model_also_flags_a_capability_gap(self):
        with patch.object(
            brain, "_ask_llm", return_value="I'm unable to control your thermostat."
        ):
            response = brain.Main_Brain("turn down the thermostat")
        self.assertIn("build a reusable tool", response)
        self.assertEqual(brain.pop_capability_gap(), "turn down the thermostat")

    def test_normal_answers_do_not_flag_a_capability_gap(self):
        with patch.object(brain, "_ask_llm", return_value="The sky is blue."):
            brain.Main_Brain("what color is the sky")
        self.assertIsNone(brain.pop_capability_gap())


class PendingToolOfferTests(unittest.TestCase):
    """co_brain.py should let a plain yes/no resolve a pending tool-creation offer."""

    @classmethod
    def setUpClass(cls):
        cls.co_brain = importlib.import_module("co_brain")

    def setUp(self):
        self.co_brain._pop_tool_offer()  # drain any leftover state between tests

    def test_offer_is_returned_exactly_once(self):
        self.co_brain._offer_tool_for("control the smart thermostat")
        self.assertEqual(self.co_brain._pop_tool_offer(), "control the smart thermostat")
        self.assertIsNone(self.co_brain._pop_tool_offer())

    def test_affirmative_replies_match(self):
        for reply in ("yes", "yeah", "sure, go ahead", "please do it", "okay"):
            with self.subTest(reply=reply):
                self.assertIsNotNone(self.co_brain._AFFIRMATIVE_PATTERN.match(reply))

    def test_negative_replies_match(self):
        for reply in ("no", "nope", "not now", "no thanks"):
            with self.subTest(reply=reply):
                self.assertIsNotNone(self.co_brain._NEGATIVE_PATTERN.match(reply))

    def test_unrelated_replies_match_neither_pattern(self):
        for reply in ("what time is it", "open chrome", "tell me a joke"):
            with self.subTest(reply=reply):
                self.assertIsNone(self.co_brain._AFFIRMATIVE_PATTERN.match(reply))
                self.assertIsNone(self.co_brain._NEGATIVE_PATTERN.match(reply))


class AutomationMatchReportingTests(unittest.TestCase):
    """The automation catch-all must report whether it actually handled a command."""

    def test_recognized_browser_action_reports_handled(self):
        from Automation.tab_automation import perform_browser_action

        with patch("Automation.tab_automation.open_new_tab") as open_new_tab:
            self.assertTrue(perform_browser_action("open new tab"))
            open_new_tab.assert_called_once()

    def test_unrecognized_browser_action_reports_unhandled(self):
        from Automation.tab_automation import perform_browser_action

        self.assertFalse(perform_browser_action("juggle flaming torches"))

    def test_unrecognized_command_is_reported_as_unmatched(self):
        from Automation.Automation_Brain import Auto_main_brain

        with patch("Automation.Automation_Brain.perform_browser_action", return_value=False), \
             patch("Automation.Automation_Brain.perform_media_action", return_value=False), \
             patch("Automation.Automation_Brain.perform_scroll_action", return_value=False):
            self.assertFalse(Auto_main_brain("do something sara has never heard of"))

    def test_recognized_command_is_reported_as_matched(self):
        from Automation.Automation_Brain import Auto_main_brain

        with patch("Automation.Automation_Brain.check_percentage") as check_percentage:
            self.assertTrue(Auto_main_brain("check battery percentage"))
            check_percentage.assert_called_once()


if __name__ == "__main__":
    unittest.main()
