"""Turn physical key events into sound rules, mute chords, and UI feedback."""
from __future__ import annotations

import logging
import threading
from typing import Callable

from .audio import Mixer
from .config import Config
from .keymap import ALT_KEYS, CTRL_KEYS, MODIFIER_KEYS, SHIFT_KEYS

LOG = logging.getLogger(__name__)


class Dispatcher:
    """Thread-safe event dispatcher shared by evdev/XInput2 and GTK."""

    def __init__(self, config: Config, mixer: Mixer,
                 on_activity: Callable[[str], None] | None = None,
                 on_mute: Callable[[bool], None] | None = None):
        self.config = config
        self.mixer = mixer
        self.on_activity = on_activity
        self.on_mute = on_mute
        self._held: set[str] = set()
        self._lock = threading.RLock()

    def handle(self, key_id: str, value: int) -> None:
        """value follows evdev: 1 press, 2 auto-repeat, 0 release."""
        with self._lock:
            if value == 0:
                self._held.discard(key_id)
                self._maybe_release_sound(key_id)
                return

            self._held.add(key_id)

            # The mute chord is detected in the key stream so it also works
            # under Wayland, where global shortcut registration is restricted.
            if key_id == "KEY_M" and self._is_mute_chord(key_id):
                if value == 1:
                    muted = self.config.toggle_muted()
                    self.config.save()
                    if self.on_mute:
                        try:
                            self.on_mute(muted)
                        except Exception:
                            LOG.exception("mute callback failed")
                return

            repeat = value == 2
            if not self.config.enabled:
                return
            if key_id in MODIFIER_KEYS and not self.config.modifiers_enabled:
                return

            rule = self.config.resolve(key_id)
            if rule.repeat is False and repeat:
                return
            if repeat and rule.repeat is not True and not self.config.hold_to_repeat:
                return

            if self.mixer.play(rule, key_id):
                if self.on_activity:
                    try:
                        self.on_activity(key_id)
                    except Exception:
                        LOG.exception("activity callback failed")

    def _maybe_release_sound(self, key_id: str) -> None:
        if not self.config.enabled:
            return
        rule = self.config.resolve_key_up(key_id)
        if rule and self.mixer.play(rule, key_id):
            if self.on_activity:
                try:
                    self.on_activity(key_id)
                except Exception:
                    pass

    def _is_mute_chord(self, key_id: str) -> bool:
        if key_id != "KEY_M":
            return False
        return bool(
            (self._held & CTRL_KEYS)
            and (self._held & ALT_KEYS)
            and (self._held & SHIFT_KEYS)
        )

    def test_key(self, key_id: str) -> bool:
        rule = self.config.resolve(key_id)
        return self.mixer.play(rule, key_id, force=True)

    def test_rule(self, rule) -> bool:
        return self.mixer.play(rule, "TEST", force=True)

    def panic(self) -> None:
        self.mixer.panic()
