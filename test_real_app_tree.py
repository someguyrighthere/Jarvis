from contextlib import ExitStack
from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from experiments.app_tree_prototype import Intent, RouteKind
import forge_workflow as forge
import project_workflow as projects
import real_reminders as reminders
import task_workflow
import tool_workflow as tools
from real_app_tree import RealAppTree
from workflow_memory import WorkflowMemory


class RealTreeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for module, name, path in (
            (reminders, "DB_PATH", self.root / "reminders.db"),
            (task_workflow, "TASK_DB_PATH", self.root / "tasks.db"),
            (projects, "PROJECTS_DIR", self.root / "projects"),
            (projects, "PENDING_PATH", self.root / "proposal.json"),
            (projects, "RUN_REQUEST_PATH", self.root / "run.json"),
            (tools, "TOOLS_DIR", self.root / "tools"),
            (forge, "PENDING_PATH", self.root / "forge.json"),
            (forge, "WORKSPACES_DIR", self.root / "workspaces"),
        ):
            self.stack.enter_context(patch.object(module, name, path))
        self.tree = RealAppTree(WorkflowMemory(self.root / "workflows.db"))
        self.answerer = Mock(return_value="Personality-preserving explanation.")
        self.planner = self.stack.enter_context(patch("real_app_tree.LocalOllamaPlanner"))
        self.planner.return_value.choose.return_value = Intent(RouteKind.ANSWER, "knowledge", answer="discard")

    def command(self, text):
        return self.tree.handle("app tree " + text, self.answerer)

    def test_real_task_requires_approval_and_explicit_confirmation(self):
        self.command("ask add task call Alex")
        self.assertEqual(task_workflow.get_open_tasks()[1], 0)
        self.assertIsNone(self.tree.handle("yes", self.answerer))
        self.command("approve")
        self.assertEqual(task_workflow.get_open_tasks()[1], 1)
        self.assertEqual(self.tree.memory.entries(), [])
        self.command("not sure")
        self.assertEqual(self.tree.memory.entries(), [])
        self.command("worked")
        self.assertEqual(self.tree.memory.entries()[0][3], 1)
        self.command("worked")
        self.assertEqual(self.tree.memory.entries()[0][3], 1)
        restarted = RealAppTree(WorkflowMemory(self.root / "workflows.db"))
        self.assertIn("Nothing has run", restarted.route("add task second task", self.answerer))
        self.assertIsNone(restarted.confirmation)
        self.assertEqual(task_workflow.get_open_tasks()[1], 1)

    def test_failed_confirmation_and_rejection_do_not_learn(self):
        self.command("ask add task example")
        self.command("reject")
        self.assertEqual(task_workflow.get_open_tasks()[1], 0)
        self.command("ask add task example")
        self.command("approve")
        self.command("failed")
        self.assertEqual(self.tree.memory.entries(), [])

    def test_persistence_failure_retains_confirmation_without_reexecuting(self):
        self.command("ask add task example")
        self.command("approve")
        with patch.object(self.tree.memory, "record", side_effect=sqlite3.OperationalError("locked")):
            with self.assertRaises(sqlite3.OperationalError):
                self.command("worked")
        self.assertIsNotNone(self.tree.confirmation)
        self.command("worked")
        self.assertEqual(task_workflow.get_open_tasks()[1], 1)
        self.assertEqual(self.tree.memory.entries()[0][3], 1)

    def test_reminder_is_real_date_specific_and_approval_gated(self):
        preview = self.command("ask remind me to call Alex tomorrow at 9 AM")
        self.assertIn("09:00", preview)
        self.assertEqual(reminders.pending_reminders(), [])
        result = self.command("approve")
        self.assertIn("Scheduled local reminder", result)
        self.assertIn("SARA must be running", result)
        saved = reminders.pending_reminders()
        self.assertEqual(saved[0][1], "call Alex")
        self.assertEqual(datetime.fromisoformat(saved[0][2]).date(), datetime.now().date() + timedelta(days=1))
        self.assertEqual(self.tree.memory.entries(), [])
        self.command("worked")
        self.assertEqual(self.tree.memory.entries()[0][1], "reminders.create")

    def test_ambiguous_reminder_never_guesses_or_saves(self):
        for request in ("remind me to call Alex tomorrow", "please create a reminder"):
            with self.subTest(request=request), self.assertRaisesRegex(ValueError, "exact local time"):
                self.command("ask " + request)
        self.assertIsNone(self.tree.pending)
        self.assertEqual(reminders.pending_reminders(), [])
        self.planner.return_value.choose.assert_not_called()

    def test_actual_file_creation_never_runs_before_approval(self):
        with patch("Features.create_file.Path.cwd", return_value=self.root):
            self.command("ask create text file named example")
            self.assertFalse((self.root / "example.txt").exists())
            self.command("approve")
            self.assertTrue((self.root / "example.txt").exists())
            self.command("failed")
            self.command("ask create text file named example")
            self.assertIn("did not overwrite", self.command("approve"))
            self.assertIsNone(self.tree.confirmation)
            self.assertEqual(self.tree.memory.entries(), [])

    def test_answers_use_existing_personality_not_planner_text(self):
        self.assertEqual(self.command("ask explain photosynthesis"), "Personality-preserving explanation.")
        self.answerer.assert_called_once_with("explain photosynthesis")
        self.assertEqual(self.tree.memory.entries(), [])
        self.planner.assert_called_once_with(model="qwen3:8b", live=True)

    def test_weather_failure_never_learns_and_discloses_network_service(self):
        self.assertIn("wttr.in", self.command("ask weather in Boston"))
        with patch("Weather_Check.check_weather.get_weather_by_address", return_value="I could not retrieve the weather right now."):
            self.assertIn("No route was learned", self.command("approve"))
        self.assertIsNone(self.tree.confirmation)

    def make_build(self):
        self.planner.return_value.choose.return_value = Intent(
            RouteKind.NEEDS_CAPABILITY, "temperature", capability_request="untrusted model request",
        )
        self.command("ask convert temperature 20 C to F")
        manifest = {
            "name": "temperature-helper", "description": "Convert temperatures.",
            "triggers": ["convert temperature"], "entrypoint": "tool.py", "permissions": [],
        }
        workspace = forge.WORKSPACES_DIR / manifest["name"]
        workspace.mkdir(parents=True)
        (workspace / "tool.py").write_text(
            "import json, sys\nrequest = json.load(sys.stdin)['request']\n"
            "print(json.dumps({'text': '68 F'}))\n",
        )
        (workspace / "sara_tool.json").write_text(json.dumps(manifest))

        def start(request, *, tool_mode):
            self.assertTrue(tool_mode)
            self.assertEqual(request, "convert temperature 20 C to F")
            projects._write_json(forge.PENDING_PATH, {
                "status": "running", "request": request, "project": manifest["name"],
                "workspace": str(workspace), "pid": 123,
            })
            return "Forge started."
        with patch.object(forge, "start_forge_project", side_effect=start):
            self.command("approve build")
        return manifest

    def test_forge_build_review_source_first_run_and_confirmed_learning(self):
        with patch.object(forge, "start_forge_project") as start:
            self.planner.return_value.choose.return_value = Intent(
                RouteKind.NEEDS_CAPABILITY, "missing", capability_request="model generated content",
            )
            self.command("ask unsupported request")
            start.assert_not_called()
            self.command("reject")
        self.make_build()
        with patch.object(forge, "_forge_process_status", return_value="finished"):
            self.assertIn("ready for review", self.command("review build"))
        self.assertIn("Separate first-run approval", self.command("approve project"))
        with patch.object(projects, "_run_project_in_sandbox",
                          return_value='Project finished in the WSL sandbox. Output: {"text":"68 F"}') as run:
            self.assertIn("separate", self.command("approve"))
            run.assert_not_called()
            self.assertIn("68 F", self.command("approve run"))
            run.assert_called_once()
        self.assertTrue((tools.TOOLS_DIR / "temperature-helper.json").exists())
        self.assertEqual(self.tree.memory.entries(), [])
        self.command("worked")
        self.assertEqual(self.tree.memory.entries()[0][1], "tool.temperature-helper")
        self.assertTrue(self.tree.memory.entries()[0][2])
        self.planner.return_value.choose.return_value = Intent(RouteKind.CAPABILITY, "temperature", capability_id="tool.temperature-helper")
        self.assertIn("Nothing has run", self.command("ask convert temperature 30 C to F"))

    def test_changed_generated_source_is_rejected_before_first_run(self):
        self.make_build()
        with patch.object(forge, "_forge_process_status", return_value="finished"):
            self.command("review build")
        self.command("approve project")
        (projects.PROJECTS_DIR / "temperature-helper" / "tool.py").write_text("print('changed')")
        with patch.object(projects, "_run_project_in_sandbox") as run:
            self.assertIn("source changed", self.command("approve run"))
            run.assert_not_called()
        self.assertEqual(self.tree.memory.entries(), [])
        self.assertEqual(tools.registered_tool_records(), [])

    def test_invalid_generated_output_is_not_enabled_or_learned(self):
        self.make_build()
        with patch.object(forge, "_forge_process_status", return_value="finished"):
            self.command("review build")
        self.command("approve project")
        with patch.object(projects, "_run_project_in_sandbox",
                          return_value='Project finished in the WSL sandbox. Output: {"ok":true}'):
            self.assertIn("invalid response", self.command("approve run"))
        self.assertIsNone(self.tree.confirmation)
        self.assertFalse(tools.TOOLS_DIR.exists())

    def test_failed_build_approval_cannot_be_reused(self):
        self.planner.return_value.choose.return_value = Intent(
            RouteKind.NEEDS_CAPABILITY, "missing", capability_request="unsupported request",
        )
        self.command("ask unsupported request")
        with patch.object(forge, "start_forge_project", return_value="Forge unavailable") as start:
            self.assertIn("approval was consumed", self.command("approve build"))
            self.assertIn("No proposed Forge build", self.command("approve build"))
            start.assert_called_once()
        self.assertEqual(self.tree.memory.entries(), [])

    def test_mock_and_real_namespaces_do_not_overlap(self):
        self.assertIsNone(self.tree.handle("app tree test approve", self.answerer))
        self.assertIsNone(self.tree.handle("approve action", self.answerer))
        self.assertIn("No real operation", self.command("approve"))

    def test_review_can_reattach_a_finished_build_after_restart_without_approval(self):
        self.make_build()
        self.tree = RealAppTree(WorkflowMemory(self.root / "workflows.db"))
        with patch.object(forge, "_forge_process_status", return_value="finished"):
            self.assertIn("ready for review", self.command("review build"))
        self.assertIsNone(self.tree.pending)
        self.assertIn("source approval", self.command("approve"))

    def test_generated_request_is_actually_executed_in_wsl_when_opted_in(self):
        import os
        if os.getenv("SARA_RUN_WSL_INTEGRATION") != "1":
            self.skipTest("set SARA_RUN_WSL_INTEGRATION=1 for actual generated tool execution")
        self.make_build()
        with patch.object(forge, "_forge_process_status", return_value="finished"):
            self.command("review build")
        self.command("approve project")
        result = self.command("approve run")
        self.assertIn("68 F", result)
        self.assertIsNotNone(self.tree.confirmation)
        self.assertEqual(self.tree.memory.entries(), [])

    def test_typed_real_window_uses_real_stage_not_mock_executor(self):
        import tkinter as tk
        from experiments.typed_app_tree_test import TypedTestWindow

        root = tk.Tk()
        root.withdraw()
        with patch("real_reminders.watch_reminders"):
            ui = TypedTestWindow(root, live=True)
        ui.stage = self.tree
        try:
            ui.process("app tree ask add task real typed task")
            ui.poll()
            self.assertEqual(task_workflow.get_open_tasks()[1], 0)
            ui.process("app tree approve")
            ui.poll()
            self.assertEqual(task_workflow.get_open_tasks()[1], 1)
            self.assertIn("Added task", ui.history.get("1.0", "end"))
            ui.process("app tree worked")
            ui.poll()
            self.assertEqual(self.tree.memory.entries()[0][3], 1)
        finally:
            ui.close()


class ReminderDeliveryTests(unittest.TestCase):
    def test_two_deliverers_cannot_announce_the_same_reminder(self):
        import threading

        with tempfile.TemporaryDirectory() as directory, patch.object(reminders, "DB_PATH", Path(directory) / "reminders.db"):
            reminders.create_reminder("call Alex", datetime(2020, 1, 1))
            announced = threading.Event()
            release = threading.Event()

            def announce(text):
                announced.set()
                release.wait(5)

            thread = threading.Thread(target=reminders.deliver_due, args=(announce,))
            thread.start()
            try:
                self.assertTrue(announced.wait(5))
                duplicate = Mock()
                reminders.deliver_due(duplicate)
                duplicate.assert_not_called()
            finally:
                release.set()
                thread.join(5)
            self.assertEqual(reminders.pending_reminders(), [])

    def test_delivery_persists_and_is_one_time(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(reminders, "DB_PATH", Path(directory) / "reminders.db"):
            now = datetime(2026, 10, 7, 11, 0)
            reminders.create_reminder("call Alex", now - timedelta(minutes=1))
            notify = Mock()
            reminders.deliver_due(notify, now)
            reminders.deliver_due(notify, now)
            notify.assert_called_once_with("Reminder: call Alex")
            self.assertEqual(reminders.pending_reminders(), [])

    def test_delivery_failure_is_retryable(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(reminders, "DB_PATH", Path(directory) / "reminders.db"):
            reminders.create_reminder("call Alex", datetime(2020, 1, 1))
            with self.assertRaises(RuntimeError):
                reminders.deliver_due(Mock(side_effect=RuntimeError("speaker unavailable")))
            self.assertEqual(len(reminders.pending_reminders()), 1)
            reminders.deliver_due(Mock())
            self.assertEqual(reminders.pending_reminders(), [])

    def test_parser_rejects_invalid_and_past_explicit_times(self):
        now = datetime(2026, 10, 7, 11, 0)
        for request in (
            "remind me to call at 25:00", "remind me to call tomorrow at 13 PM",
            "remind me to call tomorrow at 9:70 AM", "remind me to call today at 9 AM",
            "remind me to call tomorrow at 9",
        ):
            with self.subTest(request=request), self.assertRaises(ValueError):
                reminders.parse_request(request, now)


if __name__ == "__main__":
    unittest.main()
