import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import knowledge


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.path_patch = patch.object(knowledge, "KNOWLEDGE_PATH", self.root / "Sara" / "knowledge.json")
        self.legacy_patch = patch.object(knowledge, "LEGACY_KNOWLEDGE_PATH", self.root / "old" / "knowledge.json")
        self.path_patch.start()
        self.legacy_patch.start()
        self.addCleanup(self.path_patch.stop)
        self.addCleanup(self.legacy_patch.stop)
        self.addCleanup(self.directory.cleanup)

    def test_knowledge_persists_in_data_directory_and_survives_reload(self):
        self.assertTrue(knowledge.save_knowledge("SARA's local memory test"))
        self.assertTrue(knowledge.KNOWLEDGE_PATH.is_file())
        self.assertEqual(knowledge.retrieve_knowledge("local memory"), [
            {
                "content": "SARA's local memory test",
                "source": "user",
                "saved_at": json.loads(knowledge.KNOWLEDGE_PATH.read_text(encoding="utf-8"))[0]["saved_at"],
            },
        ])

    def test_legacy_knowledge_is_migrated_to_persistent_storage(self):
        knowledge.LEGACY_KNOWLEDGE_PATH.parent.mkdir(parents=True)
        knowledge.LEGACY_KNOWLEDGE_PATH.write_text(
            json.dumps([{"content": "legacy memory survives", "source": "user"}]),
            encoding="utf-8",
        )
        self.assertEqual(knowledge.retrieve_knowledge("legacy memory")[0]["content"], "legacy memory survives")
        self.assertTrue(knowledge.KNOWLEDGE_PATH.is_file())

    def test_clearing_migrated_knowledge_does_not_restore_legacy_entries(self):
        knowledge.LEGACY_KNOWLEDGE_PATH.parent.mkdir(parents=True)
        knowledge.LEGACY_KNOWLEDGE_PATH.write_text(
            json.dumps([{"content": "old memory", "source": "user"}]),
            encoding="utf-8",
        )
        self.assertEqual(knowledge.retrieve_knowledge("old memory")[0]["content"], "old memory")
        knowledge.clear_knowledge()
        self.assertEqual(knowledge.retrieve_knowledge("old memory"), [])

    def test_corrupt_knowledge_is_reported(self):
        knowledge.KNOWLEDGE_PATH.parent.mkdir(parents=True)
        knowledge.KNOWLEDGE_PATH.write_text("{bad", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            with self.assertLogs(knowledge.LOGGER, level=logging.ERROR):
                knowledge.retrieve_knowledge("anything")


if __name__ == "__main__":
    unittest.main()
