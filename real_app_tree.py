"""Live routing with host-owned approval, execution receipts, and confirmed learning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
import os
import re
import sqlite3
from typing import Callable

from experiments.app_tree_prototype import RouteKind
from experiments.ollama_app_tree_check import LocalOllamaPlanner
from workflow_memory import WorkflowMemory
from capability_context import describe_capabilities, diagnostic_capability


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Outcome:
    success: bool
    text: str


@dataclass(frozen=True)
class Operation:
    category: str
    capability: str
    preview: str
    execute: Callable[[], Outcome]
    fingerprint: str = ""


DESCRIPTIONS = {
    "system.status": "Read local Windows CPU load, memory usage, free disk space and OS. System diagnostic check.",
    "network.status": "Read local network interface status and cumulative traffic. No network changes.",
    "security.status": "Read Microsoft Defender status only. Not a scan or threat-free guarantee.",
    "clock.read": "Read the computer's current local time.",
    "weather.lookup": "Live weather for an explicitly named city, via wttr.in (network request).",
    "reminders.create": "Schedule a local reminder at an exact local date and time. No phone notifications.",
    "reminders.list": "List pending local reminders.",
    "tasks.create": "Add an item to the user's local task list.",
    "tasks.list": "Read the user's local task list.",
    "files.create": "Create an empty typed file only in SARA's working folder. Never overwrite.",
    "files.rename": "Rename a file only within SARA's working folder. Never overwrite.",
}


class RealAppTree:
    def __init__(self, memory: WorkflowMemory | None = None):
        self.memory = WorkflowMemory() if memory is None else memory
        self.pending: Operation | None = None
        self.confirmation: Operation | None = None
        self.build_request: str | None = None
        self.build_project: str | None = None
        self.build_category = ""

    def _execute(self, operation: Operation) -> str:
        # Consume approval before dispatch; never retry a side effect automatically.
        self.pending = None
        result = operation.execute()
        if not result.success:
            return result.text + " No route was learned."
        self.confirmation = operation
        return result.text + (
            " Did this work as expected? Say app tree worked, app tree failed, or app tree not sure. "
            "No route will be learned until you explicitly confirm."
        )

    def _generated(self) -> dict:
        from tool_workflow import registered_tool_records

        return {"tool." + record["project"]: record for record in registered_tool_records()}

    def _prepare(self, capability: str, request: str, category: str, generated: dict) -> Operation:
        from task_workflow import add_task, get_open_tasks
        from real_reminders import create_reminder, parse_request, pending_reminders
        from Features.create_file import create_file
        from Features.file_operations import rename_file

        if capability in {"system.status", "network.status", "security.status"}:
            from system_admin import get_system_status, get_network_status, get_security_status

            handler = {
                "system.status": get_system_status,
                "network.status": get_network_status,
                "security.status": get_security_status,
            }[capability]
            return Operation(category, capability, "Read local diagnostic status; no settings will change.",
                             lambda: Outcome(True, handler()))
        if capability in generated:
            from tool_workflow import execute_tool_record

            record = generated[capability]

            def run():
                success, text = execute_tool_record(record, request)
                return Outcome(success, "Sandbox tool output (no user files or network accessed): " + text)

            return Operation(category, capability, f"Run {capability} for: {request}. "
                             "WSL sandbox: no network, user files, or installed dependencies.", run, record["fingerprint"])
        if capability == "reminders.create":
            title, due = parse_request(request)

            def remind():
                if due <= datetime.now():
                    return Outcome(False, "The approved reminder time has passed. Request a new future time.")
                identifier = create_reminder(title, due)
                return Outcome(True, f"Scheduled local reminder {identifier}: {title}, at {due:%Y-%m-%d %H:%M}. "
                               "SARA must be running to announce it; overdue reminders are announced on restart.")

            return Operation(category, capability, f"Schedule '{title}' at {due:%Y-%m-%d %H:%M} local time. "
                             "SARA-only notification, no phone message.", remind)
        if capability == "reminders.list":
            def reminders():
                entries = pending_reminders()
                return Outcome(True, "Pending reminders: " + "; ".join(
                    f"{identifier}: {title} at {due}" for identifier, title, due in entries
                ) if entries else "No pending reminders.")
            return Operation(category, capability, "Read pending reminders.", reminders)
        if capability == "tasks.create":
            match = re.fullmatch(r"(?:add|create)(?: a)? task(?: to)? (.+)", request, re.IGNORECASE)
            if not match or not 1 <= len(match[1]) <= 300:
                raise ValueError("Use 'add task call Alex' with a title of at most 300 characters.")
            title = match[1]
            return Operation(category, capability, f"Add task: {title}.",
                             lambda: Outcome(True, f"Added task {add_task(title)}: {title}."))
        if capability == "tasks.list":
            def tasks():
                entries, total = get_open_tasks()
                return Outcome(True, "Open tasks: " + "; ".join(
                    f"{item['id']}: {item['title']}" for item in entries
                ) + f". Total: {total}.")
            return Operation(category, capability, "Read local tasks.", tasks)
        if capability == "clock.read":
            return Operation(category, capability, "Read local time.", lambda: Outcome(
                True, "The computer's local time is " + datetime.now().astimezone().strftime("%I:%M %p %Z") + ".",
            ))
        if capability == "weather.lookup":
            match = re.search(r"\b(?:in|for)\s+(.+)", request, re.IGNORECASE)
            if not match:
                raise ValueError("Name a city, for example 'weather in Boston'. No location was guessed.")
            city = match[1].rstrip(" .?!")
            if len(city) > 150 or not city:
                raise ValueError("Use a city name of at most 150 characters.")

            def weather():
                from Weather_Check.check_weather import get_weather_by_address
                text = get_weather_by_address(city)
                return Outcome(text.startswith("Current weather in "), text)

            return Operation(category, capability, f"Look up live weather for {city} using wttr.in. "
                             "The city will be sent to that service.", weather)
        if capability in {"files.create", "files.rename"}:
            if capability == "files.create" and not re.match(r"^(?:please )?create\b", request, re.IGNORECASE):
                raise ValueError("Use 'create text file named example' to specify the file to create.")
            if capability == "files.rename" and not request.casefold().startswith("rename file "):
                raise ValueError("Use 'rename file before.txt to after.txt'.")

            def file_operation():
                text = create_file(request) if capability == "files.create" else rename_file(request)
                return Outcome(text.startswith("Created " if capability == "files.create" else "Renamed "), text)

            return Operation(category, capability, f"{request}. Only SARA's working folder; no overwrite.", file_operation)
        raise ValueError("The selected capability is unavailable. Nothing was dispatched.")

    def route(self, request: str, answerer: Callable[[str], str]) -> str:
        if not request.strip() or len(request) > 1000:
            raise ValueError("App-tree requests must contain 1 to 1000 characters.")
        description = describe_capabilities(request)
        if description is not None:
            return description
        diagnostic = diagnostic_capability(request)
        if diagnostic:
            return self._prepare(diagnostic, request, "diagnostics", {}).execute().text
        blocked = bool(self.pending or self.confirmation or self.build_request or self.build_project)
        generated = self._generated()
        available = dict(DESCRIPTIONS)
        available.update({identifier: record["manifest"]["description"] for identifier, record in generated.items()})
        fingerprints = {identifier: record["fingerprint"] for identifier, record in generated.items()}
        fingerprints.update({identifier: "" for identifier in DESCRIPTIONS})
        for task, identifier, fingerprint, count in self.memory.entries():
            if identifier in available and fingerprints[identifier] == fingerprint:
                available[identifier] += f" User-confirmed for category {task!r} ({count} successes)."
        query = " ".join(request.casefold().split()).rstrip(".?!")
        # Exact host-recognized families avoid model ambiguity for basic local operations.
        fixed = (
            ("reminders.create", "reminder", bool(re.match(
                r"^(?:please )?(?:remind me\b|reminder\b|(?:create|set|add|schedule)(?: a)? reminder\b)", query,
            ))),
            ("reminders.list", "reminders", query in {"show reminders", "list reminders", "show my reminders"}),
            ("clock.read", "time", query in {"what time is it", "waht time is it", "what is the time", "tell me the time"}),
            ("tasks.create", "tasks", bool(re.match(r"^(?:add|create)(?: a)? task ", query))),
            ("tasks.list", "tasks", query in {"show tasks", "show my tasks", "list tasks"}),
            ("files.create", "files", query.startswith("create ") and " file " in query),
            ("files.rename", "files", query.startswith("rename file ")),
            ("weather.lookup", "weather", bool(re.match(r"^(?:check )?weather (?:in|for) ", query))),
        )
        selected = next(((identifier, category) for identifier, category, matches in fixed if matches), None)
        if selected:
            capability, category = selected
        else:
            trigger = next(
                (identifier for identifier, record in generated.items()
                 if any(query == phrase or query.startswith(phrase + " ") for phrase in record["manifest"]["triggers"])),
                None,
            )
            planner = LocalOllamaPlanner(model=os.environ.get("SARA_APP_TREE_OLLAMA_MODEL", "qwen3:8b"), live=True)
            if trigger:
                from experiments.app_tree_prototype import Intent

                intent = Intent(RouteKind.CAPABILITY, "generated tool", capability_id=trigger)
            else:
                intent = planner.choose(request, available)
            if intent.kind is RouteKind.ANSWER:
                return answerer(request)
            category = intent.task_type
            if blocked:
                return "A real operation is still pending. Say app tree status to inspect it, or app tree reject to discard it. No new task ran."
            if intent.kind is RouteKind.NEEDS_CAPABILITY:
                self.build_request, self.build_category = request, category
                return (
                    "No registered app can perform that request. Proposed Forge build for: " + request +
                    ". Forge will create a standard-library tool in a private workspace, with no user-file "
                    "or network access. Say app tree approve build or app tree reject. "
                    "After building, source review and a separate first-run approval are required."
                )
            capability = intent.capability_id
        if blocked:
            return "A real operation is still pending. Say app tree status to inspect it, or app tree reject to discard it. No new task ran."
        preferred = self.memory.preferred(category, fingerprints)
        # Learned preferences are suggestions, not authority to change the selected operation.
        operation = self._prepare(capability, request, category, generated)
        if capability == "clock.read":
            return operation.execute().text
        self.pending = operation
        hint = f" Previously confirmed route: {preferred}." if preferred else ""
        return "Review real operation: " + operation.preview + hint + " Say app tree approve or app tree reject. Nothing has run."

    def handle(self, command: str, answerer: Callable[[str], str]) -> str | None:
        query = " ".join(command.casefold().split()).rstrip(".?!")
        prefix = next((prefix for prefix in ("app tree", "apptree", "app-tree")
                       if query == prefix or query.startswith(prefix + " ")), None)
        if prefix is None:
            return None
        action = query[len(prefix):].strip()
        if action == "test" or action.startswith("test "):
            return None
        if action.startswith("ask "):
            return self.route(command[len(prefix):].strip()[4:], answerer)
        if action in {"help", ""}:
            return (
                "Real app tree: ask <request>, approve, reject, worked, failed, not sure, memory, "
                "clear workflows, reset, status. Forge: approve build, review build, approve project, approve run. "
                "All real operations require explicit approval; only worked learns a route."
            )
        if action == "status":
            if self.pending:
                return "Awaiting operation approval: " + self.pending.preview
            if self.confirmation:
                return "Awaiting success confirmation: " + self.confirmation.preview + " Say app tree worked or failed."
            if self.build_request:
                return "Awaiting Forge build approval: " + self.build_request + ". Say app tree approve build or reject."
            if self.build_project:
                return "Attached Forge build: " + self.build_project + ". Say app tree review build."
            return "No app-tree decision is pending."
        if action == "memory":
            entries = self.memory.entries()
            return "User-confirmed REAL workflows: " + (
                "; ".join(f"{task}: {capability}, confirmed {count} time(s)"
                          for task, capability, _, count in entries) or "none"
            ) + ". Mock memory is separate; these records never grant approval."
        if action == "clear workflows":
            self.memory.clear()
            return "Cleared real workflow memory only. Personal memory and apps are unchanged."
        if action in {"worked", "failed", "not sure"}:
            if self.confirmation is None:
                return "No real result is awaiting confirmation. Nothing was learned."
            if action == "not sure":
                return "The result remains unconfirmed. Nothing was learned."
            operation = self.confirmation
            if action == "worked":
                self.memory.record(operation.category, operation.capability, operation.fingerprint)
            self.confirmation = None
            return "Saved your confirmed real workflow; future actions still require approval." if action == "worked" else "Result not confirmed; nothing was learned."
        if action in {"reject", "reset"}:
            if self.build_project:
                import forge_workflow

                state = forge_workflow._read_pending()
                if state and state.get("project") == self.build_project and forge_workflow._forge_process_status(state) == "running":
                    return "Forge is still running. Reset cannot cancel a running Forge process; finish its window first."
                self.build_project = None
            self.pending = self.confirmation = None
            self.build_request = None
            return "Discarded pending app-tree decisions. Saved workflow memory is unchanged."
        if action == "approve":
            if self.build_project:
                return "Generated apps require the separate app tree approve run command after source approval."
            if self.pending is None:
                return "No real operation is awaiting approval. Use approve build or approve run for those separate decisions."
            return self._execute(self.pending)
        if action in {"approve build", "review build", "approve project", "approve run"}:
            return self._build_action(action)
        return "Unsupported app-tree command. Say app tree help. No real operation ran."

    def _build_action(self, action: str) -> str:
        import forge_workflow as forge
        import project_workflow as projects
        from tool_workflow import TOOLS_DIR, _manifest_from_project, execute_tool_record, tool_trigger_conflict

        if action == "approve build":
            if self.build_request is None:
                return "No proposed Forge build is awaiting approval."
            existing = forge._read_pending()
            if existing is not None and not isinstance(existing, dict):
                raise ValueError("Invalid Forge build state. Repair it before starting a build.")
            if existing and existing.get("status") == "running":
                return "Another Forge build is already running. Review it before starting another."
            approved_request = self.build_request
            self.build_request = None
            text = forge.start_forge_project(approved_request, tool_mode=True)
            state = forge._read_pending()
            if state and state.get("request") == approved_request and state.get("status") == "running":
                self.build_project = state["project"]
                return text + " Say app tree review build when Forge finishes. No generated app has run."
            return text + (
                " Build approval was consumed, but no tracked build was established. "
                "Check any opened Forge window before requesting another build. No app was enabled or workflow learned."
            )
        state = forge._read_pending()
        if state is not None and not isinstance(state, dict):
            raise ValueError("Invalid Forge build state.")
        if action == "review build" and self.build_project is None and state and state.get("status") in {"running", "ready"}:
            self.build_project = state.get("project")
            self.build_category = "generated tool"
        if not self.build_project or not state or state.get("project") != self.build_project:
            return "No app-tree Forge build is attached to this session. Existing Forge/project commands remain available."
        if action == "review build":
            text = forge.review_forge_project() if state.get("status") == "running" else projects.show_project_proposal()
            return text + " For this app-tree build, say app tree approve project after reviewing the full source."
        if action == "approve project":
            proposal = projects._read_json(projects.PENDING_PATH)
            if not proposal or proposal.get("project", {}).get("name") != self.build_project:
                return "The matching source proposal is not ready. Say app tree review build."
            manifest, error = _manifest_from_project(proposal["project"])
            if error:
                return "Forge output is not a reusable SARA tool: " + error + " No source was enabled or run."
            conflict = tool_trigger_conflict(manifest)
            if conflict or (TOOLS_DIR / (manifest["name"] + ".json")).exists():
                return conflict or "A tool with that name is already enabled. No source was enabled or run."
            text = projects.approve_project()
            project, error = projects._load_saved_project(self.build_project)
            if error or projects._read_json(projects.PENDING_PATH):
                return text
            manifest, error = _manifest_from_project(project)
            if error:
                return "Saved tool validation failed: " + error
            fingerprint = projects._project_fingerprint(project)
            record = {"project": self.build_project, "manifest": manifest, "fingerprint": fingerprint}

            def execute():
                conflict = tool_trigger_conflict(manifest)
                if conflict or (TOOLS_DIR / (record["project"] + ".json")).exists():
                    return Outcome(False, conflict or "That tool name is already enabled; no code ran.")
                success, output = execute_tool_record(record, state["request"])
                if success:
                    projects._write_json(
                        TOOLS_DIR / (record["project"] + ".json"), record,
                    )
                return Outcome(success, "Sandbox tool output (no user files or network accessed): " + output)

            self.pending = Operation(
                self.build_category, "tool." + self.build_project,
                f"Run reviewed {self.build_project} in the WSL sandbox. No user-file or network access.",
                execute, fingerprint,
            )
            return text + " Separate first-run approval required: say app tree approve run. No code has run."
        if self.pending is None or self.pending.capability != "tool." + self.build_project:
            return "Review and approve the source first with app tree approve project."
        operation = self.pending
        self.build_project = None
        return self._execute(operation)


_STAGE = RealAppTree()


def handle_real_app_tree_command(command: str, *, answerer: Callable[[str], str]) -> str | None:
    try:
        return _STAGE.handle(command, answerer)
    except (ImportError, OSError, ValueError, RuntimeError, sqlite3.Error) as error:
        LOGGER.exception("Real app-tree operation failed")
        return f"Real app-tree operation failed: {error}. No workflow was learned. Do not assume an action completed."


def route_conversation_request(request: str, answerer: Callable[[str], str]) -> str:
    try:
        return _STAGE.route(request, answerer)
    except (ImportError, OSError, ValueError, RuntimeError, sqlite3.Error) as error:
        LOGGER.exception("Real app-tree routing failed")
        return f"Real app-tree routing failed: {error}. No workflow was learned. Do not assume an action completed."


def route_registered_tool_request(request: str) -> str | None:
    query = " ".join(request.casefold().split()).rstrip(".?!")
    for record in _STAGE._generated().values():
        if any(query == trigger or query.startswith(trigger + " ") for trigger in record["manifest"]["triggers"]):
            return route_conversation_request(request, lambda text: text)
    return None


def route_known_request(request: str, answerer: Callable[[str], str]) -> str | None:
    query = " ".join(request.casefold().split()).rstrip(".?!")
    if (
        describe_capabilities(request) is not None or diagnostic_capability(request)
        or re.match(r"^(?:please )?(?:remind me\b|reminder\b|(?:create|set|add|schedule)(?: a)? reminder\b)", query)
        or query.startswith("rename file ")
        or re.match(r"^(?:add|create)(?: a)? task ", query)
        or re.match(r"^(?:check )?weather (?:in|for) ", query)
        or query.startswith("create ") and " file " in query
        or query in {"show reminders", "list reminders", "show my reminders", "show tasks", "show my tasks",
                     "list tasks", "what time is it", "waht time is it", "what is the time", "tell me the time"}
    ):
        return route_conversation_request(request, answerer)
    return None
