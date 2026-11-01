"""User sound library: importing, listing and removing custom WAV files.

Custom sounds live in ``~/.local/share/keysound/sounds`` (XDG_DATA_HOME is
respected) so they survive restarts and are separate from the read-only
built-in assets.  Everything here is pure filesystem logic so it can be tested
without GTK.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from . import paths
from .audio import decode_wav

PREFIX = "custom-"


class SoundImportError(ValueError):
    """Raised when a file cannot be imported as a custom sound."""


def _target_dir(dest_dir: Path | None) -> Path:
    target = Path(dest_dir) if dest_dir is not None else paths.CUSTOM_SOUNDS_DIR
    target.mkdir(parents=True, exist_ok=True)
    try:
        target.chmod(0o700)
    except OSError:
        pass
    return target


def sanitize_stem(stem: str) -> str:
    """Make a filesystem-safe, lower-case stem from a file name."""
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._").lower()
    return (clean[:36] or "sound")


def unique_destination(dest_dir: Path, stem: str) -> Path:
    """Return a non-existing ``custom-<stem>[-N].wav`` path."""
    stem = sanitize_stem(stem)
    candidate = dest_dir / f"{PREFIX}{stem}.wav"
    counter = 2
    while candidate.exists():
        candidate = dest_dir / f"{PREFIX}{stem[:30]}-{counter}.wav"
        counter += 1
    return candidate


def import_sound(source: Path | str, dest_dir: Path | None = None) -> Path:
    """Validate and copy a WAV into the user sound library.

    Raises :class:`SoundImportError` for missing, empty, or undecodable files.
    The destination always uses the basename of the source, so a crafted path
    cannot escape the library directory.
    """
    source = Path(source)
    if not source.is_file():
        raise SoundImportError(f"{source.name} is not a file")
    try:
        data = decode_wav(source)
    except Exception as exc:
        raise SoundImportError(f"not a readable WAV file: {exc}") from exc
    if data.size == 0:
        raise SoundImportError("the file contains no audio")

    target = _target_dir(dest_dir)
    destination = unique_destination(target, source.stem)
    try:
        shutil.copy2(source, destination)
    except OSError as exc:
        raise SoundImportError(f"could not save the sound: {exc}") from exc
    try:
        destination.chmod(0o600)
    except OSError:
        pass
    return destination


def custom_sounds(dest_dir: Path | None = None) -> list[Path]:
    """List user-imported WAV files, alphabetically."""
    target = Path(dest_dir) if dest_dir is not None else paths.CUSTOM_SOUNDS_DIR
    if not target.is_dir():
        return []
    return sorted(
        (p for p in target.iterdir() if p.is_file() and p.suffix.lower() in (".wav", ".wave")),
        key=lambda p: p.name.lower(),
    )


def remove_sound(name: str, dest_dir: Path | None = None) -> bool:
    """Delete one custom sound by name.

    Only a basename inside the library is accepted; paths such as
    ``../../settings.json`` raise :class:`SoundImportError`.
    """
    safe = Path(name).name
    if safe != name or not safe.lower().endswith((".wav", ".wave")):
        raise SoundImportError("invalid sound name")
    target = Path(dest_dir) if dest_dir is not None else paths.CUSTOM_SOUNDS_DIR
    path = target / safe
    try:
        if path.resolve().parent != target.resolve():
            raise SoundImportError("invalid sound path")
        path.unlink()
        return True
    except FileNotFoundError:
        return False
