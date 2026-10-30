"""Small helpers shared by the KeySound unit tests."""
from __future__ import annotations

import struct
import wave
from pathlib import Path

import numpy as np


def write_wav(path: Path, samples, *, width: int = 2, channels: int = 1,
              rate: int = 48_000) -> Path:
    """Write interleaved float samples as a PCM WAV file."""
    data = np.asarray(samples, dtype=np.float64)
    if channels > 1:
        data = data.reshape(-1, channels)
    flat = data.reshape(-1)
    if width == 1:
        raw = np.clip(np.round(flat * 127.0 + 128.0), 0, 255).astype(np.uint8).tobytes()
    elif width == 2:
        raw = np.clip(np.round(flat * 32767.0), -32768, 32767).astype("<i2").tobytes()
    elif width == 3:
        ints = np.clip(np.round(flat * 8388607.0), -8388608, 8388607).astype(np.int32)
        buf = bytearray()
        for value in ints:
            value &= 0xFFFFFF
            buf += bytes((value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF))
        raw = bytes(buf)
    elif width == 4:
        raw = np.clip(np.round(flat * 2147483647.0), -2147483648, 2147483647).astype("<i4").tobytes()
    else:
        raise ValueError(width)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(width)
        wf.setframerate(rate)
        wf.writeframes(raw)
    return path


def tiny_wav(path: Path, *, seconds: float = 0.01) -> Path:
    count = max(2, int(48_000 * seconds))
    return write_wav(path, np.zeros(count, dtype=np.float32))
