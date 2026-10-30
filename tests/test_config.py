"""Tests for defaults, rule resolution, persistence, and profile bundles."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from keysound import paths
from keysound.config import (
    Config, DEFAULT_KEYS, GROUP_LABELS, KEY_VOLUME_MAX, PITCH_MAX,
    PITCH_MIN, VOLUME_MAX, VOLUME_MIN, clean_rule, list_sound_files,
    resolve_sound_path,
)
from keysound.keymap import key_group

from .helpers import tiny_wav


class ConfigDefaultsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "keysound" / "settings.json"
        self.cfg = Config(self.path)

    def test_group_fallback(self):
        rule = self.cfg.resolve("KEY_A")
        self.assertEqual(rule.source, "group:letters")
        self.assertEqual(rule.mode, "random")
        self.assertEqual(len(rule.sounds), 3)
        self.assertIn("letter-1.wav", rule.sounds)

    def test_key_override_wins(self):
        rule = self.cfg.resolve("KEY_SPACE")
        self.assertEqual(rule.source, "key")
        self.assertEqual(rule.sounds, ("space.wav",))
        self.assertEqual(key_group("KEY_SPACE"), "controls")

    def test_modifier_group(self):
        rule = self.cfg.resolve("KEY_LEFTSHIFT")
        self.assertEqual(rule.source, "group:modifiers")
        self.assertLess(rule.volume, 1.0)

    def test_disabled_group_falls_back_to_default(self):
        self.cfg.data["groups"]["letters"]["enabled"] = False
        rule = self.cfg.resolve("KEY_Q")
        self.assertEqual(rule.source, "default")
        self.assertEqual(rule.sounds, ("default.wav",))

    def test_key_rule_disabled_is_ignored(self):
        self.cfg.data["keys"]["KEY_SPACE"]["enabled"] = False
        rule = self.cfg.resolve("KEY_SPACE")
        self.assertEqual(rule.source, "group:controls")

    def test_master_volume_clamped(self):
        self.cfg.set_master_volume(0.0)
        self.assertEqual(self.cfg.master_volume, VOLUME_MIN)
        self.cfg.set_master_volume(9.0)
        self.assertEqual(self.cfg.master_volume, VOLUME_MAX)

    def test_mute_and_enable_are_independent(self):
        self.assertTrue(self.cfg.enabled)
        self.cfg.set_muted(True)
        self.assertFalse(self.cfg.enabled)
        self.assertTrue(self.cfg.muted)
        self.cfg.set_muted(False)
        self.cfg.set_enabled(False)
        self.assertFalse(self.cfg.enabled)

    def test_save_load_roundtrip_and_permissions(self):
        self.cfg.set_master_volume(0.42)
        self.cfg.set_profile_name("Test Range")
        self.cfg.set_key_rule("KEY_Z", ["boom.wav"], "single", 1.2, 1.1, 0.02)
        self.cfg.save()

        self.assertTrue(self.path.exists())
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)
        raw = json.loads(self.path.read_text())
        self.assertAlmostEqual(raw["masterVolume"], 0.42)
        self.assertEqual(raw["profileName"], "Test Range")
        self.assertIn("KEY_Z", raw["keys"])

        other = Config(self.path)
        other.load()
        rule = other.resolve("KEY_Z")
        self.assertEqual(rule.source, "key")
        self.assertEqual(rule.sounds, ("boom.wav",))
        self.assertAlmostEqual(rule.volume, 1.2)
        self.assertAlmostEqual(rule.pitch, 1.1)

    def test_corrupt_file_is_backed_up_and_defaults_used(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{not json", encoding="utf-8")
        cfg = Config(self.path)
        cfg.load()
        self.assertIsNotNone(cfg.load_error)
        self.assertTrue(self.path.with_suffix(".json.corrupt").exists())
        self.assertEqual(cfg.resolve("KEY_SPACE").source, "key")

    def test_explicit_empty_key_map_is_kept(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"keys": {}, "groups": {}}), encoding="utf-8")
        cfg = Config(self.path)
        cfg.load()
        self.assertEqual(cfg.data["keys"], {})
        # Group fallback still supplies a sound for ordinary keys.
        self.assertEqual(cfg.resolve("KEY_A").source, "group:letters")

    def test_profile_merge_keeps_unknown_values_safe(self):
        merged = self.cfg._merge({
            "masterVolume": 0.5,
            "enabled": "yes",
            "defaultSound": "../../etc/passwd",
            "keys": {
                "KEY_A": {"sounds": ["letter-1.wav"], "volume": 99, "pitch": -4},
                "bad": {"sounds": ["letter-1.wav"]},
            },
        })
        self.assertEqual(merged["defaultSound"], "default.wav")
        self.assertTrue(merged["enabled"])
        self.assertAlmostEqual(merged["keys"]["KEY_A"]["volume"], KEY_VOLUME_MAX)
        self.assertAlmostEqual(merged["keys"]["KEY_A"]["pitch"], PITCH_MIN)
        self.assertNotIn("bad", merged["keys"])


class CleanRuleTest(unittest.TestCase):
    def test_rejects_path_traversal_and_wrong_extension(self):
        cleaned = clean_rule({"sounds": ["ok.wav", "../bad.wav", "/tmp/x.wav", "nope.mp3", "ok.wav"]})
        self.assertEqual(cleaned["sounds"], ["ok.wav"])

    def test_clamps_and_normalizes(self):
        cleaned = clean_rule({
            "sounds": ["a.wav"],
            "mode": "weird",
            "volume": 10,
            "pitch": 10,
            "jitter": 10,
        })
        self.assertEqual(cleaned["mode"], "single")
        self.assertEqual(cleaned["volume"], KEY_VOLUME_MAX)
        self.assertEqual(cleaned["pitch"], PITCH_MAX)
        self.assertEqual(cleaned["jitter"], 0.10)


class SoundLookupTest(unittest.TestCase):
    def test_builtin_sounds_exist(self):
        names = list_sound_files()
        self.assertGreaterEqual(len(names), 20)
        self.assertIn("default.wav", names)
        self.assertIn("shotgun.wav", names)
        for name in names:
            self.assertIsNotNone(resolve_sound_path(name))

    def test_unknown_sound_is_none(self):
        self.assertIsNone(resolve_sound_path("does-not-exist.wav"))


class ProfileBundleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.custom = self.root / "custom"
        self.custom.mkdir()
        self.patch = mock.patch.object(paths, "CUSTOM_SOUNDS_DIR", self.custom)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.cfg = Config(self.root / "settings.json")
        self.bundle = self.root / "range.keysound"

    def test_export_and_import_with_custom_sound(self):
        sound = tiny_wav(self.custom / "custom-test.wav", seconds=0.02)
        self.cfg.set_key_rule("KEY_Q", [sound.name], "single", 1.0, 1.0, 0.0)
        self.cfg.set_profile_name("Range Test")
        self.cfg.export_profile(self.bundle)

        self.assertTrue(self.bundle.exists())
        with zipfile.ZipFile(self.bundle) as zf:
            names = set(zf.namelist())
            self.assertIn("profile.json", names)
            self.assertIn("manifest.json", names)
            self.assertIn("custom_sounds/custom-test.wav", names)
            payload = json.loads(zf.read("profile.json"))
            self.assertEqual(payload["profileName"], "Range Test")
            self.assertEqual(payload["keys"]["KEY_Q"]["sounds"], ["custom-test.wav"])

        other = Config(self.root / "other.json")
        other.data["launchAtLogin"] = True
        other.import_profile(self.bundle)
        self.assertEqual(other.data["profileName"], "Range Test")
        self.assertTrue(other.data["launchAtLogin"])
        self.assertEqual(other.resolve("KEY_Q").sounds, ("custom-test.wav",))

    def test_import_rejects_bad_archive(self):
        bad = self.root / "bad.keysound"
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("nothing.txt", "x")
        with self.assertRaises(ValueError):
            self.cfg.import_profile(bad)


if __name__ == "__main__":
    unittest.main()
