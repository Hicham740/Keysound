"""Manifest and attribution completeness for the bundled sounds."""
from __future__ import annotations

import json
import unittest

from keysound import paths


class SoundManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sounds_dir = paths.BUILTIN_SOUNDS_DIR
        cls.manifest_path = cls.sounds_dir / "manifest.json"
        cls.manifest = json.loads(cls.manifest_path.read_text(encoding="utf-8"))
        cls.entries = {item["file"]: item for item in cls.manifest["sounds"]}

    def test_every_wav_on_disk_has_a_manifest_entry(self):
        on_disk = {p.name for p in self.sounds_dir.glob("*.wav")}
        self.assertEqual(on_disk, set(self.entries))

    def test_every_entry_has_source_author_and_license(self):
        for name, entry in self.entries.items():
            for field in ("source", "author", "license"):
                self.assertIn(field, entry, name)
                self.assertIsInstance(entry[field], str, name)
                self.assertTrue(entry[field].strip(), f"{name}: empty {field}")

    def test_manifest_does_not_claim_cc0_for_current_sounds(self):
        text = self.manifest_path.read_text(encoding="utf-8").lower()
        self.assertNotIn("cc0", text)
        self.assertNotIn("public domain", text)

    def test_credits_mentions_every_sound(self):
        credits = (self.sounds_dir / "CREDITS.md").read_text(encoding="utf-8")
        for name in self.entries:
            self.assertIn(name, credits)
        self.assertIn("user-supplied", credits.lower())
        self.assertIn("unknown", credits.lower())


if __name__ == "__main__":
    unittest.main()
