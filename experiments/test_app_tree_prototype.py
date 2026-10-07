import unittest
import ast
from pathlib import Path

from app_tree_prototype import (
    AppTree,
    Capability,
    Intent,
    MockExecutor,
    MockOutcome,
    ResultStatus,
    RouteKind,
)


def mock_app(capability_id, *, requires_approval=False, success=True):
    return Capability(
        capability_id=capability_id,
        description=f"Mock capability {capability_id}",
        requires_approval=requires_approval,
        executor=MockExecutor(MockOutcome(success, f"Mock result from {capability_id}")),
    )


class DeterministicMockOllama:
    """Reproducible planner fixture; it never connects to an Ollama server."""

    def choose(self, request, available_capabilities):
        if "weather" in request.casefold() and "weather.lookup" in available_capabilities:
            return Intent(
                RouteKind.CAPABILITY,
                task_type="weather",
                capability_id="weather.lookup",
            )
        return Intent(
            RouteKind.ANSWER,
            task_type="general question",
            answer="Mock Ollama answer.",
        )


class AppTreePrototypeTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTree([
            mock_app("weather.lookup"),
            mock_app("system.volume", requires_approval=True),
        ])

    def test_question_can_be_answered_without_running_a_capability(self):
        result = self.app.route(
            "What is two plus two?",
            Intent(RouteKind.ANSWER, task_type="calculation", answer="Four."),
        )
        self.assertEqual(result.status, ResultStatus.ANSWERED)
        self.assertEqual(result.message, "Four.")
        self.assertEqual(self.app.memory.successful_routes, {})

    def test_mock_ollama_selects_answer_or_registered_mock_app(self):
        planner = DeterministicMockOllama()
        available = self.app.capability_descriptions()

        answer = self.app.route(
            "What is two plus two?",
            planner.choose("What is two plus two?", available),
        )
        weather = self.app.route(
            "What is the weather?",
            planner.choose("What is the weather?", available),
        )

        self.assertEqual(answer.status, ResultStatus.ANSWERED)
        self.assertEqual(answer.message, "Mock Ollama answer.")
        self.assertEqual(weather.status, ResultStatus.AWAITING_CONFIRMATION)
        self.assertEqual(weather.capability_id, "weather.lookup")
        self.assertIn("Did this work as expected?", weather.message)
        self.assertEqual(self.app.memory.successful_routes, {})

    def test_registry_route_is_learned_only_after_explicit_confirmation(self):
        result = self.app.route(
            "What is the weather?",
            Intent(RouteKind.CAPABILITY, task_type="weather", capability_id="weather.lookup"),
        )
        self.assertEqual(result.status, ResultStatus.AWAITING_CONFIRMATION)
        self.assertEqual(self.app.memory.successful_routes, {})

        confirmed = self.app.confirm_success(result.confirmation_id, True)
        self.assertEqual(confirmed.status, ResultStatus.SUCCESS_CONFIRMED)
        self.assertEqual(
            self.app.memory.preferred_capability("weather", {"weather.lookup"}),
            "weather.lookup",
        )

    def test_no_response_does_not_learn_the_successful_route(self):
        result = self.app.route(
            "What is the weather?",
            Intent(RouteKind.CAPABILITY, task_type="weather", capability_id="weather.lookup"),
        )
        self.assertEqual(result.status, ResultStatus.AWAITING_CONFIRMATION)
        self.assertEqual(self.app.memory.successful_routes, {})
        self.assertIn(result.confirmation_id, self.app.pending_confirmations)

    def test_user_saying_it_did_not_work_does_not_learn(self):
        result = self.app.route(
            "What is the weather?",
            Intent(RouteKind.CAPABILITY, task_type="weather", capability_id="weather.lookup"),
        )
        not_confirmed = self.app.confirm_success(result.confirmation_id, False)
        self.assertEqual(not_confirmed.status, ResultStatus.NOT_CONFIRMED)
        self.assertEqual(self.app.memory.successful_routes, {})
        self.assertNotIn(result.confirmation_id, self.app.pending_confirmations)

    def test_success_confirmation_is_one_time_and_requires_a_boolean(self):
        result = self.app.route(
            "What is the weather?",
            Intent(RouteKind.CAPABILITY, task_type="weather", capability_id="weather.lookup"),
        )
        invalid = self.app.confirm_success(result.confirmation_id, "yes")
        self.assertEqual(invalid.status, ResultStatus.REJECTED)
        self.assertIn(result.confirmation_id, self.app.pending_confirmations)

        confirmed = self.app.confirm_success(result.confirmation_id, True)
        replayed = self.app.confirm_success(result.confirmation_id, True)
        self.assertEqual(confirmed.status, ResultStatus.SUCCESS_CONFIRMED)
        self.assertEqual(replayed.status, ResultStatus.REJECTED)
        self.assertEqual(
            self.app.memory.successful_routes[("weather", "weather.lookup")],
            1,
        )

    def test_failed_capability_is_not_learned(self):
        self.app = AppTree([mock_app("weather.lookup", success=False)])
        result = self.app.route(
            "What is the weather?",
            Intent(RouteKind.CAPABILITY, task_type="weather", capability_id="weather.lookup"),
        )
        self.assertEqual(result.status, ResultStatus.REJECTED)
        self.assertEqual(self.app.memory.successful_routes, {})

    def test_side_effect_waits_for_explicit_one_time_approval(self):
        result = self.app.route(
            "Set volume to 30 percent",
            Intent(RouteKind.CAPABILITY, task_type="volume", capability_id="system.volume"),
        )
        self.assertEqual(result.status, ResultStatus.AWAITING_APPROVAL)
        self.assertEqual(self.app.memory.successful_routes, {})
        completed = self.app.approve(result.approval_id)
        self.assertEqual(completed.status, ResultStatus.AWAITING_CONFIRMATION)
        self.assertEqual(self.app.memory.successful_routes, {})
        self.assertEqual(self.app.approve(result.approval_id).status, ResultStatus.REJECTED)
        self.assertEqual(
            self.app.confirm_success(completed.confirmation_id, True).status,
            ResultStatus.SUCCESS_CONFIRMED,
        )

    def test_rejected_action_is_not_executed_or_learned(self):
        result = self.app.route(
            "Set volume to 30 percent",
            Intent(RouteKind.CAPABILITY, task_type="volume", capability_id="system.volume"),
        )
        rejected = self.app.reject(result.approval_id)
        self.assertEqual(rejected.status, ResultStatus.REJECTED)
        self.assertEqual(self.app.memory.successful_routes, {})
        self.assertEqual(self.app.approve(result.approval_id).status, ResultStatus.REJECTED)

    def test_success_memory_can_suggest_an_available_previously_successful_app(self):
        first_result = self.app.route(
            "What is the weather?",
            Intent(RouteKind.CAPABILITY, task_type="weather", capability_id="weather.lookup"),
        )
        self.app.confirm_success(first_result.confirmation_id, True)
        result = self.app.route(
            "Weather tomorrow?",
            Intent(RouteKind.CAPABILITY, task_type="weather", capability_id="weather.lookup"),
        )
        self.assertEqual(result.suggested_capability, "weather.lookup")

    def test_unknown_capability_is_fail_closed(self):
        result = self.app.route(
            "Do an unknown thing",
            Intent(RouteKind.CAPABILITY, task_type="unknown", capability_id="not.registered"),
        )
        self.assertEqual(result.status, ResultStatus.REJECTED)
        self.assertEqual(self.app.memory.successful_routes, {})

    def test_missing_capability_creates_review_proposal_not_a_forge_run(self):
        result = self.app.route(
            "Help me sort my photo library",
            Intent(
                RouteKind.NEEDS_CAPABILITY,
                task_type="photo organization",
                capability_request="Propose a photo organization capability",
            ),
        )
        self.assertEqual(result.status, ResultStatus.FORGE_PROPOSAL)
        self.assertEqual(len(self.app.forge_proposals), 1)
        self.assertEqual(self.app.forge_proposals[0].status, "proposal_only")
        self.assertNotIn("photo.organizer", self.app.capability_descriptions())

    def test_real_executor_cannot_be_registered(self):
        with self.assertRaisesRegex(TypeError, "MockExecutor"):
            AppTree([
                Capability("unsafe", "Not allowed", False, executor=lambda _: "ran"),
            ])

    def test_capability_registry_is_read_only_to_callers(self):
        descriptions = self.app.capability_descriptions()
        descriptions["weather.lookup"] = "tampered"
        self.assertEqual(self.app.capability_descriptions()["weather.lookup"], "Mock capability weather.lookup")

    def test_prototype_module_imports_no_sara_or_external_runtime_modules(self):
        source_path = Path(__file__).with_name("app_tree_prototype.py")
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported_roots = {
            node.names[0].name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
        }
        imported_roots.update(
            node.module.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        self.assertLessEqual(imported_roots, {"__future__", "dataclasses", "enum", "re", "uuid"})


if __name__ == "__main__":
    unittest.main()
