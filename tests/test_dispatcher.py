"""Tests for key dispatch, repeat filtering, modifiers, and the mute chord."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from keysound.config import Config, clean_rule
from keysound.dispatcher import Dispatcher


class FakeMixer:
    def __init__(self):
        self.played = []
        self.panicked = 0

    def play(self, rule, key_id="", *, force=False):
        self.played.append((rule, key_id, force))
        return True

    def panic(self):
        self.panicked += 1

    def sounds(self):
        return [(rule.source, key_id) for rule, key_id, _ in self.played]


class DispatcherTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = Config(Path(self.tmp.name) / "settings.json")
        self.mixer = FakeMixer()
        self.activity = []
        self.mutes = []
        self.disp = Dispatcher(
            self.cfg, self.mixer,
            on_activity=self.activity.append,
            on_mute=self.mutes.append,
        )

    def press(self, key, value=1):
        self.disp.handle(key, value)

    def test_press_plays_and_records_activity(self):
        self.press("KEY_A")
        self.assertEqual(len(self.mixer.played), 1)
        self.assertEqual(self.mixer.played[0][1], "KEY_A")
        self.assertEqual(self.activity, ["KEY_A"])

    def test_auto_repeat_is_filtered_by_default(self):
        self.press("KEY_A")
        self.press("KEY_A", 2)
        self.assertEqual(len(self.mixer.played), 1)

    def test_hold_to_repeat_allows_repeat(self):
        self.cfg.data["holdToRepeat"] = True
        self.press("KEY_A")
        self.press("KEY_A", 2)
        self.assertEqual(len(self.mixer.played), 2)

    def test_per_key_repeat_false_overrides_global(self):
        self.cfg.data["holdToRepeat"] = True
        self.cfg.data["keys"]["KEY_A"] = clean_rule({
            "sounds": ["letter-1.wav"], "repeat": False,
        })
        self.press("KEY_A")
        self.press("KEY_A", 2)
        self.assertEqual(len(self.mixer.played), 1)

    def test_modifier_sounds_can_be_disabled(self):
        self.cfg.data["modifiersEnabled"] = False
        self.press("KEY_LEFTSHIFT")
        self.assertEqual(self.mixer.played, [])
        self.cfg.data["modifiersEnabled"] = True
        self.press("KEY_LEFTSHIFT")
        self.assertEqual(len(self.mixer.played), 1)

    def test_disabled_app_does_not_play(self):
        self.cfg.data["enabled"] = False
        self.press("KEY_A")
        self.assertEqual(self.mixer.played, [])

    def test_mute_chord_toggles_without_playing_m(self):
        self.press("KEY_LEFTCTRL")
        self.press("KEY_LEFTALT")
        self.press("KEY_LEFTSHIFT")
        played_before = len(self.mixer.played)
        self.press("KEY_M", 1)
        self.assertTrue(self.cfg.muted)
        self.assertEqual(self.mutes, [True])
        self.assertEqual(len(self.mixer.played), played_before)
        # Auto-repeat of M must not toggle again.
        self.press("KEY_M", 2)
        self.assertTrue(self.cfg.muted)
        self.assertEqual(self.mutes, [True])

    def test_mute_chord_works_while_disabled(self):
        self.cfg.data["enabled"] = False
        self.press("KEY_LEFTCTRL")
        self.press("KEY_LEFTALT")
        self.press("KEY_LEFTSHIFT")
        self.press("KEY_M", 1)
        self.assertTrue(self.cfg.muted)
        self.assertEqual(self.mixer.played, [])

    def test_plain_m_is_not_a_chord(self):
        self.press("KEY_M")
        self.assertEqual(self.mixer.played[0][1], "KEY_M")
        self.assertFalse(self.cfg.muted)

    def test_key_up_sound(self):
        self.cfg.data["keyUp"]["KEY_A"] = clean_rule({"sounds": ["release.wav"]})
        self.press("KEY_A")
        self.press("KEY_A", 0)
        self.assertEqual(len(self.mixer.played), 2)
        self.assertEqual(self.mixer.played[1][0].source, "keyUp")

    def test_release_without_rule_is_silent(self):
        self.press("KEY_A")
        self.press("KEY_A", 0)
        self.assertEqual(len(self.mixer.played), 1)

    def test_test_key_is_forced(self):
        self.cfg.data["enabled"] = False
        self.assertTrue(self.disp.test_key("KEY_SPACE"))
        self.assertTrue(self.mixer.played[-1][2])

    def test_panic_delegates(self):
        self.disp.panic()
        self.assertEqual(self.mixer.panicked, 1)


if __name__ == "__main__":
    unittest.main()
