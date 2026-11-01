"""Persistent configuration, rule resolution, and profile bundles."""
from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import paths
from .keymap import (
    GROUP_LABELS, key_group, key_label,
)

# Every category falls back to the single "default.wav" sound so a fresh
# install sounds uniform; per-category (and per-key) overrides are opt-in.
DEFAULT_GROUPS: dict[str, dict[str, Any]] = {
    "letters": {
        "sounds": ["default.wav"],
        "mode": "single", "volume": 1.0, "pitch": 1.0, "jitter": 0.0,
        "enabled": True,
    },
    "digits": {
        "sounds": ["default.wav"],
        "mode": "single", "volume": 1.0, "pitch": 1.0, "jitter": 0.0,
        "enabled": True,
    },
    "punctuation": {
        "sounds": ["default.wav"],
        "mode": "single", "volume": 1.0, "pitch": 1.0, "jitter": 0.0,
        "enabled": True,
    },
    "modifiers": {
        "sounds": ["default.wav"],
        "mode": "single", "volume": 1.0, "pitch": 1.0, "jitter": 0.0,
        "enabled": True,
    },
    "function": {
        "sounds": ["default.wav"],
        "mode": "single", "volume": 1.0, "pitch": 1.0, "jitter": 0.0,
        "enabled": True,
    },
    "navigation": {
        "sounds": ["default.wav"],
        "mode": "single", "volume": 1.0, "pitch": 1.0, "jitter": 0.0,
        "enabled": True,
    },
    "numpad": {
        "sounds": ["default.wav"],
        "mode": "single", "volume": 1.0, "pitch": 1.0, "jitter": 0.0,
        "enabled": True,
    },
    "controls": {
        "sounds": ["default.wav"],
        "mode": "single", "volume": 1.0, "pitch": 1.0, "jitter": 0.0,
        "enabled": True,
    },
    "media": {
        "sounds": ["default.wav"],
        "mode": "single", "volume": 1.0, "pitch": 1.0, "jitter": 0.0,
        "enabled": True,
    },
}

# No per-key overrides ship by default: keys with no explicit assignment use
# their category, and every category above uses default.wav.
DEFAULT_KEYS: dict[str, dict[str, Any]] = {}

DEFAULT_SETTINGS: dict[str, Any] = {
    "version": 1,
    "profileName": "Kali Field Kit",
    "enabled": True,
    "muted": False,
    "masterVolume": 0.8,
    "holdToRepeat": False,
    "modifiersEnabled": True,
    "launchAtLogin": False,
    "muteHotkey": "Ctrl+Alt+Shift+M",
    "defaultSound": "default.wav",
    "groups": copy.deepcopy(DEFAULT_GROUPS),
    "keys": copy.deepcopy(DEFAULT_KEYS),
    "keyUp": {},
}

VALID_MODES = {"single", "random", "roundRobin"}
VOLUME_MIN = 0.1
VOLUME_MAX = 1.0
KEY_VOLUME_MAX = 1.5
PITCH_MIN = 0.5
PITCH_MAX = 2.0
JITTER_MAX = 0.10


@dataclass(frozen=True)
class Rule:
    sounds: tuple[str, ...]
    mode: str
    volume: float
    pitch: float
    jitter: float
    source: str
    label: str
    repeat: bool | None = None


def _clamp(value: Any, low: float, high: float, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, v))


def _clean_sound_name(name: Any) -> str | None:
    if not isinstance(name, str):
        return None
    name = name.strip().replace("\\", "/")
    if not name or "/" in name or name in (".", ".."):
        return None
    if not name.lower().endswith((".wav", ".wave")):
        return None
    return name


def clean_rule(raw: Any, *, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback = fallback or {}
    if not isinstance(raw, dict):
        raw = {}
    sounds: list[str] = []
    source_sounds = raw.get("sounds")
    if isinstance(source_sounds, list):
        for item in source_sounds:
            cleaned = _clean_sound_name(item)
            if cleaned and cleaned not in sounds:
                sounds.append(cleaned)
    elif "sound" in raw:
        cleaned = _clean_sound_name(raw.get("sound"))
        if cleaned:
            sounds.append(cleaned)
    if not sounds and fallback.get("sounds"):
        sounds = list(fallback["sounds"])
    mode = raw.get("mode", fallback.get("mode", "single"))
    if mode not in VALID_MODES:
        mode = "single"
    repeat = raw.get("repeat", fallback.get("repeat"))
    if repeat not in (True, False, None):
        repeat = None
    return {
        "sounds": sounds,
        "mode": mode,
        "volume": _clamp(raw.get("volume", fallback.get("volume", 1.0)), 0.0, KEY_VOLUME_MAX, 1.0),
        "pitch": _clamp(raw.get("pitch", fallback.get("pitch", 1.0)), PITCH_MIN, PITCH_MAX, 1.0),
        "jitter": _clamp(raw.get("jitter", fallback.get("jitter", 0.015)), 0.0, JITTER_MAX, 0.015),
        "enabled": bool(raw.get("enabled", fallback.get("enabled", True))),
        "repeat": repeat,
    }


class Config:
    def __init__(self, path: Path | None = None):
        self.path = path or paths.CONFIG_PATH
        self.data: dict[str, Any] = copy.deepcopy(DEFAULT_SETTINGS)
        self.load_error: str | None = None
        self._dirty = False

    # ------------------------------------------------------------------ load
    def load(self, *, create: bool = True) -> None:
        if not self.path.exists():
            self.data = copy.deepcopy(DEFAULT_SETTINGS)
            if create:
                self.save()
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("settings root must be an object")
            self.data = self._merge(raw)
        except Exception as exc:  # corrupt settings must not stop the app
            self.load_error = str(exc)
            backup = self.path.with_suffix(".json.corrupt")
            try:
                shutil.copy2(self.path, backup)
            except OSError:
                pass
            self.data = copy.deepcopy(DEFAULT_SETTINGS)

    def _merge(self, raw: dict[str, Any]) -> dict[str, Any]:
        out = copy.deepcopy(DEFAULT_SETTINGS)
        out.update({k: v for k, v in raw.items() if k not in ("groups", "keys", "keyUp")})
        out["masterVolume"] = _clamp(out.get("masterVolume", 0.8), VOLUME_MIN, VOLUME_MAX, 0.8)
        for bool_key in ("enabled", "muted", "holdToRepeat", "modifiersEnabled", "launchAtLogin"):
            out[bool_key] = bool(out.get(bool_key, DEFAULT_SETTINGS[bool_key]))
        out["version"] = 1
        out["profileName"] = str(out.get("profileName") or "Kali Field Kit")[:80]
        out["defaultSound"] = _clean_sound_name(out.get("defaultSound")) or "default.wav"
        out["muteHotkey"] = "Ctrl+Alt+Shift+M"

        groups: dict[str, dict[str, Any]] = {}
        raw_groups = raw.get("groups") if isinstance(raw.get("groups"), dict) else {}
        for name, default in DEFAULT_GROUPS.items():
            groups[name] = clean_rule(raw_groups.get(name, {}), fallback=default)
        out["groups"] = groups

        keys: dict[str, dict[str, Any]] = {}
        raw_keys = raw.get("keys") if isinstance(raw.get("keys"), dict) else {}
        if "keys" in raw and isinstance(raw.get("keys"), dict):
            # An explicit (even empty) key map is authoritative.  This matters
            # for profiles that intentionally clear the default overrides.
            for key_id, raw_rule in raw_keys.items():
                if not isinstance(key_id, str) or not key_id.startswith("KEY_"):
                    continue
                if not isinstance(raw_rule, dict):
                    continue
                cleaned = clean_rule(raw_rule)
                if cleaned["sounds"]:
                    keys[key_id] = cleaned
        else:
            keys = copy.deepcopy(DEFAULT_KEYS)
        out["keys"] = keys

        key_up: dict[str, dict[str, Any]] = {}
        raw_up = raw.get("keyUp") if isinstance(raw.get("keyUp"), dict) else {}
        for key_id, raw_rule in raw_up.items():
            if isinstance(key_id, str) and key_id.startswith("KEY_"):
                cleaned = clean_rule(raw_rule)
                if cleaned["sounds"]:
                    key_up[key_id] = cleaned
        out["keyUp"] = key_up
        return out

    # ------------------------------------------------------------------ save
    def save(self) -> None:
        paths.ensure_dirs()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.data, indent=2, sort_keys=False) + "\n"
        fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".json", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
            self._dirty = False
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    def mark_dirty(self) -> None:
        self._dirty = True

    @property
    def dirty(self) -> bool:
        return self._dirty

    # --------------------------------------------------------------- getters
    @property
    def enabled(self) -> bool:
        return bool(self.data.get("enabled", True)) and not self.muted

    @property
    def muted(self) -> bool:
        return bool(self.data.get("muted", False))

    @property
    def master_volume(self) -> float:
        return _clamp(self.data.get("masterVolume", 0.8), VOLUME_MIN, VOLUME_MAX, 0.8)

    @property
    def hold_to_repeat(self) -> bool:
        return bool(self.data.get("holdToRepeat", False))

    @property
    def modifiers_enabled(self) -> bool:
        return bool(self.data.get("modifiersEnabled", True))

    @property
    def launch_at_login(self) -> bool:
        return bool(self.data.get("launchAtLogin", False))

    def group_rule(self, group: str) -> Rule | None:
        raw = self.data.get("groups", {}).get(group)
        if not isinstance(raw, dict):
            return None
        cleaned = clean_rule(raw, fallback=DEFAULT_GROUPS.get(group, {}))
        if not cleaned["enabled"] or not cleaned["sounds"]:
            return None
        return self._to_rule(cleaned, source=f"group:{group}", label=f"{GROUP_LABELS.get(group, group)} group")

    def key_rule(self, key_id: str) -> Rule | None:
        raw = self.data.get("keys", {}).get(key_id)
        if not isinstance(raw, dict):
            return None
        cleaned = clean_rule(raw)
        if not cleaned["enabled"] or not cleaned["sounds"]:
            return None
        return self._to_rule(cleaned, source="key", label=key_label(key_id))

    def resolve(self, key_id: str) -> Rule:
        direct = self.key_rule(key_id)
        if direct:
            return direct
        group = self.group_rule(key_group(key_id))
        if group:
            return group
        default = _clean_sound_name(self.data.get("defaultSound")) or "default.wav"
        return Rule(
            sounds=(default,), mode="single", volume=1.0, pitch=1.0,
            jitter=0.01, source="default", label="Default fallback",
        )

    def resolve_key_up(self, key_id: str) -> Rule | None:
        raw = self.data.get("keyUp", {}).get(key_id)
        if not isinstance(raw, dict):
            return None
        cleaned = clean_rule(raw)
        if not cleaned["enabled"] or not cleaned["sounds"]:
            return None
        return self._to_rule(cleaned, source="keyUp", label=f"{key_label(key_id)} release")

    @staticmethod
    def _to_rule(cleaned: dict[str, Any], source: str, label: str) -> Rule:
        return Rule(
            sounds=tuple(cleaned["sounds"]), mode=cleaned["mode"],
            volume=cleaned["volume"], pitch=cleaned["pitch"],
            jitter=cleaned["jitter"], source=source, label=label,
            repeat=cleaned.get("repeat"),
        )

    # --------------------------------------------------------------- setters
    def set_enabled(self, value: bool) -> None:
        self.data["enabled"] = bool(value)
        self.mark_dirty()

    def set_muted(self, value: bool) -> None:
        self.data["muted"] = bool(value)
        self.mark_dirty()

    def toggle_muted(self) -> bool:
        self.data["muted"] = not self.muted
        self.mark_dirty()
        return self.muted

    def set_master_volume(self, value: float) -> None:
        self.data["masterVolume"] = _clamp(value, VOLUME_MIN, VOLUME_MAX, 0.8)
        self.mark_dirty()

    def set_hold_to_repeat(self, value: bool) -> None:
        self.data["holdToRepeat"] = bool(value)
        self.mark_dirty()

    def set_modifiers_enabled(self, value: bool) -> None:
        self.data["modifiersEnabled"] = bool(value)
        self.mark_dirty()

    def set_launch_at_login(self, value: bool) -> None:
        self.data["launchAtLogin"] = bool(value)
        self.mark_dirty()

    def set_profile_name(self, value: str) -> None:
        self.data["profileName"] = (value or "Kali Field Kit")[:80]
        self.mark_dirty()

    def set_key_rule(self, key_id: str, sounds: list[str], mode: str,
                     volume: float, pitch: float, jitter: float,
                     enabled: bool = True) -> None:
        cleaned = clean_rule({
            "sounds": sounds, "mode": mode, "volume": volume,
            "pitch": pitch, "jitter": jitter, "enabled": enabled,
        })
        if cleaned["sounds"]:
            self.data.setdefault("keys", {})[key_id] = cleaned
            self.mark_dirty()

    def clear_key_rule(self, key_id: str) -> None:
        keys = self.data.setdefault("keys", {})
        if key_id in keys:
            del keys[key_id]
            self.mark_dirty()

    def set_group_rule(self, group: str, sounds: list[str], mode: str,
                       volume: float, pitch: float, jitter: float,
                       enabled: bool = True) -> None:
        cleaned = clean_rule({
            "sounds": sounds, "mode": mode, "volume": volume,
            "pitch": pitch, "jitter": jitter, "enabled": enabled,
        })
        if cleaned["sounds"]:
            self.data.setdefault("groups", {})[group] = cleaned
            self.mark_dirty()

    def reset_group(self, group: str) -> None:
        self.data.setdefault("groups", {})[group] = copy.deepcopy(DEFAULT_GROUPS[group])
        self.mark_dirty()

    def reset_all(self) -> None:
        keep_login = self.data.get("launchAtLogin", False)
        self.data = copy.deepcopy(DEFAULT_SETTINGS)
        self.data["launchAtLogin"] = keep_login
        self.mark_dirty()

    # --------------------------------------------------------------- profiles
    def export_profile(self, destination: Path) -> None:
        """Export a self-contained .keysound profile zip."""
        destination = Path(destination)
        if destination.suffix.lower() != ".keysound":
            destination = destination.with_suffix(".keysound")
        used = set()
        for raw in list(self.data.get("keys", {}).values()) + list(self.data.get("groups", {}).values()):
            if isinstance(raw, dict):
                for name in raw.get("sounds", []):
                    if isinstance(name, str):
                        used.add(name)
        default = self.data.get("defaultSound")
        if isinstance(default, str):
            used.add(default)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("profile.json", json.dumps(self.data, indent=2) + "\n")
            manifest = {"format": "keysound-profile", "version": 1,
                        "created": datetime.now(timezone.utc).isoformat()}
            zf.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
            for name in sorted(used):
                source = resolve_sound_path(name)
                if source and source.exists() and source.parent == paths.CUSTOM_SOUNDS_DIR:
                    zf.write(source, f"custom_sounds/{name}")

    def import_profile(self, source: Path) -> None:
        source = Path(source)
        with zipfile.ZipFile(source) as zf:
            try:
                raw = json.loads(zf.read("profile.json").decode("utf-8"))
            except KeyError as exc:
                raise ValueError("profile is missing profile.json") from exc
            if not isinstance(raw, dict):
                raise ValueError("profile.json must contain an object")
            for member in zf.namelist():
                if member.startswith("custom_sounds/") and member.lower().endswith(".wav"):
                    name = Path(member).name
                    if _clean_sound_name(name):
                        paths.CUSTOM_SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
                        with zf.open(member) as src, open(paths.CUSTOM_SOUNDS_DIR / name, "wb") as dst:
                            shutil.copyfileobj(src, dst)
        merged = self._merge(raw)
        keep_login = self.data.get("launchAtLogin", False)
        self.data = merged
        self.data["launchAtLogin"] = keep_login
        self.mark_dirty()


def resolve_sound_path(name: str) -> Path | None:
    cleaned = _clean_sound_name(name)
    if not cleaned:
        return None
    custom = paths.CUSTOM_SOUNDS_DIR / cleaned
    if custom.exists():
        return custom
    builtin = paths.BUILTIN_SOUNDS_DIR / cleaned
    if builtin.exists():
        return builtin
    return None


def list_sound_files() -> dict[str, Path]:
    """Return available sounds by filename, custom sounds winning."""
    found: dict[str, Path] = {}
    for directory in (paths.BUILTIN_SOUNDS_DIR, paths.CUSTOM_SOUNDS_DIR):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.wav")):
            if path.is_file() and _clean_sound_name(path.name):
                found[path.name] = path
    return found
