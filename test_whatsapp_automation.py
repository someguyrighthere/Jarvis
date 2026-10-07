import unittest
from unittest.mock import call, patch

from Whatsapp_automation import wa


class WhatsAppAutomationTests(unittest.TestCase):
    def test_message_is_previewed_and_only_sent_after_explicit_confirmation(self):
        with (
            patch.object(
                wa,
                "_read_input",
                side_effect=["", "send to anubhav.", "send to anubhav.", "message is hello there",
                             "message is hello there", "confirm send."],
            ),
            patch.object(wa, "speak") as speak,
            patch.object(wa.kit, "sendwhatmsg") as send_message,
        ):
            wa.send_msg_wa()

        send_message.assert_called_once()
        self.assertEqual(send_message.call_args.args[:2], ("+919606348280", "hello there"))
        self.assertTrue(any("Review the message" in item.args[0] for item in speak.call_args_list))

    def test_unknown_contact_and_cancel_never_send(self):
        with (
            patch.object(wa, "_read_input", side_effect=["", "send to someone else"]),
            patch.object(wa, "speak"),
            patch.object(wa.kit, "sendwhatmsg") as send_message,
        ):
            wa.send_msg_wa()
        send_message.assert_not_called()

        with (
            patch.object(wa, "_read_input", side_effect=["", "cancel message"]),
            patch.object(wa, "speak"),
            patch.object(wa.kit, "sendwhatmsg") as send_message,
        ):
            wa.send_msg_wa()
        send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
