import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import extension_workflow


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self.content}}]}


class ExtensionWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.pending_path = root / "pending.json"
        self.extensions_dir = root / "extensions"
        self.paths = (
            patch.object(extension_workflow, "PENDING_PATH", self.pending_path),
            patch.object(extension_workflow, "EXTENSIONS_DIR", self.extensions_dir),
        )
        for path_patch in self.paths:
            path_patch.start()

    def tearDown(self):
        for path_patch in self.paths:
            path_patch.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def valid_spec():
        return {
            "name": "network_brief",
            "description": "Read a brief local network status.",
            "triggers": ["network brief"],
            "steps": [{"tool": "network_status"}],
        }

    def test_rejects_unknown_and_privileged_tool_ids(self):
        for tool in ("run_shell", "install_updates", "start_security_scan", [], {"name": "network_status"}):
            spec = self.valid_spec()
            spec["steps"] = [{"tool": tool}]
            validated, error = extension_workflow.validate_extension(spec)
            self.assertIsNone(validated)
            self.assertIsNotNone(error)

    def test_rejects_one_word_triggers(self):
        spec = self.valid_spec()
        spec["triggers"] = ["network"]
        validated, error = extension_workflow.validate_extension(spec)
        self.assertIsNone(validated)
        self.assertIn("two words", error)

    def test_proposal_requires_approval_before_extension_is_active(self):
        spec = self.valid_spec()
        response = FakeResponse(json.dumps(spec))
        with patch.object(extension_workflow.requests, "post", return_value=response):
            message = extension_workflow.create_extension_proposal("a short network report")

        self.assertIn("approve extension", message)
        self.assertTrue(self.pending_path.exists())
        self.assertFalse(self.extensions_dir.exists())

        with patch.dict(extension_workflow.TOOL_RUNNERS, {"network_status": lambda: "network is up"}):
            self.assertIn("Enabled extension", extension_workflow.approve_extension())
            self.assertEqual(extension_workflow.run_extension("network brief"), "network_brief: network is up")
        self.assertFalse(self.pending_path.exists())

    def test_reject_discards_pending_proposal(self):
        extension_workflow._write_json(
            self.pending_path,
            {"status": "proposed", "extension": self.valid_spec()},
        )
        self.assertIn("discarded", extension_workflow.reject_extension())
        self.assertFalse(self.pending_path.exists())

    def test_unknown_tools_cannot_be_proposed_by_model(self):
        spec = self.valid_spec()
        spec["steps"] = [{"tool": "delete_files"}]
        with patch.object(
            extension_workflow.requests,
            "post",
            return_value=FakeResponse(json.dumps(spec)),
        ):
            message = extension_workflow.create_extension_proposal("clean temporary files")
        self.assertIn("not available", message)
        self.assertFalse(self.pending_path.exists())

    def test_action_detection_does_not_capture_questions_or_existing_commands(self):
        self.assertTrue(extension_workflow.should_propose_extension("monitor my router uptime"))
        self.assertTrue(extension_workflow.should_propose_extension("could you build a tool for this"))
        self.assertFalse(extension_workflow.should_propose_extension("what is my network status"))
        self.assertFalse(extension_workflow.should_propose_extension("open chrome"))


if __name__ == "__main__":
    unittest.main()