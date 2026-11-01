"""Application controller for the Kali Linux edition of KeySound."""
from __future__ import annotations

import logging
import os
import re
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402

from . import autostart, library, paths
from .audio import AudioEngine, Mixer, SoundBank
from .config import Config, Rule
from .dispatcher import Dispatcher
from .keymap import key_label
from .listener import Listener
from .tray import Tray
from .ui import MainWindow

LOG = logging.getLogger(__name__)


def _eyebrow(text: str) -> Gtk.Label:
    label = Gtk.Label(label=text)
    label.set_xalign(0.0)
    label.get_style_context().add_class("eyebrow")
    return label


class KeySoundApp(Gtk.Application):
    def __init__(self, *, start_minimized: bool = False, use_tray: bool = True,
                 screenshot: str | None = None):
        super().__init__(
            application_id="io.github.keysound.Kali",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.start_minimized = start_minimized
        self.use_tray = use_tray
        self.screenshot = screenshot
        self.window: MainWindow | None = None
        self.tray: Tray | None = None
        self.config = Config()
        self.bank = SoundBank()
        self.mixer = Mixer(self.bank, lambda: self.config)
        self.audio = AudioEngine(self.mixer)
        self.dispatcher = Dispatcher(
            self.config,
            self.mixer,
            on_activity=self._on_activity,
            on_mute=self._on_mute,
        )
        self.listener = Listener(self.dispatcher.handle)
        self._services_started = False
        self._save_source = 0
        self._first_activation = True

    # ------------------------------------------------------------- lifecycle
    def do_startup(self):
        Gtk.Application.do_startup(self)
        settings = Gtk.Settings.get_default()
        if settings:
            settings.set_property("gtk-application-prefer-dark-theme", True)
        try:
            Gtk.Window.set_default_icon_from_file(str(paths.ICONS_DIR / "keysound-128.png"))
        except Exception:
            pass
        provider = Gtk.CssProvider()
        try:
            provider.load_from_path(str(paths.ASSETS_DIR / "style.css"))
            screen = Gdk.Screen.get_default()
            if screen:
                Gtk.StyleContext.add_provider_for_screen(
                    screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
        except Exception:
            LOG.exception("could not load stylesheet")

    def do_activate(self):
        if self.window is None:
            self._start_services()
            self.window = MainWindow(self)
            self.window.connect("show", self._on_window_show)
        else:
            self.show_window()
            return
        if self.use_tray:
            self.tray = Tray(self)
        if self.start_minimized and self.tray and self.tray.available:
            # Realize without flashing the window on login.
            self.window.realize()
            self.start_minimized = False
        elif self.screenshot:
            self.window.show_all()
            self.start_minimized = False
            GLib.timeout_add(1400, self._take_screenshot)
        else:
            self.show_window()
        self._first_activation = False

    def _start_services(self):
        if self._services_started:
            return
        self._services_started = True
        paths.ensure_dirs()
        self.config.load()
        autostart.sync_from_disk(self.config)
        self.bank.load()
        self.audio.start()
        self.listener.start()
        if self.config.dirty:
            self.config.save()
        LOG.info("backend: %s", self.listener.status.detail)
        if self.audio.error:
            LOG.warning("audio: %s", self.audio.error)

    def do_shutdown(self):
        if self._save_source:
            GLib.source_remove(self._save_source)
            self._save_source = 0
        try:
            self.config.save()
        except Exception:
            LOG.exception("could not save settings at shutdown")
        self.listener.stop()
        self.audio.stop()
        if self.tray:
            self.tray.destroy()
        Gtk.Application.do_shutdown(self)

    # --------------------------------------------------------------- callbacks
    def _on_activity(self, key_id: str):
        if self.window:
            GLib.idle_add(self.window.flash_key, key_id)

    def _on_mute(self, muted: bool):
        GLib.idle_add(self._apply_mute_ui, muted)

    def _apply_mute_ui(self, muted: bool):
        if self.window:
            self.window.sync_mute()
            self.window.toast("Muted — Ctrl+Alt+Shift+M to unmute" if muted else "Unmuted")
        if self.tray:
            self.tray.refresh()
        return False

    def _on_window_show(self, *_):
        if self.window:
            self.window.refresh_all()

    def _take_screenshot(self):
        if not self.window or not self.screenshot:
            return False
        try:
            gdk_window = self.window.get_window()
            surface_w = gdk_window.get_width()
            surface_h = gdk_window.get_height()
            pixbuf = Gdk.pixbuf_get_from_window(gdk_window, 0, 0, surface_w, surface_h)
            # The GTK surface includes a translucent client-side shadow.  Crop
            # to the bounding box of fully opaque pixels so the screenshot is
            # just the window content.
            try:
                import numpy as np

                stride = pixbuf.get_rowstride()
                raw = np.frombuffer(pixbuf.get_pixels(), dtype=np.uint8)
                pixels = raw.reshape(surface_h, stride)[:, : surface_w * 4].reshape(surface_h, surface_w, 4)
                ys, xs = np.where(pixels[:, :, 3] >= 250)
                if xs.size:
                    x0, x1 = int(xs.min()), int(xs.max()) + 1
                    y0, y1 = int(ys.min()), int(ys.max()) + 1
                    if x1 > x0 and y1 > y0:
                        pixbuf = pixbuf.new_subpixbuf(x0, y0, x1 - x0, y1 - y0)
            except Exception:
                LOG.debug("could not crop screenshot shadow", exc_info=True)
            path = Path(self.screenshot)
            path.parent.mkdir(parents=True, exist_ok=True)
            pixbuf.savev(str(path), "png", [], [])
            print(f"screenshot: {path}")
        except Exception as exc:
            print(f"screenshot failed: {exc}", file=sys.stderr)
        self.quit_app()
        return False

    # --------------------------------------------------------------- commands
    def config_changed(self):
        self.config.mark_dirty()
        if self._save_source:
            GLib.source_remove(self._save_source)
        self._save_source = GLib.timeout_add(220, self._save_now)
        if self.tray:
            self.tray.refresh()

    def _save_now(self):
        self._save_source = 0
        try:
            self.config.save()
        except Exception as exc:
            if self.window:
                self.window.toast(f"Could not save settings: {exc}", error=True)
            else:
                LOG.exception("could not save settings")
        return False

    def save_now(self):
        if self._save_source:
            GLib.source_remove(self._save_source)
            self._save_source = 0
        self.config.save()

    def set_enabled(self, enabled: bool):
        self.config.set_enabled(enabled)
        if not enabled:
            self.mixer.panic()
        self.config_changed()
        if self.window:
            self.window.sync_enabled()
            self.window.toast("KeySound armed" if enabled else "KeySound silenced")
        if self.tray:
            self.tray.refresh()

    def set_muted(self, muted: bool):
        self.config.set_muted(muted)
        if muted:
            self.mixer.panic()
        self.config_changed()
        if self.window:
            self.window.sync_mute()
            self.window.toast("Muted — Ctrl+Alt+Shift+M to unmute" if muted else "Unmuted")
        if self.tray:
            self.tray.refresh()

    def toggle_mute(self):
        self.set_muted(not self.config.muted)

    def set_master_volume(self, value: float):
        self.config.set_master_volume(value)
        self.config_changed()

    def set_default_sound(self, name: str):
        if not name:
            return
        self.config.data["defaultSound"] = name
        self.config_changed()
        if self.window:
            self.window.refresh_assignments()

    def set_autostart(self, enabled: bool):
        ok, message = autostart.set_enabled(enabled)
        if ok:
            self.config.data["launchAtLogin"] = enabled
            self.config_changed()
        if self.window:
            self.window.sync_autostart()
            self.window.toast(message, error=not ok)
        if self.tray:
            self.tray.refresh()

    def test_default_sound(self):
        name = str(self.config.data.get("defaultSound", "default.wav"))
        rule = Rule((name,), "single", 1.0, 1.0, 0.0, "default-preview", "Default fallback")
        if not self.dispatcher.test_rule(rule) and self.window:
            self.window.toast("The default fallback sound is not available", error=True)

    def test_sound(self):
        key_id = self.window.selected_key if self.window else "KEY_ENTER"
        if not self.dispatcher.test_key(key_id or "KEY_ENTER"):
            if self.window:
                self.window.toast("No sound available for this key", error=True)

    def show_window(self):
        if not self.window:
            self.activate()
            return
        self.window.show_all()
        self.window.deiconify()
        self.window.present()
        self.window.refresh_all()

    def quit_app(self):
        try:
            self.save_now()
        except Exception:
            LOG.exception("save failed")
        self.quit()

    # --------------------------------------------------------------- dialogs
    def _file_dialog(self, title: str, action, filters=None, default_name=None) -> str | None:
        dialog = Gtk.FileChooserDialog(
            title=title, parent=self.window, action=action,
        )
        dialog.add_buttons(
            "Cancel", Gtk.ResponseType.CANCEL,
            "Open" if action == Gtk.FileChooserAction.OPEN else "Save",
            Gtk.ResponseType.ACCEPT,
        )
        dialog.set_modal(True)
        if filters:
            for label, patterns in filters:
                f = Gtk.FileFilter()
                f.set_name(label)
                for pattern in patterns:
                    f.add_pattern(pattern)
                dialog.add_filter(f)
        if default_name:
            dialog.set_current_name(default_name)
            dialog.set_do_overwrite_confirmation(True)
        response = dialog.run()
        filename = dialog.get_filename() if response == Gtk.ResponseType.ACCEPT else None
        dialog.destroy()
        return filename

    def choose_import_sound(self, on_imported=None):
        filename = self._file_dialog(
            "Add a sound", Gtk.FileChooserAction.OPEN,
            filters=[("WAV audio", ["*.wav", "*.WAVE"]), ("All files", ["*"])],
        )
        if not filename:
            return
        try:
            destination = library.import_sound(filename)
        except library.SoundImportError as exc:
            if self.window:
                self.window.toast(f"Could not add sound: {exc}", error=True)
            return
        self.bank.reload()
        if self.window:
            self.window.reload_sounds()
            self.window.toast(f"Added {destination.name} to your sound library")
        if on_imported:
            on_imported(destination.name)

    def remove_custom_sound(self, name: str) -> bool:
        try:
            removed = library.remove_sound(name)
        except library.SoundImportError as exc:
            if self.window:
                self.window.toast(f"Could not remove sound: {exc}", error=True)
            return False
        if not removed:
            return False

        cfg = self.config
        changed = False
        for section in ("keys", "keyUp"):
            section_data = cfg.data.get(section, {})
            for key_id, rule in list(section_data.items()):
                sounds = [s for s in rule.get("sounds", []) if s != name]
                if len(sounds) == len(rule.get("sounds", [])):
                    continue
                changed = True
                if sounds:
                    rule["sounds"] = sounds
                else:
                    del section_data[key_id]
        for rule in cfg.data.get("groups", {}).values():
            sounds = [s for s in rule.get("sounds", []) if s != name]
            if len(sounds) == len(rule.get("sounds", [])):
                continue
            changed = True
            if sounds:
                rule["sounds"] = sounds
            else:
                rule.update({"sounds": ["default.wav"], "mode": "single"})
        if cfg.data.get("defaultSound") == name:
            cfg.data["defaultSound"] = "default.wav"
            changed = True
        if changed:
            self.config_changed()

        self.bank.reload()
        if self.window:
            self.window.reload_sounds()
            self.window.toast(f"Removed {name}")
        return True

    def show_my_sounds(self):
        if not self.window:
            return
        dialog = Gtk.Dialog(title="My sounds", transient_for=self.window, modal=True)
        dialog.set_default_size(560, 430)
        dialog.add_button("Close", Gtk.ResponseType.CLOSE)
        add_btn = dialog.add_button("Add sound…", Gtk.ResponseType.NONE)

        content = dialog.get_content_area()
        content.set_margin_top(14)
        content.set_margin_bottom(12)
        content.set_margin_start(16)
        content.set_margin_end(16)
        content.set_spacing(8)
        content.pack_start(_eyebrow("YOUR SOUND LIBRARY"), False, False, 0)
        path_label = Gtk.Label(label=str(paths.CUSTOM_SOUNDS_DIR))
        path_label.set_xalign(0.0)
        path_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        path_label.get_style_context().add_class("hint")
        content.pack_start(path_label, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        listbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        scroll.add(listbox)
        content.pack_start(scroll, True, True, 0)

        def refresh():
            for child in list(listbox.get_children()):
                listbox.remove(child)
            files = library.custom_sounds()
            if not files:
                empty = Gtk.Label(
                    label="No custom sounds yet.\nUse “Add sound…” to import a WAV file.")
                empty.set_justify(Gtk.Justification.CENTER)
                empty.get_style_context().add_class("faint")
                listbox.pack_start(empty, False, False, 24)
            for path in files:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                row.get_style_context().add_class("card")
                row.set_margin_top(2)
                row.set_margin_bottom(2)
                info = self.bank.info_for(path.name)
                text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                name_label = Gtk.Label(label=info.label if info else path.name)
                name_label.set_xalign(0.0)
                detail = path.name
                if info and info.duration:
                    detail += f"  ·  {info.duration:.2f} s"
                detail += f"  ·  {path.stat().st_size // 1024 or 1} KB"
                detail_label = Gtk.Label(label=detail)
                detail_label.set_xalign(0.0)
                detail_label.get_style_context().add_class("hint")
                text.pack_start(name_label, False, False, 0)
                text.pack_start(detail_label, False, False, 0)
                row.pack_start(text, True, True, 8)

                preview = Gtk.Button(label="Preview")
                preview.get_style_context().add_class("pill")
                preview.connect("clicked", lambda _b, n=path.name: self.dispatcher.test_rule(
                    Rule((n,), "single", 1.0, 1.0, 0.0, "library-preview", n)))
                row.pack_end(preview, False, False, 4)

                remove = Gtk.Button(label="Remove")
                remove.get_style_context().add_class("pill")
                remove.get_style_context().add_class("ghost")
                remove.connect("clicked", lambda _b, n=path.name: confirm_remove(n))
                row.pack_end(remove, False, False, 4)
                listbox.pack_start(row, False, False, 0)
            listbox.show_all()

        def confirm_remove(name):
            confirm = Gtk.MessageDialog(
                transient_for=dialog, modal=True, message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text=f"Remove {name}?",
            )
            confirm.format_secondary_text(
                "The file is deleted from your sound library. Any key or category using it "
                "falls back to default.wav.")
            if confirm.run() == Gtk.ResponseType.YES:
                self.remove_custom_sound(name)
                refresh()
            confirm.destroy()

        def add_sound(*_):
            self.choose_import_sound(on_imported=lambda _name: refresh())

        add_btn.connect("clicked", add_sound)
        refresh()
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def choose_export_profile(self):
        default = re.sub(r"[^A-Za-z0-9._-]+", "-", str(self.config.data.get("profileName", "keysound"))).strip("-") or "keysound"
        filename = self._file_dialog(
            "Export profile", Gtk.FileChooserAction.SAVE,
            filters=[("KeySound profile", ["*.keysound"]), ("All files", ["*"])],
            default_name=default + ".keysound",
        )
        if not filename:
            return
        dest = Path(filename)
        if dest.suffix.lower() != ".keysound":
            dest = dest.with_suffix(".keysound")
        try:
            self.config.export_profile(dest)
            if self.window:
                self.window.toast(f"Exported {dest.name}")
        except Exception as exc:
            if self.window:
                self.window.toast(f"Export failed: {exc}", error=True)

    def choose_import_profile(self):
        filename = self._file_dialog(
            "Import profile", Gtk.FileChooserAction.OPEN,
            filters=[("KeySound profile", ["*.keysound", "*.zip"]), ("All files", ["*"])],
        )
        if not filename:
            return
        try:
            self.config.import_profile(Path(filename))
            self.config_changed()
            self.bank.reload()
            if self.window:
                self.window.reload_sounds()
                self.window.refresh_all()
                self.window.toast(f"Imported profile: {self.config.data.get('profileName')}")
            if self.tray:
                self.tray.refresh()
        except Exception as exc:
            if self.window:
                self.window.toast(f"Import failed: {exc}", error=True)

    def open_folder(self, path: Path):
        try:
            Gio.AppInfo.launch_default_for_uri(path.as_uri(), None)
        except Exception as exc:
            if self.window:
                self.window.toast(f"Could not open folder: {exc}", error=True)

    def show_input_status(self):
        status = self.listener.status
        dialog = Gtk.Dialog(title="Input access", parent=self.window, modal=True)
        dialog.set_default_size(560, -1)
        dialog.add_button("Close", Gtk.ResponseType.CLOSE)
        content = dialog.get_content_area()
        content.set_spacing(10)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(18)
        content.set_margin_end(18)
        head = Gtk.Label()
        head.set_markup("<b>Keyboard input backend</b>")
        head.set_xalign(0)
        content.add(head)
        body = Gtk.Label(label=status.detail)
        body.set_xalign(0)
        body.set_line_wrap(True)
        body.set_selectable(True)
        content.add(body)

        detail = Gtk.Label()
        detail.set_xalign(0)
        detail.set_line_wrap(True)
        if status.fallback:
            detail.set_markup(
                "<b>XInput2 fallback</b>\n"
                "This works on X11 (Xfce, GNOME on Xorg, KDE on Xorg). "
                "For Wayland or lower-level access, add your user to the input group:"
            )
        elif not status.active:
            detail.set_markup(
                "<b>No keyboard backend</b>\n"
                "KeySound needs either evdev access or an X11 session. "
                "On Wayland, evdev access is required. Run:"
            )
        else:
            detail.set_markup(
                "<b>evdev primary backend</b>\n"
                "Physical key codes are read directly from /dev/input. "
                "This works on X11 and Wayland. Hot-plugged keyboards are detected automatically."
            )
        content.add(detail)

        command = "sudo usermod -aG input $USER"
        cmd_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        entry = Gtk.Entry()
        entry.set_text(command)
        entry.set_editable(False)
        entry.set_hexpand(True)
        cmd_box.pack_start(entry, True, True, 0)
        copy_btn = Gtk.Button(label="Copy")
        copy_btn.connect("clicked", lambda *_: Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(command, -1))
        cmd_box.pack_start(copy_btn, False, False, 0)
        content.add(cmd_box)
        note = Gtk.Label(label="Then log out and back in (or reboot) and restart KeySound. The setup script does the same thing.")
        note.set_xalign(0)
        note.set_line_wrap(True)
        note.get_style_context().add_class("dim")
        content.add(note)

        privacy = Gtk.Label(label="Privacy: KeySound maps a key code to a sound and discards it. It never writes key codes to disk or the network.")
        privacy.set_xalign(0)
        privacy.set_line_wrap(True)
        privacy.get_style_context().add_class("tiny")
        privacy.get_style_context().add_class("faint")
        content.add(privacy)
        content.show_all()
        dialog.run()
        dialog.destroy()

    def show_about(self):
        dialog = Gtk.AboutDialog(parent=self.window, modal=True)
        dialog.set_program_name("KeySound")
        dialog.set_version(paths.VERSION)
        dialog.set_comments(
            "A per-key keyboard sound system for Kali Linux.\n\n"
            "Physical key codes are mapped to sounds and immediately discarded. "
            "No keystrokes are logged, stored, or transmitted.\n\n"
            "Application code: MIT. The bundled WAV samples are user-supplied; "
            "their author and licence are unknown — see CREDITS.md in the sounds "
            "folder and confirm the licence before redistributing."
        )
        dialog.set_license_type(Gtk.License.MIT_X11)
        dialog.set_copyright("2026 KeySound contributors. Sound samples: see CREDITS.md.")
        dialog.set_authors(["KeySound contributors"])
        try:
            dialog.set_logo(GdkPixbuf.Pixbuf.new_from_file_at_scale(
                str(paths.ICONS_DIR / "keysound-128.png"), 128, 128, True
            ))
        except Exception:
            pass
        dialog.run()
        dialog.destroy()


def diagnose() -> int:
    """Print non-sensitive environment diagnostics; never captures keystrokes."""
    import json

    from .audio import AudioEngine, Mixer, SoundBank
    from .listener import EvdevBackend, x11_keycode_map

    cfg = Config()
    cfg.load(create=False)
    bank = SoundBank()
    bank.load()
    mixer = Mixer(bank, lambda: cfg)
    audio = AudioEngine(mixer)
    audio.start()
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline and not audio.running and audio.error is None:
        time.sleep(0.05)
    ev = EvdevBackend(lambda *_: None).probe()
    out = {
        "version": paths.VERSION,
        "config": str(paths.CONFIG_PATH),
        "config_exists": paths.CONFIG_PATH.exists(),
        "sounds": len(bank.buffers),
        "sound_errors": bank.errors,
        "evdev": {"permission_ok": ev.permission_ok, "detail": ev.detail},
        "x11": {
            "display": bool(os.environ.get("DISPLAY")),
            "session": os.environ.get("XDG_SESSION_TYPE", ""),
            "keycodes_mapped": len(x11_keycode_map()),
        },
        "audio": {"running": audio.running, "error": audio.error},
        "groups": len(cfg.data.get("groups", {})),
        "keys_with_overrides": len(cfg.data.get("keys", {})),
        "privacy": "No key events are logged by diagnose().",
    }
    audio.stop()
    print(json.dumps(out, indent=2))
    return 0 if audio.running or audio.error is None else 1
