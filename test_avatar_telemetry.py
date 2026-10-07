import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import requests

from avatar_telemetry import Telemetry, gpu_stats


class TelemetryTests(unittest.TestCase):
    def test_gpu_readings_and_missing_driver(self):
        with patch("avatar_telemetry.subprocess.run", return_value=Mock(stdout="RTX, 42, 1024, 8192, 55\n")):
            result = gpu_stats()
            self.assertEqual(result["devices"][0]["percent"], 42)
            self.assertEqual(result["devices"][0]["total_mb"], 8192)
        with patch("avatar_telemetry.subprocess.run", side_effect=FileNotFoundError):
            self.assertEqual(gpu_stats()["devices"], [])
            self.assertIn("unavailable", gpu_stats()["error"])
        with patch("avatar_telemetry.subprocess.run", side_effect=subprocess.TimeoutExpired("nvidia-smi", 2)):
            self.assertIsNotNone(gpu_stats()["error"])

    def test_process_stats_prime_then_measure(self):
        process = Mock(info={"cmdline": ["python", "jarvis.py"], "cwd": str(Path.cwd())})
        process.cpu_percent.return_value = 200
        process.memory_info.return_value = Mock(rss=128 * 1024**2)
        process.create_time.return_value = 100
        telemetry = Telemetry(Path.cwd())
        with patch("avatar_telemetry.psutil.process_iter", return_value=[process]), patch("avatar_telemetry.time.time", return_value=160), patch("avatar_telemetry.psutil.cpu_count", return_value=8):
            first = telemetry.sara_stats()
            self.assertTrue(first["running"])
            self.assertIsNone(first["cpu_percent"])
            second = telemetry.sara_stats()
            self.assertEqual(second["cpu_percent"], 25)
            self.assertEqual(second["memory_mb"], 128)
            self.assertEqual(second["uptime"], 60)

    def test_read_caches_and_reports_offline(self):
        telemetry = Telemetry(Path.cwd())
        with (
            patch("avatar_telemetry.requests.get", return_value=Mock(json=lambda: {"models": [{"name": "llama3.2:latest"}]})) as request,
            patch("avatar_telemetry.psutil.process_iter", return_value=[]),
            patch("avatar_telemetry.gpu_stats", return_value={"devices": [], "error": "unavailable"}),
            patch.dict("os.environ", {"OLLAMA_MODEL": "llama3.2"}),
        ):
            result = telemetry.read()
            self.assertTrue(result["ollama"]["online"])
            self.assertTrue(result["ollama"]["available"])
            self.assertFalse(result["sara"]["running"])
            self.assertIs(telemetry.read(), result)
            request.assert_called_once()
            for key in ("cpu", "ram"):
                self.assertGreaterEqual(result[key]["percent"], 0)
                self.assertLessEqual(result[key]["percent"], 100)

    def test_ollama_failure_is_not_reported_as_online(self):
        with (
            patch("avatar_telemetry.requests.get", side_effect=requests.ConnectionError("offline")),
            patch("avatar_telemetry.psutil.process_iter", return_value=[]),
            patch("avatar_telemetry.gpu_stats", return_value={"devices": [], "error": "unavailable"}),
        ):
            result = Telemetry(Path.cwd()).read()
            self.assertFalse(result["ollama"]["online"])
            self.assertIsNotNone(result["ollama"]["error"])


if __name__ == "__main__":
    unittest.main()
