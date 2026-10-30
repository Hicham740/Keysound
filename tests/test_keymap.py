"""Tests for physical key IDs and the visual keyboard layout."""
from __future__ import annotations

import unittest

from keysound.keymap import (
    CODE_TO_KEY, KEY_TO_CODE, all_known_keys, key_group, key_label,
    keyboard_layout,
)


class KeyMapTest(unittest.TestCase):
    def test_evdev_roundtrip(self):
        self.assertEqual(KEY_TO_CODE["KEY_A"], 30)
        self.assertEqual(CODE_TO_KEY[30], "KEY_A")
        self.assertEqual(KEY_TO_CODE["KEY_ESC"], 1)
        self.assertEqual(KEY_TO_CODE["KEY_SPACE"], 57)
        self.assertEqual(KEY_TO_CODE["KEY_ENTER"], 28)

    def test_codes_are_unique(self):
        self.assertEqual(len(KEY_TO_CODE), len(CODE_TO_KEY))

    def test_labels(self):
        self.assertEqual(key_label("KEY_A"), "A")
        self.assertEqual(key_label("KEY_SPACE"), "Space")
        self.assertEqual(key_label("KEY_LEFTCTRL"), "Ctrl")
        self.assertEqual(key_label("KEY_F12"), "F12")
        self.assertEqual(key_label("KEY_UNLISTED_THING"), "Unlisted Thing")

    def test_groups(self):
        self.assertEqual(key_group("KEY_Q"), "letters")
        self.assertEqual(key_group("KEY_5"), "digits")
        self.assertEqual(key_group("KEY_LEFTSHIFT"), "modifiers")
        self.assertEqual(key_group("KEY_F5"), "function")
        self.assertEqual(key_group("KEY_KP7"), "numpad")
        self.assertEqual(key_group("KEY_UP"), "navigation")
        self.assertEqual(key_group("KEY_SEMICOLON"), "punctuation")
        self.assertEqual(key_group("KEY_MUTE"), "media")

    def test_layout_has_every_essential_key_once(self):
        layout = keyboard_layout()
        seen = []
        for section in layout.values():
            for row in section:
                seen.extend(cap.key_id for cap in row)
        for key in ("KEY_ESC", "KEY_A", "KEY_SPACE", "KEY_ENTER",
                    "KEY_LEFTSHIFT", "KEY_F12", "KEY_KP0", "KEY_UP"):
            self.assertIn(key, seen)
        self.assertEqual(len(seen), len(set(seen)))
        # The main section must be able to represent a 104-key keyboard.
        self.assertGreaterEqual(len(seen), 90)

    def test_layout_widths_are_positive(self):
        for section in keyboard_layout().values():
            for row in section:
                for cap in row:
                    self.assertGreater(cap.width, 0)
                    self.assertIn(cap.key_id, KEY_TO_CODE)

    def test_all_known_keys(self):
        keys = list(all_known_keys())
        self.assertIn("KEY_A", keys)
        self.assertGreater(len(keys), 200)


if __name__ == "__main__":
    unittest.main()
