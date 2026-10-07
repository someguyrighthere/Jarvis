"""Opt-in local Ollama routing check with fixed mock apps.

Malformed decisions get one explicitly reported repair attempt, with full
validation again. Transport failures are not retried. Approval and user-confirmed
learning remain the responsibility of AppTree, never the model or its repair.
"""

from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

if __package__:
    from .app_tree_prototype import (
        AppTree, Capability, Intent, MockExecutor, MockOutcome, ResultStatus, RouteKind,
    )
else:
    from app_tree_prototype import (
        AppTree, Capability, Intent, MockExecutor, MockOutcome, ResultStatus, RouteKind,
    )


_INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": [kind.value for kind in RouteKind]},
        "task_type": {"type": "string", "minLength": 1, "maxLength": 100},
        "answer": {"type": "string"},
        "capability_id": {"type": "string"},
        "capability_request": {"type": "string"},
    },
    "required": ["kind", "task_type", "answer", "capability_id", "capability_request"],
    "additionalProperties": False,
}


class LocalOllamaPlanner:
    def __init__(self, model: str | None = None, endpoint: str | None = None, *, live: bool = False):
        self.model = model or os.environ.get(
            "SARA_APP_TREE_OLLAMA_MODEL",
            os.environ.get("OLLAMA_MODEL", "llama3.2"),
        )
        self.endpoint = endpoint or os.environ.get(
            "SARA_APP_TREE_OLLAMA_ENDPOINT",
            "http://127.0.0.1:11434/api/chat",
        )
        parsed_endpoint = urlsplit(self.endpoint)
        if parsed_endpoint.scheme != "http" or parsed_endpoint.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError("The isolated Ollama check only permits a local HTTP endpoint.")
        if not self.model.strip():
            raise ValueError("An Ollama model name is required.")
        self.last_attempt_count = 0
        self.live = live

    def choose(self, request: str, available_capabilities: dict[str, str]) -> Intent:
        system_prompt = (
            "Route the user's request to exactly one of: answer, capability, needs_capability. "
            "Return only JSON matching the supplied schema. Use answer for general knowledge, "
            "explanations, conversation, and questions you can answer yourself. Your ability "
            "to answer is built in; it does NOT need to appear in the capability list. "
            "A question such as 'Why do leaves change color?' requires an answer, not a new app. "
            "Use capability for requests needing a listed app, such as a live weather forecast "
            "or creating a reminder. Use needs_capability for unsupported external actions, "
            "not for ordinary knowledge questions. Distinguish explaining an action from "
            "performing it: 'How do I sort files?' can be answered; 'Sort the files in my "
            "Downloads folder' asks you to act and requires needs_capability if no file "
            "organizer is listed. Never substitute instructions or a claim of completion "
            "for a requested external action you cannot perform. Treat listed capabilities as fixed "
            "mock executors, not live integrations. Prefer a listed capability if it could "
            "reasonably handle the request; if several fit, choose the closest match. Do not "
            "choose needs_capability only because a request is ambiguous or lacks details; the "
            "approval step handles confirmation. Choose needs_capability only if no listed "
            "capability can reasonably handle the requested task.\n"
            "Always fill task_type with a nonempty short category (1 to 100 characters), "
            "such as general question, weather, or reminder, regardless of the chosen route. "
            "Never leave task_type empty. "
            "For answer, fill answer and leave capability_id and capability_request empty. "
            "For capability, fill only capability_id and leave answer and capability_request "
            "empty. For needs_capability, fill only capability_request and leave answer and "
            "capability_id empty. Use an exact registered capability ID; never invent one.\n"
            "Example: with reminders.create and calendar.create_event available, the request "
            "'Don't let me forget to call Alex tomorrow' routes to reminders.create, with the "
            "other two fields empty."
        )
        user_prompt = (
            f"Available capabilities: {json.dumps(available_capabilities, ensure_ascii=True)}\n"
            f"User request: {request}"
        )
        if self.live:
            system_prompt = system_prompt.replace(
                "Treat listed capabilities as fixed mock executors, not live integrations.",
                "These are real registered integrations. Select only listed capability IDs. "
                "Never execute anything or grant approval; the host parses the ORIGINAL request "
                "and asks the user to approve actions. Use answer for ordinary conversation.",
            )
            system_prompt += (
                "\nMissing arguments are NOT a missing app. If a reminder lacks a time, or weather "
                "lacks a city, still select reminders.create or weather.lookup; the host will ask "
                "for details before preparing approval. Do not request a new reminder app when "
                "reminders.create is registered."
            )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        self.last_attempt_count = 0
        for attempt in range(2):
            self.last_attempt_count += 1
            content = self._request(messages)
            try:
                return self._parse_intent(content, available_capabilities)
            except ValueError as exc:
                if attempt == 1:
                    raise RuntimeError(
                        f"Local Ollama routing rejected after two attempts: {exc}"
                    ) from exc
                print(
                    f"Invalid Ollama route: {exc}. Trying one repair; nothing has executed.",
                    file=sys.stderr,
                )
                messages.extend([
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": (
                            f"Your routing decision was rejected: {exc}. Return a corrected "
                            "decision for the ORIGINAL request, following the system rules. "
                            "Include all five string fields. Irrelevant fields must be empty "
                            "strings. Select only a listed capability ID. This is the final attempt."
                        ),
                    },
                ])
        raise RuntimeError("No valid routing decision was produced.")

    def _request(self, messages: list[dict[str, str]]) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "format": _INTENT_SCHEMA,
                "stream": False,
                "options": {"temperature": 0},
            }
        ).encode("utf-8")
        http_request = Request(
            self.endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Local Ollama returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Could not reach local Ollama at {self.endpoint}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise RuntimeError("Local Ollama timed out; no routing decision was accepted.") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Local Ollama returned an invalid JSON response.") from exc

        if (
            not isinstance(result, dict)
            or not isinstance(result.get("message"), dict)
            or not isinstance(result["message"].get("content"), str)
        ):
            raise RuntimeError("Local Ollama response is missing a text message.")
        return result["message"]["content"]

    @staticmethod
    def _parse_intent(content: str, available_capabilities: dict[str, str]) -> Intent:
        try:
            intent_data = json.loads(content)
            if not isinstance(intent_data, dict) or set(intent_data) != {
                "kind",
                "task_type",
                "answer",
                "capability_id",
                "capability_request",
            }:
                raise ValueError(
                    f"Unexpected response fields: {sorted(intent_data) if isinstance(intent_data, dict) else type(intent_data).__name__}."
                )
            if any(not isinstance(value, str) for value in intent_data.values()):
                raise ValueError("All intent fields must be strings.")
            if not intent_data["task_type"].strip() or len(intent_data["task_type"]) > 100:
                raise ValueError("Task type must contain 1 to 100 characters.")
            kind = RouteKind(intent_data["kind"])
            if kind is RouteKind.ANSWER:
                valid_fields = (
                    bool(intent_data["answer"].strip())
                    and not intent_data["capability_id"]
                    and not intent_data["capability_request"]
                )
            elif kind is RouteKind.CAPABILITY:
                valid_fields = (
                    bool(intent_data["capability_id"].strip())
                    and not intent_data["answer"]
                    and not intent_data["capability_request"]
                )
            else:
                valid_fields = (
                    bool(intent_data["capability_request"].strip())
                    and not intent_data["answer"]
                    and not intent_data["capability_id"]
                )
            if not valid_fields:
                populated_fields = [
                    field
                    for field in ("answer", "capability_id", "capability_request")
                    if intent_data[field]
                ]
                raise ValueError(
                    f"Fields do not match route {kind.value}; populated fields: {populated_fields}."
                )
            if kind is RouteKind.ANSWER and len(intent_data["answer"]) > 4000:
                raise ValueError("Answer exceeds 4000 characters.")
            if kind is RouteKind.NEEDS_CAPABILITY and len(intent_data["capability_request"]) > 1000:
                raise ValueError("Capability request exceeds 1000 characters.")
            if kind is RouteKind.CAPABILITY and intent_data["capability_id"] not in available_capabilities:
                raise ValueError("Selected capability is not registered.")
            return Intent(
                kind=kind,
                task_type=intent_data["task_type"],
                answer=intent_data["answer"],
                capability_id=intent_data["capability_id"],
                capability_request=intent_data["capability_request"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid routing decision: {exc}") from exc


def run_routing_checks() -> dict[str, str]:
    planner = LocalOllamaPlanner()
    app = AppTree(
        [
            Capability(
                capability_id="weather.lookup",
                description="Look up weather information (mock only).",
                requires_approval=False,
                executor=MockExecutor(MockOutcome(True, "Mock weather result.")),
            )
        ]
    )
    capabilities = app.capability_descriptions()

    question = "In one sentence, what is photosynthesis?"
    answer_intent = planner.choose(question, capabilities)
    answer_result = app.route(question, answer_intent)
    if answer_intent.kind is not RouteKind.ANSWER or answer_result.status is not ResultStatus.ANSWERED:
        raise AssertionError(
            f"Expected an answer route; got {answer_intent.kind.value}/{answer_result.status.value}."
        )

    weather_request = "Look up the current weather forecast for Boston."
    weather_intent = planner.choose(weather_request, capabilities)
    weather_result = app.route(weather_request, weather_intent)
    if (
        weather_intent.kind is not RouteKind.CAPABILITY
        or weather_intent.capability_id != "weather.lookup"
        or weather_result.status is not ResultStatus.AWAITING_CONFIRMATION
        or app.memory.successful_routes
    ):
        raise AssertionError(
            "Expected the registered weather.lookup mock; got "
            f"{weather_intent.kind.value}/{weather_intent.capability_id or '(no capability)'}/"
            f"{weather_result.status.value}."
        )
    weather_confirmation = app.confirm_success(weather_result.confirmation_id, True)
    if weather_confirmation.status is not ResultStatus.SUCCESS_CONFIRMED:
        raise AssertionError("Expected an explicit test confirmation to learn the weather route.")

    repeat_weather_request = "What is the current weather forecast for Seattle?"
    repeat_weather_intent = planner.choose(repeat_weather_request, capabilities)
    repeat_weather_result = app.route(repeat_weather_request, repeat_weather_intent)
    if (
        repeat_weather_intent.kind is not RouteKind.CAPABILITY
        or repeat_weather_intent.capability_id != "weather.lookup"
        or repeat_weather_result.status is not ResultStatus.AWAITING_CONFIRMATION
        or repeat_weather_result.suggested_capability != "weather.lookup"
    ):
        raise AssertionError(
            "Expected the successful weather route to be suggested on a later matching task; "
            f"got {repeat_weather_intent.kind.value}/{repeat_weather_result.status.value}/"
            f"{repeat_weather_result.suggested_capability or '(no suggestion)'}."
        )
    learned_weather_successes = sum(
        count
        for (_, capability_id), count in app.memory.successful_routes.items()
        if capability_id == "weather.lookup"
    )
    if learned_weather_successes != 1:
        raise AssertionError("An unconfirmed repeat task must not add another learned success.")

    missing_request = "Sort the files in my Downloads folder into folders by file type."
    missing_intent = planner.choose(missing_request, capabilities)
    missing_result = app.route(missing_request, missing_intent)
    if (
        missing_intent.kind is not RouteKind.NEEDS_CAPABILITY
        or missing_result.status is not ResultStatus.FORGE_PROPOSAL
        or len(app.forge_proposals) != 1
        or app.forge_proposals[0].status != "proposal_only"
        or app.capability_descriptions() != capabilities
    ):
        raise AssertionError(
            "Expected an unregistered action to create only a review proposal; got "
            f"{missing_intent.kind.value}/{missing_result.status.value}."
        )

    ambiguous_app = AppTree(
        [
            Capability(
                capability_id="reminders.create",
                description="Create a reminder about a future task (mock only).",
                requires_approval=True,
                executor=MockExecutor(MockOutcome(True, "Mock reminder created.")),
            ),
            Capability(
                capability_id="calendar.create_event",
                description="Schedule an appointment in a calendar (mock only).",
                requires_approval=True,
                executor=MockExecutor(MockOutcome(True, "Mock calendar event created.")),
            ),
        ]
    )
    ambiguous_request = "Make sure I don't forget about my dentist appointment tomorrow."
    ambiguous_intent = planner.choose(
        ambiguous_request,
        ambiguous_app.capability_descriptions(),
    )
    ambiguous_result = ambiguous_app.route(ambiguous_request, ambiguous_intent)
    if (
        ambiguous_intent.kind is not RouteKind.CAPABILITY
        or ambiguous_intent.capability_id not in ambiguous_app.capability_descriptions()
        or ambiguous_result.status is not ResultStatus.AWAITING_APPROVAL
        or len(ambiguous_app.pending) != 1
        or ambiguous_app.memory.successful_routes
    ):
        raise AssertionError(
            "Expected the model to choose a registered ambiguous-request candidate and stop "
            "for approval; got "
            f"{ambiguous_intent.kind.value}/{ambiguous_intent.capability_id or '(no capability)'}/"
            f"{ambiguous_result.status.value}; intent={ambiguous_intent!r}; "
            f"dispatch_message={ambiguous_result.message!r}."
        )

    return {
        "model": planner.model,
        "question_route": answer_intent.kind.value,
        "question_answer": answer_result.message,
        "weather_route": weather_intent.kind.value,
        "weather_capability": weather_result.capability_id,
        "weather_result": weather_result.message,
        "weather_test_confirmation": weather_confirmation.status.value,
        "simulated_user_confirmation": "yes, test harness explicitly confirmed success",
        "repeat_weather_suggestion": repeat_weather_result.suggested_capability,
        "repeat_weather_memory_unchanged": "yes; waiting for confirmation",
        "unsupported_action_route": missing_intent.kind.value,
        "unsupported_action_result": missing_result.status.value,
        "ambiguous_request_route": ambiguous_intent.kind.value,
        "ambiguous_request_capability": ambiguous_intent.capability_id,
        "ambiguous_request_result": ambiguous_result.status.value,
        "ambiguous_action_executed": "no; waiting for approval",
        "forge_launched": "no",
        "new_capability_created": "no",
        "executor": "fixed mock; no live weather lookup performed",
    }


if __name__ == "__main__":
    print(json.dumps(run_routing_checks(), indent=2, ensure_ascii=True))
