import json
import subprocess
import time
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import avatar_bridge as bridge
import dependency_setup as setup


class DependencySetupTests(unittest.TestCase):
    def test_catalog_covers_sara_forge_and_optional_tools(self):
        keys = {row[0] for row in setup.CATALOG}
        self.assertTrue({"packages", "python", "node", "renderer", "chrome", "ollama",
                         "sara-model", "voice", "forge", "forge-model",
                         "pyright", "playwright", "sandbox", "bubblewrap"} <= keys)
        self.assertEqual(len(keys), len(setup.CATALOG))

    def test_install_commands_use_fixed_packages_and_project_environment(self):
        with patch.object(setup, "require", side_effect=lambda name: name), patch.object(setup, "run") as run:
            setup.install_component("chrome")
            self.assertEqual(run.call_args.args[0][0:5],
                             ["winget", "install", "--exact", "--id", "Google.Chrome"])
            setup.install_component("packages")
            command = run.call_args.args[0]
            self.assertEqual(command[:4], [setup.sys.executable, "-m", "pip", "install"])
            self.assertEqual(command[-1], str(setup.ROOT / "requirements.txt"))
            setup.install_component("renderer")
            self.assertEqual(run.call_args.args[0], ["npm.cmd", "ci"])
            self.assertEqual(run.call_args.kwargs["cwd"], setup.ROOT / "avatar_web")
            setup.install_component("playwright")
            self.assertEqual(run.call_args.args[0][-3:], ["pip", "install", "playwright"])
        with self.assertRaisesRegex(ValueError, "Unknown"):
            setup.install_component("arbitrary-command")

    def test_model_names_are_not_shell_commands(self):
        with patch.dict(setup.os.environ, {"OLLAMA_MODEL": "llama3.2"}):
            self.assertEqual(setup.model_name(), "llama3.2")
        with patch.dict(setup.os.environ, {"OLLAMA_MODEL": "--help; evil"}):
            with self.assertRaisesRegex(ValueError, "invalid"):
                setup.model_name()

    def test_process_failure_is_not_success(self):
        result = subprocess.CompletedProcess([], 1, stdout="", stderr="permission denied")
        with patch.object(setup.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "permission denied"):
                setup.run(["fixed-command"])

    def test_old_forge_installer_is_rejected_without_launch(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = {"tag_name": "v1.4.0"}
        with patch.object(setup.requests, "get", return_value=response), patch.object(setup, "run") as run:
            with self.assertRaisesRegex(ValueError, "older"):
                setup.install_forge()
            run.assert_not_called()

    def test_forge_requires_integrity_digest_before_download(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = {"tag_name": "v1.4.1", "assets": [{
            "name": "Forge-Setup-1.4.1.exe",
            "browser_download_url": "https://github.com/someguyrighthere/Forge/releases/download/v1.4.1/Forge-Setup-1.4.1.exe",
        }]}
        with patch.object(setup.requests, "get", return_value=response) as get, patch.object(setup, "run") as run:
            with self.assertRaisesRegex(ValueError, "integrity digest"):
                setup.install_forge()
            self.assertEqual(get.call_count, 1)
            run.assert_not_called()

    def test_refresh_checks_only_and_failed_setup_remains_explicit(self):
        service = setup.DependencyService()
        with patch.object(setup, "inspect_component", return_value=("installed", "present")), \
                patch.object(setup, "install_component") as install:
            service._run(None)
            install.assert_not_called()
        self.assertTrue(all(row["state"] == "installed" for row in service.status()["components"]))
        with patch.object(setup, "install_component", side_effect=RuntimeError("setup failed")):
            with self.assertLogs(setup.LOGGER, level="ERROR"):
                service._run("forge")
        self.assertIn("setup failed", service.status()["error"])
        self.assertFalse(service.status()["busy"])

    def test_post_install_requires_verification(self):
        service = setup.DependencyService()
        with patch.object(setup, "install_component"), \
                patch.object(setup, "inspect_component", return_value=("missing", "not found")):
            with self.assertLogs(setup.LOGGER, level="ERROR"):
                service._run("forge")
        self.assertIn("verification", service.status()["error"])

    def test_http_install_is_allowlisted_same_origin_and_busy_guarded(self):
        with patch.object(bridge.UpdateService, "start"), patch.object(setup.DependencyService, "start"):
            server = bridge.start_avatar_server()
        base = f"http://127.0.0.1:{server.server_port}"
        def post(path, origin=base):
            return urlopen(Request(base + path, data=b"{}",
                                   headers={"Origin": origin, "Content-Type": "application/json"}))
        try:
            with urlopen(base + "/api/dependencies") as response:
                self.assertEqual(len(json.load(response)["components"]), len(setup.CATALOG))
            with self.assertRaises(HTTPError) as error:
                post("/api/dependencies/install/forge", "https://example.com")
            self.assertEqual(error.exception.code, 403)
            with self.assertRaises(HTTPError) as error:
                post("/api/dependencies/install/arbitrary")
            self.assertEqual(error.exception.code, 409)
            with patch.object(setup, "install_component") as install, \
                    patch.object(setup, "inspect_component", return_value=("installed", "verified")):
                with post("/api/dependencies/install/forge") as response:
                    self.assertEqual(response.status, 202)
                for _ in range(100):
                    if not server.dependencies.status()["busy"]:
                        break
                    time.sleep(0.01)
                install.assert_called_once_with("forge")
                self.assertIn("verified", server.dependencies.status()["message"])
            server.dependencies.busy = True
            with self.assertRaises(HTTPError) as error:
                post("/api/dependencies/refresh")
            self.assertEqual(error.exception.code, 409)
        finally:
            server.shutdown()
            server.server_close()

    def test_server_checks_dependencies_on_startup_without_installing(self):
        with patch.object(bridge.UpdateService, "start"), \
                patch.object(setup, "inspect_component", return_value=("installed", "present")) as inspect, \
                patch.object(setup, "install_component") as install:
            server = bridge.start_avatar_server()
            try:
                for _ in range(100):
                    if not server.dependencies.status()["busy"]:
                        break
                    time.sleep(0.01)
                rows = server.dependencies.status()["components"]
                self.assertTrue(all(row["state"] == "installed" for row in rows))
                self.assertEqual(inspect.call_count, len(setup.CATALOG))
                install.assert_not_called()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
