"""Run with the experiment venv to measure local routing over repeated paraphrases.

Uses fixed mock apps only. Every case runs twice; the script reports first-attempt
and repaired decisions separately and exits nonzero if any expected route fails.
It never confirms success or runs an approval-gated mock action.
"""

from __future__ import annotations

import json
import os

from app_tree_prototype import AppTree, Capability, MockExecutor, MockOutcome, ResultStatus, RouteKind
from ollama_app_tree_check import LocalOllamaPlanner


CASES = [
    ("What is photosynthesis?", RouteKind.ANSWER, ""),
    ("Explain why the sky looks blue.", RouteKind.ANSWER, ""),
    ("Check the weather forecast for Boston.", RouteKind.CAPABILITY, "weather.lookup"),
    ("Will it rain in Seattle tomorrow?", RouteKind.CAPABILITY, "weather.lookup"),
    ("Remind me to call Alex tomorrow.", RouteKind.CAPABILITY, "reminders.create"),
    ("Make sure I don't forget my dentist appointment tomorrow.", RouteKind.CAPABILITY, "reminders.create"),
    ("Sort my Downloads files into folders by file type.", RouteKind.NEEDS_CAPABILITY, ""),
    ("Send a WhatsApp message to Alex saying I'll be late.", RouteKind.NEEDS_CAPABILITY, ""),
]


def run_reliability_checks() -> dict[str, object]:
    planner = LocalOllamaPlanner(model=os.environ.get("SARA_APP_TREE_OLLAMA_MODEL", "qwen3:8b"))
    rows: list[dict[str, object]] = []
    for repetition in range(1, 3):
        for request, expected_kind, expected_capability in CASES:
            app = AppTree([
                Capability("weather.lookup", "Look up a weather forecast (mock only).", False,
                           MockExecutor(MockOutcome(True, "Mock forecast."))),
                Capability("reminders.create", "Create a reminder about a future task (mock only).", True,
                           MockExecutor(MockOutcome(True, "Mock reminder."))),
            ])
            row: dict[str, object] = {"request": request, "repetition": repetition}
            try:
                intent = planner.choose(request, app.capability_descriptions())
            except RuntimeError as exc:
                row.update(passed=False, error=str(exc), attempts=planner.last_attempt_count)
            else:
                result = app.route(request, intent)
                expected_status = {
                    RouteKind.ANSWER: ResultStatus.ANSWERED,
                    RouteKind.NEEDS_CAPABILITY: ResultStatus.FORGE_PROPOSAL,
                    RouteKind.CAPABILITY: (
                        ResultStatus.AWAITING_APPROVAL if expected_capability == "reminders.create"
                        else ResultStatus.AWAITING_CONFIRMATION
                    ),
                }[expected_kind]
                passed = (
                    intent.kind is expected_kind
                    and intent.capability_id == expected_capability
                    and result.status is expected_status
                    and not app.memory.successful_routes
                )
                row.update(
                    passed=passed, route=intent.kind.value, capability=intent.capability_id,
                    status=result.status.value, attempts=planner.last_attempt_count,
                )
            rows.append(row)
            print(json.dumps(row, ensure_ascii=True), flush=True)

    return {
        "model": planner.model,
        "total": len(rows),
        "passed": sum(row["passed"] is True for row in rows),
        "passed_first_attempt": sum(
            row["passed"] is True and row["attempts"] == 1 for row in rows
        ),
        "passed_after_repair": sum(
            row["passed"] is True and row["attempts"] == 2 for row in rows
        ),
        "failed": sum(row["passed"] is False for row in rows),
        "cases": rows,
    }


if __name__ == "__main__":
    report = run_reliability_checks()
    print(json.dumps(report, indent=2, ensure_ascii=True))
    raise SystemExit(1 if report["failed"] else 0)
