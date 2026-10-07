import ast
from contextlib import ExitStack
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, mock_open, patch

from app_tree_stage import MockAppTreeStage


class MockStageTests(unittest.TestCase):
    def setUp(self):
        self.stage = MockAppTreeStage()
        self.environment = patch.dict(os.environ, {
            "SARA_APP_TREE_MOCK_ENABLED": "1", "SARA_APP_TREE_MEMORY_ENABLED": "0",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def command(self, suffix):
        return self.stage.handle("app tree test " + suffix)

    def test_default_disabled_and_no_initialization(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIn("disabled", self.command("weather"))
            self.assertIsNone(self.stage._app)
        for value in ("", "0", "true", "yes"):
            with self.subTest(value=value), patch.dict(os.environ, {"SARA_APP_TREE_MOCK_ENABLED": value}):
                with patch.object(self.stage, "_create_app") as create:
                    self.assertIn("disabled", self.command("weather"))
                    create.assert_not_called()
                    self.assertIsNone(self.stage._app)

    def test_existing_memory_and_real_commands_pass_through(self):
        commands = [
            "remember note my appointment", "remember it", "don't remember it",
            "learn this the sun is a star", "what do you know about me", "forget everything",
            "approve action", "reject action", "yes", "no", "weather in boston",
            "remind me to call alex", "open notepad", "stop talking",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertIsNone(self.stage.handle(command))
        self.assertIsNone(self.stage._app)

    def test_only_explicit_worked_learns_once(self):
        self.assertIn("not live weather", self.command("weather"))
        self.assertEqual(self.stage._app.memory.successful_routes, {})
        self.assertIsNone(self.stage.handle("yes"))
        self.assertIn("Nothing was learned", self.command("not sure"))
        self.assertIn("resolve", self.command("reminder"))
        self.assertIn("learned", self.command("worked"))
        self.assertEqual(self.stage._app.memory.successful_routes[("weather", "weather.lookup")], 1)
        self.assertIn("no mock result", self.command("worked"))
        self.assertIn("weather.lookup", self.command("memory"))

    def test_approval_is_separate_from_success_confirmation(self):
        self.assertIn("Nothing has run", self.command("reminder"))
        self.assertIn("no mock result", self.command("worked"))
        self.assertIsNone(self.stage.handle("approve action"))
        self.assertEqual(self.stage._app.pending_confirmations, {})
        self.assertIn("No real reminder", self.command("approve"))
        self.assertEqual(self.stage._app.memory.successful_routes, {})
        self.assertIn("no mock action", self.command("approve"))
        self.assertIn("nothing was learned", self.command("failed"))
        self.assertEqual(self.stage._app.memory.successful_routes, {})

    def test_reject_failure_and_proposal_do_not_learn(self):
        self.command("reminder")
        self.command("reject")
        self.assertEqual(self.stage._app.pending_confirmations, {})
        self.assertIn("failed", self.command("failure"))
        self.assertIn("Forge was not launched", self.command("missing app"))
        self.assertEqual(self.stage._app.forge_proposals[0].status, "proposal_only")
        self.assertEqual(self.stage._app.memory.successful_routes, {})

    def test_reset_and_disable_discard_test_session(self):
        self.command("weather")
        self.command("worked")
        self.command("reminder")
        self.command("reset")
        self.assertIsNone(self.stage._app)
        self.assertIsNone(self.stage._result)
        self.command("weather")
        with patch.dict(os.environ, {"SARA_APP_TREE_MOCK_ENABLED": "0"}):
            self.command("worked")
        self.assertIsNone(self.stage._app)
        self.assertIsNone(self.stage._result)

    def test_invalid_command_is_explicit_and_does_not_create_session(self):
        self.assertIn("not a supported", self.command("delete files"))
        self.assertIsNone(self.stage._app)

    def test_exact_prefix_aliases_support_explicit_commands(self):
        for prefix in ("app tree", "apptree", "app-tree"):
            with self.subTest(prefix=prefix):
                stage = MockAppTreeStage()
                self.assertIn("mock app-tree stage", stage.handle(f"{prefix} test help"))
                self.assertIn("not live weather", stage.handle(f"{prefix} test weather"))
                self.assertEqual(stage._app.memory.successful_routes, {})
                stage.handle(f"{prefix} test worked")
                self.assertEqual(stage._app.memory.successful_routes[("weather", "weather.lookup")], 1)
                stage.handle(f"{prefix} test reset")
                stage.handle(f"{prefix} test reminder")
                self.assertEqual(stage._app.pending_confirmations, {})
                stage.handle(f"{prefix} test approve")
                self.assertTrue(stage._app.pending_confirmations)
                self.assertEqual(stage._app.memory.successful_routes, {})

    def test_incomplete_or_misrecognized_commands_do_not_change_pending_decisions(self):
        self.command("reminder")
        approval = self.stage._result
        for command in (
            "app tree help", "apptree approve", "app-tree worked",
            "apptree test whether failed", "apptree test approved",
            "apptree test worked please", "app tree testing approve",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(self.stage.handle(command))
                self.assertIs(self.stage._result, approval)
                self.assertTrue(self.stage._app.pending)
                self.assertEqual(self.stage._app.pending_confirmations, {})
                self.assertEqual(self.stage._app.memory.successful_routes, {})
        self.command("approve")
        for command in ("apptree worked", "apptree test work", "apptree test whether failed"):
            self.assertIsNotNone(self.stage.handle(command))
            self.assertTrue(self.stage._app.pending_confirmations)
            self.assertEqual(self.stage._app.memory.successful_routes, {})

    def test_aliases_remain_disabled_and_prefix_boundaries_are_exact(self):
        with patch.dict(os.environ, {"SARA_APP_TREE_MOCK_ENABLED": "0"}):
            for command in ("apptree test weather", "app-tree test approve", "app tree help"):
                self.assertIn("disabled", self.stage.handle(command))
                self.assertIsNone(self.stage._app)
        for command in ("apptrees test help", "app treehouse test weather",
                        "tell me about app tree", "application tree test approve"):
            self.assertIsNone(self.stage.handle(command))

    def test_adapter_has_no_live_app_or_memory_dependencies(self):
        tree = ast.parse(Path(__file__).with_name("app_tree_stage.py").read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module)
        self.assertEqual(imports, {
            "__future__", "os", "datetime", "typing", "experiments.app_tree_prototype",
            "experiments.ollama_app_tree_check", "mock_workflow_memory",
        })

    def test_natural_answer_uses_existing_conversation_handler_not_planner_text(self):
        from experiments.app_tree_prototype import Intent, RouteKind
        answerer = Mock(return_value="SARA's personalised reply.")
        with patch("experiments.ollama_app_tree_check.LocalOllamaPlanner") as planner:
            planner.return_value.choose.return_value = Intent(RouteKind.ANSWER, "knowledge", answer="Not SARA's reply.")
            reply = self.stage.handle("app tree test ask explain photosynthesis", answerer=answerer)
        self.assertEqual(reply, "SARA's personalised reply.")
        answerer.assert_called_once_with("explain photosynthesis")
        self.assertEqual(self.stage._app.memory.successful_routes, {})

    def test_natural_reminder_requires_approval_then_success_confirmation(self):
        from experiments.app_tree_prototype import Intent, RouteKind
        with patch("experiments.ollama_app_tree_check.LocalOllamaPlanner") as planner:
            planner.return_value.choose.return_value = Intent(RouteKind.CAPABILITY, "reminder", capability_id="reminders.create")
            planner.return_value.last_attempt_count = 2
            reply = self.command("ask remind me to buy milk friday")
            self.assertIn("buy milk friday", reply)
            self.assertIn("validated repair", reply)
            self.assertEqual(self.stage._app.pending_confirmations, {})
            self.assertIn("resolve", self.command("ask another task"))
            planner.return_value.choose.assert_called_once()
        self.command("approve")
        self.assertEqual(self.stage._app.memory.successful_routes, {})
        self.command("worked")
        self.assertEqual(self.stage._app.memory.successful_routes[("reminder", "reminders.create")], 1)

    def test_natural_missing_capability_stays_proposal_only(self):
        from experiments.app_tree_prototype import Intent, RouteKind
        with patch("experiments.ollama_app_tree_check.LocalOllamaPlanner") as planner:
            planner.return_value.choose.return_value = Intent(
                RouteKind.NEEDS_CAPABILITY, "files", capability_request="File sorting proposal",
            )
            self.assertIn("Forge was not launched", self.command("ask sort my downloads"))
        self.assertEqual(self.stage._app.forge_proposals[0].status, "proposal_only")
        self.assertEqual(self.stage._app.memory.successful_routes, {})

    def test_natural_model_failure_does_not_execute_or_learn(self):
        with patch("experiments.ollama_app_tree_check.LocalOllamaPlanner") as planner:
            planner.return_value.choose.side_effect = RuntimeError("invalid after two attempts")
            self.assertIn("failed safely", self.command("ask check weather"))
        self.assertEqual(self.stage._app.pending, {})
        self.assertEqual(self.stage._app.pending_confirmations, {})
        self.assertEqual(self.stage._app.memory.successful_routes, {})

    def test_disabled_natural_request_never_calls_model(self):
        with patch.dict(os.environ, {"SARA_APP_TREE_MOCK_ENABLED": "0"}):
            with patch("experiments.ollama_app_tree_check.LocalOllamaPlanner") as planner:
                self.assertIn("disabled", self.command("ask check weather"))
                planner.assert_not_called()

    def test_clock_question_including_logged_typo_uses_actual_clock_not_model(self):
        from datetime import datetime, timezone
        for request in ("what time is it", "waht time is it", "what's the time?"):
            with self.subTest(request=request), \
                 patch("app_tree_stage.datetime") as clock, \
                 patch("experiments.ollama_app_tree_check.LocalOllamaPlanner") as planner:
                clock.now.return_value.astimezone.return_value = datetime(
                    2026, 10, 7, 11, 20, tzinfo=timezone.utc,
                )
                reply = self.command("ask " + request)
                self.assertIn("11:20 AM UTC", reply)
                planner.assert_not_called()
                self.assertEqual(self.stage._app.memory.successful_routes, {})
                self.assertEqual(self.stage._app.pending_confirmations, {})

    def test_clock_request_does_not_override_pending_decision(self):
        self.command("reminder")
        self.assertIn("resolve", self.command("ask what time is it"))
        self.assertTrue(self.stage._app.pending)
        self.assertEqual(self.stage._app.memory.successful_routes, {})

    def test_natural_answer_does_not_replace_missing_persona_handler(self):
        from experiments.app_tree_prototype import Intent, RouteKind
        with patch("experiments.ollama_app_tree_check.LocalOllamaPlanner") as planner:
            planner.return_value.choose.return_value = Intent(RouteKind.ANSWER, "knowledge", answer="Planner text")
            self.assertIn("unavailable", self.command("ask what is photosynthesis"))
        self.assertIsNone(self.stage._result)


class CommandLoopIntegrationTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"SARA_APP_TREE_MEMORY_ENABLED": "0"})
        environment.start()
        self.addCleanup(environment.stop)

    def run_command(self, text, enabled):
        import co_brain

        file = mock_open(read_data=text)
        file.return_value.read.side_effect = [text, KeyboardInterrupt()]
        stage = MockAppTreeStage()
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"SARA_APP_TREE_MOCK_ENABLED": "1" if enabled else "0"}))
            stack.enter_context(patch("builtins.open", file))
            stack.enter_context(patch.object(co_brain, "handle_mock_app_tree_command", side_effect=stage.handle))
            calls = {}
            for name in (
                "resolve_learning_request", "consume_approval", "handle_task_command",
                "handle_system_command", "handle_tool_command", "handle_extension_command",
                "run_registered_tool", "handle_project_command", "handle_forge_command",
                "_pop_tool_offer", "pop_capability_gap", "observe_user_detail",
                "route_registered_tool_request",
            ):
                calls[name] = stack.enter_context(patch.object(co_brain, name, return_value=None))
            stack.enter_context(patch.object(co_brain, "requires_confirmation", return_value=False))
            stack.enter_context(patch.object(co_brain, "should_propose_extension", return_value=False))
            stack.enter_context(patch.object(co_brain, "set_voice_state"))
            stack.enter_context(patch.object(co_brain, "_extend_follow_up_window"))
            stack.enter_context(patch.object(co_brain, "clear_file"))
            calls["speak"] = stack.enter_context(patch.object(co_brain, "speak"))
            calls["remember_note"] = stack.enter_context(patch.object(co_brain, "remember_note"))
            calls["Main_Brain"] = stack.enter_context(patch.object(co_brain, "Main_Brain", return_value="Normal reply."))
            stack.enter_context(patch.object(
                co_brain, "route_conversation_request", side_effect=lambda request, answerer: answerer(request),
            ))
            with self.assertRaises(KeyboardInterrupt):
                co_brain.check_inputs()
        return calls, file

    def test_mock_command_uses_existing_speech_and_feed_not_real_workflows(self):
        calls, file = self.run_command("sara app tree test reminder", True)
        self.assertIn("Mock reminder", calls["speak"].call_args.args[0])
        self.assertTrue(file.return_value.write.called)
        for name, call in calls.items():
            if name not in {"speak"}:
                call.assert_not_called()

    def test_disabled_mock_command_does_not_fall_through_to_real_routes(self):
        calls, _ = self.run_command("sara app tree test reminder", False)
        self.assertIn("disabled", calls["speak"].call_args.args[0])
        calls["handle_forge_command"].assert_not_called()
        calls["Main_Brain"].assert_not_called()

    def test_logged_recognition_variants_never_reach_the_model(self):
        for command, expected in (
            ("app tree help", "Real app tree"),
            ("apptree test help", "mock app-tree stage"),
            ("apptree test whether failed", "not a supported mock command"),
        ):
            with self.subTest(command=command):
                calls, _ = self.run_command("sara " + command, True)
                self.assertIn(expected, calls["speak"].call_args.args[0])
                calls["Main_Brain"].assert_not_called()
                calls["handle_forge_command"].assert_not_called()
                calls["resolve_learning_request"].assert_not_called()

    def test_existing_note_command_is_preserved_when_enabled(self):
        calls, _ = self.run_command("sara remember note my meeting is friday", True)
        calls["remember_note"].assert_called_once_with("my meeting is friday")
        calls["Main_Brain"].assert_not_called()

    def test_natural_answer_reaches_existing_brain_and_speech_feed(self):
        from experiments.app_tree_prototype import Intent, RouteKind
        with patch("experiments.ollama_app_tree_check.LocalOllamaPlanner") as planner:
            planner.return_value.choose.return_value = Intent(RouteKind.ANSWER, "knowledge", answer="Discard this")
            calls, file = self.run_command("sara apptree test ask explain photosynthesis", True)
        calls["Main_Brain"].assert_called_once_with("explain photosynthesis")
        calls["speak"].assert_called_once_with("Normal reply.")
        self.assertTrue(file.return_value.write.called)
        calls["handle_forge_command"].assert_not_called()

    def test_normal_conversation_stays_on_existing_persona_path(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                calls, _ = self.run_command("sara tell me about your functions", enabled)
                calls["Main_Brain"].assert_called_once_with("tell me about your functions")
                calls["speak"].assert_called_once_with("Normal reply.")

    def test_log_failure_is_reported_without_suppressing_the_test_result(self):
        import co_brain

        file = mock_open(read_data="sara app tree test weather")
        file.return_value.read.side_effect = ["sara app tree test weather", KeyboardInterrupt()]
        stage = MockAppTreeStage()

        def open_file(path, mode, **kwargs):
            if mode == "a":
                raise OSError("test log unavailable")
            return file()

        with patch.dict(os.environ, {"SARA_APP_TREE_MOCK_ENABLED": "1"}), \
             patch("builtins.open", side_effect=open_file), \
             patch.object(co_brain, "handle_mock_app_tree_command", side_effect=stage.handle), \
             patch.object(co_brain, "speak") as speak, \
             patch.object(co_brain, "set_voice_state"), \
             patch.object(co_brain, "_extend_follow_up_window"):
            with self.assertRaises(KeyboardInterrupt):
                co_brain.check_inputs()
        self.assertIn("could not update the HUD", speak.call_args_list[0].args[0])
        self.assertIn("Mock forecast", speak.call_args_list[1].args[0])
        self.assertEqual(stage._app.memory.successful_routes, {})


if __name__ == "__main__":
    unittest.main()
