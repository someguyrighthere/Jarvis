import json
import os
import re
import shutil
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import psutil

import project_workflow


LOCAL_DATA_DIR = project_workflow.LOCAL_DATA_DIR
WORKSPACES_DIR = LOCAL_DATA_DIR / "forge_workspaces"
FORGE_HOMES_DIR = LOCAL_DATA_DIR / "forge_homes"
PENDING_PATH = LOCAL_DATA_DIR / "forge_project.json"
MAX_REQUEST_LENGTH = 2000
MINIMUM_FORGE_VERSION = (1, 4, 1)
IGNORED_DIRECTORIES = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "venv",
}
_PROCESS = None


def _read_pending():
    try:
        return json.loads(PENDING_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"I couldn't read the Forge project state: {error}") from error


def _find_forge():
    configured = os.environ.get("FORGE_EXECUTABLE", "").strip()
    if configured:
        resolved = shutil.which(configured) or configured
        if Path(resolved).is_file():
            return str(Path(resolved).resolve())
        return None

    on_path = shutil.which("forge")
    if on_path:
        return on_path
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    installed = local_app_data / "Programs" / "Forge" / "forge.exe"
    return str(installed) if installed.is_file() else None


def _check_forge_version(executable, env):
    try:
        result = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return f"I couldn't check the Forge version: {error}"
    match = re.search(r"\bforge\s+(\d+)\.(\d+)\.(\d+)\b", result.stdout, re.IGNORECASE)
    if result.returncode != 0 or not match:
        return f"Forge returned an unreadable version response: {result.stdout.strip() or result.stderr.strip()}"
    version = tuple(map(int, match.groups()))
    if version < MINIMUM_FORGE_VERSION:
        minimum = ".".join(map(str, MINIMUM_FORGE_VERSION))
        return (
            f"Forge {minimum} or newer is required for Sara's workspace restrictions. "
            "Update Forge, then try again."
        )
    return None


def _configured_forge_model():
    forge_home = Path(os.environ.get("FORGE_HOME", Path.home() / ".forge"))
    config_path = forge_home / "config.toml"
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise RuntimeError(f"I couldn't read Forge's model setting: {error}") from error
    model = config.get("model")
    return model if isinstance(model, str) and model else None


def _project_slug(request):
    words = re.findall(r"[a-z0-9]+", request.lower())
    base = "-".join(words[:6])[:40].strip("-") or "forge-project"
    if len(base) < 2:
        base = f"{base}-project"
    candidate = base
    suffix = 2
    while (WORKSPACES_DIR / candidate).exists() or (FORGE_HOMES_DIR / candidate).exists():
        ending = f"-{suffix}"
        candidate = f"{base[:40 - len(ending)]}{ending}"
        suffix += 1
    return candidate


def start_forge_project(request):
    global _PROCESS
    request = request.strip()
    if not request:
        return "Tell me what you want Forge to build."
    if len(request) > MAX_REQUEST_LENGTH:
        return f"Forge requests must be at most {MAX_REQUEST_LENGTH} characters."
    try:
        pending = _read_pending()
    except RuntimeError as error:
        return str(error)
    if pending and pending.get("status") == "running":
        return f"A Forge project is already in progress: {pending.get('workspace', 'unknown workspace')}. Say show Forge project."
    if project_workflow._read_json(project_workflow.PENDING_PATH):
        return "Finish the pending Sara project proposal before starting another Forge project."

    executable = _find_forge()
    if not executable:
        return (
            "I couldn't find Forge. Install it with its command-line option enabled, add forge.exe to PATH, "
            "or set FORGE_EXECUTABLE to its full path."
        )

    env = {
        key: value
        for key, value in os.environ.items()
        if not any(marker in key.upper() for marker in ("TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "_KEY"))
    }
    version_error = _check_forge_version(executable, env)
    if version_error:
        return version_error

    try:
        model = _configured_forge_model()
    except RuntimeError as error:
        return str(error)

    slug = _project_slug(request)
    workspace = (WORKSPACES_DIR / slug).resolve()
    forge_home = (FORGE_HOMES_DIR / slug).resolve()
    try:
        workspace.mkdir(parents=True, exist_ok=False)
        forge_home.mkdir(parents=True, exist_ok=False)
        (workspace / "AGENT.md").write_text(
            "Build only the app requested by the user. Keep all project files in this workspace. "
            "Do not access or modify files outside this workspace. Do not install dependencies, "
            "access secrets, or use the network. Do not run the "
            "finished app unless the user separately asks Sara to run the imported project.\n",
            encoding="utf-8",
        )
        forge_config = 'mode = "ask"\nallow = []\ndeny = []\n'
        if model:
            forge_config += f"model = {json.dumps(model)}\n"
        (forge_home / "config.toml").write_text(forge_config, encoding="utf-8")
    except OSError as error:
        return f"I couldn't prepare a private workspace for Forge: {error}"

    prompt = (
        f"Create a small, complete app to help Sara with this request: {request}\n\n"
        "Work only in the current workspace. Prefer self-contained HTML/CSS/JavaScript or a Python "
        "standard-library app. Do not install dependencies or access the network. Do not modify "
        "files outside this workspace. Explain the files created and any checks performed when done."
    )
    env["FORGE_HOME"] = str(forge_home)
    env["FORGE_WORKSPACE_ROOT"] = str(workspace)
    command = [executable, "--ask", prompt]
    creationflags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
    try:
        _PROCESS = subprocess.Popen(command, cwd=workspace, env=env, creationflags=creationflags)
    except OSError as error:
        return f"I couldn't start Forge: {error}"

    proposal = {
        "status": "running",
        "request": request,
        "project": slug,
        "workspace": str(workspace),
        "pid": _PROCESS.pid,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        project_workflow._write_json(PENDING_PATH, proposal)
    except OSError as error:
        return f"Forge started, but I couldn't save its project state: {error}"
    return (
        f"Forge is working in its own workspace: {workspace}. Its window will ask before edits; shell commands, "
        "code execution, and web tools are disabled for this build session. "
        f"When Forge is finished, say review Forge project to import its files for Sara's separate project approval."
    )


def _forge_process_status(pending):
    global _PROCESS
    pid = pending.get("pid")
    if _PROCESS is not None and _PROCESS.pid == pid:
        return "running" if _PROCESS.poll() is None else "finished"
    if not isinstance(pid, int):
        return "finished"
    try:
        process = psutil.Process(pid)
        if process.name().casefold() not in {"forge.exe", "forge"}:
            return "finished"
        workspace = Path(pending["workspace"]).resolve()
        if Path(process.cwd()).resolve() == workspace:
            return "running" if process.is_running() else "finished"
        return "finished"
    except psutil.NoSuchProcess:
        return "finished"
    except (psutil.AccessDenied, OSError, KeyError, ValueError) as error:
        return f"unknown: {error}"


def show_forge_project():
    try:
        pending = _read_pending()
    except RuntimeError as error:
        return str(error)
    if not pending:
        return "There is no Forge project in progress or waiting for review."
    status = _forge_process_status(pending)
    if status.startswith("unknown:"):
        return f"I couldn't determine whether Forge is still running: {status[8:]}"
    if status == "running":
        return f"Forge is still working in {pending.get('workspace', 'its workspace')}."
    if pending.get("status") == "ready":
        proposal = project_workflow._read_json(project_workflow.PENDING_PATH)
        if not proposal or proposal.get("project", {}).get("name") != pending.get("project"):
            return "The Forge project is no longer waiting for Sara's approval."
        return (
            f"The Forge project is already prepared for Sara's review in {pending.get('workspace', 'its workspace')}. "
            "Say show project proposal, approve project, or reject project."
        )
    return (
        f"Forge has finished in {pending.get('workspace', 'its workspace')}. "
        "Say review Forge project to validate its files and prepare Sara's project proposal."
    )


def _read_forge_project(pending):
    workspace = Path(pending["workspace"]).resolve()
    expected_workspace = (WORKSPACES_DIR / pending["project"]).resolve()
    if workspace != expected_workspace or not workspace.is_dir():
        raise ValueError("The Forge workspace is missing or is not the expected private workspace.")

    files = []
    for path in sorted(workspace.rglob("*")):
        if any(part in IGNORED_DIRECTORIES for part in path.relative_to(workspace).parts):
            continue
        if path.is_symlink():
            raise ValueError(f"Forge created a symbolic link that needs manual review: {path.relative_to(workspace)}.")
        if not path.is_file() or path.name == "AGENT.md":
            continue
        try:
            relative = path.relative_to(workspace).as_posix()
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise ValueError(f"I couldn't read {path.relative_to(workspace)} as a text file: {error}") from error
        files.append({"path": relative, "content": content})

    if not files:
        raise ValueError("Forge did not create any importable project files.")
    project, error = project_workflow.validate_project(
        {
            "name": pending["project"],
            "summary": f"App created with Forge for: {pending['request'][:450]}",
            "files": files,
        }
    )
    if error:
        raise ValueError(error)
    return project


def review_forge_project():
    try:
        pending = _read_pending()
    except RuntimeError as error:
        return str(error)
    if not pending or pending.get("status") != "running":
        return "There is no Forge project waiting for review."
    status = _forge_process_status(pending)
    if status == "running":
        return "Forge is still working. Review the project after Forge has finished."
    if status.startswith("unknown:"):
        return f"I couldn't determine whether Forge is still running: {status[8:]}"
    if project_workflow._read_json(project_workflow.PENDING_PATH):
        return "Finish the pending Sara project proposal before importing the Forge project."

    try:
        project = _read_forge_project(pending)
        project_workflow._write_json(
            project_workflow.PENDING_PATH,
            {
                "status": "proposed",
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "request": pending["request"],
                "project": project,
            },
        )
        pending["status"] = "ready"
        project_workflow._write_json(PENDING_PATH, pending)
    except (OSError, KeyError, ValueError) as error:
        return f"I couldn't prepare the Forge project for Sara's review: {error}"

    files = ", ".join(item["path"] for item in project["files"])
    return (
        f"Forge project '{project['name']}' is ready for review. Files: {files}. "
        "Say show project proposal to review it, approve project to copy it into Documents/SaraProjects, "
        "or reject project to discard the proposal. The app has not been run."
    )


def handle_forge_command(text):
    query = project_workflow._normalize(text)
    if query in {"show forge project", "forge project status"}:
        return show_forge_project()
    if query in {"review forge project", "finish forge project"}:
        return review_forge_project()

    match = re.match(r"^(?:please\s+)?(?:use|ask|send)\s+forge\s+to\s+(.+)$", query)
    if match:
        return start_forge_project(match.group(1))
    return None
