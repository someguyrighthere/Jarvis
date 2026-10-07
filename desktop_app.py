import ctypes
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

import psutil

from avatar_bridge import PROJECT_ROOT, start_avatar_server
from dependency_setup import executable
from version import APP_NAME, APP_VERSION

LOGGER = logging.getLogger(__name__)


class AssistantController:
    def __init__(self, root: Path = PROJECT_ROOT):
        self.root = root
        self.lock = threading.RLock()
        self.process = None
        self.output = None
        self.error = None
        self.closed = False

    def status(self) -> dict:
        with self.lock:
            running = self.process is not None and self.process.poll() is None
            if self.process is not None and not running and self.error is None:
                self.error = f"Assistant exited (code {self.process.returncode}). See assistant-runtime.log and use Start to retry."
                LOGGER.error(self.error)
            return {"supported": True, "running": running, "error": self.error}

    def start(self) -> None:
        with self.lock:
            if self.closed:
                raise RuntimeError("The desktop app is closing.")
            if self.process is not None and self.process.poll() is None:
                return
            if not executable("chrome"):
                self.error = "Voice recognition needs Chrome. Install it in Dependencies, then select Start."
                raise RuntimeError(self.error)
            if self.output is not None:
                self.output.close()
            self.error = None
            command = ([sys.executable, "--assistant"] if getattr(sys, "frozen", False)
                       else [sys.executable, "-B", "-u", str(self.root / "jarvis.py")])
            self.output = (self.root / "assistant-runtime.log").open("a", encoding="utf-8")
            try:
                self.process = subprocess.Popen(
                    command, cwd=self.root, stdout=self.output, stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except OSError as error:
                self.output.close()
                self.output = None
                self.error = f"Could not start the assistant: {error}"
                raise RuntimeError(self.error) from error
            LOGGER.info("Started assistant PID %s", self.process.pid)

    def stop(self) -> None:
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                try:
                    parent = psutil.Process(self.process.pid)
                    children = parent.children(recursive=True)
                    parent.terminate()
                    for child in children:
                        try:
                            child.terminate()
                        except psutil.NoSuchProcess:
                            continue
                    _, alive = psutil.wait_procs([parent, *children], timeout=5)
                    for process in alive:
                        try:
                            process.kill()
                        except psutil.NoSuchProcess:
                            continue
                    _, alive = psutil.wait_procs(alive, timeout=3)
                    if alive:
                        raise RuntimeError("Could not stop all assistant processes.")
                    self.process.wait(timeout=3)
                except psutil.NoSuchProcess:
                    self.process.wait(timeout=3)
                except (psutil.Error, subprocess.TimeoutExpired, RuntimeError) as error:
                    self.error = f"Assistant shutdown failed: {error}"
                    raise RuntimeError(self.error) from error
            self.process = None
            if self.output is not None:
                self.output.close()
                self.output = None
            self.error = None
            (self.root / "voice_state.txt").write_text("STANDBY", encoding="utf-8")

    def close(self) -> None:
        with self.lock:
            self.closed = True
            self.stop()


def initialize_runtime(root: Path) -> None:
    for name, initial in [("Alam_data.txt", ""), ("input.txt", ""), ("log.txt", ""),
                          ("schedule.txt", ""), ("voice_state.txt", "STANDBY")]:
        path = root / name
        if not path.exists():
            path.write_text(initial, encoding="utf-8")


def main() -> int:
    initialize_runtime(PROJECT_ROOT)
    os.chdir(PROJECT_ROOT)
    logging.basicConfig(filename=PROJECT_ROOT / "desktop-runtime.log", encoding="utf-8",
                        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    controller = AssistantController()
    server = None
    try:
        import webview

        server = start_avatar_server()
        server.assistant = controller
        url = f"http://127.0.0.1:{server.server_port}/avatar_web/index.html"
        LOGGER.info("Desktop HUD: %s", url)
        window = webview.create_window(f"{APP_NAME} {APP_VERSION}", url, width=1280, height=820,
                                      min_size=(800, 600), maximized=True, background_color="#152633")

        def start_assistant():
            try:
                controller.start()
            except RuntimeError:
                LOGGER.exception("Assistant startup needs attention")

        window.events.loaded += start_assistant
        webview.start(gui="edgechromium" if os.name == "nt" else None)
        return 0
    except Exception as error:
        LOGGER.exception("Desktop HUD failed")
        if os.name == "nt":
            ctypes.windll.user32.MessageBoxW(
                0, f"SARA could not open its desktop window: {error}\n\n"
                "Install/repair Microsoft Edge WebView2 Runtime and restart SARA.\n"
                f"Details: {PROJECT_ROOT / 'desktop-runtime.log'}", APP_NAME, 0x10,
            )
        return 1
    finally:
        try:
            controller.close()
        except (OSError, RuntimeError):
            LOGGER.exception("Could not shut down the assistant")
            if os.name == "nt":
                ctypes.windll.user32.MessageBoxW(
                    0, "Assistant shutdown needs attention. See desktop-runtime.log.", APP_NAME, 0x10)
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
