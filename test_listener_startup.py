import unittest
from unittest.mock import Mock, patch

from NetHyTechSTT import listen as listener


class ListenerStartupTests(unittest.TestCase):
    def test_driver_uses_selenium_manager_and_cleans_up_failed_navigation(self):
        browser = Mock()
        browser.get.side_effect = RuntimeError("Navigation failed")
        with patch.object(listener.webdriver, "Chrome", return_value=browser) as chrome:
            with self.assertRaisesRegex(RuntimeError, "Navigation failed"):
                listener.create_driver()
        self.assertNotIn("service", chrome.call_args.kwargs)
        browser.set_page_load_timeout.assert_called_once_with(30)
        browser.quit.assert_called_once()

    def test_startup_failure_never_claims_listening(self):
        with patch.object(listener, "create_driver", side_effect=RuntimeError("Driver failed")), patch.object(listener, "set_voice_state") as state:
            listener.listen()
        self.assertEqual([call.args[0] for call in state.call_args_list], ["STARTING", "MIC_ERROR"])

    def test_listening_is_published_after_start_button(self):
        events = []
        browser = Mock()
        button = Mock()
        button.click.side_effect = lambda: events.append("clicked")
        wait = Mock()
        wait.until.side_effect = [button, KeyboardInterrupt()]
        with (
            patch.object(listener, "create_driver", return_value=browser),
            patch.object(listener, "WebDriverWait", return_value=wait),
            patch.object(listener, "set_voice_state", side_effect=lambda state: events.append(state)),
        ):
            listener.listen()
        self.assertEqual(events, ["STARTING", "clicked", "LISTENING", "IDLE"])
        browser.quit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
