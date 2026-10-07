import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dependency_setup as dependencies
import initial_setup as setup
import launcher
import prepare_installer


class InitialSetupTests(unittest.TestCase):
    def test_only_selected_missing_components_are_installed_in_prerequisite_order(self):
        with patch.object(setup, "inspect_component", side_effect=[
            ("missing", "Ollama"), ("installed", "Ollama"),
            ("missing", "model"), ("installed", "model"),
        ]), patch.object(setup, "install_component") as install:
            self.assertEqual(setup.install_selected(["sara-model", "ollama"]), [])
        self.assertEqual([call.args[0] for call in install.call_args_list], ["ollama", "sara-model"])

    def test_declined_and_already_installed_components_are_not_installed(self):
        with patch.object(setup, "inspect_component", return_value=("installed", "present")) as inspect, \
                patch.object(setup, "install_component") as install:
            self.assertEqual(setup.install_selected(["chrome"]), [])
            inspect.assert_called_once_with("chrome")
            install.assert_not_called()
            self.assertEqual(setup.install_selected([]), [])
            inspect.assert_called_once_with("chrome")

    def test_unknown_components_are_rejected_before_installation(self):
        with patch.object(setup, "install_component") as install:
            with self.assertRaisesRegex(ValueError, "Unknown"):
                setup.install_selected(["chrome", "arbitrary"])
            install.assert_not_called()

    def test_failure_is_logged_and_independent_choices_continue(self):
        with patch.object(setup, "inspect_component", side_effect=[
            ("missing", "Chrome"), ("installed", "Ollama"),
        ]), patch.object(setup, "install_component", side_effect=RuntimeError("permission denied")):
            with self.assertLogs(setup.LOGGER, level="ERROR"):
                errors = setup.install_selected(["chrome", "ollama"])
        self.assertEqual(errors, ["chrome: permission denied"])

    def test_failed_verification_is_not_success(self):
        with patch.object(setup, "inspect_component", return_value=("missing", "not found")), \
                patch.object(setup, "install_component"):
            with self.assertLogs(setup.LOGGER, level="ERROR"):
                errors = setup.install_selected(["chrome"])
        self.assertIn("Verification failed", errors[0])

    def test_cli_returns_failure_and_writes_log(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "dependency-setup.log"
            with patch.object(setup, "install_selected", return_value=["chrome: failed"]):
                self.assertEqual(setup.main(["--setup-components", "chrome", "--setup-log", str(log)]), 1)
            self.assertIn("chrome: failed", log.read_text(encoding="utf-8"))

    def test_launcher_routes_setup_without_starting_hud_or_assistant(self):
        with patch.object(launcher.sys, "argv", ["Jarvis.exe", "--setup-components", "chrome", "--setup-log", "setup.log"]), \
                patch.object(setup, "main", return_value=1) as main:
            self.assertEqual(launcher.main(), 1)
            main.assert_called_once_with(["--setup-components", "chrome", "--setup-log", "setup.log"])

    def test_voice_is_staged_with_attribution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / prepare_installer.PIPER_MODEL_NAME
            config = root / prepare_installer.PIPER_CONFIG_NAME
            model.write_bytes(b"model")
            config.write_text("{}")
            with patch.object(prepare_installer, "_download_piper_file", side_effect=[model, config]):
                prepare_installer.prepare_voice(root / "package")
            output = root / "package" / "models" / "piper"
            self.assertEqual((output / model.name).read_bytes(), b"model")
            self.assertEqual((output / config.name).read_text(), "{}")
            self.assertIn("CC-BY 4.0", (output / "PIPER-VOICE-NOTICE.txt").read_text())

    def test_packaged_runtime_is_bundled_without_external_python(self):
        with patch.object(dependencies.sys, "frozen", True, create=True), \
                patch.object(dependencies, "executable", return_value=None), \
                patch.dict(dependencies.os.environ, {}, clear=True):
            self.assertEqual(dependencies.inspect_component("python")[0], "bundled")
            self.assertEqual(dependencies.inspect_component("forge-python")[0], "missing")
            self.assertEqual(dependencies.inspect_component("playwright")[0], "missing")

    def test_skipped_components_remain_optional_and_installable_in_hud(self):
        service = dependencies.DependencyService()
        rows = {row["id"]: row for row in service.status()["components"]}
        for component in setup.SETUP_COMPONENTS:
            self.assertTrue(rows[component]["optional"])
        self.assertFalse(rows["packages"]["optional"])

    def test_release_metadata_and_runtime_data_isolation(self):
        from version import APP_VERSION
        root = Path(__file__).parent
        installer = (root / "installer.iss").read_text(encoding="utf-8")
        self.assertIn(f'#define AppVersion "{APP_VERSION}"', installer)
        spec = (root / "Jarvis.spec").read_text(encoding="utf-8")
        for filename in ["Alam_data.txt", "input.txt", "log.txt", "schedule.txt"]:
            self.assertNotIn(f'("{filename}", ".")', spec)
        build = (root / "build.ps1").read_text(encoding="utf-8")
        self.assertNotIn('Copy-Item ".\\$file"', build)
        self.assertIn('else { "" }', build)


if __name__ == "__main__":
    unittest.main()
