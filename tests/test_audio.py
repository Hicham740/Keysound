"""Tests for WAV decoding, voice selection, polyphony, and mixing."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from keysound.audio import (
    MAX_SOUND_SECONDS, MAX_VOICES, SAMPLE_RATE, Mixer, SoundBank, decode_wav,
)
from keysound.config import Rule

from .helpers import write_wav


class _Config:
    def __init__(self, *, enabled: bool = True, master: float = 1.0):
        self.enabled = enabled
        self.muted = False
        self.master_volume = master
        self.data = {"defaultSound": "default.wav"}


def _rule(sounds, mode="single", volume=1.0, pitch=1.0, jitter=0.0,
          source="test", repeat=None):
    return Rule(tuple(sounds), mode, volume, pitch, jitter, source, "Test", repeat)


class DecodeWavTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_16bit_mono(self):
        path = write_wav(self.root / "a.wav", [0.0, 0.5, -0.5, 0.0] * 100)
        data = decode_wav(path)
        self.assertEqual(data.dtype, np.float32)
        self.assertEqual(len(data), 400)
        self.assertLessEqual(float(np.max(np.abs(data))), 1.0)

    def test_stereo_is_mixed_to_mono(self):
        samples = np.empty((400, 2), dtype=np.float64)
        samples[:, 0] = 0.5
        samples[:, 1] = -0.5
        path = write_wav(self.root / "stereo.wav", samples, channels=2)
        data = decode_wav(path)
        self.assertEqual(len(data), 400)
        self.assertLess(float(np.mean(np.abs(data[50:-50]))), 1e-4)

    def test_8bit_and_24bit_and_32bit(self):
        for width in (1, 3, 4):
            path = write_wav(self.root / f"w{width}.wav", [0.0, 0.25, -0.25] * 20, width=width)
            data = decode_wav(path)
            self.assertEqual(len(data), 60, msg=f"width {width}")
            self.assertTrue(np.all(np.isfinite(data)))

    def test_resampling_to_48k(self):
        path = write_wav(self.root / "low.wav", np.zeros(1000), rate=24_000)
        data = decode_wav(path)
        self.assertAlmostEqual(len(data), 2000, delta=2)

    def test_long_files_are_capped(self):
        path = write_wav(self.root / "long.wav", np.zeros(SAMPLE_RATE * 3))
        data = decode_wav(path)
        self.assertEqual(len(data), int(SAMPLE_RATE * MAX_SOUND_SECONDS))

    def test_empty_file(self):
        path = write_wav(self.root / "empty.wav", np.zeros(0))
        data = decode_wav(path)
        self.assertEqual(data.size, 0)


class MixerTest(unittest.TestCase):
    def setUp(self):
        self.bank = SoundBank()
        self.bank.buffers = {
            "tone.wav": np.full(2400, 0.25, dtype=np.float32),
            "other.wav": np.full(2400, -0.25, dtype=np.float32),
            "default.wav": np.full(2400, 0.1, dtype=np.float32),
        }
        self.cfg = _Config()
        self.mixer = Mixer(self.bank, lambda: self.cfg)

    def test_play_creates_voice_with_gain(self):
        self.cfg.master_volume = 0.5
        rule = _rule(["tone.wav"], volume=0.5)
        self.assertTrue(self.mixer.play(rule, "KEY_A"))
        self.assertEqual(self.mixer.active_voices(), 1)
        self.assertAlmostEqual(self.mixer.voices[0].gain, 0.25)
        self.assertAlmostEqual(self.mixer.voices[0].step, 1.0)

    def test_pitch_is_clamped(self):
        self.mixer.play(_rule(["tone.wav"], pitch=9.0), "KEY_A")
        self.assertAlmostEqual(self.mixer.voices[-1].step, 2.0)
        self.mixer.panic()
        self.mixer.play(_rule(["tone.wav"], pitch=0.01), "KEY_B")
        self.assertAlmostEqual(self.mixer.voices[-1].step, 0.5)

    def test_twelve_voice_polyphony(self):
        rule = _rule(["tone.wav"])
        for i in range(MAX_VOICES + 5):
            self.assertTrue(self.mixer.play(rule, f"KEY_{i}"))
        self.assertEqual(self.mixer.active_voices(), MAX_VOICES)

    def test_muted_config_blocks_play_unless_forced(self):
        self.cfg.enabled = False
        self.assertFalse(self.mixer.play(_rule(["tone.wav"])))
        self.assertTrue(self.mixer.play(_rule(["tone.wav"]), force=True))

    def test_missing_sound_uses_default(self):
        self.assertTrue(self.mixer.play(_rule(["gone.wav"])))
        self.assertEqual(self.mixer.voices[-1].sound, "default.wav")

    def test_round_robin_selection(self):
        rule = _rule(["tone.wav", "other.wav"], mode="roundRobin", source="group:x")
        self.mixer.play(rule)
        self.mixer.play(rule)
        self.mixer.play(rule)
        names = [voice.sound for voice in self.mixer.voices]
        self.assertEqual(names, ["tone.wav", "other.wav", "tone.wav"])

    def test_single_mode_uses_first_sound(self):
        rule = _rule(["other.wav", "tone.wav"], mode="single")
        self.mixer.play(rule)
        self.assertEqual(self.mixer.voices[-1].sound, "other.wav")

    def test_render_mixes_and_finishes_voices(self):
        self.mixer.play(_rule(["tone.wav"]))
        block = self.mixer.render(256)
        self.assertEqual(block.shape, (256,))
        self.assertGreater(float(np.max(block)), 0.0)
        for _ in range(20):
            self.mixer.render(256)
        self.assertEqual(self.mixer.active_voices(), 0)

    def test_empty_render_is_silence(self):
        block = self.mixer.render(128)
        self.assertEqual(block.shape, (128,))
        self.assertTrue(np.all(block == 0))

    def test_panic_clears_voices(self):
        self.mixer.play(_rule(["tone.wav"]))
        self.mixer.panic()
        self.assertEqual(self.mixer.active_voices(), 0)


if __name__ == "__main__":
    unittest.main()
