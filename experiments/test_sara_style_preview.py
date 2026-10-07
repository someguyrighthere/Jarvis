import tkinter as tk
import unittest

from sara_style_preview import SaraStylePreview


class SaraStylePreviewTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.ui = SaraStylePreview(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        self.ui.close()

    def test_stop_preserves_approval_and_resume_does_not_approve(self):
        ui = self.ui
        ui.scenario.set("Reminder (approval)")
        ui.start_button.invoke()
        ui.stop_button.invoke()
        ui.approve_button.invoke()
        self.assertTrue(ui.session.awaiting_approval)
        self.assertEqual(ui.session.app.memory.successful_routes, {})
        self.assertEqual(ui.session.app.pending_confirmations, {})
        ui.resume_button.invoke()
        self.assertTrue(ui.session.awaiting_approval)
        ui.approve_button.invoke()
        self.assertTrue(ui.session.awaiting_confirmation)
        self.assertEqual(ui.session.app.memory.successful_routes, {})

    def test_stop_preserves_confirmation_and_no_does_not_learn(self):
        ui = self.ui
        ui.start_button.invoke()
        ui.stop_button.invoke()
        ui.yes_button.invoke()
        self.assertEqual(ui.session.app.memory.successful_routes, {})
        ui.resume_button.invoke()
        ui.unsure_button.invoke()
        self.assertTrue(ui.session.awaiting_confirmation)
        ui.no_button.invoke()
        self.assertEqual(ui.session.app.memory.successful_routes, {})

    def test_yes_and_reset_use_existing_learning_rules(self):
        ui = self.ui
        ui.start_button.invoke()
        ui.yes_button.invoke()
        self.assertIn("confirmed 1 time(s)", ui.memory.get())
        ui.reset()
        self.assertEqual(ui.session.app.memory.successful_routes, {})
        self.assertEqual(ui.session.app.pending_confirmations, {})

    def test_resizing_and_animation_leave_session_unchanged(self):
        ui = self.ui
        for width, height in ((900, 780), (1200, 900)):
            self.root.geometry(f"{width}x{height}")
            self.root.update_idletasks()
            ui.draw_core()
            self.assertTrue(ui.core.find_all())
        self.assertEqual(ui.session.app.memory.successful_routes, {})
        self.assertEqual(ui.session.app.pending, {})
        self.assertEqual(ui.session.app.pending_confirmations, {})

    def test_failure_and_proposal_are_honest_and_unlearned(self):
        ui = self.ui
        ui.scenario.set("Missing app (proposal only)")
        ui.start_button.invoke()
        self.assertIn("Downloads have not been accessed", ui.history.get("1.0", "end"))
        ui.scenario.set("Failed weather (mock)")
        ui.start_button.invoke()
        self.assertIn("could not complete", ui.history.get("1.0", "end"))
        self.assertEqual(ui.session.app.memory.successful_routes, {})
        self.assertTrue(ui.yes_button.instate(["disabled"]))


if __name__ == "__main__":
    unittest.main()
