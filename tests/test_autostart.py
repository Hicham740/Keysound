"""Tests for the XDG autostart entry."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from keysound import autostart, paths
from keysound.config import Config


class AutostartTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name) / "autostart"
        self.path = self.dir / "keysound.desktop"
        self.patch_dir = mock.patch.object(paths, "AUTOSTART_DIR", self.dir)
        self.patch_path = mock.patch.object(paths, "AUTOSTART_PATH", self.path)
        self.patch_dir.start()
        self.patch_path.start()
        self.addCleanup(self.patch_dir.stop)
        self.addCleanup(self.patch_path.stop)

    def test_enable_creates_valid_desktop_entry(self):
        ok, message = autostart.set_enabled(True)
        self.assertTrue(ok, message)
        self.assertTrue(self.path.exists())
        text = self.path.read_text()
        self.assertIn("[Desktop Entry]", text)
        self.assertIn("Name=KeySound", text)
        self.assertIn("--minimized", text)
        self.assertIn("Terminal=false", text)
        self.assertTrue(autostart.is_enabled())

    def test_disable_removes_entry(self):
        autostart.set_enabled(True)
        ok, _ = autostart.set_enabled(False)
        self.assertTrue(ok)
        self.assertFalse(self.path.exists())
        self.assertFalse(autostart.is_enabled())

    def test_disable_when_missing_is_ok(self):
        ok, _ = autostart.set_enabled(False)
        self.assertTrue(ok)

    def test_sync_from_disk_updates_config(self):
        cfg = Config(Path(self.tmp.name) / "settings.json")
        cfg.data["launchAtLogin"] = False
        autostart.set_enabled(True)
        autostart.sync_from_disk(cfg)
        self.assertTrue(cfg.data["launchAtLogin"])
        self.assertTrue(cfg.dirty)

        autostart.set_enabled(False)
        autostart.sync_from_disk(cfg)
        self.assertFalse(cfg.data["launchAtLogin"])


if __name__ == "__main__":
    unittest.main()
