"""Date-specific local reminders, delivered only while SARA is running."""

from datetime import datetime, timedelta
import logging
from pathlib import Path
import re
import sqlite3
import threading
import time

from local_storage import LOCAL_DATA_DIR


LOGGER = logging.getLogger(__name__)
DB_PATH = LOCAL_DATA_DIR / "reminders.sqlite3"


def parse_request(request: str, now: datetime | None = None) -> tuple[str, datetime]:
    now = datetime.now() if now is None else now
    match = re.fullmatch(
        r"(?:please\s+)?(?:remind me to|reminder to)\s+(.+?)\s+(?:(today|tomorrow|\d{4}-\d{2}-\d{2})\s+)?"
        r"at\s+(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?", request.strip(), re.IGNORECASE,
    )
    if not match:
        raise ValueError(
            "Use 'remind me to call Alex tomorrow at 9 AM', or an explicit YYYY-MM-DD date and time. "
            "I need an exact local time; no reminder was scheduled."
        )
    title, day, hour_text, minute_text, period = match.groups()
    if len(title) > 300:
        raise ValueError("Reminder titles must be at most 300 characters.")
    hour, minute = int(hour_text), int(minute_text or 0)
    if period:
        if not 1 <= hour <= 12:
            raise ValueError("AM/PM hours must be between 1 and 12.")
        hour = hour % 12 + (12 if period.casefold().startswith("p") else 0)
    elif not 0 <= hour <= 23 or minute_text is None:
        raise ValueError("Specify AM/PM, or use a 24-hour HH:MM time.")
    if not 0 <= minute <= 59:
        raise ValueError("Minutes must be between 00 and 59.")
    date = now.date()
    if day and day.casefold() == "tomorrow":
        date += timedelta(days=1)
    elif day and day.casefold() != "today":
        date = datetime.strptime(day, "%Y-%m-%d").date()
    due = datetime.combine(date, datetime.min.time()).replace(hour=hour, minute=minute)
    if due <= now:
        if day:
            raise ValueError("That reminder time is in the past.")
        due += timedelta(days=1)
    return title, due


def _connect(path: Path | None = None) -> sqlite3.Connection:
    target = DB_PATH if path is None else path
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, timeout=10)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS reminders ("
        "id INTEGER PRIMARY KEY, title TEXT NOT NULL, due TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0, "
        "lease REAL NOT NULL DEFAULT 0)"
    )
    connection.commit()
    return connection


def create_reminder(title: str, due: datetime) -> int:
    connection = _connect()
    try:
        with connection:
            cursor = connection.execute(
                "INSERT INTO reminders(title, due) VALUES (?, ?)", (title, due.isoformat()),
            )
            return cursor.lastrowid
    finally:
        connection.close()


def pending_reminders() -> list[tuple[int, str, str]]:
    connection = _connect()
    try:
        return connection.execute(
            "SELECT id, title, due FROM reminders WHERE delivered = 0 ORDER BY due"
        ).fetchall()
    finally:
        connection.close()


def deliver_due(notify, now: datetime | None = None) -> None:
    now = datetime.now() if now is None else now
    for identifier, title, due in pending_reminders():
        if datetime.fromisoformat(due) > now:
            continue
        connection = _connect()
        try:
            with connection:
                claimed = connection.execute(
                    "UPDATE reminders SET lease = ? WHERE id = ? AND delivered = 0 AND lease < ?",
                    (time.time() + 300, identifier, time.time()),
                ).rowcount
            if not claimed:
                continue
            try:
                notify(f"Reminder: {title}")
            except Exception:
                with connection:
                    connection.execute("UPDATE reminders SET lease = 0 WHERE id = ?", (identifier,))
                raise
            with connection:
                connection.execute("UPDATE reminders SET delivered = 1, lease = 0 WHERE id = ?", (identifier,))
        finally:
            connection.close()


def watch_reminders(stop: threading.Event) -> None:
    from TextToSpeech.Fast_DF_TTS import speak

    while not stop.is_set():
        try:
            deliver_due(speak)
        except (OSError, ValueError, sqlite3.Error, RuntimeError):
            LOGGER.exception("Reminder delivery failed; undelivered reminders remain pending.")
        stop.wait(10)
