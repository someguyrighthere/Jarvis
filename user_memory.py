import json
import os
import re
import sys
from pathlib import Path

MEMORY_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
MEMORY_PATH = MEMORY_ROOT / "user_preferences.json"


def load_preferences():
    try:
        with open(MEMORY_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def remember_preference(key, value):
    preferences = load_preferences()
    preferences[key.strip().lower()] = value.strip()
    _save_preferences(preferences)
    return preferences


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

    instruction = instruction.strip()
    if instruction and instruction.casefold() not in {item.casefold() for item in instructions if isinstance(item, str)}:
        instructions.append(instruction)
    preferences["standing instructions"] = instructions
    _save_preferences(preferences)
    return preferences


def format_preferences():
    lines = []
    for key, value in load_preferences().items():
        values = value if isinstance(value, list) else [value]
        lines.extend(f"- {key}: {item}" for item in values)
    return "\n".join(lines)


def forget_preferences():
    try:
        os.remove(MEMORY_PATH)
    except FileNotFoundError:
        pass


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


def _save_preferences(preferences):
    with open(MEMORY_PATH, "w", encoding="utf-8") as file:
        json.dump(preferences, file, indent=2)
