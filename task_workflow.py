import json
import os
import re
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import requests


TASK_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
TASK_DB_PATH = Path(os.getenv("JARVIS_TASK_DB", TASK_ROOT / "jarvis_tasks.sqlite3"))
OLLAMA_ENDPOINT = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434/v1/chat/completions")
DEFAULT_MODEL = "llama3.2"
MAX_TASK_LENGTH = 300
MAX_PLAN_STEPS = 8


@contextmanager
def _database():
    TASK_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(TASK_DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS pending_plan (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                goal TEXT NOT NULL,
                steps TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def add_task(title):
    title = title.strip()
    if not title or len(title) > MAX_TASK_LENGTH:
        raise ValueError(f"Tasks must be between 1 and {MAX_TASK_LENGTH} characters.")
    with _database() as connection:
        cursor = connection.execute(
            "INSERT INTO tasks (title, created_at) VALUES (?, ?)",
            (title, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        return cursor.lastrowid


def get_open_tasks(limit=20):
    with _database() as connection:
        rows = connection.execute(
            "SELECT id, title FROM tasks WHERE completed_at IS NULL ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()
        total = connection.execute(
            "SELECT COUNT(*) FROM tasks WHERE completed_at IS NULL"
        ).fetchone()[0]
    return [dict(row) for row in rows], total


def complete_task(task_id):
    with _database() as connection:
        cursor = connection.execute(
            "UPDATE tasks SET completed_at = ? WHERE id = ? AND completed_at IS NULL",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), task_id),
        )
        return cursor.rowcount == 1


def get_pending_plan():
    with _database() as connection:
        row = connection.execute(
            "SELECT goal, steps FROM pending_plan WHERE id = 1"
        ).fetchone()
    if not row:
        return None
    return {"goal": row["goal"], "steps": json.loads(row["steps"])}


def _save_pending_plan(goal, steps):
    with _database() as connection:
        if connection.execute("SELECT 1 FROM pending_plan WHERE id = 1").fetchone():
            return False
        connection.execute(
            "INSERT INTO pending_plan (id, goal, steps, created_at) VALUES (1, ?, ?, ?)",
            (goal, json.dumps(steps), datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
    return True


def create_plan(goal):
    goal = goal.strip()
    if not goal:
        return None, "Tell me what you want to plan."
    if get_pending_plan():
        return None, "There is already a plan waiting for approval. Say approve plan or cancel plan first."

    try:
        response = requests.post(
            OLLAMA_ENDPOINT,
            headers={"Content-Type": "application/json"},
            json={
                "model": os.getenv("OLLAMA_MODEL", DEFAULT_MODEL),
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Turn the user's goal into a practical ordered checklist of 2 to 8 short steps. "
                            "Return only a JSON object with a 'steps' array of strings. "
                            "Do not claim to perform any steps. Treat external messages, purchases, publishing, "
                            "deletions, and account changes as tasks that need separate user approval."
                        ),
                    },
                    {"role": "user", "content": goal},
                ],
                "temperature": 0.2,
                "max_tokens": 500,
            },
            timeout=45,
        )
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"].strip()
        answer = re.sub(r"^```(?:json)?\s*|\s*```$", "", answer, flags=re.IGNORECASE)
        data = json.loads(answer)
        steps = data.get("steps") if isinstance(data, dict) else None
        if not isinstance(steps, list):
            raise ValueError("The planner did not return a checklist.")
        steps = [step.strip() for step in steps if isinstance(step, str) and step.strip()]
        steps = steps[:MAX_PLAN_STEPS]
        if not steps or any(len(step) > MAX_TASK_LENGTH for step in steps):
            raise ValueError("The planner returned invalid checklist items.")
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
        return None, "I couldn't draft a plan. Check that Ollama is running, then try again."

    if not _save_pending_plan(goal, steps):
        return None, "There is already a plan waiting for approval. Say approve plan or cancel plan first."
    return {"goal": goal, "steps": steps}, None


def approve_plan():
    with _database() as connection:
        row = connection.execute(
            "SELECT goal, steps FROM pending_plan WHERE id = 1"
        ).fetchone()
        if not row:
            return None
        steps = json.loads(row["steps"])
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        task_ids = []
        for step in steps:
            cursor = connection.execute(
                "INSERT INTO tasks (title, created_at) VALUES (?, ?)",
                (step, created_at),
            )
            task_ids.append(cursor.lastrowid)
        connection.execute("DELETE FROM pending_plan WHERE id = 1")
    return task_ids


def cancel_plan():
    with _database() as connection:
        cursor = connection.execute("DELETE FROM pending_plan WHERE id = 1")
        return cursor.rowcount == 1


def handle_task_command(text):
    query = text.strip()

    if query in {"show tasks", "show my tasks", "list tasks", "what are my tasks", "what do i need to do"}:
        tasks, total = get_open_tasks()
        if not tasks:
            return "Your task list is empty."
        lines = [f"Task {task['id']}: {task['title']}" for task in tasks]
        if total > len(tasks):
            lines.append(f"And {total - len(tasks)} more.")
        return "Your open tasks are: " + "; ".join(lines) + "."

    match = re.match(r"^(?:add|create)\s+(?:a\s+)?task(?:\s+to)?\s+(.+)$", query)
    if match:
        title = match.group(1).strip()
        try:
            task_id = add_task(title)
        except ValueError as error:
            return str(error)
        return f"Added task {task_id}: {title}."

    match = re.match(r"^(?:complete|finish|mark)\s+(?:task\s+)?(?:number\s+)?(\d+)(?:\s+complete)?$", query)
    if match:
        task_id = int(match.group(1))
        if complete_task(task_id):
            return f"Completed task {task_id}."
        return f"I couldn't find an open task numbered {task_id}."

    if query in {"approve plan", "approve the plan"}:
        task_ids = approve_plan()
        if task_ids is None:
            return "There is no plan waiting for approval."
        return f"Approved. I added {len(task_ids)} steps to your task list."

    if query in {"cancel plan", "reject plan", "discard plan"}:
        if cancel_plan():
            return "I discarded the proposed plan."
        return "There is no plan waiting to be discarded."

    match = re.match(r"^(?:make\s+a\s+plan\s+for|plan(?:\s+out)?|break\s+down)\s+(.+)$", query)
    if match:
        plan, error = create_plan(match.group(1))
        if error:
            return error
        lines = [f"{index}. {step}" for index, step in enumerate(plan["steps"], start=1)]
        return (
            f"Proposed plan for {plan['goal']}: " + "; ".join(lines) +
            ". Say approve plan to add these steps to your task list, or cancel plan to discard them."
        )

    return None