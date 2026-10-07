import unittest
from unittest.mock import patch

import Brain.brain as brain


class ConversationClaimTests(unittest.TestCase):
    def tearDown(self):
        brain.reset_conversation()

    def test_logged_false_completion_and_notification_claims_are_blocked(self):
        for answer in (
            "I've added a reminder for you to call Alex tomorrow.",
            "I've sorted your downloads by file type.",
            "I'll also send a notification to your phone.",
            "I have successfully sent your message.",
        ):
            with self.subTest(answer=answer), patch.object(brain, "_ask_llm", return_value=answer), \
                 patch.object(brain, "search_web", return_value=[]):
                result = brain.Main_Brain("remind me to call alex tomorrow")
                self.assertIn("no verified tool result", result)
                self.assertNotIn(answer, result)
                self.assertEqual(brain._conversation_history[-1]["content"], result)

    def test_explanations_and_honest_nonexecution_are_preserved(self):
        for answer in (
            "Photosynthesis converts light energy into chemical energy.",
            "You can sort files into folders by type.",
            "I have not created a reminder.",
            "I can explain how reminders work.",
        ):
            self.assertEqual(brain._guard_conversation_answer(answer), answer)


if __name__ == "__main__":
    unittest.main()
