import json
import tempfile
import unittest
import logging
from pathlib import Path
from unittest.mock import patch

import user_memory
from Brain import brain


class UserMemoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.memory_path = Path(self.directory.name) / "user_preferences.json"
        self.legacy_path = Path(self.directory.name) / "legacy" / "user_preferences.json"
        self.path_patch = patch.object(user_memory, "MEMORY_PATH", self.memory_path)
        self.legacy_patch = patch.object(user_memory, "LEGACY_MEMORY_PATH", self.legacy_path)
        self.path_patch.start()
        self.legacy_patch.start()
        self.addCleanup(self.path_patch.stop)
        self.addCleanup(self.legacy_patch.stop)
        self.counter_patch = patch.object(user_memory, "_OBSERVED_DETAILS", user_memory.Counter())
        self.pending_patch = patch.object(user_memory, "_PENDING_LEARNING", None)
        self.declined_patch = patch.object(user_memory, "_DECLINED_DETAILS", set())
        self.counter_patch.start()
        self.pending_patch.start()
        self.declined_patch.start()
        self.addCleanup(self.counter_patch.stop)
        self.addCleanup(self.pending_patch.stop)
        self.addCleanup(self.declined_patch.stop)
        self.addCleanup(self.directory.cleanup)

    def test_memory_add_update_and_delete_preserve_existing_preferences(self):
        user_memory.remember_preference("Preferred tone", "concise")
        user_memory.remember_preference("name", "Sara User")
        user_memory.add_memory_entry("personal notes", "Project Orion uses Python.")
        entries = user_memory.list_memory_entries()
        self.assertEqual(len(entries), 3)

        user_memory.update_memory_entry("personal notes", 0, "Project Orion uses Python 3.12.")
        self.assertEqual(user_memory.format_personal_notes("Tell me about Project Orion"), "- Project Orion uses Python 3.12.")
        self.assertEqual(user_memory.format_preferences(), "- preferred tone: concise")
        self.assertEqual(user_memory.format_user_profile(), "- name: Sara User")

        self.assertTrue(user_memory.delete_memory_entry("personal notes", 0))
        self.assertEqual(user_memory.list_memory_entries(), [
            {"key": "preferred tone", "index": 0, "value": "concise"},
            {"key": "name", "index": 0, "value": "Sara User"},
        ])

    def test_legacy_preference_and_instruction_files_remain_readable(self):
        self.memory_path.write_text(
            json.dumps({"city": "London", "standing instructions": ["Use concise answers"]}),
            encoding="utf-8",
        )
        self.assertEqual(len(user_memory.list_memory_entries()), 2)
        self.assertIn("city: London", user_memory.format_user_profile())
        self.assertEqual(user_memory.format_preferences(), "- standing instructions: Use concise answers")

    def test_legacy_preferences_migrate_and_clearing_will_not_restore_them(self):
        self.legacy_path.parent.mkdir()
        self.legacy_path.write_text(json.dumps({"name": "Sara User"}), encoding="utf-8")
        self.assertEqual(user_memory.format_user_profile(), "- name: Sara User")
        self.assertTrue(self.memory_path.is_file())
        user_memory.forget_preferences()
        self.assertEqual(user_memory.list_memory_entries(), [])

    def test_invalid_memory_is_reported_instead_of_silently_discarded(self):
        self.memory_path.write_text("{invalid", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            with self.assertLogs(user_memory.LOGGER, level=logging.ERROR):
                user_memory.load_preferences()

    def test_memory_size_limits_and_missing_update_are_explicit(self):
        with self.assertRaisesRegex(ValueError, "1000 characters"):
            user_memory.add_memory_entry("notes", "x" * 1001)
        with self.assertRaises(KeyError):
            user_memory.update_memory_entry("missing", 0, "value")

    def test_relevant_local_notes_are_added_to_the_local_ai_prompt(self):
        response = unittest.mock.Mock()
        response.json.return_value = {"choices": [{"message": {"content": "A local reply."}}]}
        with (
            patch.object(brain.requests, "post", return_value=response) as post,
            patch.object(brain, "format_preferences", return_value=""),
            patch.object(brain, "format_user_profile", return_value="- name: Sara User"),
            patch.object(brain, "format_personal_notes", return_value="- Project Orion uses Python."),
            patch.object(brain, "format_knowledge", return_value=""),
            patch.object(brain, "retrieve_knowledge", return_value=[]),
        ):
            self.assertEqual(brain._ask_llm("What is Project Orion?"), "A local reply.")
        system_prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("Relevant personal notes:\n- Project Orion uses Python.", system_prompt)
        self.assertIn("User profile facts:\n- name: Sara User", system_prompt)

    def test_personal_detail_is_suggested_only_after_repetition_and_saved_after_consent(self):
        self.assertIsNone(user_memory.observe_user_detail("My name is Sara User"))
        proposal = user_memory.observe_user_detail("My name is Sara User")
        self.assertIn("your name is Sara User", proposal)
        self.assertEqual(user_memory.list_memory_entries(), [])

        self.assertIsNone(user_memory.resolve_learning_request("yes"))
        response = user_memory.resolve_learning_request("remember it")
        self.assertIn("Saved", response)
        self.assertEqual(user_memory.list_memory_entries(), [
            {"key": "name", "index": 0, "value": "Sara User"},
        ])

    def test_declined_personal_detail_is_not_saved_or_prompted_again(self):
        user_memory.observe_user_detail("I live in Toronto")
        proposal = user_memory.observe_user_detail("I live in Toronto")
        self.assertIn("your city is Toronto", proposal)
        self.assertIn("won't save", user_memory.resolve_learning_request("don't remember it"))
        self.assertEqual(user_memory.list_memory_entries(), [])
        self.assertIsNone(user_memory.observe_user_detail("I live in Toronto"))

    def test_sensitive_or_precise_location_is_not_proposed(self):
        for detail in (
            "I live in 123 Main Street",
            "My location is 10 Downing Street",
            "My name is",
            "What is my name?",
        ):
            self.assertIsNone(user_memory.observe_user_detail(detail))


if __name__ == "__main__":
    unittest.main()
