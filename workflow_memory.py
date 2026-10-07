"""Real workflow confirmations; never imports mock memory or pending approvals."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3

from local_storage import LOCAL_DATA_DIR


MEMORY_PATH = LOCAL_DATA_DIR / "confirmed_workflows.sqlite3"


class WorkflowMemory:
    def __init__(self, path: Path | None = None):
        self.path = MEMORY_PATH if path is None else path

    @contextmanager
    def database(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS confirmed_routes ("
                "task TEXT NOT NULL, capability TEXT NOT NULL, fingerprint TEXT NOT NULL, "
                "successes INTEGER NOT NULL CHECK(successes > 0), "
                "PRIMARY KEY(task, capability, fingerprint))"
            )
            with connection:
                yield connection
        finally:
            connection.close()

    def record(self, task: str, capability: str, fingerprint: str = "") -> None:
        task = " ".join(task.casefold().split())
        if not task or len(task) > 100 or not capability or len(capability) > 100:
            raise ValueError("Invalid real workflow category or capability.")
        with self.database() as connection:
            connection.execute(
                "INSERT INTO confirmed_routes VALUES (?, ?, ?, 1) "
                "ON CONFLICT(task, capability, fingerprint) "
                "DO UPDATE SET successes = successes + 1",
                (task, capability, fingerprint),
            )

    def entries(self) -> list[tuple[str, str, str, int]]:
        with self.database() as connection:
            return connection.execute(
                "SELECT task, capability, fingerprint, successes FROM confirmed_routes "
                "ORDER BY successes DESC, task, capability"
            ).fetchall()

    def preferred(self, task: str, available: dict[str, str]) -> str:
        normalized = " ".join(task.casefold().split())
        return next(
            (capability for saved, capability, fingerprint, _ in self.entries()
             if saved == normalized and capability in available and available[capability] == fingerprint),
            "",
        )

    def clear(self) -> None:
        with self.database() as connection:
            connection.execute("DELETE FROM confirmed_routes")
