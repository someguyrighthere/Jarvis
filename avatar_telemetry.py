import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import psutil
import requests


LOGGER = logging.getLogger(__name__)


def gpu_stats():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2, check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        devices = []
        for line in result.stdout.splitlines():
            name, usage, used, total, temperature = [value.strip() for value in line.rsplit(",", 4)]
            devices.append({"name": name, "percent": float(usage), "used_mb": float(used),
                            "total_mb": float(total), "temperature": float(temperature)})
        if not devices:
            raise ValueError("No GPU readings returned")
        return {"devices": devices, "error": None}
    except FileNotFoundError:
        return {"devices": [], "error": "GPU telemetry unavailable (requires NVIDIA nvidia-smi)"}
    except (subprocess.SubprocessError, ValueError) as error:
        LOGGER.warning("GPU telemetry failed: %s", error)
        return {"devices": [], "error": "GPU readings unavailable"}


class Telemetry:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.lock = threading.Lock()
        self.cached = None
        self.updated = 0.0
        self.process = None

    def sara_stats(self):
        new_process = False
        if self.process is None or not self.process.is_running():
            self.process = None
            for process in psutil.process_iter(["cmdline", "cwd"]):
                try:
                    command = process.info["cmdline"] or []
                    source = any(Path(arg).name.lower() == "jarvis.py" for arg in command[1:])
                    frozen = "--assistant" in command
                    if (source or frozen) and process.info["cwd"] and Path(process.info["cwd"]).resolve() == self.project_root:
                        self.process = process
                        process.cpu_percent()
                        new_process = True
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            if self.process is None:
                return {"running": False, "cpu_percent": None, "memory_mb": None, "uptime": None,
                        "error": "Assistant process not running or not accessible"}
        try:
            cpu = None if new_process else self.process.cpu_percent() / (psutil.cpu_count() or 1)
            return {"running": True, "cpu_percent": cpu,
                    "memory_mb": self.process.memory_info().rss / 1024**2,
                    "uptime": max(0, time.time() - self.process.create_time()), "error": None}
        except (psutil.NoSuchProcess, psutil.AccessDenied) as error:
            self.process = None
            LOGGER.warning("SARA process telemetry unavailable: %s", error)
            return {"running": False, "cpu_percent": None, "memory_mb": None, "uptime": None,
                    "error": "Assistant process unavailable"}

    def read(self):
        with self.lock:
            if self.cached is not None and time.monotonic() - self.updated < 3:
                return self.cached
            endpoint = urlsplit(os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434/v1/chat/completions"))
            model = os.getenv("OLLAMA_MODEL", "llama3.2")
            try:
                response = requests.get(f"{endpoint.scheme}://{endpoint.netloc}/api/tags", timeout=1)
                response.raise_for_status()
                names = [item["name"] for item in response.json()["models"]]
                available = any(name == model or name == f"{model}:latest" for name in names)
                ollama = {"online": True, "model": model, "available": available, "error": None}
            except (requests.RequestException, ValueError, KeyError, TypeError) as error:
                LOGGER.warning("Ollama status unavailable: %s", error)
                ollama = {"online": False, "model": model, "available": False,
                          "error": "Cannot reach Ollama or read its model list"}
            memory = psutil.virtual_memory()
            self.cached = {"ollama": ollama, "sara": self.sara_stats(),
                           "cpu": {"percent": psutil.cpu_percent(interval=0.1), "threads": psutil.cpu_count()},
                           "ram": {"percent": memory.percent, "used_gb": (memory.total - memory.available) / 1024**3,
                                   "total_gb": memory.total / 1024**3},
                           "gpu": gpu_stats(), "sampled_at": time.time()}
            self.updated = time.monotonic()
            return self.cached
