import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app_tree_stage import MockAppTreeStage
from mock_workflow_memory import MockWorkflowMemory


class MockWorkflowMemoryTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "mock_workflows.json"
        self.environment = patch.dict(os.environ, {
            "SARA_APP_TREE_MOCK_ENABLED": "1", "SARA_APP_TREE_MEMORY_ENABLED": "1",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.memory_path = patch("mock_workflow_memory.MEMORY_PATH", self.path)
        self.memory_path.start()
        self.addCleanup(self.memory_path.stop)

    def command(self, stage, suffix):
        return stage.handle("app tree test " + suffix)

    def test_explicit_success_survives_restart_but_pending_decisions_do_not(self):
        first = MockAppTreeStage()
        self.command(first, "weather")
        self.assertFalse(self.path.exists())
        self.command(first, "not sure")
        self.assertFalse(self.path.exists())
        self.command(first, "worked")
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved["scope"], "mock_test_only")
        self.assertEqual(saved["routes"][0]["confirmed_successes"], 1)
        self.command(first, "reminder")
        second = MockAppTreeStage()
        self.assertIn("Persisted MOCK-TEST-ONLY", self.command(second, "memory"))
        self.assertIn("no mock action", self.command(second, "approve"))
        self.assertEqual(second._app.pending, {})
        result = self.command(second, "weather")
        self.assertIn("Previously confirmed", result)
        self.assertEqual(second._app.memory.successful_routes[("weather", "weather.lookup")], 1)

    def test_declined_failed_and_rejected_tasks_never_save(self):
        stage = MockAppTreeStage()
        self.command(stage, "weather")
        self.command(stage, "failed")
        self.command(stage, "reminder")
        self.command(stage, "reject")
        self.command(stage, "failure")
        self.command(stage, "missing app")
        self.assertFalse(self.path.exists())

    def test_reset_preserves_saved_routes_clear_deletes_only_mock_workflows(self):
        personal = self.path.parent / "user_preferences.json"
        personal.write_text('{"name": "test user"}')
        stage = MockAppTreeStage()
        self.command(stage, "weather")
        self.command(stage, "worked")
        self.command(stage, "reset")
        self.assertIn("weather.lookup", self.command(stage, "memory"))
        self.command(stage, "clear workflows")
        self.assertEqual(MockWorkflowMemory(self.path).successful_routes, {})
        self.assertEqual(personal.read_text(), '{"name": "test user"}')
        self.assertIsNone(stage._app)

    def test_write_failure_preserves_file_and_confirmation_for_explicit_retry(self):
        stage = MockAppTreeStage()
        self.command(stage, "weather")
        self.command(stage, "worked")
        original = self.path.read_bytes()
        self.command(stage, "weather")
        with patch("mock_workflow_memory.os.replace", side_effect=OSError("disk denied")):
            with self.assertRaisesRegex(OSError, "disk denied"):
                self.command(stage, "worked")
        self.assertEqual(self.path.read_bytes(), original)
        self.assertTrue(stage._app.pending_confirmations)
        self.assertEqual(stage._app.memory.successful_routes[("weather", "weather.lookup")], 1)
        self.assertFalse(list(self.path.parent.glob("*.tmp")))
        self.command(stage, "worked")
        self.assertEqual(MockWorkflowMemory(self.path).successful_routes[("weather", "weather.lookup")], 2)
        self.command(stage, "worked")
        self.assertEqual(MockWorkflowMemory(self.path).successful_routes[("weather", "weather.lookup")], 2)

    def test_separate_instances_merge_confirmations_and_observe_clear(self):
        first, second = MockWorkflowMemory(self.path), MockWorkflowMemory(self.path)
        first.record_success("Weather", "weather.lookup")
        second.record_success("weather", "weather.lookup")
        self.assertEqual(MockWorkflowMemory(self.path).successful_routes[("weather", "weather.lookup")], 2)
        second.clear()
        self.assertEqual(first.preferred_capability("weather", {"weather.lookup"}), "")

    def test_corrupt_or_wrong_scope_memory_is_not_overwritten(self):
        invalid = [
            "{", "[]",
            json.dumps({"version": 1, "scope": "real_apps", "routes": []}),
            json.dumps({"version": True, "scope": "mock_test_only", "routes": []}),
            json.dumps({"version": 1, "scope": "mock_test_only", "routes": [
                {"task_type": "weather", "capability_id": [], "confirmed_successes": 1},
            ]}),
        ]
        for text in invalid:
            with self.subTest(text=text):
                self.path.write_text(text)
                with self.assertRaises(ValueError):
                    MockWorkflowMemory(self.path)
                self.assertEqual(self.path.read_text(), text)

    def test_clear_can_recover_a_corrupt_store(self):
        self.path.write_text("broken")
        stage = MockAppTreeStage()
        with self.assertRaises(ValueError):
            self.command(stage, "memory")
        self.command(stage, "clear workflows")
        self.assertEqual(MockWorkflowMemory(self.path).successful_routes, {})

    def test_concurrent_processes_do_not_lose_confirmations(self):
        script = (
            "from pathlib import Path; import sys; "
            "from mock_workflow_memory import MockWorkflowMemory; "
            "memory = MockWorkflowMemory(Path(sys.argv[1])); "
            "[memory.record_success('weather', 'weather.lookup') for _ in range(10)]"
        )
        processes = []
        try:
            for _ in range(3):
                processes.append(subprocess.Popen(
                    [sys.executable, "-c", script, str(self.path)],
                    cwd=Path(__file__).parent, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                ))
            for process in processes:
                output, error = process.communicate(timeout=30)
                self.assertEqual(process.returncode, 0, (output, error))
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
        self.assertEqual(MockWorkflowMemory(self.path).successful_routes[("weather", "weather.lookup")], 30)

    def test_disabled_and_normal_commands_never_open_store(self):
        self.path.write_text("broken")
        stage = MockAppTreeStage()
        self.assertIsNone(stage.handle("weather"))
        with patch.dict(os.environ, {"SARA_APP_TREE_MOCK_ENABLED": "0"}):
            self.assertIn("disabled", self.command(stage, "memory"))
        self.assertEqual(self.path.read_text(), "broken")

    def test_default_memory_remains_temporary(self):
        with patch.dict(os.environ, {"SARA_APP_TREE_MEMORY_ENABLED": "0"}):
            stage = MockAppTreeStage()
            self.command(stage, "weather")
            self.command(stage, "worked")
            self.assertFalse(self.path.exists())
            self.assertNotIsInstance(stage._app.memory, MockWorkflowMemory)

    def test_persisted_reminder_still_requires_fresh_approval(self):
        stage = MockAppTreeStage()
        self.command(stage, "reminder")
        self.command(stage, "approve")
        self.command(stage, "worked")
        restarted = MockAppTreeStage()
        self.assertIn("Nothing has run", self.command(restarted, "reminder"))
        self.assertTrue(restarted._app.pending)
        self.assertFalse(restarted._app.pending_confirmations)
        self.assertIn("no mock result", self.command(restarted, "worked"))


if __name__ == "__main__":
    unittest.main()
