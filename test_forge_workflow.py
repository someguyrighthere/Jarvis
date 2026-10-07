import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import forge_workflow
import project_workflow


class FakeProcess:
    def __init__(self, pid=4321, returncode=None):
        self.pid = pid
        self.returncode = returncode

    def poll(self):
        return self.returncode


class ForgeConfigTests(unittest.TestCase):
    def test_windows_bom_config_keeps_the_selected_model(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "config.toml").write_text('model = "qwen3:8b"\n', encoding="utf-8-sig")
            with patch.dict(os.environ, {"FORGE_HOME": directory}):
                self.assertEqual(forge_workflow._configured_forge_model(), "qwen3:8b")


class ForgeWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.local_data = root / "LocalAppData" / "Sara"
        self.workspaces = self.local_data / "forge_workspaces"
        self.forge_homes = self.local_data / "forge_homes"
        self.forge_pending = self.local_data / "forge_project.json"
        self.project_pending = self.local_data / "project_proposal.json"
        self.projects_dir = root / "Documents" / "SaraProjects"
        self.patches = (
            patch.object(forge_workflow, "LOCAL_DATA_DIR", self.local_data),
            patch.object(forge_workflow, "WORKSPACES_DIR", self.workspaces),
            patch.object(forge_workflow, "FORGE_HOMES_DIR", self.forge_homes),
            patch.object(forge_workflow, "PENDING_PATH", self.forge_pending),
            patch.object(forge_workflow, "_configured_forge_model", return_value=None),
            patch.object(project_workflow, "LOCAL_DATA_DIR", self.local_data),
            patch.object(project_workflow, "PROJECTS_DIR", self.projects_dir),
            patch.object(project_workflow, "PENDING_PATH", self.project_pending),
            patch.object(forge_workflow, "_PROCESS", None),
            patch.object(forge_workflow, "_find_forge", return_value="C:\\Forge\\forge.exe"),
            patch.object(forge_workflow.subprocess, "Popen"),
        )
        for item in self.patches:
            item.start()
        self.process = FakeProcess()
        forge_workflow.subprocess.Popen.return_value = self.process

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def start_project(self):
        with patch.object(forge_workflow, "_check_forge_version", return_value=None):
            result = forge_workflow.start_forge_project("make a reading tracker")
        self.assertIn("ask before edits", result)
        return json.loads(self.forge_pending.read_text(encoding="utf-8"))

    def test_start_uses_ask_mode_and_a_private_workspace(self):
        with patch.dict(os.environ, {"SARA_TEST_TOKEN": "do-not-pass"}):
            pending = self.start_project()
        args, kwargs = forge_workflow.subprocess.Popen.call_args

        self.assertEqual(args[0][0:2], ["C:\\Forge\\forge.exe", "--ask"])
        self.assertEqual(kwargs["cwd"], Path(pending["workspace"]))
        self.assertNotIn("SARA_TEST_TOKEN", kwargs["env"])
        self.assertEqual(Path(kwargs["env"]["FORGE_HOME"]).resolve(), (self.forge_homes / pending["project"]).resolve())
        self.assertEqual(kwargs["env"]["FORGE_WORKSPACE_ROOT"], str(Path(pending["workspace"])))
        self.assertEqual(kwargs["env"]["FORGE_PYTHON"],
                         os.environ.get("FORGE_PYTHON", forge_workflow.sys.executable))
        self.assertEqual(
            (self.forge_homes / pending["project"] / "config.toml").read_text(encoding="utf-8"),
            'mode = "ask"\nallow = []\ndeny = []\n',
        )
        self.assertTrue((Path(pending["workspace"]) / "AGENT.md").is_file())
        self.assertEqual(pending["status"], "running")

    def test_second_project_is_blocked_while_forge_is_running(self):
        self.start_project()
        result = forge_workflow.start_forge_project("make a budget planner")
        self.assertIn("already in progress", result)
        self.assertEqual(forge_workflow.subprocess.Popen.call_count, 1)

    def test_direct_forge_command_routes_the_build_request(self):
        with patch.object(forge_workflow, "start_forge_project", return_value="started") as start:
            result = forge_workflow.handle_forge_command("use forge to build a reading tracker")

        self.assertEqual(result, "started")
        start.assert_called_once_with("build a reading tracker")

    def test_old_forge_is_rejected_before_starting_a_session(self):
        completed = forge_workflow.subprocess.CompletedProcess(
            args=[], returncode=0, stdout="forge 1.4.0", stderr=""
        )
        with patch.object(forge_workflow.subprocess, "run", return_value=completed):
            error = forge_workflow._check_forge_version("forge.exe", {})

        self.assertIn("1.4.1 or newer", error)

    def test_review_imports_validated_files_into_existing_approval_flow(self):
        pending = self.start_project()
        workspace = Path(pending["workspace"])
        (workspace / "index.html").write_text("<h1>Reading tracker</h1>", encoding="utf-8")
        self.process.returncode = 0

        result = forge_workflow.review_forge_project()

        self.assertIn("approve project", result)
        proposal = project_workflow._read_json(self.project_pending)
        self.assertEqual(proposal["project"]["name"], pending["project"])
        self.assertEqual(proposal["project"]["files"][0]["path"], "index.html")
        self.assertEqual(json.loads(self.forge_pending.read_text(encoding="utf-8"))["status"], "ready")
        self.assertIn("has not been run", project_workflow.approve_project())
        self.assertTrue((self.projects_dir / pending["project"] / "index.html").is_file())

    def test_review_rejects_unsupported_files_without_creating_a_proposal(self):
        pending = self.start_project()
        workspace = Path(pending["workspace"])
        (workspace / "install.bat").write_text("echo unsafe", encoding="utf-8")
        self.process.returncode = 0

        result = forge_workflow.review_forge_project()

        self.assertIn("not allowed", result)
        self.assertIsNone(project_workflow._read_json(self.project_pending))

    def test_review_waits_until_forge_exits(self):
        self.start_project()
        self.assertIn("still working", forge_workflow.review_forge_project())
        self.assertIsNone(project_workflow._read_json(self.project_pending))


if __name__ == "__main__":
    unittest.main()
