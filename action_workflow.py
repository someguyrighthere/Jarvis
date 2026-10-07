import json
import logging
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


ACTION_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
PENDING_ACTION_PATH = ACTION_ROOT / "pending_computer_action.json"
ACTION_HISTORY_PATH = ACTION_ROOT / "computer_action_history.json"
MAX_HISTORY = 50
ACTION_APPROVAL_SECONDS = 600
LOGGER = logging.getLogger(__name__)


def _normalize(command):
    return re.sub(r"\s+", " ", command.strip().casefold()).rstrip(".,!? ")


def _action_kind(command):
    query = _normalize(command)
    if re.fullmatch(r"rename file .+ to .+", query):
        return "rename file"
    if query.startswith(("close ", "shut down ")):
        return "close"
    if query.startswith("open "):
        return "open"
    if query.startswith("send message on whatsapp"):
        return "send message"
    if query.startswith("create ") and re.search(r"\bfile\b", query):
        return "create file"
    if query.startswith("generate image"):
        return "generate image"
    if query.startswith("set volume level"):
        return "set volume"
    if query.startswith("set brightness percentage"):
        return "set brightness"
    if query.startswith("set alarm") or (
        query.startswith("tell me") and re.search(r"\b\d{1,2}:\d{2}\s*[ap]\.?m\b", query)
    ):
        return "schedule"
    if query == "undo last action":
        return "undo"
    return None


def requires_confirmation(command):
    return _action_kind(command) is not None


def _steps(command):
    kind = _action_kind(command)
    if kind == "rename file":
        from Features.file_operations import validate_rename

        source, target = validate_rename(command)
        return [
            f"Find '{source}' in SARA's working folder.",
            f"Verify '{target}' does not already exist, then rename the file.",
            f"Requested command: {command.strip()}",
        ]
    if kind in {"set volume", "set brightness"}:
        prefix = "set volume level" if kind == "set volume" else "set brightness percentage"
        match = re.fullmatch(rf"{re.escape(prefix)}\s+(\d{{1,3}})%?", _normalize(command))
        if not match or not 0 <= int(match.group(1)) <= 100:
            raise ValueError(f"{prefix.title()} must specify a whole percentage between 0 and 100.")
    actions = {
        "close": "Close the requested application. Unsaved work in that application may be lost.",
        "open": "Open the requested application or website.",
        "send message": "Start the WhatsApp message flow. Review the recipient and message before sending.",
        "create file": "Create the requested file in SARA's current working folder.",
        "rename file": "Rename the requested file in SARA's working folder without overwriting another file.",
        "generate image": "Generate the requested image and save it using SARA's image-generation workflow.",
        "set volume": "Change the Windows master volume to the requested level.",
        "set brightness": "Change the Windows display brightness to the requested level.",
        "schedule": "Create the requested alarm or reminder in SARA's local schedule.",
        "undo": "Restore the previous volume or brightness level for the most recent reversible action.",
    }
    return [actions[kind], f"Requested command: {command.strip()}"]


def _read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError):
        LOGGER.exception("Could not read SARA action data from %s", path)
        raise


def _write(path, data):
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f"{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary = Path(file.name)
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.flush()
        temporary.replace(path)
    except OSError:
        LOGGER.exception("Could not save SARA action data to %s", path)
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _pending():
    pending = _read(PENDING_ACTION_PATH, None)
    if pending is None:
        return None
    if not isinstance(pending, dict) or not isinstance(pending.get("command"), str) or not isinstance(pending.get("created_at"), str):
        raise ValueError("SARA's pending action record is invalid.")
    try:
        created_at = datetime.fromisoformat(pending["created_at"])
    except ValueError as error:
        raise ValueError("SARA's pending action timestamp is invalid.") from error
    if created_at.tzinfo is None:
        raise ValueError("SARA's pending action timestamp must include a timezone.")
    if datetime.now(timezone.utc) - created_at > timedelta(seconds=ACTION_APPROVAL_SECONDS):
        PENDING_ACTION_PATH.unlink(missing_ok=True)
        return None
    return pending


def propose_action(command):
    if not requires_confirmation(command):
        raise ValueError("That command does not require a computer-action approval.")
    if _pending():
        return "There is already a computer action waiting. Say approve action or cancel action first."
    steps = _steps(command)
    _write(PENDING_ACTION_PATH, {
        "command": command.strip(),
        "steps": steps,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "approved": False,
    })
    return "Action plan for review: " + " ".join(
        f"Step {index}: {step}" for index, step in enumerate(steps, 1)
    ) + " Say approve action to proceed, or cancel action to discard it."


def approve_action():
    pending = _pending()
    if not pending:
        return None
    pending["approved"] = True
    _write(PENDING_ACTION_PATH, pending)
    return pending["command"]


def cancel_action():
    try:
        PENDING_ACTION_PATH.unlink()
        return True
    except FileNotFoundError:
        return False


def consume_approval(command):
    pending = _pending()
    if not pending or not pending.get("approved") or _normalize(pending["command"]) != _normalize(command):
        return False
    PENDING_ACTION_PATH.unlink()
    return True


def capture_undo_state(command):
    kind = _action_kind(command)
    if kind == "rename file":
        from Features.file_operations import validate_rename

        source, target = validate_rename(command)
        return {"kind": kind, "source": source, "target": target}
    try:
        if kind == "set volume":
            from Features.set_get_volume import get_volume_percentage

            return {"kind": kind, "value": get_volume_percentage()}
        if kind == "set brightness":
            from Features.br_persentage import get_brightness_windows

            value = get_brightness_windows()
            if isinstance(value, int):
                return {"kind": kind, "value": value}
    except (ImportError, OSError, RuntimeError, ValueError):
        LOGGER.exception("Could not capture previous system setting for undo")
    return None


def record_dispatched_action(command, undo_state=None):
    history = _read(ACTION_HISTORY_PATH, [])
    if not isinstance(history, list):
        raise ValueError("SARA's computer action history is invalid.")
    history.append({
        "command": command.strip(),
        "status": "dispatched",
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        "undo": undo_state,
    })
    _write(ACTION_HISTORY_PATH, history[-MAX_HISTORY:])


def undo_last_action():
    history = _read(ACTION_HISTORY_PATH, [])
    if not isinstance(history, list):
        raise ValueError("SARA's computer action history is invalid.")
    entry = next((item for item in reversed(history) if isinstance(item, dict) and item.get("status") == "dispatched"), None)
    if entry is None or not entry.get("undo"):
        return "There is no recent volume or brightness change I can undo."
    undo = entry["undo"]
    if undo.get("kind") == "set volume":
        from Features.set_get_volume import set_volume_windows

        set_volume_windows(undo["value"])
    elif undo.get("kind") == "set brightness":
        from Features.set_br import set_brightness_windows

        set_brightness_windows(undo["value"])
    elif undo.get("kind") == "rename file":
        from Features.file_operations import undo_rename

        message = undo_rename(undo["source"], undo["target"])
    else:
        return "I cannot undo that action automatically."
    entry["status"] = "undo_dispatched"
    _write(ACTION_HISTORY_PATH, history)
    if undo.get("kind") == "rename file":
        return message
    return f"I asked Windows to restore the previous {undo['kind'].removeprefix('set ')} setting to {undo['value']}%."


def list_action_history(limit=10):
    history = _read(ACTION_HISTORY_PATH, [])
    if not isinstance(history, list):
        raise ValueError("SARA's computer action history is invalid.")
    return [
        {
            "command": entry.get("command", "Unknown command"),
            "status": entry.get("status", "unknown"),
            "dispatched_at": entry.get("dispatched_at", ""),
            "undo_available": bool(entry.get("undo")) and entry.get("status") == "dispatched",
        }
        for entry in history[-limit:]
        if isinstance(entry, dict)
    ]


def describe_action_history(limit=10):
    history = list_action_history(limit)
    if not history:
        return "No approved computer actions have been recorded yet."
    lines = []
    for entry in history[-limit:]:
        lines.append(f"{entry['command']} ({entry['status']})")
    return "Recent approved actions: " + "; ".join(lines) + ". Say undo last action to restore the last reversible setting change."
