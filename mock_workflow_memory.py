"""Separate, opt-in persistence for explicitly confirmed MOCK workflow successes."""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Generator
import json
import msvcrt
import os
from pathlib import Path
import tempfile
import threading

from experiments.app_tree_prototype import PrototypeMemory
from local_storage import LOCAL_DATA_DIR


MEMORY_PATH = LOCAL_DATA_DIR / "app_tree_mock_workflows.json"
_THREAD_LOCK = threading.Lock()


class MockWorkflowMemory(PrototypeMemory):
    def __init__(self, path: Path | None = None, *, load: bool = True) -> None:
        super().__init__()
        self.path = MEMORY_PATH if path is None else path
        if load:
            self.refresh()

    def _read(self) -> dict[tuple[str, str], int]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        if not isinstance(data, dict) or set(data) != {"version", "scope", "routes"}:
            raise ValueError("Mock workflow memory has an invalid format.")
        if type(data["version"]) is not int or data["version"] != 1 or data["scope"] != "mock_test_only":
            raise ValueError("Mock workflow memory has an unsupported version or scope.")
        if not isinstance(data["routes"], list) or len(data["routes"]) > 1000:
            raise ValueError("Mock workflow memory must contain at most 1000 routes.")
        routes: dict[tuple[str, str], int] = {}
        for entry in data["routes"]:
            if not isinstance(entry, dict) or set(entry) != {"task_type", "capability_id", "confirmed_successes"}:
                raise ValueError("Invalid saved mock workflow entry.")
            task, capability, count = entry["task_type"], entry["capability_id"], entry["confirmed_successes"]
            if (
                not isinstance(task, str) or not task.strip() or len(task) > 100
                or not isinstance(capability, str) or capability not in {"weather.lookup", "reminders.create"}
                or type(count) is not int or count < 1
            ):
                raise ValueError("Invalid task, mock capability, or confirmation count.")
            key = (" ".join(task.casefold().split()), capability)
            if key in routes:
                raise ValueError("Duplicate saved mock workflow.")
            routes[key] = count
        return routes

    @contextmanager
    def _locked(self) -> Generator[None, None, None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _THREAD_LOCK, self.path.with_suffix(".lock").open("a+b") as lock:
            # Lock a fixed byte across processes; keep the sidecar after release.
            lock.seek(0, os.SEEK_END)
            if lock.tell() == 0:
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)

    def _write(self, routes: dict[tuple[str, str], int]) -> None:
        if len(routes) > 1000:
            raise ValueError("Mock workflow memory is full; clear saved mock workflows first.")
        data = {
            "version": 1,
            "scope": "mock_test_only",
            "routes": [
                {"task_type": task, "capability_id": capability, "confirmed_successes": count}
                for (task, capability), count in sorted(routes.items())
            ],
        }
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix="mock-workflows-", suffix=".tmp", delete=False,
            ) as file:
                temporary = Path(file.name)
                json.dump(data, file, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def refresh(self) -> None:
        with self._locked():
            self.successful_routes = self._read()

    def record_success(self, task_type: str, capability_id: str) -> None:
        if capability_id not in {"weather.lookup", "reminders.create"}:
            raise ValueError("Only supported mock successes can be saved.")
        with self._locked():
            routes = self._read()
            key = (" ".join(task_type.casefold().split()), capability_id)
            if not key[0] or len(key[0]) > 100:
                raise ValueError("Invalid mock workflow task type.")
            routes[key] = routes.get(key, 0) + 1
            self._write(routes)
            self.successful_routes = routes

    def preferred_capability(self, task_type: str, available: set[str]) -> str:
        self.refresh()
        return super().preferred_capability(task_type, available)

    def clear(self) -> None:
        with self._locked():
            self._write({})
            self.successful_routes = {}
