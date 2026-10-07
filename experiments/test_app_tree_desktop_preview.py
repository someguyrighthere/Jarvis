import unittest
import tkinter as tk

from app_tree_desktop_preview import DesktopPreview, PreviewSession
from app_tree_prototype import ResultStatus


class PreviewSessionTests(unittest.TestCase):
    def setUp(self):
        self.session = PreviewSession()

    def test_yes_learns_once_and_suggests_the_confirmed_route(self):
        self.session.start("Weather (mock)")
        self.assertEqual(self.session.app.memory.successful_routes, {})
        self.session.confirm(True)
        with self.assertRaises(ValueError):
            self.session.confirm(True)
        result = self.session.start("Weather (mock)")
        self.assertEqual(result.suggested_capability, "weather.lookup")
        self.assertEqual(self.session.app.memory.successful_routes[("weather", "weather.lookup")], 1)

    def test_no_does_not_learn(self):
        self.session.start("Weather (mock)")
        self.session.confirm(False)
        self.assertEqual(self.session.result.status, ResultStatus.NOT_CONFIRMED)
        self.assertEqual(self.session.app.memory.successful_routes, {})
        self.assertEqual(self.session.app.pending_confirmations, {})

    def test_unsure_remains_pending_and_can_be_confirmed_later(self):
        result = self.session.start("Weather (mock)")
        self.assertIn("Nothing was learned", self.session.confirm(None))
        self.assertEqual(self.session.app.memory.successful_routes, {})
        self.assertIn(result.confirmation_id, self.session.app.pending_confirmations)
        with self.assertRaises(ValueError):
            self.session.start("Reminder (approval)")
        self.session.confirm(True)
        self.assertTrue(self.session.app.memory.successful_routes)

    def test_reject_prevents_execution_and_learning(self):
        self.session.start("Reminder (approval)")
        with self.assertRaises(ValueError):
            self.session.confirm(True)
        self.session.approve(False)
        self.assertEqual(self.session.app.pending_confirmations, {})
        self.assertEqual(self.session.app.memory.successful_routes, {})
        self.assertEqual(self.session.result.status, ResultStatus.REJECTED)

    def test_approval_does_not_mean_success_confirmation(self):
        self.session.start("Reminder (approval)")
        self.assertEqual(self.session.app.pending_confirmations, {})
        result = self.session.approve(True)
        self.assertEqual(result.status, ResultStatus.AWAITING_CONFIRMATION)
        self.assertEqual(self.session.app.memory.successful_routes, {})
        with self.assertRaises(ValueError):
            self.session.approve(True)
        self.session.confirm(True)
        self.assertEqual(self.session.app.memory.successful_routes[("reminder", "reminders.create")], 1)

    def test_failed_app_cannot_be_confirmed(self):
        result = self.session.start("Failed weather (mock)")
        self.assertEqual(result.status, ResultStatus.REJECTED)
        with self.assertRaises(ValueError):
            self.session.confirm(True)
        self.assertEqual(self.session.app.memory.successful_routes, {})

    def test_missing_app_stays_proposal_only(self):
        result = self.session.start("Missing app (proposal only)")
        self.assertEqual(result.status, ResultStatus.FORGE_PROPOSAL)
        self.assertEqual(self.session.app.forge_proposals[0].status, "proposal_only")
        self.assertEqual(self.session.app.memory.successful_routes, {})
        self.assertNotIn("file.organizer", self.session.app.capability_descriptions())

    def test_new_session_does_not_share_memory_or_pending_decisions(self):
        self.session.start("Weather (mock)")
        self.session.confirm(True)
        self.session.start("Reminder (approval)")
        fresh = PreviewSession()
        self.assertEqual(fresh.app.memory.successful_routes, {})
        self.assertEqual(fresh.app.pending, {})
        self.assertEqual(fresh.app.pending_confirmations, {})
        self.assertEqual(fresh.app.forge_proposals, [])


class DesktopWidgetTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.preview = DesktopPreview(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        self.root.destroy()

    def test_weather_buttons_and_reset(self):
        ui = self.preview
        self.assertTrue(ui.yes_button.instate(["disabled"]))
        ui.start_button.invoke()
        self.assertTrue(ui.start_button.instate(["disabled"]))
        self.assertTrue(ui.approve_button.instate(["disabled"]))
        self.assertFalse(ui.yes_button.instate(["disabled"]))
        ui.unsure_button.invoke()
        self.assertEqual(ui.session.app.memory.successful_routes, {})
        self.assertFalse(ui.yes_button.instate(["disabled"]))
        ui.yes_button.invoke()
        self.assertIn("confirmed 1 time(s)", ui.memory.get())
        self.assertTrue(ui.yes_button.instate(["disabled"]))
        ui.reset()
        self.assertEqual(ui.memory.get(), "Learned workflows: none.")
        self.assertFalse(ui.start_button.instate(["disabled"]))

    def test_reminder_buttons_require_approval_then_confirmation(self):
        ui = self.preview
        ui.scenario.set("Reminder (approval)")
        ui.start_button.invoke()
        self.assertFalse(ui.approve_button.instate(["disabled"]))
        self.assertTrue(ui.yes_button.instate(["disabled"]))
        ui.approve_button.invoke()
        self.assertTrue(ui.approve_button.instate(["disabled"]))
        self.assertFalse(ui.yes_button.instate(["disabled"]))
        self.assertEqual(ui.session.app.memory.successful_routes, {})
        ui.no_button.invoke()
        self.assertEqual(ui.session.app.memory.successful_routes, {})
        self.assertFalse(ui.start_button.instate(["disabled"]))

    def test_reset_discards_unanswered_confirmation(self):
        ui = self.preview
        ui.start_button.invoke()
        ui.unsure_button.invoke()
        self.assertTrue(ui.session.app.pending_confirmations)
        ui.reset()
        self.assertEqual(ui.session.app.pending_confirmations, {})
        self.assertEqual(ui.session.app.memory.successful_routes, {})
        self.assertTrue(ui.yes_button.instate(["disabled"]))


if __name__ == "__main__":
    unittest.main()
