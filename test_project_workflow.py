import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import project_workflow


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self.content}}]}


class ProjectWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.projects_dir = root / "Documents" / "SaraProjects"
        self.pending_path = root / "LocalAppData" / "Sara" / "project_proposal.json"
        self.run_request_path = root / "LocalAppData" / "Sara" / "project_run_request.json"
        self.path_patches = (
            patch.object(project_workflow, "PROJECTS_DIR", self.projects_dir),
            patch.object(project_workflow, "PENDING_PATH", self.pending_path),
            patch.object(project_workflow, "RUN_REQUEST_PATH", self.run_request_path),
        )
        for path_patch in self.path_patches:
            path_patch.start()

    def tearDown(self):
        for path_patch in self.path_patches:
            path_patch.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def valid_project():
        return {
            "name": "reading-tracker",
            "summary": "A small reading tracker.",
            "files": [
                {"path": "index.html", "content": "<h1>Reading tracker</h1>"},
                {"path": "app.py", "content": "def main():\n    return 'ready'\n"},
            ],
        }

    def test_rejects_path_traversal_and_unsupported_files(self):
        for path in ("../outside.py", "C:/outside.py", ".git/config", "run.bat"):
            project = self.valid_project()
            project["files"] = [{"path": path, "content": "text"}]
            validated, error = project_workflow.validate_project(project)
            self.assertIsNone(validated, path)
            self.assertIsNotNone(error, path)

    def test_rejects_invalid_python_and_json(self):
        for path, content in (("app.py", "def broken(:\n pass"), ("data.json", "{")):
            project = self.valid_project()
            project["files"] = [{"path": path, "content": content}]
            validated, error = project_workflow.validate_project(project)
            self.assertIsNone(validated, path)
            self.assertIsNotNone(error, path)

    def test_proposal_does_not_write_files_until_approved(self):
        project = self.valid_project()
        response = FakeResponse(json.dumps(project))
        with patch.object(project_workflow.requests, "post", return_value=response):
            message = project_workflow.create_project_proposal("a small reading tracker")

        self.assertIn("approve project", message)
        self.assertTrue(self.pending_path.exists())
        self.assertFalse((self.projects_dir / project["name"]).exists())

        result = project_workflow.approve_project()
        self.assertIn("has not been run", result)
        self.assertEqual(
            (self.projects_dir / project["name"] / "app.py").read_text(encoding="utf-8"),
            project["files"][1]["content"],
        )
        self.assertFalse(self.pending_path.exists())

    def test_existing_project_is_never_overwritten(self):
        project = self.valid_project()
        destination = self.projects_dir / project["name"]
        destination.mkdir(parents=True)
        original = destination / "keep.txt"
        original.write_text("keep", encoding="utf-8")
        project_workflow._write_json(
            self.pending_path,
            {"status": "proposed", "project": project},
        )

        self.assertIn("didn't overwrite", project_workflow.approve_project())
        self.assertEqual(original.read_text(encoding="utf-8"), "keep")

    def test_reject_discards_pending_proposal(self):
        project_workflow._write_json(
            self.pending_path,
            {"status": "proposed", "project": self.valid_project()},
        )
        self.assertIn("discarded", project_workflow.reject_project())
        self.assertFalse(self.pending_path.exists())

    def test_app_requests_route_to_project_creation(self):
        with patch.object(project_workflow, "create_project_proposal", return_value="drafted") as create:
            self.assertEqual(
                project_workflow.handle_project_command("build a simple website for reading goals"),
                "drafted",
            )
        create.assert_called_once_with("reading goals")

    def test_run_requires_explicit_approval_and_is_one_time(self):
        project = self.valid_project()
        directory = self.projects_dir / project["name"]
        directory.mkdir(parents=True)
        (directory / "main.py").write_text(project["files"][1]["content"], encoding="utf-8")

        with patch.object(project_workflow, "_run_project_in_sandbox", return_value="sandbox output") as run:
            self.assertIn("approve run", project_workflow.request_project_run(project["name"]))
            run.assert_not_called()
            self.assertEqual(project_workflow.approve_project_run(), "sandbox output")
            run.assert_called_once()
            self.assertIn("no project run", project_workflow.approve_project_run())

    def test_run_approval_is_invalidated_if_source_changes(self):
        project = self.valid_project()
        directory = self.projects_dir / project["name"]
        directory.mkdir(parents=True)
        entry = directory / "main.py"
        entry.write_text("print('first version')", encoding="utf-8")
        project_workflow.request_project_run(project["name"])
        entry.write_text("print('changed after review')", encoding="utf-8")

        with patch.object(project_workflow, "_run_project_in_sandbox") as run:
            message = project_workflow.approve_project_run()
        self.assertIn("changed after review", message)
        run.assert_not_called()

    def test_run_requires_a_root_python_entry_point(self):
        project = self.valid_project()
        directory = self.projects_dir / project["name"]
        directory.mkdir(parents=True)
        (directory / "index.html").write_text("<h1>App</h1>", encoding="utf-8")

        self.assertIn("main.py or app.py", project_workflow.request_project_run(project["name"]))
        self.assertFalse(self.run_request_path.exists())

    def test_sandbox_fails_closed_when_wsl_is_unavailable(self):
        with patch.object(project_workflow.shutil, "which", return_value=None):
            message = project_workflow._run_project_in_sandbox(self.valid_project(), "app.py")
        self.assertIn("execution is disabled", message)

    def test_sandbox_runner_uses_wsl_without_shell_execution(self):
        project = self.valid_project()
        completed = project_workflow.subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps({"ok": True, "output": "safe"}), stderr=""
        )
        with (
            patch.object(project_workflow.shutil, "which", return_value="wsl.exe"),
            patch.object(project_workflow.subprocess, "run", return_value=completed) as run,
        ):
            result = project_workflow._run_project_in_sandbox(project, "app.py")
        self.assertIn("safe", result)
        args, kwargs = run.call_args
        self.assertIn("--distribution", args[0])
        self.assertFalse(kwargs.get("shell", False))
        self.assertIn("app.py", kwargs["input"])


if __name__ == "__main__":
    unittest.main()