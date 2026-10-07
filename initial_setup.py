import argparse
import logging
import subprocess
from pathlib import Path

import requests

from dependency_setup import inspect_component, install_component

LOGGER = logging.getLogger(__name__)
SETUP_COMPONENTS = ("chrome", "ollama", "sara-model", "forge", "forge-model")
SETUP_ERRORS = (OSError, ValueError, RuntimeError, subprocess.SubprocessError,
                requests.RequestException, KeyError, TypeError, ImportError)


def install_selected(components: list[str]) -> list[str]:
    unknown = set(components) - set(SETUP_COMPONENTS)
    if unknown:
        raise ValueError(f"Unknown setup components: {', '.join(sorted(unknown))}")
    failures = []
    for component in SETUP_COMPONENTS:
        if component not in components:
            continue
        try:
            try:
                state, detail = inspect_component(component)
            except SETUP_ERRORS as error:
                LOGGER.warning("Could not check %s before setup: %s", component, error)
                state = "unavailable"
            if state in {"installed", "bundled"}:
                LOGGER.info("%s already present: %s", component, detail)
                continue
            LOGGER.info("Installing selected component: %s", component)
            install_component(component)
            state, detail = inspect_component(component)
            if state not in {"installed", "bundled"}:
                raise RuntimeError(f"Verification failed: {detail}. A restart may be required.")
            LOGGER.info("%s installed and verified: %s", component, detail)
        except SETUP_ERRORS as error:
            LOGGER.exception("Setup failed for %s", component)
            failures.append(f"{component}: {error}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install only the dependency choices selected in SARA setup.")
    parser.add_argument("--setup-components", required=True)
    parser.add_argument("--setup-log", required=True, type=Path)
    args = parser.parse_args(argv)
    args.setup_log.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(args.setup_log, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        failures = install_selected(args.setup_components.split(","))
        if failures:
            LOGGER.error("Selected setup components need attention:\n%s", "\n".join(failures))
            return 1
        LOGGER.info("All selected components are present. Unselected components were not installed.")
        return 0
    except SETUP_ERRORS:
        LOGGER.exception("Initial dependency setup failed")
        return 1
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)
        handler.close()


if __name__ == "__main__":
    raise SystemExit(main())
