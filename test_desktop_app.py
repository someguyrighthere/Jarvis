import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import avatar_bridge as bridge
import desktop_app as desktop
import launcher


class DesktopAppTests(unittest.TestCase):
    def test_launcher_uses_desktop_window(self):
        with patch.object(sys, "argv", ["Jarvis.exe"]), patch.object(desktop, "main", return_value=0) as main:
            self.assertEqual(launcher.main(), 0)
            main.assert_called_once_with()

    def test_source_start_is_idempotent_and_logs_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process = MagicMock()
            process.poll.return_value = None
            with patch.object(desktop, "executable", return_value="chrome.exe"), \
                    patch.object(desktop.subprocess, "Popen", return_value=process) as spawn:
                controller = desktop.AssistantController(root)
                controller.start()
                controller.start()
                spawn.assert_called_once()
                self.assertEqual(spawn.call_args.args[0], [sys.executable, "-B", "-u", str(root / "jarvis.py")])
                self.assertEqual(spawn.call_args.kwargs["cwd"], root)
                self.assertTrue(controller.status()["running"])
                process.poll.return_value = 0
                controller.close()
                self.assertTrue(controller.output is None)
                self.assertEqual((root / "voice_state.txt").read_text(), "STANDBY")

    def test_frozen_start_uses_assistant_switch(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(desktop, "executable", return_value="chrome.exe"), \
                patch.object(desktop.sys, "frozen", True, create=True), \
                patch.object(desktop.subprocess, "Popen") as spawn:
            spawn.return_value.poll.return_value = 0
            controller = desktop.AssistantController(Path(directory))
            controller.start()
            self.assertEqual(spawn.call_args.args[0], [sys.executable, "--assistant"])
            controller.close()

    def test_missing_chrome_and_failed_process_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = desktop.AssistantController(Path(directory))
            with patch.object(desktop, "executable", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "Chrome"):
                    controller.start()
            self.assertIn("Dependencies", controller.status()["error"])
            with patch.object(desktop, "executable", return_value="chrome.exe"), \
                    patch.object(desktop.subprocess, "Popen", side_effect=OSError("denied")):
                with self.assertRaisesRegex(RuntimeError, "denied"):
                    controller.start()
            self.assertIsNone(controller.output)
            controller.close()

    def test_stop_targets_only_owned_process_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = desktop.AssistantController(Path(directory))
            controller.process = MagicMock(pid=123)
            controller.process.poll.return_value = None
            parent, child = MagicMock(), MagicMock()
            parent.children.return_value = [child]
            with patch.object(desktop.psutil, "Process", return_value=parent) as lookup, \
                    patch.object(desktop.psutil, "wait_procs", return_value=([], [])):
                controller.close()
                lookup.assert_called_once_with(123)
                parent.terminate.assert_called_once()
                child.terminate.assert_called_once()
            with self.assertRaisesRegex(RuntimeError, "closing"):
                controller.start()

    def test_unexpected_exit_reports_error(self):
        controller = desktop.AssistantController()
        controller.process = MagicMock(returncode=3)
        controller.process.poll.return_value = 3
        with self.assertLogs(desktop.LOGGER, level="ERROR"):
            data = controller.status()
        self.assertFalse(data["running"])
        self.assertIn("code 3", data["error"])

    def test_initialize_preserves_existing_user_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "log.txt").write_text("existing")
            desktop.initialize_runtime(root)
            self.assertEqual((root / "log.txt").read_text(), "existing")
            self.assertTrue((root / "schedule.txt").exists())

    def test_native_window_owns_server_and_assistant_lifecycle(self):
        class Event:
            def __iadd__(self, callback):
                self.callback = callback
                return self
        loaded = Event()
        window = SimpleNamespace(events=SimpleNamespace(loaded=loaded))
        webview = MagicMock()
        webview.create_window.return_value = window
        webview.start.side_effect = lambda **_: loaded.callback()
        server = MagicMock(server_port=12345)
        with patch.dict(sys.modules, {"webview": webview}), \
                patch.object(desktop, "initialize_runtime"), patch.object(desktop.os, "chdir"), \
                patch.object(desktop.logging, "basicConfig"), \
                patch.object(desktop, "start_avatar_server", return_value=server), \
                patch.object(desktop, "AssistantController") as controller:
            self.assertEqual(desktop.main(), 0)
            self.assertIn("127.0.0.1:12345", webview.create_window.call_args.args[1])
            self.assertTrue(webview.create_window.call_args.kwargs["maximized"])
            controller.return_value.start.assert_called_once()
            controller.return_value.close.assert_called_once()
            server.shutdown.assert_called_once()
            server.server_close.assert_called_once()

    def test_http_controls_guard_origin_and_report_failures(self):
        with patch.object(bridge.UpdateService, "start"), patch.object(bridge.DependencyService, "start"):
            server = bridge.start_avatar_server()
        base = f"http://127.0.0.1:{server.server_port}"
        def post(action, origin=base):
            return urlopen(Request(base + "/api/assistant/" + action, data=b"{}",
                                   headers={"Origin": origin, "Content-Type": "application/json"}))
        try:
            with urlopen(base + "/api/assistant") as response:
                self.assertFalse(json.load(response)["supported"])
            with self.assertRaises(HTTPError) as error:
                post("start")
            self.assertEqual(error.exception.code, 409)
            controller = MagicMock()
            controller.status.return_value = {"supported": True, "running": True, "error": None}
            server.assistant = controller
            with self.assertRaises(HTTPError) as error:
                post("start", "https://example.com")
            self.assertEqual(error.exception.code, 403)
            controller.start.assert_not_called()
            with post("start") as response:
                self.assertTrue(json.load(response)["running"])
            controller.start.assert_called_once()
            with post("stop"):
                controller.stop.assert_called_once()
            controller.start.side_effect = RuntimeError("Chrome missing")
            with self.assertRaises(HTTPError) as error:
                post("start")
            self.assertEqual(error.exception.code, 409)
            self.assertIn("Chrome missing", json.load(error.exception)["error"])
        finally:
            server.shutdown()
            server.server_close()
