import logging
import re
import tempfile
import threading
from pathlib import Path

import requests

from version import APP_NAME, APP_VERSION

RELEASE_API = "https://api.github.com/repos/someguyrighthere/Jarvis/releases/latest"
RELEASE_ASSET_PREFIX = "https://github.com/someguyrighthere/Jarvis/releases/download/"
LOGGER = logging.getLogger(__name__)


def is_newer_version(latest, current):
    latest_parts = tuple(int(part) for part in re.findall(r"\d+", str(latest)))
    current_parts = tuple(int(part) for part in re.findall(r"\d+", str(current)))
    if not latest_parts or not current_parts:
        return False
    size = max(len(latest_parts), len(current_parts))
    return latest_parts + (0,) * (size - len(latest_parts)) > current_parts + (0,) * (size - len(current_parts))


def check_release() -> dict | None:
    with requests.get(RELEASE_API, headers={"Accept": "application/vnd.github+json",
                                          "User-Agent": APP_NAME}, timeout=8) as response:
        response.raise_for_status()
        release = response.json()
    latest = release.get("tag_name", "").strip()
    if not is_newer_version(latest, APP_VERSION):
        return None
    number = re.sub(r"^v", "", latest, flags=re.IGNORECASE).strip()
    if not re.fullmatch(r"\d+(?:\.\d+)*(?:[-+][A-Za-z0-9.-]+)?", number):
        raise ValueError("The release version is invalid.")
    name = f"jarvis-setup-{number}.exe"
    for asset in release.get("assets", []):
        url = asset.get("browser_download_url", "")
        if asset.get("name", "").lower() == name.lower() and url.startswith(RELEASE_ASSET_PREFIX):
            return {"version": latest, "url": url, "name": name}
    raise ValueError(f"{APP_NAME} {latest} was found, but its installer asset is missing.")


def download_installer(update: dict) -> Path:
    if not update["url"].startswith(RELEASE_ASSET_PREFIX):
        raise ValueError("The installer URL is not an approved release asset.")
    path = None
    try:
        with requests.get(update["url"], stream=True, timeout=(10, 60)) as response:
            response.raise_for_status()
            downloaded = 0
            with tempfile.NamedTemporaryFile(prefix="JARVIS-Setup-", suffix=".exe", delete=False) as installer:
                path = Path(installer.name)
                for chunk in response.iter_content(chunk_size=128 * 1024):
                    if not chunk:
                        continue
                    downloaded += len(chunk)
                    if downloaded > 500 * 1024 * 1024:
                        raise ValueError("The installer exceeded the 500 MB size limit.")
                    installer.write(chunk)
        with path.open("rb") as installer:
            if installer.read(2) != b"MZ":
                raise ValueError("The downloaded file is not a Windows installer.")
        return path
    except (requests.RequestException, OSError, ValueError, KeyError):
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                LOGGER.exception("Could not remove failed installer download")
        raise


class UpdateService:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = "unchecked"
        self.info = None
        self.error = None
        self.closed = False

    def status(self) -> dict:
        with self.lock:
            return {"state": self.state, "current_version": APP_VERSION,
                    "version": self.info["version"] if self.info else None, "error": self.error}

    def start(self, action: str) -> None:
        if action != "check":
            raise ValueError("Unknown update action.")
        with self.lock:
            if self.closed or self.state in {"checking", "downloading"}:
                raise ValueError("An update operation is already running or the server is closing.")
            self.error = None
            self.state = "checking"
        threading.Thread(target=self._run, args=(action,), daemon=True).start()

    def _run(self, action: str) -> None:
        try:
            info = check_release()
            with self.lock:
                self.info = info
                self.state = "available" if info else "current"
        except (requests.RequestException, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            LOGGER.exception("HUD update %s failed", action)
            with self.lock:
                self.state = "error"
                self.error = f"The update operation failed: {error}"

    def close(self) -> None:
        with self.lock:
            self.closed = True
