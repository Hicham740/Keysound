"""XDG paths and application constants."""
from __future__ import annotations

import os
from pathlib import Path

APP_ID = "keysound"
APP_NAME = "KeySound"
APP_SLUG = "keysound"
VERSION = "1.0.0"

PACKAGE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = PACKAGE_DIR / "assets"
BUILTIN_SOUNDS_DIR = ASSETS_DIR / "sounds"
ICONS_DIR = ASSETS_DIR / "icons"


def _xdg(env: str, fallback: str) -> Path:
    value = os.environ.get(env)
    return Path(value).expanduser() if value else Path.home() / fallback


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config") / APP_SLUG
DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share") / APP_SLUG
CACHE_DIR = _xdg("XDG_CACHE_HOME", ".cache") / APP_SLUG
CONFIG_PATH = CONFIG_DIR / "settings.json"
CUSTOM_SOUNDS_DIR = DATA_DIR / "sounds"
PROFILES_DIR = CONFIG_DIR / "profiles"
AUTOSTART_DIR = _xdg("XDG_CONFIG_HOME", ".config") / "autostart"
AUTOSTART_PATH = AUTOSTART_DIR / f"{APP_SLUG}.desktop"
ICON_PATH = ICONS_DIR / "keysound.svg"


def ensure_dirs() -> None:
    for path in (CONFIG_DIR, DATA_DIR, CACHE_DIR, CUSTOM_SOUNDS_DIR, PROFILES_DIR):
        path.mkdir(parents=True, exist_ok=True)
        try:
            path.chmod(0o700)
        except OSError:
            pass
