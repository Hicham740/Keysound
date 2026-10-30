"""Global keyboard backends for Kali Linux.

Primary backend: evdev (`/dev/input/event*`), which works under both X11 and
Wayland and reports the physical key code.  Fallback backend: XInput2 raw
events, which works immediately on an X11 desktop without the `input` group.
The two backends emit the same `KEY_*` IDs and never persist key events.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import errno
import fcntl
import glob
import logging
import os
import select
import struct
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .keymap import CODE_TO_KEY, KEY_TO_CODE, KEYSYM_TO_KEY

LOG = logging.getLogger(__name__)

EV_KEY = 1
KEY_A = 30
KEY_MAX = 0x2FF
EVENT_STRUCT = struct.Struct("llHHi")
EVENT_SIZE = EVENT_STRUCT.size

KeyCallback = Callable[[str, int], None]


@dataclass
class BackendStatus:
    name: str
    active: bool
    detail: str
    permission_ok: bool = True
    fallback: bool = False


def _ioc(direction: int, kind: str, number: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord(kind) << 8) | number


EVIOCGNAME = _ioc(2, "E", 0x06, 256)
EVIOCGBIT_EV = _ioc(2, "E", 0x20, 4)


def _keyboard_at(fd: int) -> tuple[bool, str]:
    try:
        ev_bits = fcntl.ioctl(fd, EVIOCGBIT_EV, b"\0" * 4)
        if not (int.from_bytes(ev_bits, "little") & (1 << EV_KEY)):
            return False, ""
        key_bytes = (KEY_MAX + 7) // 8
        keys = fcntl.ioctl(fd, _ioc(2, "E", 0x21, key_bytes), b"\0" * key_bytes)
        if not (int.from_bytes(keys, "little") & (1 << KEY_A)):
            return False, ""
        name = fcntl.ioctl(fd, EVIOCGNAME, b"\0" * 256)
        return True, name.split(b"\0", 1)[0].decode("utf-8", "replace") or "Keyboard"
    except OSError:
        return False, ""


def _input_group_hint() -> str:
    user = os.environ.get("USER") or "your-user"
    return f"sudo usermod -aG input {user}  # then log out and back in"


class EvdevBackend:
    """Read every readable evdev keyboard, including hot-plugged ones."""

    def __init__(self, callback: KeyCallback):
        self.callback = callback
        self._running = False
        self._lock = threading.RLock()
        self._devices: dict[str, tuple[int, threading.Thread, str]] = {}
        self._watch_thread: threading.Thread | None = None
        self._saw_keyboard = False
        self._permission_denied = False
        self._enabled = False
        self.status = BackendStatus("evdev", False, "Not started")

    def probe(self) -> BackendStatus:
        paths = sorted(glob.glob("/dev/input/event*"))
        found = 0
        denied = 0
        names: list[str] = []
        for path in paths:
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
            except PermissionError:
                denied += 1
                continue
            except OSError:
                continue
            try:
                ok, name = _keyboard_at(fd)
                if ok:
                    found += 1
                    names.append(name)
            finally:
                os.close(fd)
        if found:
            return BackendStatus(
                "evdev", False,
                f"evdev ready: {found} keyboard{'s' if found != 1 else ''} ({', '.join(names[:3])})",
                permission_ok=True,
            )
        if denied:
            return BackendStatus(
                "evdev", False,
                "evdev permission required. " + _input_group_hint(),
                permission_ok=False,
            )
        return BackendStatus("evdev", False, "No evdev keyboard devices found")

    def start(self) -> bool:
        with self._lock:
            if self._running:
                return True
            self._running = True
            self._enabled = True
            self._saw_keyboard = False
            self._permission_denied = False
        self._scan()
        with self._lock:
            if not self._devices:
                self._enabled = False
                self._running = False
                return False
        self._watch_thread = threading.Thread(target=self._watch, name="keysound-evdev-hotplug", daemon=True)
        self._watch_thread.start()
        with self._lock:
            names = [name for (_, _, name) in self._devices.values()]
            self.status = BackendStatus(
                "evdev", True,
                f"evdev active: {len(names)} keyboard{'s' if len(names) != 1 else ''} ({', '.join(names[:3])})",
            )
        return True

    def _scan(self) -> None:
        current = set(glob.glob("/dev/input/event*"))
        with self._lock:
            known = set(self._devices)
        for path in sorted(current - known):
            self._open_device(path)
        # Dead threads remove themselves; close anything that vanished.
        for path in sorted(known - current):
            self._close_device(path)

    def _open_device(self, path: str) -> None:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        except PermissionError:
            with self._lock:
                self._permission_denied = True
            return
        except OSError:
            return
        ok, name = _keyboard_at(fd)
        if not ok:
            os.close(fd)
            return
        with self._lock:
            self._saw_keyboard = True
        thread = threading.Thread(
            target=self._read_loop, args=(path, fd, name),
            name=f"keysound-evdev-{Path(path).name}", daemon=True,
        )
        with self._lock:
            self._devices[path] = (fd, thread, name)
        thread.start()

    def _close_device(self, path: str) -> None:
        with self._lock:
            item = self._devices.pop(path, None)
        if item:
            fd, _, _ = item
            try:
                os.close(fd)
            except OSError:
                pass

    def _read_loop(self, path: str, fd: int, name: str) -> None:
        buf = b""
        while True:
            with self._lock:
                if not self._running or path not in self._devices:
                    break
            try:
                ready, _, _ = select.select([fd], [], [], 0.35)
            except (OSError, ValueError):
                break
            if not ready:
                continue
            try:
                chunk = os.read(fd, EVENT_SIZE * 64)
            except BlockingIOError:
                continue
            except OSError as exc:
                if exc.errno not in (errno.ENODEV, errno.EIO, errno.EBADF):
                    LOG.debug("evdev read ended for %s: %s", name, exc.errno)
                break
            if not chunk:
                break
            buf += chunk
            while len(buf) >= EVENT_SIZE:
                _sec, _usec, ev_type, code, value = EVENT_STRUCT.unpack(buf[:EVENT_SIZE])
                buf = buf[EVENT_SIZE:]
                if ev_type != EV_KEY or value not in (0, 1, 2):
                    continue
                key_id = CODE_TO_KEY.get(code, "KEY_UNKNOWN")
                if key_id == "KEY_UNKNOWN" and code == 0:
                    continue
                try:
                    self.callback(key_id, value)
                except Exception:
                    LOG.exception("key dispatch failed")
        with self._lock:
            self._devices.pop(path, None)
        try:
            os.close(fd)
        except OSError:
            pass

    def _watch(self) -> None:
        while True:
            with self._lock:
                if not self._running:
                    return
            time.sleep(1.2)
            self._scan()

    def stop(self) -> None:
        with self._lock:
            self._running = False
            self._enabled = False
            items = list(self._devices.values())
            self._devices.clear()
        for fd, thread, _ in items:
            try:
                os.close(fd)
            except OSError:
                pass
            thread.join(timeout=0.4)
        if self._watch_thread:
            self._watch_thread.join(timeout=0.5)


# --------------------------------------------------------------------------- X11

_X11 = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
_XI = ctypes.CDLL(ctypes.util.find_library("Xi") or "libXi.so.6")

_D = ctypes.c_void_p
_W = ctypes.c_ulong
_UL = ctypes.c_ulong
_I = ctypes.c_int
_B = ctypes.c_int


class _XIEventMask(ctypes.Structure):
    _fields_ = [
        ("deviceid", ctypes.c_int),
        ("mask_len", ctypes.c_int),
        ("mask", ctypes.POINTER(ctypes.c_ubyte)),
    ]


_X11.XOpenDisplay.restype = _D
_X11.XOpenDisplay.argtypes = [ctypes.c_char_p]
_X11.XCloseDisplay.restype = _I
_X11.XCloseDisplay.argtypes = [_D]
_X11.XDefaultRootWindow.restype = _W
_X11.XDefaultRootWindow.argtypes = [_D]
_X11.XConnectionNumber.restype = _I
_X11.XConnectionNumber.argtypes = [_D]
_X11.XPending.restype = _I
_X11.XPending.argtypes = [_D]
_X11.XNextEvent.restype = _I
_X11.XNextEvent.argtypes = [_D, ctypes.c_void_p]
_X11.XSync.restype = _I
_X11.XSync.argtypes = [_D, _B]
_X11.XGetEventData.restype = _B
_X11.XGetEventData.argtypes = [_D, ctypes.c_void_p]
_X11.XFreeEventData.restype = None
_X11.XFreeEventData.argtypes = [_D, ctypes.c_void_p]
_X11.XkbKeycodeToKeysym.restype = _UL
_X11.XkbKeycodeToKeysym.argtypes = [_D, ctypes.c_ubyte, _I, _I]
_X11.XKeysymToString.restype = ctypes.c_char_p
_X11.XKeysymToString.argtypes = [_UL]

_XI.XIQueryVersion.restype = _I
_XI.XIQueryVersion.argtypes = [_D, ctypes.POINTER(_I), ctypes.POINTER(_I)]
_XI.XISelectEvents.restype = _I
_XI.XISelectEvents.argtypes = [_D, _W, ctypes.c_void_p, _I]

_X_ERROR_HANDLER = ctypes.CFUNCTYPE(_I, _D, ctypes.c_void_p)


@_X_ERROR_HANDLER
def _ignore_x_error(_display, _event):
    return 0


_X11.XSetErrorHandler.restype = ctypes.c_void_p
_X11.XSetErrorHandler.argtypes = [_X_ERROR_HANDLER]
_X11.XSetErrorHandler(_ignore_x_error)


def x11_keycode_map() -> dict[int, str]:
    """Build a physical X11 keycode -> evdev-style key ID map.

    Xkb group 0 is the US layout.  The keycode, not the typed character, is
    what matters, so the mapping is stable when the layout changes.
    """
    display = _X11.XOpenDisplay(None)
    if not display:
        return {}
    mapping: dict[int, str] = {}
    try:
        for code in range(8, 256):
            keysym = _X11.XkbKeycodeToKeysym(display, code, 0, 0)
            if not keysym:
                continue
            raw = _X11.XKeysymToString(keysym)
            if not raw:
                continue
            name = raw.decode("ascii", "ignore")
            key_id = KEYSYM_TO_KEY.get(name)
            if key_id == "KEY_TOUCHPAD_TOGGLE":
                key_id = "KEY_UNKNOWN"
            if key_id:
                mapping[code] = key_id
    finally:
        _X11.XCloseDisplay(display)
    return mapping


class X11Backend:
    """XInput2 raw-event fallback for X11 sessions without evdev permission."""

    def __init__(self, callback: KeyCallback):
        self.callback = callback
        self._running = False
        self._thread: threading.Thread | None = None
        self._display = None
        self._keycodes = x11_keycode_map()
        self.status = BackendStatus(
            "xinput2", False,
            "XInput2 fallback available" if self._keycodes else "XInput2 unavailable",
            permission_ok=True, fallback=True,
        )

    def start(self) -> bool:
        if not os.environ.get("DISPLAY"):
            self.status = BackendStatus("xinput2", False, "No X11 display and no evdev permission", permission_ok=False)
            return False
        if not self._keycodes:
            self.status = BackendStatus("xinput2", False, "Could not read the X11 keymap", permission_ok=False)
            return False
        self._running = True
        self._thread = threading.Thread(target=self._run, name="keysound-xinput2", daemon=True)
        self._thread.start()
        # Give the thread a moment to open the display.
        for _ in range(20):
            if self.status.active or not self._thread.is_alive():
                break
            time.sleep(0.01)
        return self.status.active

    def _run(self) -> None:
        display = _X11.XOpenDisplay(None)
        if not display:
            self.status = BackendStatus("xinput2", False, "Could not open X11 display", permission_ok=False)
            return
        self._display = display
        try:
            major, minor = _I(2), _I(2)
            _XI.XIQueryVersion(display, ctypes.byref(major), ctypes.byref(minor))
            root = _X11.XDefaultRootWindow(display)
            maskbits = (ctypes.c_ubyte * 4)()
            # XI_RawKeyPress = 13, XI_RawKeyRelease = 14
            maskbits[13 // 8] |= 1 << (13 % 8)
            maskbits[14 // 8] |= 1 << (14 % 8)
            mask = _XIEventMask(
                1,  # XIAllMasterDevices
                4,
                ctypes.cast(maskbits, ctypes.POINTER(ctypes.c_ubyte)),
            )
            rc = _XI.XISelectEvents(display, root, ctypes.byref(mask), 1)
            _X11.XSync(display, 0)
            if rc != 0:
                self.status = BackendStatus("xinput2", False, "XInput2 selection failed", permission_ok=False)
                return
            self.status = BackendStatus(
                "xinput2", True,
                "XInput2 fallback active (X11). Add yourself to the input group for Wayland-ready evdev.",
                fallback=True,
            )
            event = (ctypes.c_ubyte * 192)()
            held: set[int] = set()
            last_release: dict[int, float] = {}
            fd = _X11.XConnectionNumber(display)
            while self._running:
                try:
                    ready, _, _ = select.select([fd], [], [], 0.25)
                except (OSError, ValueError):
                    break
                if not ready:
                    continue
                while self._running and _X11.XPending(display):
                    _X11.XNextEvent(display, event)
                    evtype = _I.from_buffer(event, 36).value
                    if evtype not in (13, 14):
                        continue
                    if not _X11.XGetEventData(display, event):
                        continue
                    try:
                        data = ctypes.c_void_p.from_buffer(event, 48).value
                        if not data:
                            continue
                        code = ctypes.cast(data, ctypes.POINTER(_I))[14]
                    finally:
                        _X11.XFreeEventData(display, event)
                    key_id = self._keycodes.get(code)
                    if not key_id:
                        continue
                    now = time.monotonic()
                    if evtype == 13:
                        repeat = code in held or (now - last_release.get(code, 0.0)) < 0.03
                        held.add(code)
                        value = 2 if repeat else 1
                    else:
                        held.discard(code)
                        last_release[code] = now
                        value = 0
                    try:
                        self.callback(key_id, value)
                    except Exception:
                        LOG.exception("key dispatch failed")
        finally:
            try:
                _X11.XCloseDisplay(display)
            except Exception:
                pass
            self._display = None
            if self._running:
                self.status = BackendStatus("xinput2", False, "XInput2 listener stopped", permission_ok=False)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.8)
        self.status = BackendStatus("xinput2", False, "Stopped", fallback=True)


class Listener:
    """Select evdev when permitted, otherwise use XInput2 on X11."""

    def __init__(self, callback: KeyCallback):
        self.callback = callback
        self.evdev = EvdevBackend(callback)
        self.x11 = X11Backend(callback)
        self.backend: EvdevBackend | X11Backend | None = None
        self.status = BackendStatus("none", False, "Not started")

    def start(self) -> BackendStatus:
        probe = self.evdev.probe()
        if probe.permission_ok:
            if self.evdev.start():
                self.backend = self.evdev
                self.status = self.evdev.status
                return self.status
        # No evdev access: X11 fallback if possible.
        if os.environ.get("DISPLAY") and self.x11.start():
            self.backend = self.x11
            self.status = self.x11.status
            if probe.permission_ok is False:
                self.status.detail = (
                    "XInput2 fallback active. For Wayland and lower-level access, run: "
                    + _input_group_hint()
                )
            return self.status
        self.status = probe
        if not probe.permission_ok:
            self.status.detail = (
                "No keyboard access. Run the setup script or: " + _input_group_hint()
            )
        return self.status

    def stop(self) -> None:
        if self.backend is self.evdev:
            self.evdev.stop()
        elif self.backend is self.x11:
            self.x11.stop()
        self.backend = None

    @property
    def mode(self) -> str:
        if isinstance(self.backend, EvdevBackend):
            return "evdev"
        if isinstance(self.backend, X11Backend):
            return "xinput2"
        return "none"
