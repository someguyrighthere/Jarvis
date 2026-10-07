import json
import logging
import re
import tempfile
from collections import Counter
from pathlib import Path

from local_storage import LEGACY_DATA_ROOT, LOCAL_DATA_DIR

MEMORY_PATH = LOCAL_DATA_DIR / "user_preferences.json"
LEGACY_MEMORY_PATH = LEGACY_DATA_ROOT / "user_preferences.json"
LEARNING_THRESHOLD = 2
MAX_MEMORY_ENTRIES = 100
MAX_MEMORY_KEY_LENGTH = 100
MAX_MEMORY_VALUE_LENGTH = 1000
LOGGER = logging.getLogger(__name__)
_OBSERVED_DETAILS = Counter()
_PENDING_LEARNING = None
_DECLINED_DETAILS = set()

_USER_DETAIL_PATTERNS = (
    ("name", re.compile(r"^(?:my name is|you can call me)\s+(.+)$", re.IGNORECASE)),
    ("city", re.compile(r"^(?:i live in|i'm in|i am in|my city is)\s+(.+)$", re.IGNORECASE)),
    ("location", re.compile(r"^my location is\s+(.+)$", re.IGNORECASE)),
    ("country", re.compile(r"^(?:i live in the country of|my country is)\s+(.+)$", re.IGNORECASE)),
    ("location", re.compile(r"^(?:i'm from|i am from)\s+(.+)$", re.IGNORECASE)),
    ("occupation", re.compile(r"^(?:i work as|my job is|i'm a|i am a|i'm an|i am an)\s+(.+)$", re.IGNORECASE)),
    ("preferred language", re.compile(r"^(?:my preferred language is|i prefer to speak)\s+(.+)$", re.IGNORECASE)),
    ("preferred units", re.compile(r"^(?:i prefer|please use)\s+(metric|imperial)\s+(?:units|measurements)\s*$", re.IGNORECASE)),
    ("current project", re.compile(r"^(?:i'm working on|i am working on|my current project is)\s+(.+)$", re.IGNORECASE)),
)


def load_preferences():
    _migrate_legacy_memory()
    try:
        data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError):
        LOGGER.exception("Could not read SARA's saved memory")
        raise
    if not isinstance(data, dict):
        raise ValueError("SARA's saved memory must contain a JSON object.")
    return data


def remember_preference(key, value):
    key, value = _validate_memory_item(key, value)
    preferences = load_preferences()
    normalized_key = key.casefold()
    existing_key = next((item for item in preferences if item.casefold() == normalized_key), key.lower())
    preferences[existing_key] = value
    _save_preferences(preferences)
    return preferences


def observe_user_detail(text):
    global _PENDING_LEARNING
    detail = _extract_user_detail(text)
    if detail is None:
        return None
    key, value = detail
    if any(
        entry["key"].casefold() == key.casefold() and entry["value"].casefold() == value.casefold()
        for entry in list_memory_entries()
    ):
        return None
    identity = (key.casefold(), value.casefold())
    if identity in _DECLINED_DETAILS:
        return None
    _OBSERVED_DETAILS[identity] += 1
    if _OBSERVED_DETAILS[identity] < LEARNING_THRESHOLD or _PENDING_LEARNING is not None:
        return None
    _PENDING_LEARNING = {"key": key, "value": value}
    return (
        f"I've heard you mention that your {key} is {value}. "
        "Would you like me to remember that on this computer? Say 'remember it' or 'don't remember it'."
    )


def resolve_learning_request(text):
    global _PENDING_LEARNING
    if _PENDING_LEARNING is None:
        return None
    response = re.sub(r"[.!?]+$", "", text.strip().casefold())
    if response in {"remember it", "yes remember it", "yes, remember it", "remember that", "yes, remember that"}:
        detail = _PENDING_LEARNING
        remember_preference(detail["key"], detail["value"])
        _PENDING_LEARNING = None
        return f"Saved. I'll remember your {detail['key']} is {detail['value']}. You can edit or delete it in Manage Memory."
    if response in {"don't remember it", "do not remember it", "no", "no thanks", "forget it", "don't save it"}:
        detail = _PENDING_LEARNING
        _DECLINED_DETAILS.add((detail["key"].casefold(), detail["value"].casefold()))
        _PENDING_LEARNING = None
        return f"Understood. I won't save that detail about your {detail['key']}."
    return None


def parse_preference_request(text):
    request = text.strip()
    match = re.match(r"^(?:remember|learn)(?:\s+(?:that|this))?\s+(.+)$", request, re.IGNORECASE)
    if match:
        statement = match.group(1).strip()
        assignment = re.match(r"^(.+?)\s+is\s+(.+)$", statement, re.IGNORECASE)
        if assignment:
            return "preference", assignment.group(1).strip(), assignment.group(2).strip()
        return "instruction", "standing instructions", _normalize_instruction(statement)

    match = re.match(r"^(?:from now on|going forward)\s*,?\s+(.+)$", request, re.IGNORECASE)
    if match:
        return "instruction", "standing instructions", _normalize_instruction(match.group(1))
    return None


def remember_instruction(instruction):
    preferences = load_preferences()
    instructions = preferences.get("standing instructions", [])
    if isinstance(instructions, str):
        instructions = [instructions]
    elif not isinstance(instructions, list):
        instructions = []

    _, instruction = _validate_memory_item("standing instructions", instruction)
    if instruction and instruction.casefold() not in {item.casefold() for item in instructions if isinstance(item, str)}:
        instructions.append(instruction)
    if len(instructions) > MAX_MEMORY_ENTRIES:
        raise ValueError(f"SARA can save at most {MAX_MEMORY_ENTRIES} memory entries.")
    preferences["standing instructions"] = instructions
    _save_preferences(preferences)
    return preferences


def add_memory_entry(key, value):
    key, value = _validate_memory_item(key, value)
    preferences = load_preferences()
    existing_key = next((item for item in preferences if item.casefold() == key.casefold()), key.lower())
    current = preferences.get(existing_key, [])
    values = current if isinstance(current, list) else [current]
    if sum(len(items if isinstance(items, list) else [items]) for items in preferences.values()) >= MAX_MEMORY_ENTRIES:
        raise ValueError(f"SARA can save at most {MAX_MEMORY_ENTRIES} memory entries.")
    values.append(value)
    preferences[existing_key] = values
    _save_preferences(preferences)
    return preferences


def remember_note(note):
    return add_memory_entry("personal notes", note)


def forget_memory_category(key):
    if not isinstance(key, str) or not key.strip():
        raise ValueError("A memory category is required.")
    preferences = load_preferences()
    existing_key = next((item for item in preferences if item.casefold() == key.casefold()), None)
    if existing_key is None:
        return False
    del preferences[existing_key]
    _save_preferences(preferences)
    return True


def list_memory_entries():
    entries = []
    for key, value in load_preferences().items():
        values = value if isinstance(value, list) else [value]
        entries.extend(
            {"key": key, "index": index, "value": item}
            for index, item in enumerate(values)
            if isinstance(item, str)
        )
    return entries


def update_memory_entry(key, index, value):
    key, value = _validate_memory_item(key, value)
    preferences = load_preferences()
    existing_key = next((item for item in preferences if item.casefold() == key.casefold()), None)
    if existing_key is None:
        raise KeyError("That saved memory entry no longer exists.")
    values = preferences[existing_key] if isinstance(preferences[existing_key], list) else [preferences[existing_key]]
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(values):
        raise KeyError("That saved memory entry no longer exists.")
    values[index] = value
    preferences[existing_key] = values[0] if len(values) == 1 else values
    _save_preferences(preferences)
    return preferences


def delete_memory_entry(key, index):
    if not isinstance(key, str) or not key.strip():
        raise ValueError("A memory category is required.")
    preferences = load_preferences()
    existing_key = next((item for item in preferences if item.casefold() == key.casefold()), None)
    if existing_key is None:
        return False
    values = preferences[existing_key] if isinstance(preferences[existing_key], list) else [preferences[existing_key]]
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(values):
        return False
    del values[index]
    if values:
        preferences[existing_key] = values[0] if len(values) == 1 else values
    else:
        del preferences[existing_key]
    _save_preferences(preferences)
    return True


def mutate_memory(payload):
    if not isinstance(payload, dict):
        raise ValueError("Memory changes must be a JSON object.")
    action = payload.get("action")
    if action == "add" and set(payload) == {"action", "key", "value"}:
        add_memory_entry(payload["key"], payload["value"])
    elif action == "update" and set(payload) == {"action", "key", "index", "value"}:
        update_memory_entry(payload["key"], payload["index"], payload["value"])
    elif action == "delete" and set(payload) == {"action", "key", "index"}:
        delete_memory_entry(payload["key"], payload["index"])
    else:
        raise ValueError("Use a valid add, update, or delete memory request.")
    return list_memory_entries()


def format_preferences():
    lines = []
    for key, value in load_preferences().items():
        if key.casefold() == "personal notes" or _is_profile_key(key):
            continue
        values = value if isinstance(value, list) else [value]
        lines.extend(f"- {key}: {item}" for item in values)
    return "\n".join(lines)


def format_user_profile():
    lines = []
    for key, value in load_preferences().items():
        if not _is_profile_key(key):
            continue
        values = value if isinstance(value, list) else [value]
        lines.extend(f"- {key}: {item}" for item in values)
    return "\n".join(lines)


def format_personal_notes(query, limit=5):
    query_terms = set(re.findall(r"[a-z0-9]{3,}", query.casefold()))
    entries = [
        entry for entry in list_memory_entries()
        if entry["key"].casefold() == "personal notes"
    ]
    scored = [
        (len(query_terms & set(re.findall(r"[a-z0-9]{3,}", entry["value"].casefold()))), entry)
        for entry in entries
    ]
    relevant = [entry for score, entry in scored if score > 0]
    if not relevant:
        relevant = entries[-limit:]
    return "\n".join(f"- {entry['value']}" for entry in relevant[-limit:])


def forget_preferences():
    _save_preferences({})


def describe_preferences():
    preferences = load_preferences()
    if not preferences:
        return "I do not have any saved preferences yet."
    items = [
        f"{key}: {item}"
        for key, value in preferences.items()
        for item in (value if isinstance(value, list) else [value])
    ]
    return "I remember " + "; ".join(items) + "."


def _normalize_instruction(instruction):
    instruction = re.sub(r"^not to\s+", "Do not ", instruction, flags=re.IGNORECASE)
    instruction = re.sub(r"^(?:please\s+)?don't\s+", "Do not ", instruction, flags=re.IGNORECASE)
    instruction = re.sub(r"^I do not want you to\s+", "Do not ", instruction, flags=re.IGNORECASE)
    instruction = re.sub(r"^I don't want you to\s+", "Do not ", instruction, flags=re.IGNORECASE)
    return instruction


def _extract_user_detail(text):
    statement = re.sub(r"[.!?]+$", "", text.strip())
    for key, pattern in _USER_DETAIL_PATTERNS:
        match = pattern.fullmatch(statement)
        if not match:
            continue
        value = match.group(1).strip().strip("\"'")
        value = re.sub(r"\s+", " ", value)
        if (
            not value
            or len(value) > 100
            or any(character.isdigit() for character in value)
            or re.search(r"\b(?:street|st\.|road|rd\.|avenue|ave\.|apartment|unit|postcode|zip code)\b", value, re.IGNORECASE)
        ):
            return None
        if key == "occupation" and len(value.split()) > 8:
            return None
        return key, value
    return None


def _is_profile_key(key):
    normalized = key.casefold()
    return any(
        field in normalized
        for field in ("name", "city", "location", "country", "timezone", "occupation", "job", "current project")
    )


def _migrate_legacy_memory():
    if MEMORY_PATH.exists() or LEGACY_MEMORY_PATH == MEMORY_PATH or not LEGACY_MEMORY_PATH.is_file():
        return
    try:
        data = json.loads(LEGACY_MEMORY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        LOGGER.exception("Could not migrate SARA's existing local memory")
        raise
    if not isinstance(data, dict):
        raise ValueError("The existing SARA memory file must contain a JSON object.")
    _save_preferences(data)


def _validate_memory_item(key, value):
    if not isinstance(key, str) or not isinstance(value, str):
        raise ValueError("Memory categories and entries must be text.")
    key = key.strip()
    value = value.strip()
    if not key or len(key) > MAX_MEMORY_KEY_LENGTH:
        raise ValueError(f"Memory categories must be between 1 and {MAX_MEMORY_KEY_LENGTH} characters.")
    if not value or len(value) > MAX_MEMORY_VALUE_LENGTH:
        raise ValueError(f"Memory entries must be between 1 and {MAX_MEMORY_VALUE_LENGTH} characters.")
    return key, value


def _save_preferences(preferences):
    temporary_path = None
    try:
        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=MEMORY_PATH.parent,
            prefix=f"{MEMORY_PATH.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            json.dump(preferences, file, indent=2, ensure_ascii=False)
            file.flush()
        temporary_path.replace(MEMORY_PATH)
    except OSError:
        LOGGER.exception("Could not save SARA's local memory")
        raise
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
