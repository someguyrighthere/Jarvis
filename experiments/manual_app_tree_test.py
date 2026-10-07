"""Interactive, isolated test of app-tree routing and user-confirmed learning."""

from __future__ import annotations

import os

from app_tree_prototype import (
    AppTree,
    Capability,
    MockExecutor,
    MockOutcome,
    ResultStatus,
)
from ollama_app_tree_check import LocalOllamaPlanner


def _show_memory(app: AppTree) -> None:
    if not app.memory.successful_routes:
        print("No workflows have been learned in this session.")
        return
    print("User-confirmed workflows learned in this session:")
    for (task_type, capability_id), count in sorted(app.memory.successful_routes.items()):
        print(f"  {task_type} -> {capability_id} (confirmed {count} time(s))")


def _resolve_pending(app: AppTree, pending: dict[int, str], command: str) -> None:
    parts = command.split()
    if len(parts) != 3 or parts[0] != ":confirm" or parts[2].casefold() not in {"yes", "no"}:
        print("Use :confirm <number> yes or :confirm <number> no.")
        return
    try:
        label = int(parts[1])
    except ValueError:
        print("The pending confirmation number must be an integer.")
        return
    confirmation_id = pending.get(label)
    if confirmation_id is None:
        print(f"There is no pending confirmation #{label}.")
        return

    result = app.confirm_success(confirmation_id, parts[2].casefold() == "yes")
    if result.status is ResultStatus.REJECTED:
        print(f"Confirmation was not applied: {result.message}")
        return
    del pending[label]
    print(result.message)


def run_manual_test() -> None:
    model = os.environ.get("SARA_APP_TREE_OLLAMA_MODEL", "qwen3:8b")
    planner = LocalOllamaPlanner(model=model)
    app = AppTree(
        [
            Capability(
                capability_id="weather.lookup",
                description="Look up weather information (mock only).",
                requires_approval=False,
                executor=MockExecutor(MockOutcome(True, "Mock result: sunny and 20 C.")),
            )
        ]
    )
    pending: dict[int, str] = {}
    next_pending_label = 1

    print(f"Isolated SARA app-tree demo using local Ollama model: {planner.model}")
    print("Only the fixed mock weather capability is available; it performs no real lookup.")
    print("Try: 'Check the weather forecast for Boston.'")
    print("Commands: :memory, :pending, :confirm <number> yes|no, :quit")
    print("Learned routes and pending confirmations exist only until this process exits.\n")

    while True:
        try:
            request = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nEnding the demo. Unconfirmed routes will not be learned.")
            break

        if not request:
            continue
        if request.casefold() in {":quit", ":q"}:
            break
        if request.casefold() == ":memory":
            _show_memory(app)
            continue
        if request.casefold() == ":pending":
            if not pending:
                print("No pending confirmations.")
            else:
                print("Pending success confirmations:")
                for label in sorted(pending):
                    print(f"  #{label}: reply with :confirm {label} yes|no")
            continue
        if request.casefold().startswith(":confirm"):
            _resolve_pending(app, pending, request)
            continue
        if request.startswith(":"):
            print("Unknown command. Use :memory, :pending, :confirm <number> yes|no, or :quit.")
            continue

        try:
            intent = planner.choose(request, app.capability_descriptions())
        except RuntimeError as exc:
            print(f"Routing failed safely: {exc}")
            continue

        result = app.route(request, intent)
        if result.suggested_capability:
            print(f"SARA suggests the previously confirmed route: {result.suggested_capability}")

        if result.status is ResultStatus.ANSWERED:
            print(f"SARA: {result.message}")
            continue
        if result.status is ResultStatus.FORGE_PROPOSAL:
            print(f"SARA: {result.message}")
            continue
        if result.status is ResultStatus.REJECTED:
            print(f"SARA could not route that safely: {result.message}")
            continue
        if result.status is not ResultStatus.AWAITING_CONFIRMATION:
            print(f"Unexpected prototype result: {result.status.value}: {result.message}")
            continue

        print(f"SARA (mock app result): {result.message}")
        while True:
            try:
                confirmation = input("Did it work as expected? [yes/no/skip]: ").strip().casefold()
            except (EOFError, KeyboardInterrupt):
                print("\nNo confirmation received; this result was not learned.")
                return
            if confirmation in {"yes", "y"}:
                confirmed = app.confirm_success(result.confirmation_id, True)
                print(f"SARA: {confirmed.message}")
                break
            if confirmation in {"no", "n"}:
                declined = app.confirm_success(result.confirmation_id, False)
                print(f"SARA: {declined.message}")
                break
            if confirmation in {"skip", "s"}:
                pending[next_pending_label] = result.confirmation_id
                print(
                    f"No confirmation received; nothing was learned. "
                    f"Confirmation #{next_pending_label} remains pending for this session."
                )
                next_pending_label += 1
                break
            print("Please enter yes, no, or skip.")

    _show_memory(app)
    if pending:
        print(f"{len(pending)} confirmation(s) remain unanswered and were not learned.")
    print("Demo ended; all prototype memory is discarded.")


if __name__ == "__main__":
    run_manual_test()
