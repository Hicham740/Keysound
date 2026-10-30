"""Ayatana/StatusNotifierItem tray integration for Xfce, GNOME and KDE."""
from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3 as AppIndicator  # noqa: E402
from gi.repository import Gtk  # noqa: E402

from . import paths  # noqa: E402

LOG = logging.getLogger(__name__)


class Tray:
    def __init__(self, app):
        self.app = app
        self.indicator = None
        self.menu = None
        self.armed_item = None
        self.mute_item = None
        self.available = False
        self._syncing = False
        self._build()

    def _build(self) -> None:
        try:
            self.indicator = AppIndicator.Indicator.new(
                "keysound",
                "keysound-tray",
                AppIndicator.IndicatorCategory.APPLICATION_STATUS,
            )
            self.indicator.set_icon_theme_path(str(paths.ICONS_DIR))
            self.indicator.set_icon_full("keysound-tray", "KeySound")
            self.indicator.set_title("KeySound")
            self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
            self.menu = Gtk.Menu()
            self.indicator.set_menu(self.menu)

            open_item = Gtk.MenuItem(label="Open KeySound")
            open_item.connect("activate", lambda *_: self.app.show_window())
            self.menu.append(open_item)

            self.armed_item = Gtk.CheckMenuItem(label="Armed")
            self.armed_item.connect("toggled", self._on_armed)
            self.menu.append(self.armed_item)

            self.mute_item = Gtk.CheckMenuItem(label="Mute")
            self.mute_item.connect("toggled", self._on_mute)
            self.menu.append(self.mute_item)

            self.autostart_item = Gtk.CheckMenuItem(label="Start at login")
            self.autostart_item.connect("toggled", self._on_autostart)
            self.menu.append(self.autostart_item)

            self.menu.append(Gtk.SeparatorMenuItem())

            test_item = Gtk.MenuItem(label="Test sound")
            test_item.connect("activate", lambda *_: self.app.test_sound())
            self.menu.append(test_item)

            status_item = Gtk.MenuItem(label="Input status…")
            status_item.connect("activate", lambda *_: self.app.show_input_status())
            self.menu.append(status_item)

            self.menu.append(Gtk.SeparatorMenuItem())

            quit_item = Gtk.MenuItem(label="Quit KeySound")
            quit_item.connect("activate", lambda *_: self.app.quit_app())
            self.menu.append(quit_item)

            self.menu.show_all()
            self.available = True
            self.refresh()
        except Exception as exc:
            LOG.warning("tray unavailable: %s", exc)
            self.available = False

    def _on_armed(self, item):
        if self._syncing:
            return
        self.app.set_enabled(item.get_active())

    def _on_mute(self, item):
        if self._syncing:
            return
        self.app.set_muted(item.get_active())

    def _on_autostart(self, item):
        if self._syncing:
            return
        self.app.set_autostart(item.get_active())

    def refresh(self) -> None:
        if not self.available:
            return
        self._syncing = True
        try:
            if self.armed_item:
                self.armed_item.set_active(bool(self.app.config.data.get("enabled", True)))
            if self.mute_item:
                self.mute_item.set_active(self.app.config.muted)
            if self.autostart_item:
                self.autostart_item.set_active(self.app.config.launch_at_login)
            if self.indicator:
                if self.app.config.muted:
                    self.indicator.set_icon_full("keysound-tray", "KeySound (muted)")
                else:
                    self.indicator.set_icon_full("keysound-tray", "KeySound")
        finally:
            self._syncing = False

    def destroy(self) -> None:
        if self.indicator:
            try:
                self.indicator.set_status(AppIndicator.IndicatorStatus.PASSIVE)
            except Exception:
                pass
            self.indicator = None
        self.available = False
