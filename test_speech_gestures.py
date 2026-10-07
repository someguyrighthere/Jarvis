import unittest

from speech_gestures import plan_gestures


class SpeechGestureTests(unittest.TestCase):
    def test_intents_select_distinct_gestures(self):
        for text, kind in (("Hello, welcome back.", "greeting"),
                           ("Perhaps this might work.", "uncertainty"),
                           ("Remember to save your work.", "emphasis"),
                           ("Because this is how it works.", "explanation")):
            self.assertEqual(plan_gestures(text, 5)[0]["kind"], kind)

    def test_phases_gaps_and_bounds(self):
        text = "Hello. " + "word " * 20 + "Important. " + "word " * 20 + "Because this works."
        events = plan_gestures(text, 24)
        self.assertTrue({"greeting", "emphasis", "explanation"}.issubset({e["kind"] for e in events}))
        for event in events:
            self.assertGreaterEqual(event["start"], 0)
            self.assertLessEqual(event["start"] + event["duration"], 24.001)
            self.assertAlmostEqual(sum(event[key] for key in ("prepare", "stroke", "hold", "recover")),
                                   event["duration"], places=3)
            self.assertGreater(event["recover"], event["stroke"])
        for first, second in zip(events, events[1:]):
            self.assertGreaterEqual(second["start"] - first["start"] - first["duration"], 0.119)

    def test_short_or_empty_speech_does_not_wave(self):
        self.assertEqual(plan_gestures("", 4), [])
        self.assertEqual(plan_gestures("Hi", 0.5), [])
        self.assertEqual(plan_gestures("silent text", 4, [0] * 100), [])
        short = plan_gestures("Hello there.", 1.2)
        self.assertEqual(len(short), 1)
        self.assertLessEqual(short[0]["start"] + short[0]["duration"], 1.2)

    def test_long_response_uses_small_beats_and_dominant_hand_groups(self):
        events = plan_gestures("ordinary words " * 30, 20)
        self.assertGreaterEqual(len(events), 5)
        self.assertEqual({event["kind"] for event in events}, {"beat"})
        self.assertEqual(events[0]["side"], events[1]["side"])
        self.assertNotEqual(events[1]["side"], events[2]["side"])
        self.assertIn("link_next", events[0])
        self.assertTrue(events[1]["linked"])
        self.assertGreater(len({event["duration"] for event in events}), 1)
        long_events = plan_gestures("ordinary words " * 300, 180)
        self.assertEqual(len(long_events), 12)
        self.assertGreater(long_events[-1]["start"] + long_events[-1]["duration"], 177)

    def test_stroke_tracks_nearby_audio_accent(self):
        text = "Some ordinary words here. Remember this useful detail."
        baseline = next(e for e in plan_gestures(text, 8) if e["kind"] == "emphasis")
        predicted = baseline["start"] + baseline["prepare"] + baseline["stroke"] / 2
        peak = round((predicted + 0.16) / 0.04)
        levels = [0.15] * 200
        levels[peak] = 1
        event = next(e for e in plan_gestures(text, 8, levels) if e["kind"] == "emphasis")
        actual = event["start"] + event["prepare"] + event["stroke"] / 2
        self.assertAlmostEqual(actual, peak * 0.04, places=3)
        self.assertLess(event["start"], actual)

    def test_phrase_punctuation_changes_timing(self):
        plain = plan_gestures("These ordinary words describe a useful detail today", 8)
        phrased = plan_gestures("These ordinary words. Describe a useful detail today.", 8)
        self.assertNotEqual([event["start"] for event in plain], [event["start"] for event in phrased])

    def test_uncertainty_has_asymmetric_support_hand(self):
        event = plan_gestures("Perhaps this might work.", 5)[0]
        self.assertGreater(event["support"], 0)
        self.assertLess(event["support"], 0.6)


if __name__ == "__main__":
    unittest.main()
