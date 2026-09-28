import unittest
from unittest.mock import patch

import system_admin


class SystemCommandTests(unittest.TestCase):
    def test_routes_hardware_status(self):
        with patch.object(system_admin, "get_system_status", return_value="hardware report") as report:
            self.assertEqual(system_admin.handle_system_command("system status"), "hardware report")
        report.assert_called_once_with()

    def test_routes_security_scan_only_for_explicit_scan_command(self):
        with patch.object(system_admin, "start_security_scan", return_value="scan started") as scan:
            self.assertEqual(system_admin.handle_system_command("scan for threats"), "scan started")
            self.assertIsNone(system_admin.handle_system_command("check security threats"))
        scan.assert_called_once_with()

    def test_updates_only_run_for_explicit_update_command(self):
        with patch.object(system_admin, "install_updates", return_value="update result") as install:
            self.assertEqual(
                system_admin.handle_system_command("update drivers and software"),
                "update result",
            )
        install.assert_called_once_with()
        with patch.object(system_admin, "check_for_updates", return_value="update inventory") as check:
            self.assertEqual(system_admin.handle_system_command("check for updates"), "update inventory")
        check.assert_called_once_with()

    def test_unrecognized_commands_are_left_for_existing_router(self):
        self.assertIsNone(system_admin.handle_system_command("restart the computer"))


if __name__ == "__main__":
    unittest.main()