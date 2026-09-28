import json
import re
from datetime import datetime, timezone

import project_workflow


TOOLS_DIR = project_workflow.LOCAL_DATA_DIR / "tools"
PENDING_PATH = project_workflow.LOCAL_DATA_DIR / "tool_proposal.json"
MAX_TRIGGERS = 4
MAX_RESPONSE_CHARACTERS = 4000
RESERVED_TRIGGERS = {
    "show project proposal",
    "approve project",
    "reject project",
    "run project",
    "approve run",
    "reject run",
    "show run request",
    "open application",
    "open website",
    "close application",
    "shut down",
    "tell me",
    "set alarm",
    "learn this",
    "save this knowledge",
    "forget learned knowledge",
    "remember",
    "improve yourself",
    "check weather",
    "weather",
    "what can you see",
    "what is this",
    "create file",
    "generate image",
    "send message on whatsapp",
    "check microphone",
    "check speaker",
    "check brightness",
    "set brightness",
    "check volume",
    "set volume",
    "check running application",
    "play music",
    "search",
    "show extension proposal",
    "approve extension",
    "reject extension",
    "list extensions",
    "list my tools",
    "show tool proposal",
    "approve tool",
    "reject tool",
    "check security",
    "security status",
    "check my network",
    "network status",
    "check system health",
    "system status",
    "hardware status",
    "monitor hardware",
    "monitor my network",
    "scan for threats",
    "run security scan",
    "check for updates",
    "update drivers and software",
    "show my tasks",
    "approve plan",
    "cancel plan",
}


def _normalize(text):
    return re.sub(r"\s+", " ", text.strip().lower()).rstrip(".,!? ")


def validate_tool_manifest(manifest, project_name):
    expected = {"name", "description", "triggers", "entrypoint", "permissions"}
    if not isinstance(manifest, dict) or set(manifest) != expected:
        return None, "The tool manifest must contain only name, description, triggers, entrypoint, and permissions."
    name = manifest["name"]
    description = manifest["description"]
    triggers = manifest["triggers"]
    if name != project_name or not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]{1,39}", name):
        return None, "The tool name must match its saved project name."
    if not isinstance(description, str) or not description.strip() or len(description) > 300:
        return None, "The tool needs a description of at most 300 characters."
    if manifest["entrypoint"] != "tool.py":
        return None, "Sara tools must use the reviewed root tool.py entry point."
    if manifest["permissions"] != []:
        return None, "Sara tools cannot request additional permissions in this version."
    if not isinstance(triggers, list) or not 1 <= len(triggers) <= MAX_TRIGGERS:
        return None, f"A Sara tool must define between 1 and {MAX_TRIGGERS} trigger phrases."

    normalized_triggers = []
    for trigger in triggers:
        if not isinstance(trigger, str) or not 5 <= len(trigger.strip()) <= 80:
            return None, "Each tool trigger must be between 5 and 80 characters."
        normalized = _normalize(trigger)
        if len(normalized.split()) < 2:
            return None, "Tool triggers must contain at least two words."
        if normalized in RESERVED_TRIGGERS or any(
            reserved.startswith(normalized + " ") or normalized.startswith(reserved + " ")
            for reserved in RESERVED_TRIGGERS
        ):
            return None, f"The trigger phrase '{normalized}' conflicts with a Sara command."
        if normalized in normalized_triggers:
            return None, "Tool trigger phrases must be unique."
        normalized_triggers.append(normalized)
    return {
        "name": name,
        "description": description.strip(),
        "triggers": normalized_triggers,
        "entrypoint": "tool.py",
        "permissions": [],
    }, None


def _manifest_from_project(project):
    manifest_file = next((item for item in project["files"] if item["path"] == "sara_tool.json"), None)
    entrypoint = next((item for item in project["files"] if item["path"] == "tool.py"), None)
    if not manifest_file or not entrypoint:
        return None, "The project needs root sara_tool.json and tool.py files."
    try:
        manifest = json.loads(manifest_file["content"])
    except (TypeError, json.JSONDecodeError) as error:
        return None, f"The Sara tool manifest is invalid: {error}"
    return validate_tool_manifest(manifest, project["name"])


def create_tool_project(request):
    return project_workflow.create_project_proposal(request, tool_mode=True)


def propose_project_as_tool(project_name):
    if project_workflow._read_json(project_workflow.PENDING_PATH):
        return "Finish the pending project proposal before proposing a saved project as a tool."
    if project_workflow._read_json(PENDING_PATH):
        return "There is already a Sara tool proposal waiting. Say approve tool or reject tool first."
    project, error = project_workflow._load_saved_project(project_name)
    if error:
        return error
    manifest, error = _manifest_from_project(project)
    if error:
        return error
    for path in TOOLS_DIR.glob("*.json") if TOOLS_DIR.is_dir() else ():
        enabled = project_workflow._read_json(path)
        enabled_manifest = enabled.get("manifest") if enabled else None
        if enabled_manifest and set(enabled_manifest.get("triggers", [])) & set(manifest["triggers"]):
            return f"A trigger phrase is already used by Sara tool '{enabled_manifest.get('name', path.stem)}'."

    project_fingerprint = project_workflow._project_fingerprint(project)
    project_path = project_workflow.PROJECTS_DIR / project_name
    project_workflow._write_json(
        PENDING_PATH,
        {
            "status": "proposed",
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "project": project_name,
            "project_path": str(project_path),
            "fingerprint": project_fingerprint,
            "manifest": manifest,
        },
    )
    return (
        f"Proposed Sara tool '{manifest['name']}': {manifest['description']} "
        f"Triggers: {', '.join(manifest['triggers'])}. Additional permissions: none. "
        f"Review {project_path / 'tool.py'} and {project_path / 'sara_tool.json'}, then say show tool proposal or approve tool."
    )


def show_tool_proposal():
    proposal = project_workflow._read_json(PENDING_PATH)
    if not proposal or proposal.get("status") != "proposed":
        return "There is no Sara tool proposal waiting for review."
    project, error = project_workflow._load_saved_project(proposal.get("project"))
    if error:
        return f"The Sara tool proposal is no longer valid: {error}"
    if project_workflow._project_fingerprint(project) != proposal.get("fingerprint"):
        return "The project changed after the tool proposal was created. Review it and propose the tool again."
    manifest, error = _manifest_from_project(project)
    if error or manifest != proposal.get("manifest"):
        return f"The Sara tool proposal is invalid: {error or 'its manifest changed'}"
    return (
        f"Tool '{manifest['name']}': {manifest['description']} "
        f"Triggers: {', '.join(manifest['triggers'])}. Permissions: none. "
        f"Entry point: {proposal['project_path']}\\tool.py. It will run only in the WSL sandbox."
    )


def approve_tool():
    proposal = project_workflow._read_json(PENDING_PATH)
    if not proposal or proposal.get("status") != "proposed":
        return "There is no Sara tool proposal waiting for approval."
    project, error = project_workflow._load_saved_project(proposal.get("project"))
    if error:
        return f"I didn't enable the tool: {error}"
    if project_workflow._project_fingerprint(project) != proposal.get("fingerprint"):
        return "I didn't enable the tool because its project changed after review. Propose it again after reviewing the changes."
    manifest, error = _manifest_from_project(project)
    if error or manifest != proposal.get("manifest"):
        return f"I didn't enable the tool: {error or 'its manifest changed'}"
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    destination = TOOLS_DIR / f"{manifest['name']}.json"
    if destination.exists():
        return f"A Sara tool named '{manifest['name']}' is already enabled."
    for path in TOOLS_DIR.glob("*.json"):
        enabled = project_workflow._read_json(path)
        enabled_manifest = enabled.get("manifest") if enabled else None
        if enabled_manifest and set(enabled_manifest.get("triggers", [])) & set(manifest["triggers"]):
            return f"A trigger phrase is already used by Sara tool '{enabled_manifest.get('name', path.stem)}'."

    project_workflow._write_json(
        destination,
        {
            "manifest": manifest,
            "project": project["name"],
            "fingerprint": proposal["fingerprint"],
            "enabled_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    try:
        PENDING_PATH.unlink()
    except OSError:
        return f"Enabled '{manifest['name']}', but couldn't remove its proposal."
    return f"Enabled Sara tool '{manifest['name']}'. It has no extra permissions and runs in the WSL sandbox."


def reject_tool():
    proposal = project_workflow._read_json(PENDING_PATH)
    if not proposal or proposal.get("status") != "proposed":
        return "There is no Sara tool proposal waiting to reject."
    try:
        PENDING_PATH.unlink()
    except OSError as error:
        return f"I couldn't discard the Sara tool proposal: {error}"
    return "I discarded the Sara tool proposal."


def list_tools():
    if not TOOLS_DIR.is_dir():
        return "No Sara tools are enabled."
    tools = []
    for path in sorted(TOOLS_DIR.glob("*.json")):
        record = project_workflow._read_json(path)
        manifest = record.get("manifest") if record else None
        normalized, error = validate_tool_manifest(manifest, record.get("project") if record else "")
        if not error and normalized:
            tools.append(normalized)
    if not tools:
        return "No valid Sara tools are enabled."
    return "Enabled Sara tools: " + "; ".join(
        f"{tool['name']} ({', '.join(tool['triggers'])})" for tool in tools
    ) + "."


def run_registered_tool(text):
    query = _normalize(text)
    if not TOOLS_DIR.is_dir():
        return None
    for path in sorted(TOOLS_DIR.glob("*.json")):
        record = project_workflow._read_json(path)
        if not record:
            continue
        manifest, error = validate_tool_manifest(record.get("manifest"), record.get("project", ""))
        if error or not any(query == trigger or query.startswith(trigger + " ") for trigger in manifest["triggers"]):
            continue
        project, error = project_workflow._load_saved_project(record["project"])
        if error:
            return f"I couldn't run Sara tool '{manifest['name']}': {error}"
        if project_workflow._project_fingerprint(project) != record.get("fingerprint"):
            return f"Sara tool '{manifest['name']}' is disabled because its source changed. Review it and approve it again."
        source_manifest, error = _manifest_from_project(project)
        if error or source_manifest != manifest:
            return f"Sara tool '{manifest['name']}' is disabled because its manifest changed."
        result = project_workflow._run_project_in_sandbox(
            project,
            "tool.py",
            tool_input={"request": text[:1000]},
        )
        prefix = "Project finished in the WSL sandbox. Output: "
        if not result.startswith(prefix):
            return result
        try:
            response = json.loads(result[len(prefix):])
        except json.JSONDecodeError:
            return f"Sara tool '{manifest['name']}' returned invalid JSON."
        if not isinstance(response, dict) or set(response) != {"text"}:
            return f"Sara tool '{manifest['name']}' returned an invalid response."
        answer = response["text"]
        if not isinstance(answer, str) or not answer.strip() or len(answer) > MAX_RESPONSE_CHARACTERS:
            return f"Sara tool '{manifest['name']}' returned invalid or oversized text."
        return answer.strip()
    return None


def handle_tool_command(text):
    query = _normalize(text)
    if query in {"show tool proposal", "review tool proposal"}:
        return show_tool_proposal()
    if query in {"approve tool", "enable proposed tool", "approve sara tool"}:
        return approve_tool()
    if query in {"reject tool", "cancel tool proposal", "discard tool proposal"}:
        return reject_tool()
    if query in {"list my tools", "list sara tools", "what tools have i enabled"}:
        return list_tools()

    match = re.match(
        r"^(?:please\s+)?(?:create|make|build|develop)\s+(?:a\s+)?(?:(?:new|reusable)\s+)?"
        r"(?:sara\s+)?tool(?:\s+(?:for|to|that)\s+)?(.+)$",
        query,
    )
    if match:
        return create_tool_project(match.group(1))

    match = re.match(
        r"^(?:propose|enable)\s+project\s+([a-z][a-z0-9-]{1,39})\s+as\s+(?:a\s+)?sara\s+tool$",
        query,
    )
    if match:
        return propose_project_as_tool(match.group(1))
    return None