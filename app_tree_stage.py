"""Disabled-by-default mock command adapter; optional local model routing, no real apps.

The "app tree test" namespace accepts exact prefix spelling variants; incomplete
app-tree commands receive guidance, never model interpretation. Mock workflow persistence
requires a separate opt-in; approvals and pending confirmations stay in-process.
This adapter does not read or write SARA's profile, preferences, notes, or knowledge.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from experiments.app_tree_prototype import AppTree, DispatchResult


class MockAppTreeStage:
    def __init__(self) -> None:
        self._app: AppTree | None = None
        self._result: DispatchResult | None = None

    def _create_app(self) -> AppTree:
        from experiments.app_tree_prototype import AppTree, Capability, MockExecutor, MockOutcome

        memory = None
        if os.environ.get("SARA_APP_TREE_MEMORY_ENABLED") == "1":
            from mock_workflow_memory import MockWorkflowMemory

            memory = MockWorkflowMemory()
        return AppTree([
            Capability("weather.lookup", "Fixed mock weather lookup; no network request.", False,
                       MockExecutor(MockOutcome(True, "Mock forecast: sunny and 20 C. This is not live weather."))),
            Capability("reminders.create", "Mock reminder simulation. No real reminder will be scheduled.", True,
                       MockExecutor(MockOutcome(True, "The mock reminder returned success. No real reminder was created."))),
            Capability("weather.failed", "Fixed failed mock weather lookup.", False,
                       MockExecutor(MockOutcome(False, "The mock weather service failed. Nothing was learned."))),
        ], memory=memory)

    def handle(self, command: str, *, answerer: Callable[[str], str] | None = None) -> str | None:
        text = " ".join(command.casefold().split())
        prefix = next(
            (candidate for candidate in ("app tree", "apptree", "app-tree")
             if text == candidate or text.startswith(candidate + " ")),
            None,
        )
        if prefix is None:
            return None
        remainder = text[len(prefix):].strip()
        if os.environ.get("SARA_APP_TREE_MOCK_ENABLED") != "1":
            # Discard stale test decisions if the feature is disabled in-process.
            self._app = None
            self._result = None
            return "The mock app-tree stage is disabled. No test or real action was run."
        if remainder != "test" and not remainder.startswith("test "):
            return (
                "For the isolated mock test, say app tree test help. "
                "Include the word test. No action was run or workflow learned."
            )

        from experiments.app_tree_prototype import Intent, ResultStatus, RouteKind

        action = remainder.removeprefix("test").strip()
        if action == "reset":
            self._app = None
            self._result = None
            return "I reset the active mock session and pending decisions. Persisted mock workflows and personal memory are unchanged."
        if not action or action == "help":
            return (
                "This is the mock app-tree stage, not real app execution. Say app tree test followed by "
                "weather, reminder, failure, or missing app. Use app tree test approve or reject for a "
                "mock action, and app tree test worked, failed, or not sure for its result. "
                "Use app tree test memory to inspect mock workflows, or app tree test reset."
                " Say app tree test ask followed by a natural request for local Ollama routing."
                " Use app tree test clear workflows to delete saved mock successes only."
            )
        natural_request = action.removeprefix("ask ").strip() if action.startswith("ask ") else ""
        if not natural_request and action not in {
            "weather", "reminder", "failure", "missing app",
            "approve", "reject", "worked", "failed", "not sure", "memory", "clear workflows",
        }:
            return (
                "That is not a supported mock command. Say app tree test help. "
                "For a weather scenario, say app tree test weather; respond separately "
                "with app tree test worked or app tree test failed. No action was run."
            )
        from mock_workflow_memory import MockWorkflowMemory

        if action == "clear workflows":
            if self._app is not None and isinstance(self._app.memory, MockWorkflowMemory):
                self._app.memory.clear()
            elif self._app is None and os.environ.get("SARA_APP_TREE_MEMORY_ENABLED") == "1":
                MockWorkflowMemory(load=False).clear()
            elif self._app is not None:
                self._app.memory.successful_routes.clear()
            self._app = None
            self._result = None
            return "Cleared mock workflow successes and pending mock decisions. Personal memory is unchanged."
        if self._app is None:
            self._app = self._create_app()
        app = self._app
        result = self._result
        approval_pending = result is not None and result.status is ResultStatus.AWAITING_APPROVAL
        confirmation_pending = result is not None and result.status is ResultStatus.AWAITING_CONFIRMATION
        persistent = isinstance(app.memory, MockWorkflowMemory)
        if action == "memory":
            if persistent:
                app.memory.refresh()
            routes = app.memory.successful_routes
            scope = "Persisted MOCK-TEST-ONLY" if persistent else "Temporary"
            if not routes:
                return f"{scope} memory: no mock workflows have been learned. Your existing personal memory is unchanged."
            entries = "; ".join(
                f"{task}: {capability}, confirmed {count} time(s)"
                for (task, capability), count in sorted(routes.items())
            )
            return f"{scope}, user-confirmed test workflows: {entries}. Your existing memory is unchanged."
        if action in {"approve", "reject"}:
            if not approval_pending or result is None:
                return "There is no mock action awaiting approval. No real action was affected."
            self._result = app.approve(result.approval_id) if action == "approve" else app.reject(result.approval_id)
        elif action in {"worked", "failed", "not sure"}:
            if not confirmation_pending or result is None:
                return "There is no mock result awaiting success confirmation. Nothing was learned."
            if action == "not sure":
                return "Quite all right. Nothing was learned; the mock result remains unconfirmed. Decide later or reset the test."
            self._result = app.confirm_success(result.confirmation_id, action == "worked")
        else:
            if approval_pending or confirmation_pending:
                return "Please resolve the current mock decision first, or say app tree test reset. Nothing new was run."
            if natural_request:
                if natural_request.rstrip(".?!") in {
                    "what time is it", "waht time is it", "what's the time",
                    "what is the time", "tell me the time",
                }:
                    now = datetime.now().astimezone()
                    return f"The computer's local time is {now.strftime('%I:%M %p %Z')}."
                from experiments.ollama_app_tree_check import LocalOllamaPlanner

                planner = LocalOllamaPlanner(
                    model=os.environ.get("SARA_APP_TREE_OLLAMA_MODEL", "qwen3:8b")
                )
                # The failed weather fixture is not a useful model routing candidate.
                available = {
                    "weather.lookup": "Mock weather forecast for a requested location; no live lookup.",
                    "reminders.create": "Mock reminder for the user's task; no actual scheduling.",
                }
                try:
                    intent = planner.choose(natural_request, available)
                except (RuntimeError, ValueError) as error:
                    return f"Mock routing failed safely: {error}. No app ran or workflow was learned."
                if intent.kind is RouteKind.ANSWER:
                    if answerer is None:
                        return "SARA's conversation handler is unavailable. No planner answer was substituted."
                    answer = answerer(natural_request)
                    if not isinstance(answer, str) or not answer.strip():
                        return "SARA did not return a conversation answer. No app ran or workflow was learned."
                    return answer
                self._result = app.route(natural_request, intent)
                message = self._describe_result()
                if self._result.status is ResultStatus.AWAITING_APPROVAL:
                    message = (
                        f"Review mock request: {natural_request}. This simulates a reminder only; "
                        "no real reminder will be scheduled. Say app tree test approve or app tree test reject."
                    )
                repair_note = (
                    "The initial model decision needed one validated repair. "
                    if planner.last_attempt_count == 2 else ""
                )
                return repair_note + message
            scenarios = {
                "weather": ("Mock Boston forecast.", Intent(RouteKind.CAPABILITY, "weather", capability_id="weather.lookup")),
                "reminder": ("Mock reminder tomorrow at 9 AM: call Alex.",
                             Intent(RouteKind.CAPABILITY, "reminder", capability_id="reminders.create")),
                "failure": ("Failed mock forecast.", Intent(RouteKind.CAPABILITY, "weather", capability_id="weather.failed")),
                "missing app": ("Mock file organization request.",
                                Intent(RouteKind.NEEDS_CAPABILITY, "file organization",
                                       capability_request="Proposal only: file organization helper.")),
            }
            request, intent = scenarios[action]
            self._result = app.route(request, intent)
        return self._describe_result()

    def _describe_result(self) -> str:
        from experiments.app_tree_prototype import ResultStatus

        result = self._result
        if result is None:
            raise RuntimeError("No mock result is available to describe.")
        message = result.message
        if result.status is ResultStatus.AWAITING_APPROVAL:
            message += " Say app tree test approve or app tree test reject."
        elif result.status is ResultStatus.AWAITING_CONFIRMATION:
            message += " Say app tree test worked, app tree test failed, or app tree test not sure."
        elif result.status is ResultStatus.SUCCESS_CONFIRMED:
            from mock_workflow_memory import MockWorkflowMemory

            scope = "persisted mock-test-only memory" if isinstance(self._app.memory, MockWorkflowMemory) else "temporary test memory"
            message += f" This is {scope} only; it does not prove a real app works. Future actions still need approval."
        if result.suggested_capability:
            message += f" Previously confirmed test route: {result.suggested_capability}."
        return message


_stage = MockAppTreeStage()


def handle_mock_app_tree_command(
    command: str, *, answerer: Callable[[str], str] | None = None,
) -> str | None:
    return _stage.handle(command, answerer=answerer)
