"""Standalone app-tree design prototype. Imports no SARA runtime modules and runs no real tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from uuid import uuid4


class RouteKind(str, Enum):
    ANSWER = "answer"
    CAPABILITY = "capability"
    NEEDS_CAPABILITY = "needs_capability"


class ResultStatus(str, Enum):
    ANSWERED = "answered"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    SUCCESS_CONFIRMED = "success_confirmed"
    NOT_CONFIRMED = "not_confirmed"
    FORGE_PROPOSAL = "forge_proposal"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Intent:
    kind: RouteKind
    task_type: str
    answer: str = ""
    capability_id: str = ""
    capability_request: str = ""


@dataclass(frozen=True)
class MockOutcome:
    success: bool
    message: str


@dataclass(frozen=True)
class MockExecutor:
    """Fixed test response; intentionally has no callback, subprocess, or network hook."""

    outcome: MockOutcome

    def execute(self, request: str) -> MockOutcome:
        return self.outcome


@dataclass(frozen=True)
class Capability:
    capability_id: str
    description: str
    requires_approval: bool
    executor: MockExecutor


@dataclass(frozen=True)
class DispatchResult:
    status: ResultStatus
    message: str
    capability_id: str = ""
    approval_id: str = ""
    confirmation_id: str = ""
    suggested_capability: str = ""


@dataclass
class ForgeProposal:
    proposal_id: str
    request: str
    status: str = "proposal_only"


@dataclass
class PrototypeMemory:
    """Ephemeral test memory; it never reads or writes SARA's real memory files."""

    successful_routes: dict[tuple[str, str], int] = field(default_factory=dict)

    def record_success(self, task_type: str, capability_id: str) -> None:
        key = (_normalize(task_type), capability_id)
        self.successful_routes[key] = self.successful_routes.get(key, 0) + 1

    def preferred_capability(self, task_type: str, available: set[str]) -> str:
        matches = [
            (count, capability_id)
            for (saved_task, capability_id), count in self.successful_routes.items()
            if saved_task == _normalize(task_type) and capability_id in available
        ]
        if not matches:
            return ""
        return sorted(matches, key=lambda item: (-item[0], item[1]))[0][1]


class AppTree:
    def __init__(self, capabilities: list[Capability], memory: PrototypeMemory | None = None):
        self._capabilities = {}
        for capability in capabilities:
            if capability.capability_id in self._capabilities:
                raise ValueError(f"Duplicate prototype capability: {capability.capability_id}")
            if type(capability.executor) is not MockExecutor:
                raise TypeError("The isolated prototype accepts only fixed MockExecutor capabilities.")
            self._capabilities[capability.capability_id] = capability
        self.memory = memory or PrototypeMemory()
        self.pending: dict[str, tuple[Intent, Capability, str]] = {}
        self.pending_confirmations: dict[str, tuple[str, str]] = {}
        self.forge_proposals: list[ForgeProposal] = []

    def capability_descriptions(self) -> dict[str, str]:
        return {
            capability_id: capability.description
            for capability_id, capability in sorted(self._capabilities.items())
        }

    def route(self, request: str, intent: Intent) -> DispatchResult:
        if not isinstance(intent, Intent) or not isinstance(intent.kind, RouteKind):
            return DispatchResult(ResultStatus.REJECTED, "The planner returned an invalid route.")
        if not isinstance(intent.task_type, str) or not intent.task_type.strip() or len(intent.task_type) > 100:
            return DispatchResult(ResultStatus.REJECTED, "The planner returned an invalid task type.")
        task_type = _normalize(intent.task_type)
        if intent.kind is RouteKind.ANSWER:
            if not isinstance(intent.answer, str) or not intent.answer.strip() or len(intent.answer) > 4000:
                return DispatchResult(ResultStatus.REJECTED, "The answer was empty.")
            return DispatchResult(ResultStatus.ANSWERED, intent.answer.strip())

        if intent.kind is RouteKind.NEEDS_CAPABILITY:
            if (
                not isinstance(intent.capability_request, str)
                or not intent.capability_request.strip()
                or len(intent.capability_request) > 1000
            ):
                return DispatchResult(ResultStatus.REJECTED, "A capability request is required.")
            proposal = ForgeProposal(str(uuid4()), intent.capability_request.strip())
            self.forge_proposals.append(proposal)
            return DispatchResult(
                ResultStatus.FORGE_PROPOSAL,
                "Capability request recorded for review; Forge was not launched and no app was created.",
            )

        if not isinstance(intent.capability_id, str) or not re.fullmatch(
            r"[a-z][a-z0-9_.-]{1,79}", intent.capability_id
        ):
            return DispatchResult(ResultStatus.REJECTED, "The planner returned an invalid capability identifier.")
        capability = self._capabilities.get(intent.capability_id)
        if capability is None:
            return DispatchResult(
                ResultStatus.REJECTED,
                "The selected capability is not in the prototype registry.",
            )

        suggested = self.memory.preferred_capability(task_type, set(self._capabilities))
        if capability.requires_approval:
            approval_id = str(uuid4())
            self.pending[approval_id] = (intent, capability, request)
            return DispatchResult(
                ResultStatus.AWAITING_APPROVAL,
                f"Review: {capability.description}. Nothing has run yet.",
                capability_id=capability.capability_id,
                approval_id=approval_id,
                suggested_capability=suggested,
            )
        return self._execute(intent, capability, request, suggested)

    def approve(self, approval_id: str) -> DispatchResult:
        pending = self.pending.pop(approval_id, None)
        if pending is None:
            return DispatchResult(ResultStatus.REJECTED, "No matching pending approval.")
        intent, capability, request = pending
        suggested = self.memory.preferred_capability(intent.task_type, set(self._capabilities))
        return self._execute(intent, capability, request, suggested)

    def reject(self, approval_id: str) -> DispatchResult:
        if self.pending.pop(approval_id, None) is None:
            return DispatchResult(ResultStatus.REJECTED, "No matching pending approval.")
        return DispatchResult(ResultStatus.REJECTED, "The proposed action was discarded.")

    def confirm_success(self, confirmation_id: str, worked: bool) -> DispatchResult:
        if not isinstance(worked, bool):
            return DispatchResult(
                ResultStatus.REJECTED,
                "Success confirmation must be an explicit yes or no.",
            )
        pending = self.pending_confirmations.get(confirmation_id)
        if pending is None:
            return DispatchResult(
                ResultStatus.REJECTED,
                "No matching pending success confirmation.",
            )
        task_type, capability_id = pending
        if not worked:
            self.pending_confirmations.pop(confirmation_id)
            return DispatchResult(
                ResultStatus.NOT_CONFIRMED,
                "The result was not confirmed; nothing was learned.",
                capability_id=capability_id,
            )
        self.memory.record_success(task_type, capability_id)
        self.pending_confirmations.pop(confirmation_id)
        return DispatchResult(
            ResultStatus.SUCCESS_CONFIRMED,
            "The result was confirmed and this route was learned.",
            capability_id=capability_id,
        )

    def _execute(
        self,
        intent: Intent,
        capability: Capability,
        request: str,
        suggested: str,
    ) -> DispatchResult:
        outcome = capability.executor.execute(request)
        if outcome.success:
            confirmation_id = str(uuid4())
            self.pending_confirmations[confirmation_id] = (
                intent.task_type,
                capability.capability_id,
            )
            return DispatchResult(
                ResultStatus.AWAITING_CONFIRMATION,
                f"{outcome.message} Did this work as expected? No route will be learned unless you confirm yes.",
                capability_id=capability.capability_id,
                confirmation_id=confirmation_id,
                suggested_capability=suggested,
            )
        return DispatchResult(
            ResultStatus.REJECTED,
            outcome.message,
            capability_id=capability.capability_id,
            suggested_capability=suggested,
        )


def _normalize(text: str) -> str:
    return " ".join(text.strip().casefold().split())
