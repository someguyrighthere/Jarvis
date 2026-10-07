import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Features.create_file import create_file


class CreateFileTests(unittest.TestCase):
    def test_creates_only_in_working_folder_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("Features.create_file.Path.cwd", return_value=root):
                self.assertEqual(
                    create_file("create a text file named report"),
                    "Created report.txt in SARA's working folder.",
                )
                existing = root / "existing.txt"
                existing.write_text("keep me", encoding="utf-8")
                self.assertEqual(
                    create_file("create text file named existing"),
                    "I did not overwrite the existing file existing.txt.",
                )
            self.assertEqual(existing.read_text(encoding="utf-8"), "keep me")

    def test_rejects_path_traversal_and_unsupported_file_types(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "Features.create_file.Path.cwd", return_value=Path(directory)
        ):
            self.assertIn("not valid", create_file("create text file named ..\\outside"))
            self.assertIn("specify its type", create_file("create file named report"))
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
