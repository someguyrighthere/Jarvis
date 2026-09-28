import importlib
import unittest
from unittest.mock import patch

import Brain.brain as brain
import extension_workflow
import project_workflow
import self_update


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


class JsonExtractionTests(unittest.TestCase):
    """The small local model often wraps or precedes its JSON proposal with chatter
    or unescaped newlines; the proposal parsers must tolerate both."""

    def test_extracts_plain_json_with_no_wrapping(self):
        raw = '{"name": "demo", "description": "x"}'
        self.assertEqual(
            project_workflow._extract_json_object(raw),
            raw,
        )

    def test_extracts_json_from_fenced_code_block(self):
        raw = 'Sure, here you go:\n```json\n{"name": "demo"}\n```\nLet me know if that helps.'
        self.assertEqual(
            project_workflow._extract_json_object(raw),
            '{"name": "demo"}',
        )

    def test_extracts_json_with_leading_and_trailing_chatter_and_no_fence(self):
        raw = 'Sure! Here is the JSON you asked for: {"name": "demo"} Hope that helps!'
        self.assertEqual(
            project_workflow._extract_json_object(raw),
            '{"name": "demo"}',
        )

    def test_missing_json_object_raises_value_error(self):
        with self.assertRaises(ValueError):
            project_workflow._extract_json_object("I can't help with that right now.")

    def test_unclosed_json_object_raises_value_error(self):
        with self.assertRaises(ValueError):
            project_workflow._extract_json_object('{"name": "demo"')

    def test_tolerates_unescaped_newlines_inside_string_values(self):
        raw = '{"content": "line one\nline two"}'
        parsed = project_workflow.json.loads(
            project_workflow._extract_json_object(raw), strict=False
        )
        self.assertEqual(parsed["content"], "line one\nline two")

    def test_extension_workflow_extractor_handles_chatter_and_fences(self):
        raw = 'Here you go:\n```json\n{"name": "demo"}\n```'
        self.assertEqual(
            extension_workflow._extract_json_object(raw),
            '{"name": "demo"}',
        )

    def test_self_update_extractor_handles_chatter_and_fences(self):
        raw = 'Sure thing! ```json\n{"summary": "x", "content": "print(1)"}\n``` done.'
        self.assertEqual(
            self_update._extract_json_object(raw),
            '{"summary": "x", "content": "print(1)"}',
        )

    def test_project_proposal_recovers_from_chatter_wrapped_json(self):
        response_payload = {
            "choices": [
                {
                    "message": {
                        "content": (
                            "Sure, here's a small project for you!\n\n"
                            '```json\n{"name": "demo-app", "summary": "A demo.", '
                            '"files": [{"path": "main.py", "content": "print(1)"}]}\n```'
                        )
                    }
                }
            ]
        }
        with patch.object(project_workflow, "_read_json", return_value=None), \
             patch.object(project_workflow, "_write_json"), \
             patch.object(project_workflow.requests, "post") as mock_post:
            mock_post.return_value.raise_for_status = lambda: None
            mock_post.return_value.json = lambda: response_payload
            message = project_workflow.create_project_proposal("build me a demo app")
        self.assertIn("demo-app", message)
        self.assertNotIn("couldn't", message)


if __name__ == "__main__":
    unittest.main()
