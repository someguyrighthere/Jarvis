import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests

from system_admin import get_network_status, get_security_status, get_system_status


PROJECT_ROOT = Path(__file__).resolve().parent
EXTENSIONS_DIR = PROJECT_ROOT / "SaraExtensions"
PENDING_PATH = PROJECT_ROOT / "extension_proposal.json"
OLLAMA_ENDPOINT = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434/v1/chat/completions")
MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
TOOL_RUNNERS = {
    "system_status": get_system_status,
    "network_status": get_network_status,
    "security_status": get_security_status,
}
TOOL_DESCRIPTIONS = {
    "system_status": "Read CPU, memory, and free disk usage for this computer.",
    "network_status": "Read active network interfaces and cumulative traffic for this computer.",
    "security_status": "Read Microsoft Defender status for this computer.",
}
MAX_STEPS = 4
MAX_TRIGGERS = 5


def _read_json(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as temporary_file:
            json.dump(value, temporary_file, indent=2)
            temporary_file.write("\n")
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def _normalize(text):
    return re.sub(r"\s+", " ", text.strip().lower()).rstrip(".,!? ")


def validate_extension(extension):
    if not isinstance(extension, dict) or set(extension) != {"name", "description", "triggers", "steps"}:
        return None, "The extension must contain only name, description, triggers, and steps."

    name = extension["name"]
    description = extension["description"]
    triggers = extension["triggers"]
    steps = extension["steps"]
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{1,39}", name):
        return None, "The extension name must be a short lowercase identifier."
    if not isinstance(description, str) or not description.strip() or len(description) > 500:
        return None, "The extension needs a description of at most 500 characters."
    if not isinstance(triggers, list) or not 1 <= len(triggers) <= MAX_TRIGGERS:
        return None, f"An extension must have between 1 and {MAX_TRIGGERS} trigger phrases."

    normalized_triggers = []
    reserved = {"approve extension", "reject extension", "show extension proposal", "list extensions"}
    for trigger in triggers:
        if not isinstance(trigger, str) or not 3 <= len(trigger.strip()) <= 80:
            return None, "Each trigger phrase must be between 3 and 80 characters."
        normalized = _normalize(trigger)
        if len(normalized.split()) < 2:
            return None, "Trigger phrases must contain at least two words to avoid accidental matches."
        if normalized in reserved or normalized.startswith(("create tool", "make tool", "approve ", "reject ")):
            return None, f"The trigger phrase '{normalized}' conflicts with an extension command."
        if normalized in normalized_triggers:
            return None, "Trigger phrases must be unique."
        normalized_triggers.append(normalized)
    if not normalized_triggers:
        return None, "At least one unique trigger phrase is required."

    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        return None, f"An extension must contain between 1 and {MAX_STEPS} tool steps."
    normalized_steps = []
    for step in steps:
        if not isinstance(step, dict) or set(step) != {"tool"}:
            return None, "Each step must refer to one allowlisted tool and take no other arguments."
        tool = step["tool"]
        if not isinstance(tool, str) or tool not in TOOL_RUNNERS:
            return None, f"The tool '{tool}' is not available for extensions."
        normalized_steps.append({"tool": tool})

    return {
        "name": name,
        "description": description.strip(),
        "triggers": normalized_triggers,
        "steps": normalized_steps,
    }, None


def _extract_json_object(text):
    """Pull the first complete JSON object out of an LLM response.

    Small local models often ignore "reply with JSON only" instructions and wrap
    the object in chatter and/or a ```json fenced block. This locates a fenced
    block if present, otherwise scans for the first balanced {...} span, so a
    stray sentence before/after the JSON doesn't break parsing.
    """
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = fence_match.group(1).strip() if fence_match else text

    start = candidate.find("{")
    if start == -1:
        raise ValueError("The model's response did not contain a JSON object.")

    depth = 0
    in_string = False
    escape = False
    end = None
    for index in range(start, len(candidate)):
        char = candidate[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index
                break
    if end is None:
        raise ValueError("The model's JSON object was never closed.")
    return candidate[start : end + 1]


def create_extension_proposal(request):
    request = request.strip()
    if not request:
        return "Tell me what task the new extension should help with."
    if _read_json(PENDING_PATH):
        return "There is already an extension proposal waiting. Say approve extension or reject extension first."

    available_tools = "\n".join(
        f"- {name}: {description}" for name, description in TOOL_DESCRIPTIONS.items()
    )
    prompt = (
        "Design a reusable Sara extension as JSON only, with exactly these keys: "
        "name, description, triggers, steps. Do not return Python or executable code. "
        "Each step must be an object with exactly one key, tool. Use only the listed tool IDs. "
        f"Use 1 to {MAX_STEPS} steps and 1 to {MAX_TRIGGERS} short trigger phrases. "
        "If the request cannot be served by these tools, use an empty steps array.\n\n"
        f"Available read-only tools:\n{available_tools}\n\n"
        f"User's requested extension: {request}"
    )
    try:
        response = requests.post(
            OLLAMA_ENDPOINT,
            headers={"Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 1000,
            },
            timeout=60,
        )
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"].strip()
        # strict=False tolerates raw control characters (e.g. literal newlines) that
        # models sometimes leave unescaped inside multi-line description strings.
        extension, error = validate_extension(json.loads(_extract_json_object(answer), strict=False))
        if error:
            return f"I couldn't make a usable extension proposal: {error}"
        if not extension["steps"]:
            return "I don't have an approved tool for that task yet, so I can't create an extension for it."
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
        return f"I couldn't create an extension proposal: {error}"

    _write_json(
        PENDING_PATH,
        {
            "status": "proposed",
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "request": request,
            "extension": extension,
        },
    )
    tool_names = ", ".join(step["tool"] for step in extension["steps"])
    return (
        f"Proposed extension '{extension['name']}': {extension['description']} "
        f"It responds to: {', '.join(extension['triggers'])}. It uses: {tool_names}. "
        "Say show extension proposal to review it, approve extension to enable it, or reject extension to discard it."
    )


def show_extension_proposal():
    proposal = _read_json(PENDING_PATH)
    if not proposal or proposal.get("status") != "proposed":
        return "There is no extension proposal waiting for review."
    extension, error = validate_extension(proposal.get("extension"))
    if error:
        return f"The pending extension proposal is invalid: {error}"
    steps = ", ".join(step["tool"] for step in extension["steps"])
    return (
        f"Extension '{extension['name']}': {extension['description']} "
        f"Triggers: {', '.join(extension['triggers'])}. Tools: {steps}."
    )


def approve_extension():
    proposal = _read_json(PENDING_PATH)
    if not proposal or proposal.get("status") != "proposed":
        return "There is no extension proposal waiting for approval."
    extension, error = validate_extension(proposal.get("extension"))
    if error:
        return f"I didn't enable the extension because its proposal is invalid: {error}"

    EXTENSIONS_DIR.mkdir(parents=True, exist_ok=True)
    destination = EXTENSIONS_DIR / f"{extension['name']}.json"
    if destination.exists():
        return f"An extension named '{extension['name']}' is already enabled."
    for path in EXTENSIONS_DIR.glob("*.json"):
        existing = _read_json(path)
        if existing and set(existing.get("triggers", [])) & set(extension["triggers"]):
            return f"One of those trigger phrases is already used by extension '{existing.get('name', path.stem)}'."

    extension["enabled_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(destination, extension)
    try:
        PENDING_PATH.unlink()
    except OSError:
        return f"Enabled extension '{extension['name']}', but could not remove its pending proposal."
    return f"Enabled extension '{extension['name']}'. It is ready to use."


def reject_extension():
    proposal = _read_json(PENDING_PATH)
    if not proposal or proposal.get("status") != "proposed":
        return "There is no extension proposal waiting to reject."
    try:
        PENDING_PATH.unlink()
    except OSError as error:
        return f"I couldn't discard the extension proposal: {error}"
    return "I discarded the extension proposal."


def list_extensions():
    if not EXTENSIONS_DIR.is_dir():
        return "No extensions are enabled."
    enabled = []
    for path in sorted(EXTENSIONS_DIR.glob("*.json")):
        extension = _read_json(path)
        if extension:
            normalized, error = validate_extension(
                {key: extension.get(key) for key in ("name", "description", "triggers", "steps")}
            )
            if not error:
                enabled.append(normalized)
    if not enabled:
        return "No valid extensions are enabled."
    return "Enabled extensions: " + "; ".join(
        f"{extension['name']} ({', '.join(extension['triggers'])})" for extension in enabled
    ) + "."


def run_extension(text):
    query = _normalize(text)
    if not EXTENSIONS_DIR.is_dir():
        return None
    for path in sorted(EXTENSIONS_DIR.glob("*.json")):
        stored = _read_json(path)
        if not stored:
            continue
        extension, error = validate_extension(
            {key: stored.get(key) for key in ("name", "description", "triggers", "steps")}
        )
        if error or not any(query == trigger or query.startswith(trigger + " ") for trigger in extension["triggers"]):
            continue
        results = [TOOL_RUNNERS[step["tool"]]() for step in extension["steps"]]
        return f"{extension['name']}: " + " ".join(results)
    return None


def handle_extension_command(text):
    query = _normalize(text)
    if query in {"show extension proposal", "show pending extension", "review extension"}:
        return show_extension_proposal()
    if query in {"approve extension", "enable extension", "approve proposed extension"}:
        return approve_extension()
    if query in {"reject extension", "cancel extension", "discard extension proposal"}:
        return reject_extension()
    if query in {"list extensions", "show extensions", "what extensions are enabled"}:
        return list_extensions()

    match = re.match(
        r"^(?:create|make|build|develop)\s+(?:a\s+)?(?:new\s+)?(?:reusable\s+)?(?:tool|extension)(?:\s+(?:for|to|that)\s+)?(.+)$",
        query,
    )
    if match:
        return create_extension_proposal(match.group(1))
    return run_extension(query)


def should_propose_extension(text):
    return bool(
        re.match(
            r"^(?:(?:please|can you|could you)\s+)*(?:create|make|build|monitor|inspect|analy[sz]e|find|track|organize|summarize|report)\b",
            _normalize(text),
        )
    )