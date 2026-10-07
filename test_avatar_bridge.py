import json
import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import avatar_bridge as bridge
import user_memory
from TextToSpeech import Fast_DF_TTS as speech


class AvatarBridgeTests(unittest.TestCase):
    def test_playback_includes_response_gestures(self):
        with (
            patch.object(speech.platform, "system", return_value="Windows"),
            patch.object(speech.ctypes, "windll", Mock()),
            patch.object(speech, "audio_envelope", return_value=[1] * 100),
            patch.object(speech, "publish_speech") as publish,
        ):
            speech.ctypes.windll.winmm.mciSendStringW.return_value = 0
            speech._play_audio("test.wav", "Hello, welcome back.")
            self.assertEqual(publish.call_args_list[0].kwargs["gestures"][0]["kind"], "greeting")
            self.assertEqual(publish.call_args_list[-1].args, ([], "idle"))

    def test_atomic_publish_retries_transient_windows_file_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replace = bridge.os.replace
            attempts = []

            def locked_once(source, destination):
                attempts.append(source)
                if len(attempts) == 1:
                    raise PermissionError("Reader briefly holds file")
                replace(source, destination)

            with (
                patch.object(bridge, "PROJECT_ROOT", root),
                patch.object(bridge, "SPEECH_PATH", root / "speech.json"),
                patch.object(bridge.os, "replace", side_effect=locked_once),
            ):
                bridge.publish_speech([1], "audio", gestures=[{"kind": "greeting"}])
                self.assertEqual(len(attempts), 2)
                self.assertEqual(json.loads((root / "speech.json").read_text())["gestures"], [{"kind": "greeting"}])

    def test_audio_publishes_only_after_playback_starts_and_resets(self):
        events = []

        def send(command, *_):
            events.append(command)
            return 0

        def publish(levels, mode, **kwargs):
            events.append((levels, mode))

        with (
            patch.object(speech.platform, "system", return_value="Windows"),
            patch.object(speech.ctypes, "windll", Mock()),
            patch.object(speech, "audio_envelope", return_value=[0, 1]),
            patch.object(speech, "publish_speech", side_effect=publish),
        ):
            speech.ctypes.windll.winmm.mciSendStringW.side_effect = send
            speech._play_audio("test.wav")
        self.assertLess(events.index("play jarvis_speech"), events.index(([0, 1], "audio")))
        self.assertIn(([], "idle"), events)
        self.assertEqual(events[-1], "close jarvis_speech")

    def test_failed_playback_clears_the_mouth(self):
        with (
            patch.object(speech.platform, "system", return_value="Windows"),
            patch.object(speech.ctypes, "windll", Mock()),
            patch.object(speech, "audio_envelope", return_value=[1]),
            patch.object(speech, "publish_speech") as publish,
        ):
            speech.ctypes.windll.winmm.mciSendStringW.side_effect = [0, 1, 0, 0]
            with self.assertRaisesRegex(RuntimeError, "start audio"):
                speech._play_audio("test.wav")
            publish.assert_called_once_with([], "idle")

    def test_envelope_preserves_silence_and_audio_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "voice.wav"
            with wave.open(str(path), "wb") as audio:
                audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                samples = [0] * 640 + [int(10000 * math.sin(i * 0.3)) for i in range(640)]
                audio.writeframes(struct.pack(f"<{len(samples)}h", *samples))
            values = bridge.audio_envelope(str(path))
            self.assertEqual(len(values), 2)
            self.assertEqual(values[0], 0)
            self.assertGreater(values[1], 0.9)

    def test_publish_replaces_speech_on_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(bridge, "PROJECT_ROOT", root), patch.object(bridge, "SPEECH_PATH", root / "speech.json"):
                bridge.publish_speech([0, 1], "audio", 123.0)
                payload = json.loads((root / "speech.json").read_text())
                self.assertEqual(payload["started_at"], 123)
                self.assertEqual(payload["levels"], [0, 1])
                bridge.publish_speech([], "idle")
                self.assertEqual(json.loads((root / "speech.json").read_text())["mode"], "idle")
                self.assertEqual(list(root.glob("*.tmp")), [])

    def test_unsupported_wav_format_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unsupported.wav"
            with wave.open(str(path), "wb") as audio:
                audio.setparams((1, 1, 16000, 0, "NONE", "not compressed"))
                audio.writeframes(bytes([128]) * 640)
            with self.assertRaisesRegex(ValueError, "16-bit"):
                bridge.audio_envelope(str(path))

    def test_server_state_and_private_files(self):
        with patch.object(bridge.UpdateService, "start"), patch.object(bridge.DependencyService, "start"):
            server = bridge.start_avatar_server()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(base + "/api/state") as response:
                self.assertIn("state", json.load(response))
            with patch.object(server.telemetry, "read", return_value={"cpu": {"percent": 25}}):
                with urlopen(base + "/api/telemetry") as response:
                    self.assertEqual(json.load(response)["cpu"]["percent"], 25)
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
            with urlopen(base + "/avatar_web/index.html") as response:
                self.assertIn(b"Live 3D avatar", response.read())
            with patch("mimetypes.guess_type", return_value=("text/plain", None)):
                for filename in ("speech_motion.mjs", "avatar.js", "memory.js", "action_history.js"):
                    with urlopen(base + "/avatar_web/" + filename) as response:
                        self.assertIn("javascript", response.headers["Content-Type"])
            with self.assertRaises(HTTPError) as raised:
                urlopen(base + "/log.txt")
            self.assertEqual(raised.exception.code, 404)
            for path in ("/avatar_web/", "/avatar_web/%2e%2e/log.txt", "/avatar_web/%2e%2e%5clog.txt"):
                for method in ("GET", "HEAD"):
                    with self.subTest(path=path, method=method):
                        with self.assertRaises(HTTPError) as raised:
                            urlopen(Request(base + path, method=method))
                        self.assertEqual(raised.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()

    def test_local_memory_api_lists_and_updates_only_through_same_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            memory_path = Path(directory) / "user_preferences.json"
            with (
                patch.object(user_memory, "MEMORY_PATH", memory_path),
                patch.object(bridge.UpdateService, "start"),
                patch.object(bridge.DependencyService, "start"),
            ):
                server = bridge.start_avatar_server()
                try:
                    base = f"http://127.0.0.1:{server.server_port}"
                    with urlopen(base + "/api/memory") as response:
                        self.assertEqual(json.load(response), {"entries": []})

                    payload = json.dumps({"action": "add", "key": "projects", "value": "SARA"})
                    request = Request(
                        base + "/api/memory",
                        data=payload.encode(),
                        headers={
                            "Origin": base,
                            "Content-Type": "application/json",
                        },
                        method="POST",
                    )
                    with urlopen(request) as response:
                        self.assertEqual(json.load(response)["entries"][0]["value"], "SARA")

                    bad_origin = Request(
                        base + "/api/memory",
                        data=payload.encode(),
                        headers={
                            "Origin": "http://example.com",
                            "Content-Type": "application/json",
                        },
                        method="POST",
                    )
                    with self.assertRaises(HTTPError) as raised:
                        urlopen(bad_origin)
                    self.assertEqual(raised.exception.code, 403)
                finally:
                    server.shutdown()
                    server.server_close()


if __name__ == "__main__":
    unittest.main()
