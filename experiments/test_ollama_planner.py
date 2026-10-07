"""Offline checks of bounded model repair; no Ollama server is required."""

import contextlib
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

from app_tree_prototype import AppTree, Capability, MockExecutor, MockOutcome, ResultStatus
from ollama_app_tree_check import LocalOllamaPlanner


def decision(**changes):
    fields = dict(kind="capability", task_type="weather", answer="",
                  capability_id="weather.lookup", capability_request="")
    fields.update(changes)
    return json.dumps(fields)


class OllamaPlannerTests(unittest.TestCase):
    def setUp(self):
        self.planner = LocalOllamaPlanner(model="test-model")
        self.available = {"weather.lookup": "Mock weather"}

    def test_valid_route_uses_one_attempt(self):
        with patch.object(self.planner, "_request", return_value=decision()) as request:
            intent = self.planner.choose("Weather?", self.available)
        self.assertEqual(intent.capability_id, "weather.lookup")
        self.assertEqual(request.call_count, 1)
        self.assertEqual(self.planner.last_attempt_count, 1)

    def test_invalid_route_gets_exactly_one_validated_repair(self):
        failures = [
            "not JSON", "null", "[]", '{"kind": "answer"}',
            decision(answer="contradictory"),
            decision(capability_id="unknown.app"),
            decision(task_type=""),
            decision(task_type=42),
            decision(kind="invented"),
            decision(kind="answer", answer="x" * 4001, capability_id=""),
            decision(kind="needs_capability", capability_id="", capability_request="x" * 1001),
        ]
        for invalid in failures:
            with self.subTest(invalid=invalid[:60]):
                with patch.object(self.planner, "_request", side_effect=[invalid, decision()]) as request:
                    with contextlib.redirect_stderr(io.StringIO()) as warnings:
                        intent = self.planner.choose("Weather?", self.available)
                self.assertEqual(intent.capability_id, "weather.lookup")
                self.assertEqual(request.call_count, 2)
                self.assertIn("nothing has executed", warnings.getvalue())
                messages = request.call_args.args[0]
                self.assertEqual(messages[1]["content"].split("User request: ")[1], "Weather?")
                self.assertIn("final attempt", messages[-1]["content"])

    def test_second_invalid_response_fails_closed(self):
        with patch.object(self.planner, "_request", return_value=decision(capability_id="unknown.app")) as request:
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, "after two attempts"):
                    self.planner.choose("Weather?", self.available)
        self.assertEqual(request.call_count, 2)

    def test_network_errors_are_not_repaired(self):
        for error in (URLError("offline"), TimeoutError("too slow")):
            with self.subTest(error=error):
                with patch("ollama_app_tree_check.urlopen", side_effect=error) as request:
                    with self.assertRaises(RuntimeError):
                        self.planner.choose("Weather?", self.available)
                self.assertEqual(request.call_count, 1)

    def test_invalid_server_envelope_fails_explicitly(self):
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"message": null}'
        with patch("ollama_app_tree_check.urlopen", return_value=response) as request:
            with self.assertRaisesRegex(RuntimeError, "missing a text message"):
                self.planner.choose("Weather?", self.available)
        self.assertEqual(request.call_count, 1)

    def test_repaired_route_does_not_bypass_approval_or_learning_confirmation(self):
        app = AppTree([Capability(
            "weather.lookup", "Mock weather", True, MockExecutor(MockOutcome(True, "Mock result")),
        )])
        with patch.object(self.planner, "_request", side_effect=[decision(answer="invalid"), decision()]):
            with contextlib.redirect_stderr(io.StringIO()):
                intent = self.planner.choose("Weather?", app.capability_descriptions())
        result = app.route("Weather?", intent)
        self.assertEqual(result.status, ResultStatus.AWAITING_APPROVAL)
        self.assertEqual(app.pending_confirmations, {})
        self.assertEqual(app.memory.successful_routes, {})
        executed = app.approve(result.approval_id)
        self.assertEqual(executed.status, ResultStatus.AWAITING_CONFIRMATION)
        self.assertEqual(app.memory.successful_routes, {})
        app.confirm_success(executed.confirmation_id, True)
        self.assertEqual(app.memory.successful_routes[("weather", "weather.lookup")], 1)


if __name__ == "__main__":
    unittest.main()
