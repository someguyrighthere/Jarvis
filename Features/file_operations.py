import re
from pathlib import Path


def _safe_file_name(name):
    reserved_names = {"CON", "PRN", "AUX", "NUL"}
    reserved_names.update(f"COM{i}" for i in range(1, 10))
    reserved_names.update(f"LPT{i}" for i in range(1, 10))
    return (
        bool(name)
        and len(name) <= 150
        and bool(re.fullmatch(r"[A-Za-z0-9 _.-]+", name))
        and name not in {".", ".."}
        and not name.endswith((".", " "))
        and name.split(".", 1)[0].upper() not in reserved_names
    )


def parse_rename_command(command):
    match = re.fullmatch(r"\s*rename file\s+(.+?)\s+to\s+(.+?)\s*", command, re.IGNORECASE)
    if not match:
        raise ValueError("Say: rename file <current name> to <new name>.")
    source_name, target_name = (part.strip().strip("\"'") for part in match.groups())
    if not _safe_file_name(source_name) or not _safe_file_name(target_name):
        raise ValueError("File names must be simple names in SARA's working folder.")
    if source_name.casefold() == target_name.casefold():
        raise ValueError("The new file name must be different from the current name.")
    return source_name, target_name


def validate_rename(command):
    source_name, target_name = parse_rename_command(command)
    working_folder = Path.cwd().resolve()
    source = working_folder / source_name
    target = working_folder / target_name
    if not source.is_file() or source.resolve().parent != working_folder:
        raise FileNotFoundError(f"I could not find {source_name} in SARA's working folder.")
    if target.exists():
        raise FileExistsError(f"I will not overwrite the existing file {target_name}.")
    return source_name, target_name


def rename_file(command):
    try:
        source_name, target_name = validate_rename(command)
        (Path.cwd() / source_name).rename(Path.cwd() / target_name)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as error:
        return str(error)
    return f"Renamed {source_name} to {target_name}."


def undo_rename(source_name, target_name):
    command = f"rename file {target_name} to {source_name}"
    source_name, target_name = validate_rename(command)
    (Path.cwd() / source_name).rename(Path.cwd() / target_name)
    return f"Renamed {source_name} back to {target_name}."
