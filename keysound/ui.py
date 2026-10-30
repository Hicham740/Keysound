"""GTK3 desktop UI for KeySound (Kali Linux edition)."""
from __future__ import annotations

import logging
import math
import os
import shlex
import subprocess
from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402

from . import paths
from .audio import SoundBank
from .config import (
    Config, KEY_VOLUME_MAX, JITTER_MAX, PITCH_MAX, PITCH_MIN, Rule,
    VOLUME_MAX, VOLUME_MIN,
)
from .keymap import (
    GROUP_LABELS, all_known_keys, key_group, key_label, keyboard_layout,
)
from .listener import BackendStatus, Listener

LOG = logging.getLogger(__name__)
BASE_KEY = 32
KEY_GAP = 4
KEY_HEIGHT = 42
FN_HEIGHT = 30
MODE_LABELS = [("single", "Single"), ("random", "Random"), ("roundRobin", "Round robin")]


def _cls(widget: Gtk.Widget, *names: str) -> None:
    ctx = widget.get_style_context()
    for name in names:
        ctx.add_class(name)


def _label(text: str = "", *classes: str, xalign: float = 0.0) -> Gtk.Label:
    lab = Gtk.Label(label=text)
    lab.set_xalign(xalign)
    if classes:
        _cls(lab, *classes)
    return lab


def _button(text: str, *classes: str) -> Gtk.Button:
    b = Gtk.Button(label=text)
    b.set_relief(Gtk.ReliefStyle.NONE)
    if classes:
        _cls(b, *classes)
    return b


def _separator(vertical: bool = False) -> Gtk.Separator:
    sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL)
    return sep


def _image(name: str, size: Gtk.IconSize = Gtk.IconSize.BUTTON) -> Gtk.Image:
    return Gtk.Image.new_from_icon_name(name, size)


class KeyboardView(Gtk.Box):
    def __init__(self, on_select: Callable[[str], None]):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        self.on_select = on_select
        self.buttons: dict[str, Gtk.Button] = {}
        self.selected: str | None = None
        self._flash_generation: dict[str, int] = {}
        self.set_halign(Gtk.Align.START)
        self._build()

    def _cap_button(self, cap, height: int) -> Gtk.Button:
        width = int(round(cap.width * BASE_KEY + (cap.width - 1) * KEY_GAP))
        b = Gtk.Button()
        b.set_size_request(width, height)
        b.set_hexpand(False)
        b.set_vexpand(False)
        b.set_relief(Gtk.ReliefStyle.NONE)
        b.set_can_focus(False)
        _cls(b, "key")
        if cap.key_id in {"KEY_LEFTCTRL", "KEY_RIGHTCTRL", "KEY_LEFTSHIFT",
                          "KEY_RIGHTSHIFT", "KEY_LEFTALT", "KEY_RIGHTALT",
                          "KEY_LEFTMETA", "KEY_RIGHTMETA", "KEY_CAPSLOCK",
                          "KEY_NUMLOCK", "KEY_MENU"}:
            _cls(b, "mod")
        if cap.accent:
            _cls(b, "accent")
        if cap.key_id.startswith("KEY_F") and cap.key_id[5:].isdigit():
            _cls(b, "fn")
        label = Gtk.Label(label=cap.label)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_justify(Gtk.Justification.CENTER)
        label.set_xalign(0.5)
        label.set_max_width_chars(9)
        _cls(label, "key-label")
        b.add(label)
        b.connect("clicked", lambda *_: self.on_select(cap.key_id))
        b.set_tooltip_text(f"{cap.label}  ·  {cap.key_id}")
        self.buttons[cap.key_id] = b
        return b

    def _row(self, caps, height: int, spacing: int = KEY_GAP) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=spacing)
        row.set_halign(Gtk.Align.START)
        row.set_size_request(-1, height)
        for cap in caps:
            row.pack_start(self._cap_button(cap, height), False, False, 0)
        return row

    def _build(self) -> None:
        layout = keyboard_layout()
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=KEY_GAP)
        for i, caps in enumerate(layout["main"]):
            main.pack_start(self._row(caps, FN_HEIGHT if i == 0 else KEY_HEIGHT), False, False, 0)

        nav = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=KEY_GAP)
        for i, caps in enumerate(layout["nav"]):
            height = FN_HEIGHT if i == 0 else KEY_HEIGHT
            if not caps:
                spacer = Gtk.Box()
                spacer.set_size_request(3 * BASE_KEY + 2 * KEY_GAP, height)
                nav.pack_start(spacer, False, False, 0)
                continue
            if i == 4:  # centre the Up arrow
                wrap = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
                wrap.set_size_request(3 * BASE_KEY + 2 * KEY_GAP, height)
                left = Gtk.Box()
                left.set_size_request(BASE_KEY + KEY_GAP, height)
                wrap.pack_start(left, False, False, 0)
                wrap.pack_start(self._cap_button(caps[0], height), False, False, 0)
                nav.pack_start(wrap, False, False, 0)
            else:
                nav.pack_start(self._row(caps, height), False, False, 0)

        numpad_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=KEY_GAP)
        top = Gtk.Box()
        top.set_size_request(4 * BASE_KEY + 3 * KEY_GAP, FN_HEIGHT)
        numpad_wrap.pack_start(top, False, False, 0)
        grid = Gtk.Grid()
        grid.set_row_spacing(KEY_GAP)
        grid.set_column_spacing(KEY_GAP)
        grid.set_halign(Gtk.Align.START)
        # left, top, width, height
        grid.attach(self._cap_button(layout["numpad"][0][0], KEY_HEIGHT), 0, 0, 1, 1)
        grid.attach(self._cap_button(layout["numpad"][0][1], KEY_HEIGHT), 1, 0, 1, 1)
        grid.attach(self._cap_button(layout["numpad"][0][2], KEY_HEIGHT), 2, 0, 1, 1)
        grid.attach(self._cap_button(layout["numpad"][0][3], KEY_HEIGHT), 3, 0, 1, 1)
        # row 1: 7 8 9 +
        grid.attach(self._cap_button(layout["numpad"][1][0], KEY_HEIGHT), 0, 1, 1, 1)
        grid.attach(self._cap_button(layout["numpad"][1][1], KEY_HEIGHT), 1, 1, 1, 1)
        grid.attach(self._cap_button(layout["numpad"][1][2], KEY_HEIGHT), 2, 1, 1, 1)
        grid.attach(self._cap_button(layout["numpad"][2][3], KEY_HEIGHT * 2 + KEY_GAP), 3, 1, 1, 2)
        # row 2: 4 5 6
        grid.attach(self._cap_button(layout["numpad"][2][0], KEY_HEIGHT), 0, 2, 1, 1)
        grid.attach(self._cap_button(layout["numpad"][2][1], KEY_HEIGHT), 1, 2, 1, 1)
        grid.attach(self._cap_button(layout["numpad"][2][2], KEY_HEIGHT), 2, 2, 1, 1)
        # row 3: 1 2 3 Enter
        grid.attach(self._cap_button(layout["numpad"][3][0], KEY_HEIGHT), 0, 3, 1, 1)
        grid.attach(self._cap_button(layout["numpad"][3][1], KEY_HEIGHT), 1, 3, 1, 1)
        grid.attach(self._cap_button(layout["numpad"][3][2], KEY_HEIGHT), 2, 3, 1, 1)
        grid.attach(self._cap_button(layout["numpad"][4][2], KEY_HEIGHT * 2 + KEY_GAP), 3, 3, 1, 2)
        # row 4: 0 (2u) .
        zero = self._cap_button(layout["numpad"][4][0], KEY_HEIGHT)
        zero.set_size_request(2 * BASE_KEY + KEY_GAP, KEY_HEIGHT)
        grid.attach(zero, 0, 4, 2, 1)
        grid.attach(self._cap_button(layout["numpad"][4][1], KEY_HEIGHT), 2, 4, 1, 1)
        numpad_wrap.pack_start(grid, False, False, 0)

        self.pack_start(main, False, False, 0)
        self.pack_start(nav, False, False, 0)
        self.pack_start(numpad_wrap, False, False, 0)

    def refresh(self, config: Config) -> None:
        for key_id, button in self.buttons.items():
            mapped = config.key_rule(key_id) is not None
            ctx = button.get_style_context()
            if mapped:
                ctx.add_class("mapped")
            else:
                ctx.remove_class("mapped")
            rule = config.resolve(key_id)
            names = ", ".join(rule.sounds[:3])
            if len(rule.sounds) > 3:
                names += "…"
            button.set_tooltip_text(f"{key_label(key_id)}  ·  {key_id}\n{rule.label}: {names}")

    def set_selected(self, key_id: str | None) -> None:
        if self.selected and self.selected in self.buttons:
            self.buttons[self.selected].get_style_context().remove_class("selected")
        self.selected = key_id
        if key_id and key_id in self.buttons:
            self.buttons[key_id].get_style_context().add_class("selected")

    def flash(self, key_id: str) -> None:
        button = self.buttons.get(key_id)
        if not button:
            return
        gen = self._flash_generation.get(key_id, 0) + 1
        self._flash_generation[key_id] = gen
        button.get_style_context().add_class("pressed")

        def clear():
            if self._flash_generation.get(key_id) == gen:
                button.get_style_context().remove_class("pressed")
            return False

        GLib.timeout_add(110, clear)


class RuleEditor(Gtk.Box):
    """Reusable editor for one key or one group fallback."""

    def __init__(self, bank: SoundBank, *,
                 on_apply: Callable[[list[str], str, float, float, float], None],
                 on_clear: Callable[[], None],
                 on_reset: Callable[[], None],
                 on_preview: Callable[[list[str], str, float, float, float], None]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.bank = bank
        self.on_apply = on_apply
        self.on_clear = on_clear
        self.on_reset = on_reset
        self.on_preview = on_preview
        self._loading = False
        self._context_key = ""
        self._allow_fallback = True
        self._fallback_label = "Use group fallback"
        self._sounds: list[str] = []
        self._mode = "single"
        self._volume = 1.0
        self._pitch = 1.0
        self._jitter = 0.015
        self._build()

    def _build(self) -> None:
        self.title = _label("", "title-xl")
        self.subtitle = _label("", "mono", "faint")
        self.source = _label("", "eyebrow")
        head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        head.pack_start(self.source, False, False, 0)
        head.pack_start(self.title, False, False, 0)
        head.pack_start(self.subtitle, False, False, 0)
        head_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        head_row.pack_start(head, True, True, 0)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        buttons.set_valign(Gtk.Align.CENTER)
        self.preview_btn = _button("Preview", "blue", "pill")
        self.preview_btn.set_valign(Gtk.Align.CENTER)
        self.preview_btn.connect("clicked", self._on_preview_clicked)
        buttons.pack_start(self.preview_btn, False, False, 0)
        self.reset_btn = _button("Reset", "ghost", "pill")
        self.reset_btn.set_valign(Gtk.Align.CENTER)
        self.reset_btn.connect("clicked", lambda *_: self.on_reset())
        buttons.pack_start(self.reset_btn, False, False, 0)
        head_row.pack_end(buttons, False, False, 0)
        self.pack_start(head_row, False, False, 0)
        self.pack_start(_separator(), False, False, 2)

        self.sound_label = _label("SOUND", "eyebrow")
        self.pack_start(self.sound_label, False, False, 0)
        self.sound_combo = Gtk.ComboBoxText()
        self.sound_combo.connect("changed", self._on_sound_changed)
        self.pack_start(self.sound_combo, False, False, 0)

        variant_head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        variant_head.pack_start(_label("VARIANTS", "eyebrow"), True, True, 0)
        self.add_variant_btn = _button("+ Add", "ghost", "pill")
        self.add_variant_btn.set_tooltip_text("Add the selected sound as another variant")
        self.add_variant_btn.connect("clicked", self._on_add_variant)
        variant_head.pack_end(self.add_variant_btn, False, False, 0)
        self.pack_start(variant_head, False, False, 0)
        self.variants = Gtk.FlowBox()
        self.variants.set_selection_mode(Gtk.SelectionMode.NONE)
        self.variants.set_max_children_per_line(3)
        self.variants.set_min_children_per_line(1)
        self.variants.set_column_spacing(4)
        self.variants.set_row_spacing(4)
        self.variants.set_homogeneous(False)
        self.pack_start(self.variants, False, False, 0)

        self.mode_label = _label("PLAYBACK MODE", "eyebrow")
        self.pack_start(self.mode_label, False, False, 0)
        self.mode_combo = Gtk.ComboBoxText()
        for mode_id, mode_label in MODE_LABELS:
            self.mode_combo.append(mode_id, mode_label)
        self.mode_combo.connect("changed", self._on_mode_changed)
        self.pack_start(self.mode_combo, False, False, 0)

        self.pack_start(_separator(), False, False, 2)
        self.volume_value = self._slider_row("VOLUME", 0, int(KEY_VOLUME_MAX * 100), self._on_volume)
        self.pitch_value = self._slider_row("PITCH", int(PITCH_MIN * 100), int(PITCH_MAX * 100), self._on_pitch)
        self.jitter_value = self._slider_row("PITCH JITTER", 0, int(JITTER_MAX * 100), self._on_jitter)

    def _slider_row(self, title: str, low: int, high: int, callback) -> Gtk.Label:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.pack_start(_label(title, "eyebrow"), False, False, 0)
        value = _label("", "volume-label")
        value.set_xalign(1.0)
        row.pack_end(value, False, False, 0)
        self.pack_start(row, False, False, 0)
        adjustment = Gtk.Adjustment(value=100 if high == 100 else (low + high) // 2, lower=low, upper=high, step_increment=1, page_increment=5)
        scale = Gtk.Scale.new(Gtk.Orientation.HORIZONTAL, adjustment)
        scale.set_draw_value(False)
        scale.set_hexpand(True)
        scale.connect("value-changed", callback)
        self.pack_start(scale, False, False, 0)
        setattr(self, f"{title.lower().replace(' ', '_')}_scale", scale)
        value.set_text(f"{int(adjustment.get_value())}%")
        return value

    # ------------------------------------------------------------------ load
    def rebuild_sounds(self) -> None:
        current = self.sound_combo.get_active_id()
        was = self._loading
        self._loading = True
        try:
            self._populate_combo()
            if current and self.sound_combo.set_active_id(current):
                return
            if self._sounds:
                self.sound_combo.set_active_id(self._sounds[0])
        finally:
            self._loading = was

    def _populate_combo(self) -> None:
        previous = self._loading
        self._loading = True
        try:
            self.sound_combo.remove_all()
            if self._allow_fallback:
                self.sound_combo.append("__fallback__", self._fallback_label)
            for name in self.bank.names():
                info = self.bank.info_for(name)
                label = info.label if info else name
                if info and info.custom:
                    label = f"{label}  ·  custom"
                self.sound_combo.append(name, label)
        finally:
            self._loading = previous

    def load(self, *, title: str, subtitle: str, source: str,
             sounds: list[str], mode: str, volume: float, pitch: float,
             jitter: float, allow_fallback: bool, fallback_label: str = "Use group fallback",
             can_reset: bool) -> None:
        self._loading = True
        try:
            self._context_key = subtitle
            self._allow_fallback = allow_fallback
            self._fallback_label = fallback_label
            self._sounds = [s for s in sounds if self.bank.get(s) is not None]
            self._mode = mode if mode in dict(MODE_LABELS) else "single"
            self._volume = max(0.0, min(KEY_VOLUME_MAX, volume))
            self._pitch = max(PITCH_MIN, min(PITCH_MAX, pitch))
            self._jitter = max(0.0, min(JITTER_MAX, jitter))
            self.title.set_text(title)
            self.subtitle.set_text(subtitle)
            self.source.set_text(source.upper())
            self._populate_combo()
            if self._sounds:
                self.sound_combo.set_active_id(self._sounds[0])
            elif allow_fallback:
                self.sound_combo.set_active_id("__fallback__")
            self.mode_combo.set_active_id(self._mode)
            self.volume_scale.set_value(round(self._volume * 100))
            self.pitch_scale.set_value(round(self._pitch * 100))
            self.pitch_jitter_scale.set_value(round(self._jitter * 100))
            self.volume_value.set_text(f"{round(self._volume * 100)}%")
            self.pitch_value.set_text(f"{round(self._pitch * 100)}%")
            self.jitter_value.set_text(f"{round(self._jitter * 100)}%")
            self.reset_btn.set_visible(can_reset)
            self._render_variants()
        finally:
            self._loading = False

    def _render_variants(self) -> None:
        for child in self.variants.get_children():
            self.variants.remove(child)
        for name in self._sounds:
            info = self.bank.info_for(name)
            text = info.label if info else name
            chip = _button(f"{text}  ×", "chip")
            chip.set_tooltip_text(f"Remove {name}")
            chip.connect("clicked", lambda _b, n=name: self._remove_variant(n))
            self.variants.add(chip)
            chip.show()
        self.variants.show()

    def _remove_variant(self, name: str) -> None:
        if len(self._sounds) <= 1:
            return
        if name in self._sounds:
            self._sounds.remove(name)
            self._render_variants()
            if self._sounds:
                was = self._loading
                self._loading = True
                try:
                    self.sound_combo.set_active_id(self._sounds[0])
                finally:
                    self._loading = was
            self._emit()

    def _on_add_variant(self, *_):
        name = self.sound_combo.get_active_id()
        if not name or name == "__fallback__" or name in self._sounds:
            return
        self._sounds.append(name)
        self._render_variants()
        was = self._loading
        self._loading = True
        try:
            self.sound_combo.set_active_id(self._sounds[0])
        finally:
            self._loading = was
        self._emit()

    def _on_sound_changed(self, combo):
        if self._loading:
            return
        name = combo.get_active_id()
        if name == "__fallback__":
            self._sounds = []
            self._render_variants()
            self.on_clear()
            return
        if name and self.bank.get(name) is not None:
            self._sounds = [name]
            self._render_variants()
            self._emit()

    def _on_mode_changed(self, combo):
        if self._loading:
            return
        mode = combo.get_active_id()
        if mode:
            self._mode = mode
            self._emit()

    def _on_volume(self, scale):
        if self._loading:
            return
        self._volume = scale.get_value() / 100.0
        self.volume_value.set_text(f"{int(scale.get_value())}%")
        self._emit()

    def _on_pitch(self, scale):
        if self._loading:
            return
        self._pitch = scale.get_value() / 100.0
        self.pitch_value.set_text(f"{int(scale.get_value())}%")
        self._emit()

    def _on_jitter(self, scale):
        if self._loading:
            return
        self._jitter = scale.get_value() / 100.0
        self.jitter_value.set_text(f"{int(scale.get_value())}%")
        self._emit()

    def _emit(self) -> None:
        if self._loading or not self._sounds:
            return
        self.on_apply(list(self._sounds), self._mode, self._volume, self._pitch, self._jitter)

    def _on_preview_clicked(self, *_):
        if self._sounds:
            self.on_preview(list(self._sounds), self._mode, self._volume, self._pitch, self._jitter)


class KeyInspector(Gtk.Box):
    def __init__(self, app, bank: SoundBank):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.app = app
        self.key_id: str | None = None
        self.editor = RuleEditor(
            bank,
            on_apply=self._apply,
            on_clear=self._clear,
            on_reset=self._clear,
            on_preview=self._preview,
        )
        self.pack_start(self.editor, False, False, 0)

    def load(self, key_id: str) -> None:
        self.key_id = key_id
        cfg: Config = self.app.config
        rule = cfg.key_rule(key_id)
        fallback = cfg.resolve(key_id)
        if rule:
            sounds = list(rule.sounds)
            mode, volume, pitch, jitter = rule.mode, rule.volume, rule.pitch, rule.jitter
            source = f"Custom override · {key_label(key_id)}"
            can_reset = True
            fallback_label = f"Use fallback ({fallback.label})"
        else:
            sounds = list(fallback.sounds)
            mode, volume, pitch, jitter = fallback.mode, fallback.volume, fallback.pitch, fallback.jitter
            source = f"Using {fallback.label}"
            can_reset = False
            fallback_label = f"Use fallback ({fallback.label})"
        group = GROUP_LABELS.get(key_group(key_id), "Controls")
        self.editor.load(
            title=key_label(key_id),
            subtitle=key_id,
            source=source,
            sounds=sounds,
            mode=mode,
            volume=volume,
            pitch=pitch,
            jitter=jitter,
            allow_fallback=True,
            fallback_label=fallback_label,
            can_reset=can_reset,
        )

    def _apply(self, sounds, mode, volume, pitch, jitter):
        if not self.key_id:
            return
        self.app.config.set_key_rule(self.key_id, sounds, mode, volume, pitch, jitter)
        self.app.config_changed()
        self.load(self.key_id)
        self.app.window.refresh_assignments()

    def _clear(self):
        if not self.key_id:
            return
        self.app.config.clear_key_rule(self.key_id)
        self.app.config_changed()
        self.load(self.key_id)
        self.app.window.refresh_assignments()

    def _preview(self, sounds, mode, volume, pitch, jitter):
        rule = Rule(tuple(sounds), mode, volume, pitch, jitter, "preview", "Preview")
        self.app.dispatcher.test_rule(rule)


class GroupInspector(Gtk.Box):
    def __init__(self, app, bank: SoundBank):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.app = app
        self.group = "letters"
        selector = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        selector.pack_start(_label("GROUP", "eyebrow"), False, False, 0)
        self.combo = Gtk.ComboBoxText()
        for group, label in GROUP_LABELS.items():
            self.combo.append(group, label)
        self.combo.connect("changed", self._on_group_changed)
        selector.pack_start(self.combo, True, True, 0)
        self.pack_start(selector, False, False, 0)
        self.editor = RuleEditor(
            bank,
            on_apply=self._apply,
            on_clear=lambda: None,
            on_reset=self._reset,
            on_preview=self._preview,
        )
        self.pack_start(self.editor, False, False, 0)

    def _on_group_changed(self, combo):
        group = combo.get_active_id()
        if group:
            self.load(group)

    def load(self, group: str | None = None) -> None:
        if group:
            self.group = group
        self.combo.set_active_id(self.group)
        cfg: Config = self.app.config
        raw = cfg.data.get("groups", {}).get(self.group, {})
        fallback = cfg.group_rule(self.group)
        if fallback:
            sounds = list(fallback.sounds)
            mode, volume, pitch, jitter = fallback.mode, fallback.volume, fallback.pitch, fallback.jitter
        else:
            from .config import clean_rule
            cleaned = clean_rule(raw)
            sounds = list(cleaned["sounds"])
            mode, volume, pitch, jitter = cleaned["mode"], cleaned["volume"], cleaned["pitch"], cleaned["jitter"]
        count = sum(1 for k in all_known_keys() if key_group(k) == self.group)
        self.editor.load(
            title=GROUP_LABELS[self.group],
            subtitle=f"{count} keys",
            source="Group fallback",
            sounds=sounds,
            mode=mode,
            volume=volume,
            pitch=pitch,
            jitter=jitter,
            allow_fallback=False,
            can_reset=True,
        )

    def _apply(self, sounds, mode, volume, pitch, jitter):
        self.app.config.set_group_rule(self.group, sounds, mode, volume, pitch, jitter)
        self.app.config_changed()
        self.load(self.group)
        self.app.window.refresh_assignments(keep_selection=True)

    def _reset(self):
        self.app.config.reset_group(self.group)
        self.app.config_changed()
        self.load(self.group)
        self.app.window.refresh_assignments(keep_selection=True)

    def _preview(self, sounds, mode, volume, pitch, jitter):
        rule = Rule(tuple(sounds), mode, volume, pitch, jitter, "preview", "Preview")
        self.app.dispatcher.test_rule(rule)


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.app = app
        self.set_title("KeySound")
        self.set_default_size(1280, 860)
        self.set_size_request(1040, 700)
        try:
            self.set_icon_from_file(str(paths.ICONS_DIR / "keysound-128.png"))
        except Exception:
            pass
        self._syncing = False
        self._save_source = 0
        self._toast_source = 0
        self.selected_key = "KEY_A"
        self.connect("delete-event", self._on_delete)
        self._build()
        self.refresh_all()
        self.select_key("KEY_A")

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_decoration_layout("minimize,maximize,close")
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        try:
            img = Gtk.Image.new_from_file(str(paths.ICONS_DIR / "keysound-32.png"))
            title_box.pack_start(img, False, False, 0)
        except Exception:
            pass
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        t = _label("KEYSOUND", "title")
        st = _label("PER-KEY SOUND  //  KALI EDITION", "subtitle")
        titles.pack_start(t, False, False, 0)
        titles.pack_start(st, False, False, 0)
        title_box.pack_start(titles, False, False, 0)
        header.set_custom_title(title_box)

        menu = Gtk.Menu()
        for label, callback in (
            ("Import sound…", lambda *_: self.app.choose_import_sound()),
            ("Import profile…", lambda *_: self.app.choose_import_profile()),
            ("Export profile…", lambda *_: self.app.choose_export_profile()),
            (None, None),
            ("Open config folder", lambda *_: self.app.open_folder(paths.CONFIG_DIR)),
            ("Input setup…", lambda *_: self.app.show_input_status()),
            ("About KeySound", lambda *_: self.app.show_about()),
            (None, None),
            ("Quit KeySound", lambda *_: self.app.quit_app()),
        ):
            if label is None:
                menu.append(Gtk.SeparatorMenuItem())
            else:
                item = Gtk.MenuItem(label=label)
                item.connect("activate", callback)
                menu.append(item)
        menu.show_all()
        menu_btn = Gtk.MenuButton()
        menu_btn.set_popup(menu)
        menu_btn.set_image(_image("open-menu-symbolic"))
        menu_btn.set_tooltip_text("Menu")
        header.pack_start(menu_btn)

        right = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.badge = _label("ARMED", "badge", "armed")
        self.badge.set_valign(Gtk.Align.CENTER)
        right.pack_start(self.badge, False, False, 0)
        self.power_switch = Gtk.Switch()
        self.power_switch.set_valign(Gtk.Align.CENTER)
        self.power_switch.set_tooltip_text("Arm or silence KeySound")
        self.power_switch.connect("notify::active", self._on_power_switch)
        right.pack_start(self.power_switch, False, False, 0)
        header.pack_end(right)
        self.set_titlebar(header)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_margin_top(16)
        outer.set_margin_bottom(0)
        outer.set_margin_start(16)
        outer.set_margin_end(16)
        overlay = Gtk.Overlay()
        overlay.add(outer)
        self.add(overlay)

        # Input access banner (only when using the X11 fallback or no backend).
        self.banner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        _cls(self.banner, "banner")
        self.banner_label = _label("", "tiny")
        self.banner_label.set_line_wrap(True)
        self.banner_label.set_xalign(0.0)
        self.banner.pack_start(self.banner_label, True, True, 0)
        setup_btn = _button("Input setup", "ghost", "pill")
        setup_btn.connect("clicked", lambda *_: self.app.show_input_status())
        self.banner.pack_end(setup_btn, False, False, 0)
        self.banner.hide()
        outer.pack_start(self.banner, False, False, 0)

        outer.pack_start(self._build_topbar(), False, False, 0)

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        outer.pack_start(body, True, True, 0)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        left.set_hexpand(True)
        body.pack_start(left, True, True, 0)

        kb_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        _cls(kb_card, "card")
        kb_card.set_margin_top(2)
        kb_card.set_margin_bottom(2)
        kb_card.set_margin_start(2)
        kb_card.set_margin_end(2)
        kb_head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        kb_head.set_margin_start(14)
        kb_head.set_margin_end(14)
        kb_head.set_margin_top(12)
        kb_head.pack_start(_label("PHYSICAL KEY MAP", "section-title"), False, False, 0)
        hint = _label("Click any key to assign its sound", "hint")
        hint.set_xalign(1.0)
        kb_head.pack_end(hint, False, False, 0)
        kb_card.pack_start(kb_head, False, False, 0)
        kb_line = _separator()
        kb_line.set_margin_start(12)
        kb_line.set_margin_end(12)
        kb_card.pack_start(kb_line, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        _cls(scroll, "keyboard-scroll")
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        scroll.set_shadow_type(Gtk.ShadowType.NONE)
        scroll.set_margin_start(12)
        scroll.set_margin_end(12)
        scroll.set_margin_top(10)
        scroll.set_margin_bottom(8)
        self.keyboard = KeyboardView(self.select_key)
        scroll.add(self.keyboard)
        kb_card.pack_start(scroll, True, True, 0)

        fallback_line = _separator()
        fallback_line.set_margin_start(12)
        fallback_line.set_margin_end(12)
        kb_card.pack_start(fallback_line, False, False, 0)

        fallback = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        fallback.set_margin_start(14)
        fallback.set_margin_end(14)
        fallback.set_margin_top(2)
        fallback.set_margin_bottom(10)
        fallback.pack_start(_label("DEFAULT FALLBACK", "eyebrow"), False, False, 0)
        self.default_combo = Gtk.ComboBoxText()
        self.default_combo.set_size_request(190, -1)
        self._populate_default_combo()
        self.default_combo.connect("changed", self._on_default_sound)
        self.default_combo.set_tooltip_text("Sound used when a key and its group are both silent")
        fallback.pack_start(self.default_combo, False, False, 0)
        preview_default = _button("Preview", "ghost", "pill")
        preview_default.set_valign(Gtk.Align.CENTER)
        preview_default.connect("clicked", lambda *_: self.app.test_default_sound())
        fallback.pack_start(preview_default, False, False, 0)
        fallback.pack_end(
            _label("Used only when a key and its group are silent", "hint"),
            False, False, 0,
        )
        kb_card.pack_start(fallback, False, False, 0)
        left.pack_start(kb_card, True, True, 0)

        self.left_footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.left_footer.set_margin_start(4)
        self.left_footer.set_margin_end(4)
        dot = Gtk.Box()
        _cls(dot, "status-dot")
        dot.set_size_request(7, 7)
        dot.set_valign(Gtk.Align.CENTER)
        self.backend_dot = dot
        self.backend_label = _label("", "tiny", "dim")
        self.left_footer.pack_start(dot, False, False, 0)
        self.left_footer.pack_start(self.backend_label, False, False, 0)
        self.left_footer.pack_end(_label("12 voices  ·  48 kHz  ·  local only", "tiny", "faint"), False, False, 0)
        left.pack_start(self.left_footer, False, False, 0)

        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        _cls(side, "card")
        side.set_size_request(362, -1)
        side.set_hexpand(False)
        body.pack_start(side, False, False, 0)

        switch_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        switch_box.set_margin_start(14)
        switch_box.set_margin_end(14)
        switch_box.set_margin_top(12)
        self.stack_switcher = Gtk.StackSwitcher()
        self.stack_switcher.set_halign(Gtk.Align.START)
        switch_box.pack_start(self.stack_switcher, False, False, 0)
        side.pack_start(switch_box, False, False, 0)
        side.pack_start(_separator(), False, False, 4)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(120)
        self.stack.set_margin_start(14)
        self.stack.set_margin_end(14)
        self.stack.set_margin_top(12)
        self.stack.set_margin_bottom(12)
        self.key_inspector = KeyInspector(self.app, self.app.bank)
        self.group_inspector = GroupInspector(self.app, self.app.bank)
        self.stack.add_titled(self._scroll(self.key_inspector), "key", "Key")
        self.stack.add_titled(self._scroll(self.group_inspector), "groups", "Groups")
        self.stack_switcher.set_stack(self.stack)
        side.pack_start(self.stack, True, True, 0)

        outer.pack_start(self._build_profile_bar(), False, False, 0)

        self.toast_revealer = Gtk.Revealer()
        self.toast_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        self.toast_revealer.set_halign(Gtk.Align.END)
        self.toast_revealer.set_valign(Gtk.Align.END)
        self.toast_revealer.set_margin_end(18)
        self.toast_revealer.set_margin_bottom(18)
        self.toast_label = _label("", "toast")
        self.toast_revealer.add(self.toast_label)
        overlay.add_overlay(self.toast_revealer)

    def _scroll(self, child: Gtk.Widget) -> Gtk.ScrolledWindow:
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_shadow_type(Gtk.ShadowType.NONE)
        sw.add(child)
        return sw

    def _populate_default_combo(self) -> None:
        was = self._syncing
        self._syncing = True
        try:
            self.default_combo.remove_all()
            for name in self.app.bank.names():
                info = self.app.bank.info_for(name)
                label = info.label if info else name
                if info and info.custom:
                    label = f"{label}  ·  custom"
                self.default_combo.append(name, label)
        finally:
            self._syncing = was

    def _build_topbar(self) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        _cls(card, "card")
        card.set_margin_start(2)
        card.set_margin_end(2)

        vol = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        vol.set_margin_start(14)
        vol.set_margin_top(10)
        vol.set_margin_bottom(10)
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        head.pack_start(_label("MASTER", "eyebrow"), False, False, 0)
        self.volume_label = _label("80%", "volume-label")
        head.pack_end(self.volume_label, False, False, 0)
        vol.pack_start(head, False, False, 0)
        self.volume_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 10, 100, 1)
        self.volume_scale.set_draw_value(False)
        self.volume_scale.set_size_request(175, -1)
        self.volume_scale.connect("value-changed", self._on_volume)
        vol.pack_start(self.volume_scale, False, False, 0)
        card.pack_start(vol, False, False, 0)

        card.pack_start(_separator(True), False, False, 4)

        toggles = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        toggles.set_margin_top(9)
        toggles.set_margin_bottom(9)
        self.repeat_switch = self._toggle(
            "Hold to repeat", "Play while a key is held down", self._on_repeat_switch)
        self.mod_switch = self._toggle(
            "Modifier keys", "Play a sound for Shift, Ctrl, Alt and Super", self._on_mod_switch)
        self.autostart_switch = self._toggle(
            "Start at login", "Launch KeySound hidden in the tray when you log in",
            self._on_autostart_switch)
        toggles.pack_start(self.repeat_switch[0], False, False, 0)
        toggles.pack_start(self.mod_switch[0], False, False, 0)
        toggles.pack_start(self.autostart_switch[0], False, False, 0)
        card.pack_start(toggles, False, False, 0)

        card.pack_start(_separator(True), False, False, 4)

        mute_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        mute_box.set_margin_top(10)
        mute_box.set_margin_bottom(10)
        self.mute_btn = _button("MUTE", "ghost", "pill")
        self.mute_btn.set_valign(Gtk.Align.CENTER)
        self.mute_btn.set_tooltip_text("Mute everywhere (Ctrl+Alt+Shift+M)")
        self.mute_btn.connect("clicked", lambda *_: self.app.toggle_mute())
        mute_box.pack_start(self.mute_btn, False, False, 0)
        card.pack_start(mute_box, False, False, 0)

        card.pack_end(self._build_test_button(), False, False, 0)
        return card

    def _build_test_button(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_margin_end(12)
        self.test_btn = _button("Test hit", "accent", "pill")
        self.test_btn.set_valign(Gtk.Align.CENTER)
        self.test_btn.set_tooltip_text("Preview the selected key's sound")
        self.test_btn.connect("clicked", lambda *_: self.app.test_sound())
        box.pack_end(self.test_btn, False, False, 0)
        return box

    def _toggle(self, title: str, tooltip: str, callback) -> tuple[Gtk.Box, Gtk.Switch]:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        box.set_tooltip_text(tooltip)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        labels.pack_start(_label(title, "tiny"), False, False, 0)
        box.pack_start(labels, False, False, 0)
        switch = Gtk.Switch()
        switch.set_valign(Gtk.Align.CENTER)
        box.pack_start(switch, False, False, 0)
        switch.connect("notify::active", callback)
        return box, switch

    def _build_profile_bar(self) -> Gtk.Box:
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        _cls(bar, "profile-bar")
        bar.set_margin_top(2)
        bar.set_margin_bottom(0)
        bar.set_margin_start(0)
        bar.set_margin_end(0)
        bar.set_border_width(0)
        privacy = _label("No keystrokes are logged, stored, or transmitted.", "statusbar")
        privacy.set_margin_start(12)
        privacy.set_margin_top(8)
        privacy.set_margin_bottom(8)
        bar.pack_start(privacy, True, True, 0)

        profile_label = _label("PROFILE", "eyebrow")
        bar.pack_start(profile_label, False, False, 0)
        self.profile_entry = Gtk.Entry()
        self.profile_entry.set_width_chars(22)
        self.profile_entry.set_placeholder_text("Profile name")
        self.profile_entry.connect("focus-out-event", self._on_profile_focus)
        self.profile_entry.connect("activate", lambda *_: self._commit_profile())
        bar.pack_start(self.profile_entry, False, False, 0)
        for text, cb in (("Import", self.app.choose_import_profile),
                         ("Export", self.app.choose_export_profile)):
            b = _button(text, "ghost", "pill")
            b.connect("clicked", lambda _b, f=cb: f())
            bar.pack_start(b, False, False, 0)
        open_cfg = _button("Settings folder", "ghost", "pill")
        open_cfg.connect("clicked", lambda *_: self.app.open_folder(paths.CONFIG_DIR))
        bar.pack_start(open_cfg, False, False, 0)
        bar.set_margin_end(0)
        return bar

    # -------------------------------------------------------------- actions
    def select_key(self, key_id: str) -> None:
        self.selected_key = key_id
        self.keyboard.set_selected(key_id)
        self.key_inspector.load(key_id)
        self.stack.set_visible_child_name("key")

    def flash_key(self, key_id: str) -> None:
        self.keyboard.flash(key_id)

    def refresh_assignments(self, keep_selection: bool = True) -> None:
        self.keyboard.refresh(self.app.config)
        if keep_selection and self.selected_key:
            self.keyboard.set_selected(self.selected_key)
        self.group_inspector.load(self.group_inspector.group)

    def refresh_all(self) -> None:
        cfg = self.app.config
        self._syncing = True
        try:
            self.power_switch.set_active(bool(cfg.data.get("enabled", True)))
            self.volume_scale.set_value(round(cfg.master_volume * 100))
            self.volume_label.set_text(f"{round(cfg.master_volume * 100)}%")
            self.repeat_switch[1].set_active(cfg.hold_to_repeat)
            self.mod_switch[1].set_active(cfg.modifiers_enabled)
            self.autostart_switch[1].set_active(cfg.launch_at_login)
            self.default_combo.set_active_id(str(cfg.data.get("defaultSound", "default.wav")))
            self.profile_entry.set_text(str(cfg.data.get("profileName", "Kali Field Kit")))
        finally:
            self._syncing = False
        self._update_badge()
        self._update_mute_button()
        self.keyboard.refresh(cfg)
        self._update_backend()
        self._update_banner()
        if self.selected_key:
            self.key_inspector.load(self.selected_key)
        self.group_inspector.load(self.group_inspector.group)

    def _update_badge(self) -> None:
        cfg = self.app.config
        for cls in ("armed", "safe", "muted"):
            self.badge.get_style_context().remove_class(cls)
        if cfg.muted:
            self.badge.set_text("MUTED")
            self.badge.get_style_context().add_class("muted")
        elif cfg.data.get("enabled", True):
            self.badge.set_text("ARMED")
            self.badge.get_style_context().add_class("armed")
        else:
            self.badge.set_text("SAFE")
            self.badge.get_style_context().add_class("safe")

    def _update_mute_button(self) -> None:
        if self.app.config.muted:
            self.mute_btn.set_label("UNMUTE")
            self.mute_btn.get_style_context().add_class("accent")
            self.mute_btn.get_style_context().remove_class("ghost")
        else:
            self.mute_btn.set_label("MUTE")
            self.mute_btn.get_style_context().remove_class("accent")
            self.mute_btn.get_style_context().add_class("ghost")

    def _update_backend(self) -> None:
        status: BackendStatus = self.app.listener.status
        self.backend_label.set_text(status.detail)
        ctx = self.backend_dot.get_style_context()
        for cls in ("warn", "bad"):
            ctx.remove_class(cls)
        if not status.active:
            ctx.add_class("bad")
        elif status.fallback:
            ctx.add_class("warn")

    def _update_banner(self) -> None:
        status = self.app.listener.status
        if status.active and not status.fallback:
            self.banner.hide()
            return
        self.banner.show_all()
        if not status.active:
            self.banner_label.set_text(
                "KeySound could not access a keyboard. On Wayland, evdev access is required. "
                "Run the supplied setup script, then log out and back in."
            )
            self.banner.get_style_context().add_class("error")
        else:
            self.banner_label.set_text(
                "XInput2 fallback is active and works on X11. For Wayland support and direct "
                "physical-key capture, add your user to the input group."
            )
            self.banner.get_style_context().remove_class("error")

    def toast(self, message: str, error: bool = False) -> None:
        if self._toast_source:
            GLib.source_remove(self._toast_source)
            self._toast_source = 0
        self.toast_label.set_text(message)
        ctx = self.toast_label.get_style_context()
        if error:
            ctx.add_class("error")
        else:
            ctx.remove_class("error")
        self.toast_revealer.set_reveal_child(True)

        def hide():
            self.toast_revealer.set_reveal_child(False)
            self._toast_source = 0
            return False

        self._toast_source = GLib.timeout_add(3800, hide)

    # -------------------------------------------------------------- signals
    def _on_power_switch(self, switch, _param):
        if self._syncing:
            return
        self.app.set_enabled(switch.get_active())

    def _on_volume(self, scale):
        if self._syncing:
            return
        value = scale.get_value() / 100.0
        self.volume_label.set_text(f"{int(scale.get_value())}%")
        self.app.set_master_volume(value)

    def _on_repeat_switch(self, switch, _param):
        if self._syncing:
            return
        self.app.config.data["holdToRepeat"] = switch.get_active()
        self.app.config_changed()

    def _on_mod_switch(self, switch, _param):
        if self._syncing:
            return
        self.app.config.data["modifiersEnabled"] = switch.get_active()
        self.app.config_changed()

    def _on_autostart_switch(self, switch, _param):
        if self._syncing:
            return
        self.app.set_autostart(switch.get_active())

    def _on_default_sound(self, combo):
        if self._syncing:
            return
        name = combo.get_active_id()
        if name:
            self.app.set_default_sound(name)

    def _on_profile_focus(self, entry, _event):
        self._commit_profile()
        return False

    def _commit_profile(self) -> None:
        name = self.profile_entry.get_text().strip()
        if name and name != self.app.config.data.get("profileName"):
            self.app.config.set_profile_name(name)
            self.app.config_changed()

    def _on_delete(self, *_):
        if self.app.tray and self.app.tray.available:
            self.hide()
            return True
        self.app.quit_app()
        return False

    def sync_mute(self) -> None:
        self._update_badge()
        self._update_mute_button()

    def sync_enabled(self) -> None:
        self._syncing = True
        self.power_switch.set_active(bool(self.app.config.data.get("enabled", True)))
        self._syncing = False
        self._update_badge()

    def sync_autostart(self) -> None:
        was = self._syncing
        self._syncing = True
        try:
            self.autostart_switch[1].set_active(self.app.config.launch_at_login)
        finally:
            self._syncing = was

    def reload_sounds(self) -> None:
        self.key_inspector.editor.rebuild_sounds()
        self.group_inspector.editor.rebuild_sounds()
        self._populate_default_combo()
        self.default_combo.set_active_id(str(self.app.config.data.get("defaultSound", "default.wav")))
        if self.selected_key:
            self.key_inspector.load(self.selected_key)
        self.group_inspector.load(self.group_inspector.group)

    def update_profile(self) -> None:
        self.profile_entry.set_text(str(self.app.config.data.get("profileName", "Kali Field Kit")))
