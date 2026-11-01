"""Preloaded PCM sound bank and a 12-voice PulseAudio/PipeWire mixer."""
from __future__ import annotations

import ctypes
import ctypes.util
import logging
import math
import random
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from . import paths
from .config import Rule, list_sound_files, resolve_sound_path

LOG = logging.getLogger(__name__)
SAMPLE_RATE = 48_000
CHANNELS = 1
FRAMES_PER_BLOCK = 256
MAX_VOICES = 12
MAX_SOUND_SECONDS = 3.0  # user samples can run long (e.g. artillery, 2.4 s)


@dataclass(frozen=True)
class SoundInfo:
    name: str
    path: Path
    label: str
    description: str = ""
    custom: bool = False
    duration: float = 0.0


class SoundBank:
    def __init__(self) -> None:
        self.buffers: dict[str, np.ndarray] = {}
        self.info: dict[str, SoundInfo] = {}
        self.errors: dict[str, str] = {}
        self.lock = threading.RLock()
        self._labels = self._load_manifest()

    @staticmethod
    def _load_manifest() -> dict[str, dict[str, str]]:
        try:
            import json
            raw = json.loads((paths.BUILTIN_SOUNDS_DIR / "manifest.json").read_text())
            return {item["file"]: item for item in raw.get("sounds", []) if "file" in item}
        except Exception:
            return {}

    def load(self) -> None:
        with self.lock:
            self.buffers.clear()
            self.info.clear()
            self.errors.clear()
            for name, path in list_sound_files().items():
                try:
                    data = decode_wav(path)
                    if data.size == 0:
                        raise ValueError("empty audio file")
                    self.buffers[name] = data
                    meta = self._labels.get(name, {})
                    custom = path.parent == paths.CUSTOM_SOUNDS_DIR
                    self.info[name] = SoundInfo(
                        name=name,
                        path=path,
                        label=meta.get("label") or Path(name).stem.replace("-", " ").title(),
                        description=meta.get("description", "Custom imported sound" if custom else ""),
                        custom=custom,
                        duration=len(data) / SAMPLE_RATE,
                    )
                except Exception as exc:
                    self.errors[name] = str(exc)

    def get(self, name: str) -> np.ndarray | None:
        with self.lock:
            return self.buffers.get(name)

    def names(self) -> list[str]:
        with self.lock:
            return sorted(self.buffers, key=lambda n: (self.info[n].custom, self.info[n].label.lower()))

    def info_for(self, name: str) -> SoundInfo | None:
        with self.lock:
            return self.info.get(name)

    def reload(self) -> None:
        self.load()


def decode_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        rate = wf.getframerate()
        frames = wf.getnframes()
        raw = wf.readframes(frames)
    if not raw:
        return np.zeros(0, dtype=np.float32)

    if width == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8)
        b = b[: (len(b) // 3) * 3].reshape(-1, 3).astype(np.int32)
        values = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        values = np.where(values & 0x800000, values - 0x1000000, values)
        data = values.astype(np.float32) / 8388608.0
    elif width == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"unsupported WAV sample width: {width}")

    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)

    max_frames = int(SAMPLE_RATE * MAX_SOUND_SECONDS)
    if len(data) > max_frames:
        data = data[:max_frames]

    if rate != SAMPLE_RATE and len(data) > 1:
        duration = len(data) / rate
        new_len = max(1, int(duration * SAMPLE_RATE))
        old_x = np.linspace(0.0, duration, len(data), endpoint=False)
        new_x = np.linspace(0.0, duration, new_len, endpoint=False)
        data = np.interp(new_x, old_x, data).astype(np.float32)

    # Remove DC and prevent a click at playback start/end.
    if data.size:
        data = data - float(np.mean(data))
        edge = min(len(data), int(SAMPLE_RATE * 0.0015))
        if edge > 1:
            data[:edge] *= np.linspace(0.0, 1.0, edge, dtype=np.float32)
            data[-edge:] *= np.linspace(1.0, 0.0, edge, dtype=np.float32)
    return np.ascontiguousarray(data, dtype=np.float32)


@dataclass
class Voice:
    data: np.ndarray
    pos: float
    step: float
    gain: float
    born: int
    key_id: str = ""
    sound: str = ""


class _PulseSpec(ctypes.Structure):
    _fields_ = [
        ("format", ctypes.c_int),
        ("rate", ctypes.c_uint32),
        ("channels", ctypes.c_uint8),
    ]


class _PulseBufferAttr(ctypes.Structure):
    _fields_ = [
        ("maxlength", ctypes.c_uint32),
        ("tlength", ctypes.c_uint32),
        ("prebuf", ctypes.c_uint32),
        ("minreq", ctypes.c_uint32),
        ("fragsize", ctypes.c_uint32),
    ]


PA_SAMPLE_S16LE = 3
PA_STREAM_PLAYBACK = 1
PA_USEC_INVALID = 0xFFFFFFFF


class Mixer:
    def __init__(self, bank: SoundBank, config_getter):
        self.bank = bank
        self.config = config_getter
        self.lock = threading.RLock()
        self.voices: list[Voice] = []
        self.counter = 0
        self.round_robin: dict[str, int] = {}
        self.rng = random.Random()

    def play(self, rule: Rule, key_id: str = "", *, force: bool = False) -> bool:
        cfg = self.config()
        if not force and not cfg.enabled:
            return False
        if rule.volume <= 0 or not rule.sounds:
            return False
        name = self._choose(rule)
        data = self.bank.get(name)
        if data is None or data.size < 2:
            # A missing assignment falls back to the configured default sound,
            # and if even that is unavailable, to the built-in default.wav.
            fallback = str(cfg.data.get("defaultSound", "default.wav"))
            data = self.bank.get(fallback)
            if data is None or data.size < 2:
                fallback = "default.wav"
                data = self.bank.get(fallback)
            if data is None:
                return False
            name = fallback
        jitter = self.rng.uniform(-rule.jitter, rule.jitter) if rule.jitter else 0.0
        pitch = max(0.5, min(2.0, rule.pitch + jitter))
        gain = max(0.0, min(1.5, rule.volume)) * cfg.master_volume
        with self.lock:
            self.counter += 1
            voice = Voice(data=data, pos=0.0, step=pitch, gain=gain,
                          born=self.counter, key_id=key_id, sound=name)
            if len(self.voices) >= MAX_VOICES:
                oldest = min(range(len(self.voices)), key=lambda i: self.voices[i].born)
                self.voices[oldest] = voice
            else:
                self.voices.append(voice)
        return True

    def _choose(self, rule: Rule) -> str:
        sounds = rule.sounds
        if len(sounds) == 1:
            return sounds[0]
        if rule.mode == "roundRobin":
            idx = self.round_robin.get(rule.source, 0) % len(sounds)
            self.round_robin[rule.source] = idx + 1
            return sounds[idx]
        if rule.mode == "random":
            return self.rng.choice(sounds)
        return sounds[0]

    def render(self, frames: int) -> np.ndarray:
        with self.lock:
            voices = self.voices[:]
        if not voices:
            return np.zeros(frames, dtype=np.float32)
        out = np.zeros(frames, dtype=np.float32)
        finished: list[Voice] = []
        with self.lock:
            for voice in voices:
                data = voice.data
                count = int(math.ceil(frames * voice.step)) + 2
                start = int(voice.pos)
                if start >= len(data):
                    finished.append(voice)
                    continue
                idx = start + np.arange(count, dtype=np.float64) * voice.step
                idx = idx[idx < len(data) - 1]
                if idx.size == 0:
                    finished.append(voice)
                    continue
                i0 = idx.astype(np.int64)
                frac = (idx - i0).astype(np.float32)
                samples = data[i0] * (1.0 - frac) + data[i0 + 1] * frac
                take = min(frames, len(samples))
                out[:take] += samples[:take] * voice.gain
                voice.pos += frames * voice.step
                if voice.pos >= len(data) - 1:
                    finished.append(voice)
            if finished:
                ids = {id(v) for v in finished}
                self.voices = [v for v in self.voices if id(v) not in ids]
        # Gentle saturation; normal material stays linear.
        np.clip(out, -0.98, 0.98, out=out)
        return out

    def panic(self) -> None:
        with self.lock:
            self.voices.clear()

    def active_voices(self) -> int:
        with self.lock:
            return len(self.voices)


class AudioEngine:
    """A continuously running PulseAudio simple stream.

    PipeWire's pulse compatibility layer is used automatically on Kali.  If the
    stream dies (device switch, server restart), the writer thread retries with
    a fresh stream without crashing the UI.
    """

    def __init__(self, mixer: Mixer):
        self.mixer = mixer
        self.lock = threading.RLock()
        self._stream: int | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._lib = None
        self._error: str | None = None
        self._last_latency_us: int | None = None
        self._load_pulse()

    def _load_pulse(self) -> None:
        name = ctypes.util.find_library("pulse-simple")
        if not name:
            self._error = "libpulse-simple is not installed"
            return
        try:
            lib = ctypes.CDLL(name)
            lib.pa_simple_new.restype = ctypes.c_void_p
            lib.pa_simple_new.argtypes = [
                ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
                ctypes.c_char_p, ctypes.POINTER(_PulseSpec), ctypes.c_void_p,
                ctypes.POINTER(_PulseBufferAttr), ctypes.POINTER(ctypes.c_int),
            ]
            lib.pa_simple_write.restype = ctypes.c_int
            lib.pa_simple_write.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_int)]
            lib.pa_simple_free.restype = None
            lib.pa_simple_free.argtypes = [ctypes.c_void_p]
            lib.pa_simple_get_latency.restype = ctypes.c_ulong
            lib.pa_simple_get_latency.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
            self._lib = lib
        except Exception as exc:
            self._error = f"could not load PulseAudio: {exc}"

    def start(self) -> bool:
        if self._lib is None:
            return False
        with self.lock:
            if self._running:
                return True
            self._running = True
            self._thread = threading.Thread(target=self._run, name="keysound-audio", daemon=True)
            self._thread.start()
        return True

    def _open_stream(self) -> int | None:
        assert self._lib is not None
        spec = _PulseSpec(PA_SAMPLE_S16LE, SAMPLE_RATE, CHANNELS)
        # 16 ms target buffer, 256-frame writes.  This keeps latency low while
        # leaving enough room for Python scheduling jitter.
        attr = _PulseBufferAttr(
            maxlength=4096,
            tlength=1536,
            prebuf=1024,
            minreq=256,
            fragsize=0xFFFFFFFF,
        )
        err = ctypes.c_int(0)
        stream = self._lib.pa_simple_new(
            None, b"keysound", PA_STREAM_PLAYBACK, None,
            b"per-key keyboard audio", ctypes.byref(spec), None,
            ctypes.byref(attr), ctypes.byref(err),
        )
        if not stream:
            self._error = f"PulseAudio connection failed (error {err.value})"
            LOG.warning(self._error)
            return None
        with self.lock:
            self._stream = stream
            self._error = None
        return stream

    def _close_stream(self) -> None:
        with self.lock:
            stream = self._stream
            self._stream = None
        if stream and self._lib:
            try:
                self._lib.pa_simple_free(stream)
            except Exception:
                pass

    def _run(self) -> None:
        stream = self._open_stream()
        retry_at = time.monotonic() + 2.0
        while self._running:
            if stream is None:
                if time.monotonic() < retry_at:
                    time.sleep(0.2)
                    continue
                stream = self._open_stream()
                retry_at = time.monotonic() + 3.0
                if stream is None:
                    continue
            block = self.mixer.render(FRAMES_PER_BLOCK)
            pcm = np.clip(block, -1.0, 1.0)
            pcm = (pcm * 32767.0).astype("<i2")
            err = ctypes.c_int(0)
            rc = self._lib.pa_simple_write(
                stream, pcm.ctypes.data_as(ctypes.c_void_p), pcm.nbytes,
                ctypes.byref(err),
            )
            if rc < 0:
                LOG.warning("PulseAudio write failed (error %s); reconnecting", err.value)
                self._close_stream()
                stream = None
                retry_at = time.monotonic() + 1.0
                continue
            # Read latency occasionally (not on every block).
            if self.mixer.active_voices() and random.random() < 0.02:
                lat_err = ctypes.c_int(0)
                lat = self._lib.pa_simple_get_latency(stream, ctypes.byref(lat_err))
                if lat != PA_USEC_INVALID and lat_err.value == 0:
                    self._last_latency_us = int(lat)
        self._close_stream()

    def stop(self) -> None:
        self._running = False
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=1.5)
        self._close_stream()

    @property
    def error(self) -> str | None:
        with self.lock:
            return self._error

    @property
    def latency_ms(self) -> float | None:
        if self._last_latency_us is None:
            return None
        return self._last_latency_us / 1000.0

    @property
    def running(self) -> bool:
        with self.lock:
            return self._stream is not None
