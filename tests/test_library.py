"""Tests for the user sound library (import, list, remove)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from keysound import library, paths
from keysound.audio import SoundBank

from .helpers import tiny_wav, write_wav


class SoundLibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.library = self.root / "sounds"
        self.source = tiny_wav(self.root / "My Cool Sound.wav", seconds=0.02)

    def test_import_copies_and_sanitizes_name(self):
        dest = library.import_sound(self.source, self.library)
        self.assertTrue(dest.exists())
        self.assertEqual(dest.name, "custom-my-cool-sound.wav")
        self.assertEqual(dest.read_bytes(), self.source.read_bytes())

    def test_import_collision_gets_numbered(self):
        first = library.import_sound(self.source, self.library)
        second = library.import_sound(self.source, self.library)
        third = library.import_sound(self.source, self.library)
        self.assertNotEqual(first.name, second.name)
        self.assertEqual(first.name, "custom-my-cool-sound.wav")
        self.assertEqual(second.name, "custom-my-cool-sound-2.wav")
        self.assertEqual(third.name, "custom-my-cool-sound-3.wav")

    def test_invalid_file_is_rejected(self):
        bad = self.root / "bad.wav"
        bad.write_text("this is not audio")
        with self.assertRaises(library.SoundImportError):
            library.import_sound(bad, self.library)

    def test_empty_wav_is_rejected(self):
        empty = write_wav(self.root / "empty.wav", np.zeros(0))
        with self.assertRaises(library.SoundImportError):
            library.import_sound(empty, self.library)

    def test_missing_file_is_rejected(self):
        with self.assertRaises(library.SoundImportError):
            library.import_sound(self.root / "nope.wav", self.library)

    def test_list_is_sorted_and_filtered(self):
        library.import_sound(self.source, self.library)
        (self.library / "notes.txt").write_text("ignore me")
        names = [p.name for p in library.custom_sounds(self.library)]
        self.assertEqual(names, ["custom-my-cool-sound.wav"])

    def test_remove_deletes_only_library_files(self):
        dest = library.import_sound(self.source, self.library)
        self.assertTrue(library.remove_sound(dest.name, self.library))
        self.assertFalse(dest.exists())
        self.assertFalse(library.remove_sound(dest.name, self.library))

    def test_remove_rejects_path_traversal(self):
        outside = self.root / "settings.json"
        outside.write_text("{}")
        for name in ("../settings.json", "../../etc/passwd", str(outside)):
            with self.assertRaises(library.SoundImportError):
                library.remove_sound(name, self.library)
        self.assertTrue(outside.exists())

    def test_bank_lists_imported_sound_as_custom(self):
        dest = library.import_sound(self.source, self.library)
        with mock.patch.object(paths, "CUSTOM_SOUNDS_DIR", self.library):
            bank = SoundBank()
            bank.load()
        self.assertIn(dest.name, bank.buffers)
        info = bank.info_for(dest.name)
        self.assertIsNotNone(info)
        self.assertTrue(info.custom)
        self.assertGreater(info.duration, 0)


if __name__ == "__main__":
    unittest.main()
