import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath

import requests


PROJECT_ROOT = Path(__file__).resolve().parent
LOCAL_DATA_DIR = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Sara"
PROJECTS_DIR = Path.home() / "Documents" / "SaraProjects"
PENDING_PATH = LOCAL_DATA_DIR / "project_proposal.json"
RUN_REQUEST_PATH = LOCAL_DATA_DIR / "project_run_request.json"
OLLAMA_ENDPOINT = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434/v1/chat/completions")
MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
WSL_DISTRIBUTION = os.getenv("SARA_WSL_DISTRIBUTION", "Ubuntu")
ALLOWED_SUFFIXES = {".css", ".html", ".js", ".json", ".md", ".py", ".txt"}
MAX_FILES = 12
MAX_FILE_CHARACTERS = 60_000
MAX_TOTAL_CHARACTERS = 200_000
MAX_RUN_SECONDS = 15
MAX_RUN_OUTPUT = 32_000
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
_WSL_SANDBOX_RUNNER = r'''
import json
import os
import pathlib
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time

MAX_FILE_CHARS = 60000
MAX_TOTAL_CHARS = 200000
MAX_FILES = 12
MAX_OUTPUT = 32000
MAX_SECONDS = 15
ALLOWED_SUFFIXES = {".css", ".html", ".js", ".json", ".md", ".py", ".txt"}
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}

def respond(value):
    print(json.dumps(value, ensure_ascii=True))

def safe_path(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError("invalid relative file path")
    path = pathlib.PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} or part.startswith(".") or part.endswith((".", " ")) for part in path.parts):
        raise ValueError("unsafe project file path")
    if any(part.split(".", 1)[0].upper() in RESERVED for part in path.parts):
        raise ValueError("reserved project file path")
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError("unsupported project file type")
    return path

source_root = None
try:
    payload = json.load(sys.stdin)
    files = payload.get("files")
    entry = payload.get("entry")
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise ValueError("invalid project file list")
    tool_mode = isinstance(payload.get("input"), dict)
    if entry not in ({"tool.py"} if tool_mode else {"main.py", "app.py"}):
        raise ValueError("invalid project entry point")
    source_root = pathlib.Path(tempfile.mkdtemp(prefix="sara-source-"))
    total = 0
    seen = set()
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "content"} or not isinstance(item["content"], str):
            raise ValueError("invalid project file")
        relative = safe_path(item["path"])
        key = relative.as_posix().casefold()
        if key in seen:
            raise ValueError("duplicate project path")
        seen.add(key)
        content = item["content"]
        total += len(content)
        if len(content) > MAX_FILE_CHARS or total > MAX_TOTAL_CHARS:
            raise ValueError("project size limit exceeded")
        target = source_root.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    if entry not in seen:
        raise ValueError("entry point is missing")

    bwrap = shutil.which("bwrap")
    prlimit = shutil.which("prlimit")
    python = shutil.which("python3")
    if not bwrap or not prlimit or not python:
        raise RuntimeError("Bubblewrap, prlimit, and Python 3 are required in Ubuntu")

    command = [
        bwrap, "--unshare-all", "--die-with-parent", "--clearenv",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind-try", "/bin", "/bin",
        "--ro-bind-try", "/lib", "/lib",
        "--ro-bind-try", "/lib64", "/lib64",
        "--ro-bind", "/etc", "/etc",
        "--proc", "/proc", "--dev", "/dev",
        "--dir", "/work", "--dir", "/work/project",
        "--ro-bind", str(source_root), "/work/project",
        "--size", "67108864", "--tmpfs", "/work/output",
        "--size", "67108864", "--tmpfs", "/tmp",
        "--setenv", "HOME", "/work/output",
        "--setenv", "SARA_OUTPUT_DIR", "/work/output",
        "--setenv", "PATH", "/usr/bin:/bin",
        "--chdir", "/work/project",
        prlimit, "--as=536870912", "--cpu=8", "--nproc=32",
        "--fsize=16777216", "--nofile=64", "--",
        python, "-I", str(pathlib.PurePosixPath("/work/project") / entry),
    ]
    tool_input = payload.get("input")
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE if isinstance(tool_input, dict) else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    if isinstance(tool_input, dict):
        process.stdin.write(json.dumps(tool_input).encode("utf-8") + b"\n")
        process.stdin.close()
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    output = bytearray()
    deadline = time.monotonic() + MAX_SECONDS
    timed_out = False
    truncated = False
    while True:
        if time.monotonic() >= deadline:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            break
        events = selector.select(timeout=0.1)
        for key, _ in events:
            chunk = os.read(key.fd, 4096)
            if not chunk:
                selector.unregister(key.fileobj)
                break
            remaining = MAX_OUTPUT - len(output)
            output.extend(chunk[:remaining])
            if len(chunk) > remaining:
                truncated = True
                os.killpg(process.pid, signal.SIGKILL)
                break
        if truncated or process.poll() is not None and not events:
            break
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    respond({
        "ok": process.returncode == 0 and not timed_out and not truncated,
        "returncode": process.returncode,
        "timed_out": timed_out,
        "truncated": truncated,
        "output": output.decode("utf-8", errors="replace"),
    })
except Exception as error:
    respond({"ok": False, "error": str(error)})
finally:
    if source_root is not None:
        shutil.rmtree(source_root, ignore_errors=True)
'''


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


def _validate_file_path(path):
    if not isinstance(path, str) or not path or "\\" in path or ":" in path:
        return None, "Project file paths must be relative POSIX-style paths."
    relative = PurePosixPath(path)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        return None, f"The file path '{path}' is not a safe relative path."
    if any(part.startswith(".") or part.endswith((".", " ")) for part in relative.parts):
        return None, f"Hidden or ambiguous path components are not allowed: '{path}'."
    if any(part.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES for part in relative.parts):
        return None, f"The file path '{path}' uses a reserved Windows name."
    if relative.suffix.lower() not in ALLOWED_SUFFIXES:
        return None, f"Files ending in '{relative.suffix}' are not allowed in generated projects."
    return relative, None


def validate_project(project):
    if not isinstance(project, dict) or set(project) != {"name", "summary", "files"}:
        return None, "The project proposal must contain only name, summary, and files."
    name = project["name"]
    summary = project["summary"]
    files = project["files"]
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]{1,39}", name):
        return None, "The project name must be a short lowercase slug."
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 500:
        return None, "The project needs a summary of at most 500 characters."
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        return None, f"A project must contain between 1 and {MAX_FILES} files."

    normalized_files = []
    seen_paths = set()
    total_characters = 0
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "content"}:
            return None, "Each project file must contain only a path and text content."
        relative, error = _validate_file_path(item["path"])
        if error:
            return None, error
        content = item["content"]
        if not isinstance(content, str):
            return None, f"The content for '{item['path']}' must be text."
        path_key = relative.as_posix().casefold()
        if path_key in seen_paths:
            return None, f"The project contains a duplicate path: '{item['path']}'."
        seen_paths.add(path_key)
        if len(content) > MAX_FILE_CHARACTERS:
            return None, f"The file '{item['path']}' exceeds the size limit."
        total_characters += len(content)
        if total_characters > MAX_TOTAL_CHARACTERS:
            return None, "The project exceeds the total source size limit."
        if relative.suffix.lower() == ".py":
            try:
                ast.parse(content, filename=relative.as_posix())
            except SyntaxError as error:
                return None, f"The Python file '{item['path']}' has a syntax error: {error.msg}."
        elif relative.suffix.lower() == ".json":
            try:
                json.loads(content)
            except json.JSONDecodeError as error:
                return None, f"The JSON file '{item['path']}' is invalid: {error.msg}."
        elif relative.suffix.lower() == ".html":
            try:
                HTMLParser().feed(content)
            except Exception as error:
                return None, f"The HTML file '{item['path']}' could not be parsed: {error}."
        normalized_files.append({"path": relative.as_posix(), "content": content})

    return {"name": name, "summary": summary.strip(), "files": normalized_files}, None


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


def create_project_proposal(request, tool_mode=False):
    request = request.strip()
    if not request:
        return "Describe the app or project you want me to create."
    if _read_json(PENDING_PATH):
        return "There is already a project proposal waiting. Say approve project or reject project first."

    project_instructions = (
        "This is a Sara tool project. Include a root tool.py and a root sara_tool.json. "
        "The JSON manifest must contain exactly name, description, triggers, entrypoint, and permissions. "
        "Use the project name as manifest name, set entrypoint to tool.py, and set permissions to an empty list. "
        "Use 1 to 4 specific multiword trigger phrases. tool.py must read one JSON object from stdin with key request, "
        "perform its task without network access, and print exactly one JSON object with key text to stdout. "
        "Do not print anything else. Keep all tool logic in tool.py and do not include an installer or dependencies."
        if tool_mode
        else "Prefer a self-contained HTML/CSS/JavaScript app or a Python CLI app using the standard library. "
        "For runnable Python projects, include a root main.py or app.py entry point and write generated files only under SARA_OUTPUT_DIR. "
        "Do not require internet access or package installation."
    )
    prompt = (
        "Create a small, complete project as JSON only with exactly these keys: "
        "name, summary, files. Each item in files must contain exactly path and content. "
        "Use a lowercase hyphenated name and relative POSIX-style paths. "
        f"Create at most {MAX_FILES} text files, each no larger than {MAX_FILE_CHARACTERS} characters. "
        f"Allowed file extensions: {', '.join(sorted(ALLOWED_SUFFIXES))}. "
        "Do not include binaries, hidden files, dependency installation scripts, secrets, or instructions to run commands. "
        "Generate source for review only; it will not be executed automatically. "
        f"{project_instructions}\n\n"
        f"User's project request: {request}"
    )
    try:
        response = requests.post(
            OLLAMA_ENDPOINT,
            headers={"Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 6000,
            },
            timeout=120,
        )
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"].strip()
        # strict=False tolerates raw control characters (e.g. literal newlines) that
        # models sometimes leave unescaped inside multi-line file content strings.
        project, error = validate_project(json.loads(_extract_json_object(answer), strict=False))
        if error:
            return f"I couldn't prepare a valid project proposal: {error}"
        if tool_mode:
            from tool_workflow import _manifest_from_project

            _, error = _manifest_from_project(project)
            if error:
                return f"I couldn't prepare a valid Sara tool project: {error}"
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
        return f"I couldn't create a project proposal: {error}"

    _write_json(
        PENDING_PATH,
        {
            "status": "proposed",
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "request": request,
            "project": project,
        },
    )
    files = ", ".join(item["path"] for item in project["files"])
    return (
        f"Drafted project '{project['name']}': {project['summary']} "
        f"Files: {files}. Review the source in {PENDING_PATH}, then say approve project to write it to "
        f"Documents/SaraProjects/{project['name']}. I will not run it."
    )


def show_project_proposal():
    proposal = _read_json(PENDING_PATH)
    if not proposal or proposal.get("status") != "proposed":
        return "There is no project proposal waiting for review."
    project, error = validate_project(proposal.get("project"))
    if error:
        return f"The project proposal is invalid: {error}"
    files = ", ".join(item["path"] for item in project["files"])
    return (
        f"Project '{project['name']}': {project['summary']} Files: {files}. "
        f"Review the full source in {PENDING_PATH} before approving it."
    )


def approve_project():
    proposal = _read_json(PENDING_PATH)
    if not proposal or proposal.get("status") != "proposed":
        return "There is no project proposal waiting for approval."
    project, error = validate_project(proposal.get("project"))
    if error:
        return f"I didn't write the project because its proposal is invalid: {error}"

    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    projects_root = PROJECTS_DIR.resolve()
    destination = projects_root / project["name"]
    if destination.exists() or destination.is_symlink():
        return f"I didn't overwrite the existing project at Documents/SaraProjects/{project['name']}."

    staging = Path(tempfile.mkdtemp(prefix=".sara-project-", dir=projects_root))
    try:
        for item in project["files"]:
            relative, error = _validate_file_path(item["path"])
            if error:
                raise ValueError(error)
            target = staging.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.resolve().is_relative_to(staging.resolve()):
                raise ValueError(f"The path '{item['path']}' escapes the project folder.")
            target.write_text(item["content"], encoding="utf-8", newline="")
        staging.rename(destination)
    except (OSError, ValueError) as error:
        shutil.rmtree(staging, ignore_errors=True)
        return f"I couldn't create the project: {error}"

    try:
        PENDING_PATH.unlink()
    except OSError:
        return f"Created the project at Documents/SaraProjects/{project['name']}, but couldn't remove the proposal file."
    return f"Created the project at Documents/SaraProjects/{project['name']}. Its code is saved for review and has not been run."


def reject_project():
    proposal = _read_json(PENDING_PATH)
    if not proposal or proposal.get("status") != "proposed":
        return "There is no project proposal waiting to reject."
    try:
        PENDING_PATH.unlink()
    except OSError as error:
        return f"I couldn't discard the project proposal: {error}"
    return "I discarded the project proposal."


def _load_saved_project(name):
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]{1,39}", name):
        return None, "Use the project's lowercase folder name."
    try:
        projects_root = PROJECTS_DIR.resolve()
        project_path = PROJECTS_DIR / name
        if project_path.is_symlink() or not project_path.is_dir():
            return None, f"I couldn't find a saved project named '{name}'."
        project_path = project_path.resolve()
        if not project_path.is_relative_to(projects_root):
            return None, "The project folder is outside SaraProjects."
        files = []
        for path in sorted(project_path.rglob("*")):
            if path.is_symlink():
                return None, f"The project contains a symbolic link: {path.relative_to(project_path)}."
            if path.is_dir():
                continue
            if not path.is_file():
                return None, "The project contains an unsupported filesystem entry."
            relative_path = path.relative_to(project_path).as_posix()
            _, error = _validate_file_path(relative_path)
            if error:
                return None, error
            content = path.read_text(encoding="utf-8")
            files.append({"path": relative_path, "content": content})
        project, error = validate_project(
            {"name": name, "summary": "Saved project", "files": files}
        )
        if error:
            return None, error
        return project, None
    except (OSError, UnicodeError, ValueError) as error:
        return None, f"I couldn't safely read the project: {error}"


def _project_fingerprint(project):
    serialized = json.dumps(project["files"], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def request_project_run(name):
    if _read_json(RUN_REQUEST_PATH):
        return "There is already a project run waiting. Say approve run or reject run first."
    project, error = _load_saved_project(name)
    if error:
        return error
    entry = next((path for path in ("main.py", "app.py") if any(file["path"] == path for file in project["files"])), None)
    if not entry:
        return "I can currently run Python projects with a root main.py or app.py entry point."
    _write_json(
        RUN_REQUEST_PATH,
        {
            "status": "proposed",
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "project": name,
            "entry": entry,
            "fingerprint": _project_fingerprint(project),
        },
    )
    return (
        f"Run request prepared for '{name}' using {entry}. Review the source in "
        f"{PROJECTS_DIR / name}, then say approve run. It will have no network, Windows-drive, or home-directory access."
    )


def show_project_run_request():
    request = _read_json(RUN_REQUEST_PATH)
    if not request or request.get("status") != "proposed":
        return "There is no project run waiting for approval."
    project, error = _load_saved_project(request.get("project"))
    if error:
        return f"The run request is no longer valid: {error}"
    if _project_fingerprint(project) != request.get("fingerprint"):
        return "The project changed after its run request was created. Request a new run after reviewing the changes."
    filenames = ", ".join(item["path"] for item in project["files"])
    return (
        f"Project '{project['name']}' will run {request.get('entry')} in the WSL sandbox. "
        f"Files: {filenames}. Network and Windows files are unavailable."
    )


def _run_project_in_sandbox(project, entry, tool_input=None):
    allowed_entries = {"main.py", "app.py"} if tool_input is None else {"tool.py"}
    if entry not in allowed_entries:
        return "Project execution was rejected because its entry point is not allowed."
    wsl = shutil.which("wsl.exe") or shutil.which("wsl")
    if not wsl:
        return "Project execution is disabled because Windows Subsystem for Linux is unavailable."
    command = [
        wsl,
        "--distribution",
        WSL_DISTRIBUTION,
        "--exec",
        "/usr/bin/python3",
        "-I",
        "-c",
        _WSL_SANDBOX_RUNNER,
    ]
    payload = json.dumps({"entry": entry, "files": project["files"], "input": tool_input})
    try:
        result = subprocess.run(
            command,
            input=payload,
            capture_output=True,
            text=True,
            timeout=MAX_RUN_SECONDS + 20,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return "The WSL sandbox did not respond in time. The project was not run or was stopped."
    except OSError:
        return "I couldn't start WSL. Project execution is disabled."

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[:1000]
        return f"The WSL sandbox failed to start (code {result.returncode}). {detail}"
    try:
        response = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return "The WSL sandbox returned an invalid response."
    if not isinstance(response, dict):
        return "The WSL sandbox returned an invalid response."
    if response.get("timed_out"):
        return f"Project execution stopped at the {MAX_RUN_SECONDS}-second time limit."
    if response.get("truncated"):
        return f"Project output exceeded the {MAX_RUN_OUTPUT}-character limit and was stopped."
    output = response.get("output", "")
    if not isinstance(output, str):
        return "The project returned an invalid output value."
    output = output[:MAX_RUN_OUTPUT].strip()
    if response.get("ok"):
        return f"Project finished in the WSL sandbox. Output: {output or '(no output)'}"
    error = response.get("error")
    if isinstance(error, str):
        return f"Project execution is unavailable: {error[:1000]}"
    code = response.get("returncode")
    return f"Project exited with code {code}. Output: {output or '(no output)'}"


def approve_project_run():
    request = _read_json(RUN_REQUEST_PATH)
    if not request or request.get("status") != "proposed":
        return "There is no project run waiting for approval."
    project, error = _load_saved_project(request.get("project"))
    if error:
        return f"I didn't run the project: {error}"
    if _project_fingerprint(project) != request.get("fingerprint"):
        return "I didn't run it because the project changed after review. Request a new run after reviewing the changes."
    entry = request.get("entry")
    if entry not in {"main.py", "app.py"} or not any(file["path"] == entry for file in project["files"]):
        return "I didn't run it because its Python entry point is invalid."

    try:
        RUN_REQUEST_PATH.unlink()
    except OSError as error:
        return f"I couldn't consume the approval request, so I did not run the project: {error}"
    return _run_project_in_sandbox(project, entry)


def reject_project_run():
    request = _read_json(RUN_REQUEST_PATH)
    if not request or request.get("status") != "proposed":
        return "There is no project run waiting to reject."
    try:
        RUN_REQUEST_PATH.unlink()
    except OSError as error:
        return f"I couldn't discard the run request: {error}"
    return "I discarded the project run request."


def handle_project_command(text):
    query = _normalize(text)
    if query in {"show run request", "show project run request", "review run request"}:
        return show_project_run_request()
    if query in {"approve run", "approve project run", "run approved project"}:
        return approve_project_run()
    if query in {"reject run", "cancel run", "cancel project run"}:
        return reject_project_run()
    if query in {"show project proposal", "preview project proposal", "review project proposal"}:
        return show_project_proposal()
    if query in {"approve project", "approve project proposal", "write approved project"}:
        return approve_project()
    if query in {"reject project", "cancel project", "discard project proposal"}:
        return reject_project()

    run_match = re.match(r"^(?:please\s+)?run project ([a-z][a-z0-9-]{1,39})$", query)
    if run_match:
        return request_project_run(run_match.group(1))

    match = re.match(
        r"^(?:please\s+)?(?:create|build|make|generate)\s+(?:me\s+)?(?:(?:a|an)\s+)?"
        r"(?:(?:simple|small|new)\s+)*(?:(?:web|mobile|desktop)\s+)?"
        r"(?:app|application|website|program|project)\b(?:\s+(?:for|that|to)\s+)?(.*)$",
        query,
    )
    if match:
        return create_project_proposal(match.group(1))
    return None