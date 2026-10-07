import sys
import unittest
from unittest.mock import patch

import launcher


class LauncherTests(unittest.TestCase):
    def test_packaged_real_app_tree_entrypoint(self):
        with patch.object(sys, "argv", ["Jarvis.exe", "--app-tree"]), \
             patch("experiments.typed_app_tree_test.main", return_value=0) as tree, \
             patch("desktop_app.main") as hud:
            self.assertEqual(launcher.main(), 0)
            tree.assert_called_once_with(live=True)
            hud.assert_not_called()

    def test_packaged_typed_test_does_not_launch_normal_hud(self):
        with patch.object(sys, "argv", ["Jarvis.exe", "--app-tree-test"]), \
             patch("experiments.typed_app_tree_test.main", return_value=0) as typed, \
             patch("desktop_app.main") as hud:
            self.assertEqual(launcher.main(), 0)
            typed.assert_called_once_with()
            hud.assert_not_called()

    def test_default_still_launches_normal_hud(self):
        with patch.object(sys, "argv", ["Jarvis.exe"]), \
             patch("desktop_app.main", return_value=0) as hud:
            self.assertEqual(launcher.main(), 0)
            hud.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
