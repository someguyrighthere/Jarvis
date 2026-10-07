import os
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from experiments.typed_app_tree_test import TypedTestWindow, conversation_answer
from experiments.app_tree_prototype import Intent, RouteKind


class TypedTestTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"SARA_APP_TREE_MEMORY_ENABLED": "0"})
        environment.start()
        self.addCleanup(environment.stop)

    def test_clear_button_requires_confirmation_and_close_waits_for_save(self):
        root = tk.Tk()
        root.withdraw()
        ui = TypedTestWindow(root)
        try:
            with patch("experiments.typed_app_tree_test.messagebox.askyesno", return_value=False), \
                 patch("experiments.typed_app_tree_test.threading.Thread") as thread:
                ui.submit("clear workflows")
                thread.assert_not_called()
                self.assertFalse(ui.busy)
            with patch("experiments.typed_app_tree_test.messagebox.askyesno", return_value=True), \
                 patch("experiments.typed_app_tree_test.threading.Thread") as thread:
                ui.submit("clear workflows")
                thread.assert_called_once()
                self.assertTrue(ui.busy)
                ui.close()
                self.assertFalse(ui.closed)
            ui.busy = False
        finally:
            ui.close()

    def test_conversation_callback_checks_claims_without_external_search(self):
        with patch("Brain.brain._ask_llm", return_value="I've sorted your downloads."), \
             patch("Brain.brain._record_turn", side_effect=lambda request, answer: answer):
            self.assertIn("no verified tool result", conversation_answer("sort files"))

    def test_actual_window_controls_drive_the_staged_adapter(self):
        root = tk.Tk()
        root.withdraw()
        ui = TypedTestWindow(root)
        try:
            with patch.dict(os.environ, {"SARA_APP_TREE_MOCK_ENABLED": "1"}), \
                 patch("experiments.ollama_app_tree_check.LocalOllamaPlanner") as planner:
                planner.return_value.choose.return_value = Intent(
                    RouteKind.CAPABILITY, "reminder", capability_id="reminders.create",
                )
                ui.process("app tree test ask remind me to call alex")
                ui.poll()
                self.assertIn("Review mock request", ui.history.get("1.0", "end"))
                self.assertEqual(ui.stage._app.pending_confirmations, {})
                ui.process("app tree test approve")
                ui.poll()
                self.assertEqual(ui.stage._app.memory.successful_routes, {})
                ui.process("app tree test worked")
                ui.poll()
                self.assertEqual(ui.stage._app.memory.successful_routes[("reminder", "reminders.create")], 1)
        finally:
            ui.close()

    def test_model_error_is_visible(self):
        root = tk.Tk()
        root.withdraw()
        ui = TypedTestWindow(root)
        try:
            with patch.object(ui.stage, "handle", side_effect=RuntimeError("model unavailable")):
                ui.process("app tree test ask weather")
            ui.poll()
            self.assertIn("model unavailable", ui.history.get("1.0", "end"))
        finally:
            ui.close()

    def test_persistent_ui_reports_save_failure_and_retry_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch("mock_workflow_memory.MEMORY_PATH", Path(directory) / "mock.json"), \
             patch.dict(os.environ, {
                 "SARA_APP_TREE_MOCK_ENABLED": "1", "SARA_APP_TREE_MEMORY_ENABLED": "1",
             }):
            root = tk.Tk()
            root.withdraw()
            ui = TypedTestWindow(root)
            try:
                ui.process("app tree test weather")
                ui.poll()
                with patch("mock_workflow_memory.os.replace", side_effect=OSError("save denied")):
                    ui.process("app tree test worked")
                    ui.poll()
                self.assertIn("save denied", ui.history.get("1.0", "end"))
                self.assertTrue(ui.stage._app.pending_confirmations)
                ui.process("app tree test worked")
                ui.poll()
                self.assertIn("persisted mock-test-only", ui.history.get("1.0", "end"))
            finally:
                ui.close()
            restarted_root = tk.Tk()
            restarted_root.withdraw()
            restarted = TypedTestWindow(restarted_root)
            try:
                restarted.process("app tree test memory")
                restarted.poll()
                self.assertIn("weather.lookup", restarted.history.get("1.0", "end"))
                self.assertFalse(restarted.stage._app.pending_confirmations)
            finally:
                restarted.close()


if __name__ == "__main__":
    unittest.main()
