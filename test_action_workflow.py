import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import action_workflow as actions
from Features.file_operations import rename_file


class ActionWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.pending_patch = patch.object(actions, "PENDING_ACTION_PATH", root / "pending.json")
        self.history_patch = patch.object(actions, "ACTION_HISTORY_PATH", root / "history.json")
        self.pending_patch.start()
        self.history_patch.start()
        self.addCleanup(self.pending_patch.stop)
        self.addCleanup(self.history_patch.stop)
        self.addCleanup(self.directory.cleanup)

    def test_action_must_be_reviewed_and_approved_before_one_time_dispatch(self):
        self.assertTrue(actions.requires_confirmation("close chrome"))
        self.assertIn("Unsaved work", actions.propose_action("close chrome"))
        pending = json.loads(actions.PENDING_ACTION_PATH.read_text(encoding="utf-8"))
        self.assertFalse(pending["approved"])

    def test_approved_command_is_consumed_only_for_exact_command(self):
        actions.propose_action("set volume level 25%")
        command = actions.approve_action()
        self.assertEqual(command, "set volume level 25%")
        self.assertFalse(actions.consume_approval("set volume level 50%"))
        self.assertTrue(actions.consume_approval("Set volume level 25%"))
        self.assertFalse(actions.consume_approval(command))

    def test_pending_action_can_be_cancelled_and_history_is_visible(self):
        actions.propose_action("send message on whatsapp")
        self.assertTrue(actions.cancel_action())
        self.assertFalse(actions.cancel_action())
        actions.record_dispatched_action("set volume level 25%", {"kind": "set volume", "value": 70})
        self.assertIn("set volume level 25% (dispatched)", actions.describe_action_history())

    def test_undo_restores_only_last_reversible_setting(self):
        actions.record_dispatched_action("send message on whatsapp", None)
        actions.record_dispatched_action("set volume level 25%", {"kind": "set volume", "value": 70})
        with patch("Features.set_get_volume.set_volume_windows") as set_volume:
            self.assertIn("restore the previous volume setting to 70%", actions.undo_last_action())
        set_volume.assert_called_once_with(70)
        history = json.loads(actions.ACTION_HISTORY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(history[-1]["status"], "undo_dispatched")

    def test_unconfirmed_commands_cannot_be_approved(self):
        self.assertFalse(actions.requires_confirmation("what is the weather"))
        self.assertIsNone(actions.approve_action())

    def test_invalid_volume_plan_is_rejected_before_approval(self):
        with self.assertRaisesRegex(ValueError, "between 0 and 100"):
            actions.propose_action("set volume level 120%")

    def test_rename_plan_checks_files_and_can_undo_after_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "before.txt"
            original.write_text("keep this content", encoding="utf-8")
            with patch("Features.file_operations.Path.cwd", return_value=root):
                plan = actions.propose_action("rename file before.txt to after.txt")
                self.assertIn("Verify 'after.txt' does not already exist", plan)
                approved = actions.approve_action()
                self.assertTrue(actions.consume_approval(approved))
                undo_state = actions.capture_undo_state(approved)
                self.assertEqual(rename_file(approved), "Renamed before.txt to after.txt.")
                actions.record_dispatched_action(approved, undo_state)
                self.assertIn("back to before.txt", actions.undo_last_action())
            self.assertEqual(original.read_text(encoding="utf-8"), "keep this content")


if __name__ == "__main__":
    unittest.main()
