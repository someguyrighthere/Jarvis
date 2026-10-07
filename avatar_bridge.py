import json
import logging
import math
import os
import struct
import sys
import tempfile
import threading
import time
import wave
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from avatar_telemetry import Telemetry
from app_updates import UpdateService
from dependency_setup import DependencyService
import psutil


PROJECT_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
SPEECH_PATH = PROJECT_ROOT / "avatar_speech.json"
LOGGER = logging.getLogger(__name__)


def audio_envelope(path: str) -> list[float]:
    with wave.open(path, "rb") as audio:
        if audio.getsampwidth() != 2:
            raise ValueError("Avatar speech analysis requires 16-bit PCM audio.")
        frames = max(1, round(audio.getframerate() * 0.04))
        levels = []
        while chunk := audio.readframes(frames):
            samples = struct.unpack(f"<{len(chunk) // 2}h", chunk)
            rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
            levels.append(rms / 32768)
        peak = max(levels, default=0)
        return [round(min(1, value / max(peak * 0.65, 0.01)), 4) for value in levels]


def publish_speech(levels: list[float], mode: str, started_at: float | None = None,
                   gestures: list[dict] | None = None) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=PROJECT_ROOT,
                                         prefix="avatar-speech-", suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            json.dump({"mode": mode, "started_at": time.time() if started_at is None else started_at,
                       "step": 0.04, "levels": levels, "gestures": gestures or []}, file)
        for attempt in range(5):
            try:
                os.replace(temporary, SPEECH_PATH)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.02)
    except OSError:
        LOGGER.exception("Could not publish avatar speech state")
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                LOGGER.exception("Could not remove temporary avatar speech state")


class AvatarServer(ThreadingHTTPServer):
    def __init__(self, address, handler):
        super().__init__(address, handler)
        self.telemetry = Telemetry(PROJECT_ROOT)
        self.updates = UpdateService()
        self.dependencies = DependencyService()
        self.assistant = None

    def server_close(self):
        self.updates.close()
        super().server_close()


class AvatarHandler(SimpleHTTPRequestHandler):
    server: AvatarServer
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
    }

    def send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        update_action = self.path == "/api/updates/check"
        assistant_action = self.path.removeprefix("/api/assistant/") if self.path in {"/api/assistant/start", "/api/assistant/stop"} else None
        refresh = self.path == "/api/dependencies/refresh"
        dependency = self.path.removeprefix("/api/dependencies/install/") if self.path.startswith("/api/dependencies/install/") else None
        if not update_action and not refresh and dependency is None and assistant_action is None:
            self.send_error(404)
            return
        origin = f"http://127.0.0.1:{self.server.server_port}"
        if self.headers.get("Origin") != origin or self.headers.get("Content-Type") != "application/json":
            self.send_json({"error": "Update actions must originate from this HUD."}, 403)
            return
        if self.headers.get("Content-Length") != "2":
            self.send_json({"error": "Expected an empty JSON object."}, 400)
            return
        if self.rfile.read(2) != b"{}":
            self.send_json({"error": "Expected an empty JSON object."}, 400)
            return
        try:
            if assistant_action is not None:
                if self.server.assistant is None:
                    raise ValueError("Assistant controls are available only in the SARA desktop app.")
                if assistant_action == "start":
                    self.server.assistant.start()
                else:
                    self.server.assistant.stop()
                payload = self.server.assistant.status()
            elif update_action:
                self.server.updates.start("check")
                payload = self.server.updates.status()
            else:
                self.server.dependencies.start(dependency)
                payload = self.server.dependencies.status()
        except (ValueError, RuntimeError, OSError) as error:
            LOGGER.warning("HUD action failed: %s", error)
            self.send_json({"error": str(error)}, 409)
            return
        self.send_json(payload, 202)

    def do_GET(self) -> None:
        if self.path == "/api/assistant":
            self.send_json(self.server.assistant.status() if self.server.assistant is not None
                           else {"supported": False, "running": False, "error": None})
            return
        if self.path == "/api/updates":
            self.send_json(self.server.updates.status())
            return
        if self.path == "/api/dependencies":
            self.send_json(self.server.dependencies.status())
            return
        if self.path == "/api/telemetry":
            try:
                payload = json.dumps(self.server.telemetry.read()).encode()
            except (OSError, psutil.Error) as error:
                LOGGER.exception("Could not read system telemetry")
                self.send_error(503, str(error))
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == "/api/state":
            try:
                state_path = PROJECT_ROOT / "voice_state.txt"
                state = state_path.read_text(encoding="utf-8").strip() if state_path.exists() else "STANDBY"
                speech = json.loads(SPEECH_PATH.read_text(encoding="utf-8")) if SPEECH_PATH.exists() else None
                payload = json.dumps({"state": state, "speech": speech, "server_time": time.time()}).encode()
            except (OSError, ValueError) as error:
                LOGGER.exception("Could not read avatar state")
                self.send_error(503, str(error))
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        super().do_GET()

    def send_head(self):
        path = unquote(urlsplit(self.path).path)
        if "\\" in path or ".." in Path(path).parts:
            self.send_error(404)
            return None
        file = Path(self.translate_path(path)).resolve()
        roots = (RESOURCE_ROOT / "avatar_web", RESOURCE_ROOT / "assets" / "avatars" / "business-female-01")
        if not file.is_file() or not any(file.is_relative_to(root.resolve()) for root in roots):
            self.send_error(404)
            return None
        return super().send_head()

    def log_message(self, format, *args):
        LOGGER.debug(format, *args)


def start_avatar_server() -> ThreadingHTTPServer:
    module = RESOURCE_ROOT / "avatar_web" / "node_modules" / "three" / "build" / "three.module.js"
    if not module.is_file():
        raise RuntimeError("Avatar renderer is missing. Run npm install in avatar_web first.")
    handler = partial(AvatarHandler, directory=str(RESOURCE_ROOT))
    server = AvatarServer(("127.0.0.1", 0), handler)
    server.updates.start("check")
    server.dependencies.start()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    server = start_avatar_server()
    print(f"http://127.0.0.1:{server.server_port}/avatar_web/index.html", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()
        server.server_close()
