import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import app_updates as updates
import avatar_bridge as bridge


def response_for(payload=None, chunks=()):
    response = MagicMock()
    response.__enter__.return_value = response
    response.json.return_value = payload
    response.iter_content.return_value = chunks
    return response


class AppUpdateTests(unittest.TestCase):
    def test_version_and_exact_asset_match(self):
        self.assertTrue(updates.is_newer_version("v1.0.6", "1.0.5"))
        self.assertFalse(updates.is_newer_version("v1.0.5", "1.0.5.0"))
        self.assertFalse(updates.is_newer_version("", "1.0.5"))
        prefix = updates.RELEASE_ASSET_PREFIX
        payload = {"tag_name": "v2.0.3", "assets": [
            {"name": "jarvis-setup-1.0.4.exe", "browser_download_url": prefix + "v1.0.4/old.exe"},
            {"name": "jarvis-setup-2.0.3.exe", "browser_download_url": "https://example.com/bad.exe"},
            {"name": "jarvis-setup-2.0.3.exe", "browser_download_url": prefix + "v2.0.3/new.exe"},
        ]}
        with patch.object(updates.requests, "get", return_value=response_for(payload)):
            info = updates.check_release()
        self.assertEqual(info["url"], prefix + "v2.0.3/new.exe")
        self.assertEqual(info["name"], "jarvis-setup-2.0.3.exe")

    def test_current_missing_and_invalid_release(self):
        for payload, expected in [
            ({"tag_name": "v2.0.0"}, None),
            ({"tag_name": "v2.0.3", "assets": []}, "missing"),
            ({"tag_name": 'v2.0.3"bad'}, "invalid"),
        ]:
            with patch.object(updates.requests, "get", return_value=response_for(payload)):
                if expected is None:
                    self.assertIsNone(updates.check_release())
                else:
                    with self.assertRaisesRegex(ValueError, expected):
                        updates.check_release()

    def test_download_validates_header_and_cleans_failed_files(self):
        info = {"url": updates.RELEASE_ASSET_PREFIX + "v1.0.6/test.exe"}
        with tempfile.TemporaryDirectory() as directory:
            real_temp = tempfile.NamedTemporaryFile
            def local_temp(**kwargs):
                return real_temp(dir=directory, **kwargs)
            with patch.object(updates.tempfile, "NamedTemporaryFile", side_effect=local_temp):
                with patch.object(updates.requests, "get", return_value=response_for(chunks=[b"MZinstaller"])):
                    path = updates.download_installer(info)
                    self.assertEqual(path.read_bytes(), b"MZinstaller")
                    path.unlink()
                with patch.object(updates.requests, "get", return_value=response_for(chunks=[b"not an exe"])):
                    with self.assertRaisesRegex(ValueError, "Windows installer"):
                        updates.download_installer(info)
                self.assertEqual(list(Path(directory).iterdir()), [])
        with self.assertRaisesRegex(ValueError, "approved"):
            updates.download_installer({"url": "https://example.com/installer.exe"})

    def test_service_errors_and_cleanup(self):
        service = updates.UpdateService()
        with self.assertRaisesRegex(ValueError, "Unknown"):
            service.start("download")
        with patch.object(updates, "check_release", side_effect=ValueError("missing installer")):
            with self.assertLogs(updates.LOGGER, level="ERROR"):
                service._run("check")
        self.assertEqual(service.status()["state"], "error")
        self.assertIn("missing installer", service.status()["error"])
        service.close()
        with self.assertRaisesRegex(ValueError, "closing"):
            service.start("check")

    def test_http_check_only_and_same_origin(self):
        with patch.object(updates.UpdateService, "start"), patch.object(bridge.DependencyService, "start"):
            server = bridge.start_avatar_server()
        base = f"http://127.0.0.1:{server.server_port}"
        info = {"version": "v1.0.6", "name": "jarvis-setup-1.0.6.exe",
                "url": updates.RELEASE_ASSET_PREFIX + "v1.0.6/test.exe"}
        def post(action, origin=base):
            return urlopen(Request(base + "/api/updates/" + action, data=b"{}",
                                   headers={"Origin": origin, "Content-Type": "application/json"}))
        def wait_state(expected):
            for _ in range(100):
                with urlopen(base + "/api/updates") as response:
                    data = json.load(response)
                if data["state"] == expected:
                    return data
                time.sleep(0.01)
            self.fail(f"Expected {expected}, got {data}")
        try:
            with self.assertRaises(HTTPError) as error:
                post("check", "https://example.com")
            self.assertEqual(error.exception.code, 403)
            with self.assertRaises(HTTPError) as error:
                post("download")
            self.assertEqual(error.exception.code, 404)
            with patch.object(updates, "check_release", return_value=info):
                with post("check") as response:
                    self.assertEqual(response.status, 202)
                self.assertEqual(wait_state("available")["version"], "v1.0.6")
            with self.assertRaises(HTTPError) as error:
                urlopen(base + "/api/updates/installer")
            self.assertEqual(error.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()

    def test_server_checks_for_updates_on_startup(self):
        for info, expected in [
            (None, "current"),
            ({"version": "v1.0.6"}, "available"),
        ]:
            with self.subTest(state=expected), patch.object(updates, "check_release", return_value=info) as check, \
                    patch.object(bridge.DependencyService, "start"):
                server = bridge.start_avatar_server()
                try:
                    for _ in range(100):
                        status = server.updates.status()
                        if status["state"] != "checking":
                            break
                        time.sleep(0.01)
                    self.assertEqual(status["state"], expected)
                    check.assert_called_once_with()
                finally:
                    server.shutdown()
                    server.server_close()


if __name__ == "__main__":
    unittest.main()
