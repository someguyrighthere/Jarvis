import hashlib
import importlib.metadata
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import requests

LOGGER = logging.getLogger(__name__)
ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
RESOURCES = Path(getattr(sys, "_MEIPASS", ROOT))
FORGE_MINIMUM = (1, 4, 1)
CATALOG = (
    ("python", "SARA Python runtime", "Included in packaged SARA; source runs use the current Python."),
    ("packages", "SARA Python packages", "All packages declared in requirements.txt; restart SARA after changes."),
    ("chrome", "Google Chrome", "Optional install now or later; required for current speech recognition."),
    ("ollama", "Ollama", "Optional install now or later; required for local AI responses."),
    ("sara-model", "SARA AI model", "Optional install now or later; local AI requires Ollama and this model (OLLAMA_MODEL, or llama3.2)."),
    ("voice", "Piper voice files", "Local Alba voice model and configuration."),
    ("node", "Node.js / npm", "Avatar renderer setup and Forge's Pyright tools."),
    ("renderer", "3D avatar renderer", "Pinned Three.js dependencies from package-lock.json."),
    ("webview", "Microsoft Edge WebView2 Runtime", "Desktop window renderer; installed automatically by SARA setup if missing. Does not require Chrome."),
    ("forge", "Forge 1.4.1+", "Coding agent with SARA's workspace restrictions."),
    ("forge-model", "Forge AI model", "Configured Forge model, or qwen3:8b (several GB)."),
    ("forge-python", "Forge external Python", "Optional Python 3.12 installation for Forge's Python/browser tools."),
    ("pyright", "Forge Pyright tools", "Optional Python code intelligence; installed through npm."),
    ("playwright", "Forge Playwright tools", "Optional browser tools in the Python environment Forge uses."),
    ("sandbox", "Ubuntu / WSL sandbox", "Optional approved project runs; may require admin, initialization and restart."),
    ("bubblewrap", "Sandbox Python / Bubblewrap", "Optional isolation tools inside the Ubuntu WSL distribution."),
)
OPTIONAL_COMPONENTS = {"chrome", "ollama", "sara-model", "node", "forge", "forge-model",
                       "forge-python", "pyright", "playwright", "sandbox", "bubblewrap"}
WINGET = {"python": "Python.Python.3.12", "forge-python": "Python.Python.3.12", "chrome": "Google.Chrome",
          "ollama": "Ollama.Ollama", "node": "OpenJS.NodeJS.LTS", "webview": "Microsoft.EdgeWebView2Runtime"}


def webview_runtime_installed() -> bool:
    if os.name != "nt":
        return False
    import winreg
    key = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(hive, key, 0, winreg.KEY_READ | view) as registry:
                    version, _ = winreg.QueryValueEx(registry, "pv")
                    if isinstance(version, str) and version and version != "0.0.0.0":
                        return True
            except FileNotFoundError:
                continue
    return False


def executable(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    candidates = {
        "chrome": [Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
                   local / "Google" / "Chrome" / "Application" / "chrome.exe"],
        "ollama": [local / "Programs" / "Ollama" / "ollama.exe"],
        "node": [Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "nodejs" / "node.exe"],
        "npm.cmd": [Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "nodejs" / "npm.cmd"],
        "pyright": [Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "npm" / "pyright.cmd"],
    }
    return next((str(path) for path in candidates.get(name, []) if path.is_file()), None)


def run(command: list[str], timeout: int = 3600, cwd: Path = ROOT) -> str:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    output = (result.stdout + "\n" + result.stderr).strip()
    if result.returncode:
        raise RuntimeError(f"Setup command failed ({result.returncode}): {output[-1800:]}")
    return output


def require(name: str) -> str:
    path = executable(name)
    if not path:
        raise RuntimeError(f"{name} is missing. Install its prerequisite first.")
    return path


def model_name(forge: bool = False) -> str:
    if forge:
        from forge_workflow import _configured_forge_model
        model = _configured_forge_model() or "qwen3:8b"
    else:
        model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]*", model):
        raise ValueError("The configured model name is invalid.")
    return model


def python_path(forge: bool = False) -> str:
    if forge:
        configured = os.environ.get("FORGE_PYTHON")
        if configured:
            path = shutil.which(configured) or configured
            if Path(path).is_file():
                return path
            raise RuntimeError("FORGE_PYTHON does not point to an installed Python.")
    if not getattr(sys, "frozen", False):
        return sys.executable
    path = executable("python")
    if not path:
        raise RuntimeError("Install Python and configure FORGE_PYTHON first.")
    return path


def inspect_component(component: str) -> tuple[str, str]:
    if component == "webview":
        return ("installed", "Desktop WebView2 runtime available.") if webview_runtime_installed() else (
            "missing", "Install Microsoft Edge WebView2 Runtime to open the desktop HUD.")
    if component == "python":
        if getattr(sys, "frozen", False):
            return "bundled", "Included in SARA; no external Python is needed for the assistant."
        return "installed", f"Running Python {sys.version.split()[0]}."
    if component == "forge-python":
        if getattr(sys, "frozen", False) and not os.environ.get("FORGE_PYTHON") and not executable("python"):
            return "missing", "Optional Forge extras need external Python; SARA's own runtime is bundled."
        path = python_path(True)
        return "installed", f"Forge extras use {path}."
    if component == "packages":
        if getattr(sys, "frozen", False):
            return "bundled", "Included in the application. Use an app update to repair."
        missing = []
        for requirement in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
            requirement = requirement.strip()
            if not requirement or requirement.startswith("#"):
                continue
            match = re.fullmatch(r"([A-Za-z0-9_.-]+)(?:==(.+))?", requirement)
            if not match:
                raise ValueError(f"Unsupported dependency specification: {requirement}")
            try:
                installed = importlib.metadata.version(match[1])
                if match[2] and installed != match[2]:
                    missing.append(requirement)
            except importlib.metadata.PackageNotFoundError:
                missing.append(requirement)
        return ("missing", "Missing/version mismatch: " + ", ".join(missing)) if missing else ("installed", "All declared packages are present.")
    if component in {"chrome", "ollama", "node", "pyright"}:
        return ("installed", "Executable found.") if executable(component) else ("missing", "Not found.")
    if component in {"sara-model", "forge-model"}:
        name = model_name(component == "forge-model")
        endpoint = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434/v1/chat/completions")
        from urllib.parse import urlsplit
        url = urlsplit(endpoint)
        with requests.get(f"{url.scheme}://{url.netloc}/api/tags", timeout=3) as response:
            response.raise_for_status()
            names = {item["name"] for item in response.json()["models"]}
        installed = name in names or (":" not in name and name + ":latest" in names)
        return ("installed" if installed else "missing"), name
    if component == "voice":
        from TextToSpeech.Fast_DF_TTS import PIPER_MODEL_DIRECTORY, PIPER_MODEL_NAME, PIPER_CONFIG_NAME
        ready = all((PIPER_MODEL_DIRECTORY / name).is_file() and (PIPER_MODEL_DIRECTORY / name).stat().st_size
                    for name in (PIPER_MODEL_NAME, PIPER_CONFIG_NAME))
        return ("installed" if ready else "missing"), "en_GB-alba-medium"
    if component == "renderer":
        ready = (RESOURCES / "avatar_web" / "node_modules" / "three" / "build" / "three.module.js").is_file()
        return ("bundled" if ready and getattr(sys, "frozen", False) else "installed" if ready else "missing"), "Three.js 0.180.0"
    if component == "forge":
        from forge_workflow import _find_forge
        path = _find_forge()
        if not path:
            return "missing", "Install Forge with its command-line option enabled."
        output = run([path, "--version"], 10)
        match = re.search(r"\bforge (\d+)\.(\d+)\.(\d+)\b", output, re.I)
        if not match:
            raise ValueError("Forge returned an unreadable version.")
        return ("installed" if tuple(map(int, match.groups())) >= FORGE_MINIMUM else "missing"), output
    if component == "playwright":
        if getattr(sys, "frozen", False) and not os.environ.get("FORGE_PYTHON") and not executable("python"):
            return "missing", "Install Forge external Python first, then install Playwright."
        output = run([python_path(True), "-c",
                      "import importlib.util; print('installed' if importlib.util.find_spec('playwright') else 'missing')"], 15)
        if output == "missing":
            return "missing", f"Not installed in {python_path(True)}."
        if output != "installed":
            raise ValueError("Python returned an unreadable Playwright check.")
        return "installed", f"Available in {python_path(True)}. Set FORGE_PYTHON to this environment for Forge."
    if component == "sandbox":
        run([require("wsl.exe"), "-d", "Ubuntu", "--", "true"], 15)
        return "installed", "Ubuntu WSL distribution initialized."
    if component == "bubblewrap":
        run([require("wsl.exe"), "-d", "Ubuntu", "--", "sh", "-c",
             "command -v bwrap && command -v python3"], 15)
        return "installed", "Ubuntu has Bubblewrap and Python."
    raise ValueError("Unknown dependency.")


def install_forge() -> None:
    path = None
    try:
        with requests.get("https://api.github.com/repos/someguyrighthere/forge/releases/latest",
                          headers={"Accept": "application/vnd.github+json"}, timeout=10) as response:
            response.raise_for_status()
            release = response.json()
        version = release["tag_name"].lstrip("v")
        if not re.fullmatch(r"\d+\.\d+\.\d+", version) or tuple(map(int, version.split("."))) < FORGE_MINIMUM:
            raise ValueError("The latest public Forge installer is older than required 1.4.1. Get a compatible release before installing.")
        asset = next((a for a in release["assets"] if a["name"].lower() == f"forge-setup-{version}.exe"), None)
        if not asset or not asset["browser_download_url"].lower().startswith("https://github.com/someguyrighthere/forge/releases/download/"):
            raise ValueError("A compatible official Forge installer is unavailable.")
        digest = asset.get("digest", "")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
            raise ValueError("The Forge release has no SHA-256 integrity digest.")
        sha = hashlib.sha256()
        size = 0
        with requests.get(asset["browser_download_url"], stream=True, timeout=(10, 60)) as response:
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(prefix="Forge-Setup-", suffix=".exe", delete=False) as file:
                path = Path(file.name)
                for chunk in response.iter_content(128 * 1024):
                    size += len(chunk)
                    if size > 500 * 1024 * 1024:
                        raise ValueError("Forge installer exceeds 500 MB.")
                    sha.update(chunk)
                    file.write(chunk)
        if sha.hexdigest() != digest.split(":")[1]:
            raise ValueError("Forge installer SHA-256 verification failed.")
        with path.open("rb") as file:
            if file.read(2) != b"MZ":
                raise ValueError("Forge download is not a Windows installer.")
        run([str(path)], 1800)
    finally:
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                LOGGER.exception("Could not remove temporary Forge installer")


def install_component(component: str) -> None:
    if component in WINGET:
        run([require("winget"), "install", "--exact", "--id", WINGET[component],
             "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity"], 1800)
    elif component == "packages":
        if getattr(sys, "frozen", False):
            raise RuntimeError("Python packages are bundled; update the application instead.")
        run([python_path(), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")])
    elif component in {"sara-model", "forge-model"}:
        run([require("ollama"), "pull", model_name(component == "forge-model")], 7200)
    elif component == "voice":
        from TextToSpeech.Fast_DF_TTS import _download_piper_file, PIPER_MODEL_NAME, PIPER_CONFIG_NAME
        _download_piper_file(PIPER_MODEL_NAME, 150 * 1024 * 1024)
        _download_piper_file(PIPER_CONFIG_NAME, 1024 * 1024)
    elif component == "renderer":
        if getattr(sys, "frozen", False):
            raise RuntimeError("The avatar renderer is bundled; reinstall/update SARA to repair.")
        run([require("npm.cmd"), "ci"], cwd=ROOT / "avatar_web")
    elif component == "forge":
        install_forge()
    elif component == "pyright":
        run([require("npm.cmd"), "install", "--global", "pyright"])
    elif component == "playwright":
        run([python_path(True), "-m", "pip", "install", "playwright"])
    elif component == "sandbox":
        run([require("wsl.exe"), "--install", "-d", "Ubuntu", "--no-launch"], 3600)
    elif component == "bubblewrap":
        run([require("wsl.exe"), "-d", "Ubuntu", "-u", "root", "--", "sh", "-c",
             "apt-get update && apt-get install -y bubblewrap python3"], 1800)
    else:
        raise ValueError("Unknown dependency.")


class DependencyService:
    def __init__(self):
        self.lock = threading.Lock()
        self.busy = False
        self.active = None
        self.message = "Select Refresh to check dependencies. Nothing installs automatically."
        self.error = None
        self.rows = [{"id": key, "name": name, "description": description,
                      "optional": key in OPTIONAL_COMPONENTS,
                      "state": "unchecked", "detail": ""} for key, name, description in CATALOG]

    def status(self) -> dict:
        with self.lock:
            return {"busy": self.busy, "active": self.active, "message": self.message,
                    "error": self.error, "components": [dict(row) for row in self.rows]}

    def start(self, component: str | None = None) -> None:
        if component is not None and component not in {row[0] for row in CATALOG}:
            raise ValueError("Unknown dependency.")
        with self.lock:
            if self.busy:
                raise ValueError("A dependency operation is already running.")
            self.busy = True
            self.active = component
            self.error = None
            self.message = "Installing selected dependency..." if component else "Checking dependencies..."
        threading.Thread(target=self._run, args=(component,), daemon=True).start()

    def _inspect(self, key: str) -> None:
        try:
            state, detail = inspect_component(key)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError,
                requests.RequestException, KeyError, TypeError, ImportError) as error:
            LOGGER.warning("Dependency check %s failed: %s", key, error)
            state, detail = "unavailable", str(error)
        with self.lock:
            row = next(row for row in self.rows if row["id"] == key)
            row.update(state=state, detail=detail)

    def _run(self, component: str | None) -> None:
        try:
            if component:
                install_component(component)
                self._inspect(component)
                with self.lock:
                    row = next(row for row in self.rows if row["id"] == component)
                    if row["state"] not in {"installed", "bundled"}:
                        raise RuntimeError(f"Setup ran, but verification needs attention: {row['detail']}. A restart or initialization may be required.")
                    self.message = f"{row['name']} installed and verified."
            else:
                for key, _, _ in CATALOG:
                    self._inspect(key)
                with self.lock:
                    self.message = "Dependency checks complete. Install only the components you need."
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError,
                requests.RequestException, KeyError, TypeError, ImportError) as error:
            LOGGER.exception("Dependency setup failed")
            with self.lock:
                self.error = str(error)
                self.message = "Dependency setup needs attention."
        finally:
            with self.lock:
                self.busy = False
                self.active = None
