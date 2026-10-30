"""XDG autostart support for Kali/Xfce, GNOME, and KDE."""
from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

from . import paths


def _python_launcher() -> list[str]:
    """Return a command that starts this checkout when not installed system-wide."""
    wrapper = Path("/usr/bin/keysound")
    if wrapper.exists():
        return [str(wrapper)]
    package_root = Path(__file__).resolve().parent.parent
    entry = package_root / "run.py"
    if entry.exists():
        return [sys.executable, str(entry)]
    return [sys.executable, "-m", "keysound"]


def is_enabled() -> bool:
    return paths.AUTOSTART_PATH.exists()


def set_enabled(enabled: bool) -> tuple[bool, str]:
    if not enabled:
        try:
            paths.AUTOSTART_PATH.unlink(missing_ok=True)
            return True, "Autostart disabled"
        except OSError as exc:
            return False, f"Could not remove autostart entry: {exc}"

    paths.AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    command = _python_launcher() + ["--minimized"]
    exec_line = " ".join(shlex.quote(part) for part in command)
    icon = str(paths.ICON_PATH)
    desktop = f"""[Desktop Entry]
Type=Application
Version=1.0
Name=KeySound
GenericName=Per-key keyboard sounds
Comment=Play a different sound for every physical key
Exec={exec_line}
Icon={icon}
Terminal=false
Categories=Utility;AudioVideo;
Keywords=keyboard;sound;audio;typing;
StartupNotify=false
X-GNOME-Autostart-enabled=true
"""
    try:
        tmp = paths.AUTOSTART_PATH.with_suffix(".desktop.tmp")
        tmp.write_text(desktop, encoding="utf-8")
        os.chmod(tmp, 0o644)
        os.replace(tmp, paths.AUTOSTART_PATH)
        return True, "Autostart enabled"
    except OSError as exc:
        return False, f"Could not write autostart entry: {exc}"


def sync_from_disk(config) -> None:
    """Keep the stored toggle honest if the user edits the .desktop file."""
    actual = is_enabled()
    if config.launch_at_login != actual:
        config.data["launchAtLogin"] = actual
        config.mark_dirty()
