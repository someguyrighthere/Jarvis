import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import project_workflow
import tool_workflow


class ToolWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.projects_dir = root / "Documents" / "SaraProjects"
        self.tools_dir = root / "LocalAppData" / "Sara" / "tools"
        self.pending_path = root / "LocalAppData" / "Sara" / "tool_proposal.json"
        self.project_pending_path = root / "LocalAppData" / "Sara" / "project_proposal.json"
        self.path_patches = (
            patch.object(project_workflow, "PROJECTS_DIR", self.projects_dir),
            patch.object(project_workflow, "PENDING_PATH", self.project_pending_path),
            patch.object(tool_workflow, "TOOLS_DIR", self.tools_dir),
            patch.object(tool_workflow, "PENDING_PATH", self.pending_path),
        )
        for path_patch in self.path_patches:
            path_patch.start()

    def tearDown(self):
        for path_patch in self.path_patches:
            path_patch.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def valid_manifest():
        return {
            "name": "temperature-helper",
            "description": "Convert temperature values between scales.",
            "triggers": ["convert temperature"],
            "entrypoint": "tool.py",
            "permissions": [],
        }

    def save_tool_project(self):
        project_dir = self.projects_dir / "temperature-helper"
        project_dir.mkdir(parents=True)
        (project_dir / "tool.py").write_text(
            "import json, os, socket, sys\n"
            "request = json.load(sys.stdin)['request']\n"
            "try:\n open('tool.py', 'a').close(); source_read_only = False\n"
            "except OSError:\n source_read_only = True\n"
            "try:\n open(os.path.join(os.environ['SARA_OUTPUT_DIR'], 'probe.txt'), 'w').write('ok'); output_writable = True\n"
            "except OSError:\n output_writable = False\n"
            "isolated = not os.path.exists('/mnt/c/Users') and not os.path.exists('/home/xarcy') and len(socket.if_nameindex()) == 1 and socket.if_nameindex()[0][1] == 'lo' and source_read_only and output_writable\n"
            "print(json.dumps({'text': 'sandbox-isolated' if isolated else 'sandbox-not-isolated'}))\n",
            encoding="utf-8",
        )
        (project_dir / "sara_tool.json").write_text(
            json.dumps(self.valid_manifest()),
            encoding="utf-8",
        )
        return project_dir

    def test_manifest_rejects_permissions_and_reserved_triggers(self):
        manifest = dict(self.valid_manifest(), permissions=["network"])
        validated, error = tool_workflow.validate_tool_manifest(manifest, "temperature-helper")
        self.assertIsNone(validated)
        self.assertIn("additional permissions", error)

        manifest = dict(self.valid_manifest(), triggers=["approve project"])
        validated, error = tool_workflow.validate_tool_manifest(manifest, "temperature-helper")
        self.assertIsNone(validated)
        self.assertIn("conflicts", error)

    def test_tool_project_generation_requires_valid_manifest(self):
        manifest = self.valid_manifest()
        generated = {
            "name": manifest["name"],
            "summary": "A temperature tool.",
            "files": [
                {"path": "tool.py", "content": "pass\n"},
                {"path": "sara_tool.json", "content": json.dumps(manifest)},
            ],
        }

        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": json.dumps(generated)}}]}

        with patch.object(project_workflow.requests, "post", return_value=Response()) as request:
            result = tool_workflow.create_tool_project("convert temperatures")
        self.assertIn("Drafted project", result)
        self.assertIn("empty list", request.call_args.kwargs["json"]["messages"][0]["content"])
        self.project_pending_path.unlink()

        invalid = dict(manifest, permissions=["network"])
        generated["files"][1]["content"] = json.dumps(invalid)
        with patch.object(project_workflow.requests, "post", return_value=Response()):
            result = tool_workflow.create_tool_project("convert temperatures")
        self.assertIn("cannot request additional permissions", result)
        self.assertFalse(self.project_pending_path.exists())

    def test_tool_creation_phrase_routes_to_tool_project_generator(self):
        with patch.object(tool_workflow, "create_tool_project", return_value="proposal") as create:
            self.assertEqual(tool_workflow.handle_tool_command("create a Sara tool to convert temperature"), "proposal")
        create.assert_called_once_with("convert temperature")

    def test_registration_requires_review_and_approval(self):
        self.save_tool_project()
        message = tool_workflow.propose_project_as_tool("temperature-helper")
        self.assertIn("Additional permissions: none", message)
        self.assertTrue(self.pending_path.exists())
        self.assertFalse(self.tools_dir.exists())
        self.assertIn("Permissions: none", tool_workflow.show_tool_proposal())

        self.assertIn("Enabled Sara tool", tool_workflow.approve_tool())
        self.assertTrue((self.tools_dir / "temperature-helper.json").exists())
        self.assertFalse(self.pending_path.exists())

    def test_registered_tool_runs_in_sandbox_with_only_request_text(self):
        self.save_tool_project()
        tool_workflow.propose_project_as_tool("temperature-helper")
        tool_workflow.approve_tool()
        sandbox_result = 'Project finished in the WSL sandbox. Output: {"text":"Converted safely."}'
        with patch.object(project_workflow, "_run_project_in_sandbox", return_value=sandbox_result) as run:
            result = tool_workflow.run_registered_tool("convert temperature 20 c to f")

        self.assertEqual(result, "Converted safely.")
        run.assert_called_once()
        args, kwargs = run.call_args
        self.assertEqual(args[1], "tool.py")
        self.assertEqual(kwargs["tool_input"], {"request": "convert temperature 20 c to f"})

    def test_changed_tool_source_is_disabled_until_reapproved(self):
        project_dir = self.save_tool_project()
        tool_workflow.propose_project_as_tool("temperature-helper")
        tool_workflow.approve_tool()
        (project_dir / "tool.py").write_text("print('changed')", encoding="utf-8")

        with patch.object(project_workflow, "_run_project_in_sandbox") as run:
            result = tool_workflow.run_registered_tool("convert temperature")
        self.assertIn("source changed", result)
        run.assert_not_called()

    def test_duplicate_triggers_are_rejected(self):
        self.save_tool_project()
        tool_workflow.propose_project_as_tool("temperature-helper")
        tool_workflow.approve_tool()
        other = dict(self.valid_manifest(), name="other-helper")
        second_project = self.projects_dir / "other-helper"
        second_project.mkdir()
        (second_project / "tool.py").write_text("pass\n", encoding="utf-8")
        (second_project / "sara_tool.json").write_text(json.dumps(other), encoding="utf-8")
        project, error = project_workflow._load_saved_project("other-helper")
        self.assertIsNone(error)
        project_workflow._write_json(
            self.pending_path,
            {
                "status": "proposed",
                "project": "other-helper",
                "fingerprint": project_workflow._project_fingerprint(project),
                "manifest": other,
            },
        )

        self.assertIn("already used", tool_workflow.approve_tool())
        self.assertFalse((self.tools_dir / "other-helper.json").exists())

    def test_invalid_tool_output_is_not_returned_as_assistant_text(self):
        self.save_tool_project()
        tool_workflow.propose_project_as_tool("temperature-helper")
        tool_workflow.approve_tool()
        with patch.object(
            project_workflow,
            "_run_project_in_sandbox",
            return_value='Project finished in the WSL sandbox. Output: {"text":"ok","run":"extra"}',
        ):
            result = tool_workflow.run_registered_tool("convert temperature")
        self.assertIn("invalid response", result)

    @unittest.skipUnless(
        os.getenv("SARA_RUN_WSL_INTEGRATION") == "1",
        "set SARA_RUN_WSL_INTEGRATION=1 to run the WSL Bubblewrap integration test",
    )
    def test_real_wsl_tool_execution_has_no_host_mount_or_network(self):
        self.save_tool_project()
        tool_workflow.propose_project_as_tool("temperature-helper")
        tool_workflow.approve_tool()
        result = tool_workflow.run_registered_tool("convert temperature")
        self.assertEqual(result, "sandbox-isolated")


if __name__ == "__main__":
    unittest.main()