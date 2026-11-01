#!/usr/bin/env python3
"""Generate the original, royalty-free sound set shipped with KeySound.

The key sounds use a small physical model of a mechanical switch rather than a
single oscillator:

  * a 1-2 ms broadband impact transient (stem / click-jacket contact),
  * a plastic "snap" made of a few high-Q resonances around 4-9 kHz,
  * a metallic spring ping just above the click,
  * aluminium/steel plate modes around 1.3-4.3 kHz,
  * a short low-frequency bottom-out thock,
  * a filtered housing noise tail.

The result is a bright, high, crisp click in the style of a clicky mechanical
keyboard.  Everything is synthesized from scratch with numpy, so there are no
licensing questions.  The script is deterministic and writes 48 kHz, 16-bit
mono WAV files.  It is kept in the repository so the sound set can be
regenerated.
"""
from __future__ import annotations

import json
import math
import sys
import wave
from pathlib import Path

import numpy as np

SR = 48_000
OUT = Path(__file__).resolve().parents[1] / "keysound" / "assets" / "sounds"
BASE_SEED = 0x5A17


# --------------------------------------------------------------------------- #
# Small DSP helpers
# --------------------------------------------------------------------------- #
def t(duration: float) -> np.ndarray:
    return np.arange(max(1, int(SR * duration)), dtype=np.float64) / SR


def normalize(x: np.ndarray, peak: float = 0.85) -> np.ndarray:
    m = float(np.max(np.abs(x)))
    if m < 1e-9:
        return x
    return x * (peak / m)


def fade(x: np.ndarray, ms: float = 0.8) -> np.ndarray:
    n = min(len(x), max(1, int(SR * ms / 1000)))
    x = x.copy()
    x[:n] *= np.linspace(0, 1, n)
    x[-n:] *= np.linspace(1, 0, n)
    return x


def shaped_noise(n: int, rng: np.random.Generator, *, low: float | None = None,
                 high: float | None = None, tilt: float = 0.0) -> np.ndarray:
    """FFT-shaped white noise with soft high/low shelves."""
    spectrum = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, 1.0 / SR)
    mask = np.ones_like(freqs)
    if low:
        mask *= 1.0 - np.exp(-(freqs / low) ** 2)
    if high:
        mask *= np.exp(-(freqs / high) ** 2)
    if tilt:
        mask *= (np.maximum(freqs, 20.0) / 1000.0) ** tilt
    return np.fft.irfft(spectrum * mask, n)


def soft_clip(x: np.ndarray, drive: float = 1.15) -> np.ndarray:
    return np.tanh(x * drive) / math.tanh(drive)


# --------------------------------------------------------------------------- #
# Physical key model
# --------------------------------------------------------------------------- #
def key_model(*, seed: int, duration: float = 0.085, pitch: float = 1.0,
              click: float = 1.0, body: float = 1.0, spring: float = 1.0,
              weight: float = 1.0, brightness: float = 1.0,
              snap: float = 1.0) -> np.ndarray:
    """Synthesize one mechanical key press.

    All frequencies scale with ``pitch`` (1.0 = balanced high click).
    ``click`` controls the impact transient, ``body`` the plate modes and noise
    tail, ``spring`` the metallic ping, ``weight`` the low bottom-out thump.
    """
    rng = np.random.default_rng(seed)
    tt = t(duration)
    n = len(tt)
    out = np.zeros(n)

    # 1. Broadband impact transient: very fast, bright, and slightly dirty.
    transient = shaped_noise(
        n, rng,
        low=900.0 * brightness,
        high=19_000.0,
        tilt=0.10,
    )
    transient *= np.exp(-tt / 0.0016) * (0.95 * click)
    transient[0] += 0.55 * click          # one-sample contact edge
    out += transient

    # 2. Plastic click-jacket snap: inharmonic high resonances.
    for freq, decay, gain, phase in (
        (4_250.0, 0.010, 0.30, 0.2),
        (5_900.0, 0.0075, 0.24, 1.1),
        (7_300.0, 0.0055, 0.17, 2.4),
        (8_900.0, 0.0040, 0.11, 4.0),
    ):
        out += (gain * click * snap
                * np.sin(2 * math.pi * freq * pitch * tt + phase)
                * np.exp(-tt / decay))

    # 3. Spring ping: tiny, high, metallic, and just after the click.
    for freq, decay, gain, phase in (
        (6_400.0, 0.014, 0.075, 0.7),
        (8_100.0, 0.010, 0.055, 2.0),
        (9_700.0, 0.0065, 0.035, 3.3),
    ):
        out += (gain * spring
                * np.sin(2 * math.pi * freq * pitch * tt + phase)
                * np.exp(-tt / decay))

    # 4. Plate / housing modes: the woody-metallic body of the press.
    for freq, decay, gain, phase in (
        (1_320.0, 0.030, 0.20, 1.6),
        (2_050.0, 0.023, 0.16, 0.4),
        (3_050.0, 0.016, 0.105, 2.7),
        (4_150.0, 0.010, 0.065, 5.1),
    ):
        out += (gain * body
                * np.sin(2 * math.pi * freq * pitch * tt + phase)
                * np.exp(-tt / decay))

    # 5. Bottom-out thock, delayed by the stem travel (~0.7 ms).
    delay = min(n - 1, int(0.0007 * SR))
    low = np.zeros(n)
    tl = tt[: n - delay]
    low[delay:] = (
        0.50 * np.sin(2 * math.pi * 178.0 * pitch * tl)
        * np.exp(-tl / 0.021)
        + 0.26 * np.sin(2 * math.pi * 292.0 * pitch * tl)
        * np.exp(-tl / 0.013)
    )
    out += low * body * weight

    # 6. Housing rattle / air tail.
    tail = shaped_noise(n, rng, low=650.0, high=7_500.0)
    out += tail * np.exp(-tt / 0.019) * (0.20 * body)

    # A touch of saturation adds the "plastic under pressure" edge.
    out = soft_clip(out, 1.18)
    return normalize(out, 0.86)


def heavy(seed: int, *, pitch: float = 0.72, duration: float = 0.16) -> np.ndarray:
    """A heavy, deep Enter / numpad key with a real bottom-out."""
    return key_model(
        seed=seed, duration=duration, pitch=pitch,
        click=0.78, body=1.9, spring=0.55, weight=1.65, brightness=0.72,
    )


def release(seed: int) -> np.ndarray:
    """Light, high key-release tick."""
    return key_model(
        seed=seed, duration=0.032, pitch=1.22,
        click=0.55, body=0.34, spring=0.55, weight=0.30, brightness=1.15,
    )


def shotgun(seed: int) -> np.ndarray:
    """Optional showpiece: a punchy, high crack over a short low blast."""
    rng = np.random.default_rng(seed)
    tt = t(0.20)
    n = len(tt)
    crack = shaped_noise(n, rng, low=1_200.0, high=20_000.0)
    crack *= np.exp(-tt / 0.0025) * 1.1
    blast = (np.sin(2 * math.pi * 72.0 * tt)
             + 0.5 * np.sin(2 * math.pi * 108.0 * tt))
    blast *= np.exp(-tt / 0.055) * 0.9
    body = shaped_noise(n, rng, low=180.0, high=3_500.0)
    body *= np.exp(-tt / 0.075) * 0.55
    return normalize(soft_clip(crack + blast + body, 1.3), 0.88)


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def write(name: str, data: np.ndarray):
    data = fade(normalize(data, 0.86), 0.9)
    pcm = np.clip(data, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    OUT.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT / name), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


def main():
    # The shipped sound set is now user-supplied weapon samples.  Regenerating
    # would overwrite them, so writing is opt-in.
    if "--write" not in sys.argv:
        print(
            "Refusing to write: the shipped sounds in\n"
            f"  {OUT}\n"
            "are user-supplied samples and running this script would overwrite\n"
            "them.  If you really want to regenerate the legacy synthesized\n"
            "clicky set, back up the folder first and run:\n"
            "    python3 tools/generate_sounds.py --write\n",
            file=sys.stderr,
        )
        return 1
    sounds = {
        # Balanced, bright default click.
        "default.wav": key_model(seed=BASE_SEED + 1, pitch=1.03),
        "test.wav": key_model(
            seed=BASE_SEED + 2, pitch=1.05, click=1.05, body=1.0,
        ),

        # Heavier keys.
        "thock.wav": key_model(
            seed=BASE_SEED + 3, duration=0.10, pitch=0.88,
            click=0.62, body=1.45, spring=0.55, weight=1.30, brightness=0.82,
        ),
        "space.wav": key_model(
            seed=BASE_SEED + 4, duration=0.13, pitch=0.80,
            click=0.85, body=1.70, spring=0.55, weight=1.90, brightness=0.78,
        ),
        "boom.wav": heavy(BASE_SEED + 5),
        "backspace.wav": key_model(
            seed=BASE_SEED + 6, duration=0.075, pitch=1.00,
            click=1.10, body=1.10, spring=0.90, weight=1.05,
        ),
        "numpad-1.wav": key_model(
            seed=BASE_SEED + 7, duration=0.08, pitch=0.95,
            click=1.00, body=1.25, spring=0.80, weight=1.25,
        ),
        "numpad-2.wav": key_model(
            seed=BASE_SEED + 8, duration=0.075, pitch=0.99,
            click=1.05, body=1.20, spring=0.85, weight=1.20,
        ),

        # Sharp, high keys.
        "escape.wav": key_model(
            seed=BASE_SEED + 9, duration=0.07, pitch=1.16,
            click=1.20, body=0.82, spring=1.10, weight=0.70, brightness=1.12,
        ),
        "letter-1.wav": key_model(
            seed=BASE_SEED + 10, pitch=1.00, click=1.00, body=1.00,
        ),
        "letter-2.wav": key_model(
            seed=BASE_SEED + 11, pitch=1.045, click=1.03, body=0.96,
        ),
        "letter-3.wav": key_model(
            seed=BASE_SEED + 12, pitch=0.965, click=0.98, body=1.04,
        ),
        "digit-1.wav": key_model(
            seed=BASE_SEED + 13, duration=0.072, pitch=1.09,
            click=1.10, body=0.82, spring=1.00, weight=0.75,
        ),
        "digit-2.wav": key_model(
            seed=BASE_SEED + 14, duration=0.070, pitch=1.14,
            click=1.12, body=0.78, spring=1.05, weight=0.70,
        ),
        "punct-1.wav": key_model(
            seed=BASE_SEED + 15, duration=0.060, pitch=1.22,
            click=1.15, body=0.62, spring=1.10, weight=0.55, brightness=1.15,
        ),
        "punct-2.wav": key_model(
            seed=BASE_SEED + 16, duration=0.058, pitch=1.29,
            click=1.18, body=0.58, spring=1.15, weight=0.50, brightness=1.18,
        ),
        "mod-1.wav": key_model(
            seed=BASE_SEED + 17, duration=0.048, pitch=1.30,
            click=0.90, body=0.45, spring=0.75, weight=0.40, brightness=1.20,
        ),
        "mod-2.wav": key_model(
            seed=BASE_SEED + 18, duration=0.044, pitch=1.38,
            click=0.88, body=0.42, spring=0.80, weight=0.36, brightness=1.22,
        ),
        "fn-1.wav": key_model(
            seed=BASE_SEED + 19, duration=0.055, pitch=1.18,
            click=1.00, body=0.55, spring=0.95, weight=0.45,
        ),
        "fn-2.wav": key_model(
            seed=BASE_SEED + 20, duration=0.052, pitch=1.26,
            click=1.02, body=0.52, spring=1.00, weight=0.42,
        ),
        "nav-1.wav": key_model(
            seed=BASE_SEED + 21, duration=0.068, pitch=1.06,
            click=1.00, body=0.85, spring=0.90, weight=0.75,
        ),
        "nav-2.wav": key_model(
            seed=BASE_SEED + 22, duration=0.064, pitch=1.10,
            click=1.02, body=0.80, spring=0.95, weight=0.72,
        ),

        "release.wav": release(BASE_SEED + 23),
        "shotgun.wav": shotgun(BASE_SEED + 24),
    }
    for name, data in sounds.items():
        write(name, data)

    manifest = {
        "name": "Kali Field Kit — High Clicky",
        "version": 2,
        "license": "MIT (synthesized for this project)",
        "sounds": [
            {"file": "default.wav", "label": "High click — default",
             "description": "Bright mechanical click with a crisp high transient"},
            {"file": "thock.wav", "label": "Deep thock",
             "description": "Deeper, heavier bottom-out with a softer click"},
            {"file": "boom.wav", "label": "Heavy Enter",
             "description": "Weighty Enter / numpad bottom-out"},
            {"file": "space.wav", "label": "Spacebar",
             "description": "Wide spacebar with a deep, long body"},
            {"file": "backspace.wav", "label": "Backspace",
             "description": "Strong, bright delete clack"},
            {"file": "escape.wav", "label": "Escape snap",
             "description": "Sharp, high escape click"},
            {"file": "letter-1.wav", "label": "Letter A",
             "description": "High clicky letter variant 1"},
            {"file": "letter-2.wav", "label": "Letter B",
             "description": "High clicky letter variant 2"},
            {"file": "letter-3.wav", "label": "Letter C",
             "description": "High clicky letter variant 3"},
            {"file": "digit-1.wav", "label": "Digit A",
             "description": "Bright digit click 1"},
            {"file": "digit-2.wav", "label": "Digit B",
             "description": "Bright digit click 2"},
            {"file": "mod-1.wav", "label": "Modifier A",
             "description": "Short, high modifier tick"},
            {"file": "mod-2.wav", "label": "Modifier B",
             "description": "Higher, lighter modifier tick"},
            {"file": "fn-1.wav", "label": "Function A",
             "description": "Crisp function-row click"},
            {"file": "fn-2.wav", "label": "Function B",
             "description": "Higher function-row click"},
            {"file": "nav-1.wav", "label": "Navigation A",
             "description": "Medium navigation click"},
            {"file": "nav-2.wav", "label": "Navigation B",
             "description": "Brighter navigation click"},
            {"file": "numpad-1.wav", "label": "Numpad A",
             "description": "Heavy numpad click 1"},
            {"file": "numpad-2.wav", "label": "Numpad B",
             "description": "Heavy numpad click 2"},
            {"file": "punct-1.wav", "label": "Punctuation A",
             "description": "Very high punctuation tick"},
            {"file": "punct-2.wav", "label": "Punctuation B",
             "description": "Highest punctuation tick"},
            {"file": "release.wav", "label": "Release tick",
             "description": "Light, high key-up tick"},
            {"file": "test.wav", "label": "Test hit",
             "description": "Balanced preview click"},
            {"file": "shotgun.wav", "label": "Shotgun",
             "description": "Optional punchy blast with a high crack"},
        ],
    }
    for entry in manifest["sounds"]:
        entry["source"] = "generated by tools/generate_sounds.py"
        entry["author"] = "KeySound contributors"
        entry["license"] = "MIT"
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {len(sounds)} sounds to {OUT}")


if __name__ == "__main__":
    main()
