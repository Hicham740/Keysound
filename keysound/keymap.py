"""Keyboard identity, layout metadata, and the built-in key groups.

The public key ID format is the Linux evdev `KEY_*` name.  evdev codes are
physical, so a mapping for KEY_A stays on the same physical key when the user
switches from QWERTY to AZERTY.  The X11 fallback converts X11 key symbols to
the same IDs so both backends share one configuration format.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


# Linux input-event-codes.h (the subset a desktop keyboard can produce).
_EVDEV_CODES: dict[str, int] = {
    "KEY_ESC": 1,
    "KEY_1": 2, "KEY_2": 3, "KEY_3": 4, "KEY_4": 5, "KEY_5": 6,
    "KEY_6": 7, "KEY_7": 8, "KEY_8": 9, "KEY_9": 10, "KEY_0": 11,
    "KEY_MINUS": 12, "KEY_EQUAL": 13, "KEY_BACKSPACE": 14, "KEY_TAB": 15,
    "KEY_Q": 16, "KEY_W": 17, "KEY_E": 18, "KEY_R": 19, "KEY_T": 20,
    "KEY_Y": 21, "KEY_U": 22, "KEY_I": 23, "KEY_O": 24, "KEY_P": 25,
    "KEY_LEFTBRACE": 26, "KEY_RIGHTBRACE": 27, "KEY_ENTER": 28,
    "KEY_LEFTCTRL": 29,
    "KEY_A": 30, "KEY_S": 31, "KEY_D": 32, "KEY_F": 33, "KEY_G": 34,
    "KEY_H": 35, "KEY_J": 36, "KEY_K": 37, "KEY_L": 38,
    "KEY_SEMICOLON": 39, "KEY_APOSTROPHE": 40, "KEY_GRAVE": 41,
    "KEY_LEFTSHIFT": 42, "KEY_BACKSLASH": 43,
    "KEY_Z": 44, "KEY_X": 45, "KEY_C": 46, "KEY_V": 47, "KEY_B": 48,
    "KEY_N": 49, "KEY_M": 50,
    "KEY_COMMA": 51, "KEY_DOT": 52, "KEY_SLASH": 53, "KEY_RIGHTSHIFT": 54,
    "KEY_KPASTERISK": 55, "KEY_LEFTALT": 56, "KEY_SPACE": 57,
    "KEY_CAPSLOCK": 58,
    "KEY_F1": 59, "KEY_F2": 60, "KEY_F3": 61, "KEY_F4": 62, "KEY_F5": 63,
    "KEY_F6": 64, "KEY_F7": 65, "KEY_F8": 66, "KEY_F9": 67, "KEY_F10": 68,
    "KEY_NUMLOCK": 69, "KEY_SCROLLLOCK": 70,
    "KEY_KP7": 71, "KEY_KP8": 72, "KEY_KP9": 73, "KEY_KPMINUS": 74,
    "KEY_KP4": 75, "KEY_KP5": 76, "KEY_KP6": 77, "KEY_KPPLUS": 78,
    "KEY_KP1": 79, "KEY_KP2": 80, "KEY_KP3": 81, "KEY_KP0": 82,
    "KEY_KPDOT": 83, "KEY_102ND": 86, "KEY_F11": 87, "KEY_F12": 88,
    "KEY_KPENTER": 96, "KEY_RIGHTCTRL": 97, "KEY_KPSLASH": 98,
    "KEY_SYSRQ": 99, "KEY_RIGHTALT": 100, "KEY_LINEFEED": 101,
    "KEY_HOME": 102, "KEY_UP": 103, "KEY_PAGEUP": 104, "KEY_LEFT": 105,
    "KEY_RIGHT": 106, "KEY_END": 107, "KEY_DOWN": 108, "KEY_PAGEDOWN": 109,
    "KEY_INSERT": 110, "KEY_DELETE": 111,
    "KEY_MUTE": 113, "KEY_VOLUMEDOWN": 114, "KEY_VOLUMEUP": 115,
    "KEY_POWER": 116, "KEY_KPEQUAL": 117, "KEY_KPPLUSMINUS": 118,
    "KEY_PAUSE": 119, "KEY_KPCOMMA": 121,
    "KEY_LEFTMETA": 125, "KEY_RIGHTMETA": 126, "KEY_COMPOSE": 127,
    "KEY_STOP": 128, "KEY_AGAIN": 129, "KEY_PROPS": 130, "KEY_UNDO": 131,
    "KEY_FRONT": 132, "KEY_COPY": 133, "KEY_OPEN": 134, "KEY_PASTE": 135,
    "KEY_FIND": 136, "KEY_CUT": 137, "KEY_HELP": 138, "KEY_MENU": 139,
    "KEY_CALC": 140, "KEY_SETUP": 141, "KEY_SLEEP": 142, "KEY_WAKEUP": 143,
    "KEY_FILE": 144, "KEY_SENDFILE": 145, "KEY_DELETEFILE": 146,
    "KEY_XFER": 147, "KEY_PROG1": 148, "KEY_PROG2": 149, "KEY_WWW": 150,
    "KEY_MSDOS": 151, "KEY_COFFEE": 152, "KEY_DIRECTION": 153,
    "KEY_CYCLEWINDOWS": 154, "KEY_MAIL": 155, "KEY_BOOKMARKS": 156,
    "KEY_COMPUTER": 157, "KEY_BACK": 158, "KEY_FORWARD": 159,
    "KEY_CLOSECD": 160, "KEY_EJECTCD": 161, "KEY_EJECTCLOSECD": 162,
    "KEY_NEXTSONG": 163, "KEY_PLAYPAUSE": 164, "KEY_PREVSONG": 165,
    "KEY_STOPCD": 166, "KEY_RECORD": 167, "KEY_REWIND": 168,
    "KEY_PHONE": 169, "KEY_ISO": 170, "KEY_CONFIG": 171,
    "KEY_HOMEPAGE": 172, "KEY_REFRESH": 173, "KEY_EXIT": 174,
    "KEY_MOVE": 175, "KEY_EDIT": 176, "KEY_SCROLLUP": 177,
    "KEY_SCROLLDOWN": 178, "KEY_NEW": 181, "KEY_REDO": 182,
    "KEY_F13": 183, "KEY_F14": 184, "KEY_F15": 185, "KEY_F16": 186,
    "KEY_F17": 187, "KEY_F18": 188, "KEY_F19": 189, "KEY_F20": 190,
    "KEY_F21": 191, "KEY_F22": 192, "KEY_F23": 193, "KEY_F24": 194,
    "KEY_PLAYCD": 200, "KEY_PAUSECD": 201, "KEY_PROG3": 202,
    "KEY_PROG4": 203, "KEY_DASHBOARD": 204, "KEY_SUSPEND": 205,
    "KEY_CLOSE": 206, "KEY_PLAY": 207, "KEY_FASTFORWARD": 208,
    "KEY_BASSBOOST": 209, "KEY_PRINT": 210, "KEY_HP": 211,
    "KEY_CAMERA": 212, "KEY_SOUND": 213, "KEY_QUESTION": 214,
    "KEY_EMAIL": 215, "KEY_CHAT": 216, "KEY_SEARCH": 217,
    "KEY_CONNECT": 218, "KEY_FINANCE": 219, "KEY_SPORT": 220,
    "KEY_SHOP": 221, "KEY_ALTERASE": 222, "KEY_CANCEL": 223,
    "KEY_BRIGHTNESSDOWN": 224, "KEY_BRIGHTNESSUP": 225, "KEY_MEDIA": 226,
    "KEY_SWITCHVIDEOMODE": 227, "KEY_KBDILLUMTOGGLE": 228,
    "KEY_KBDILLUMDOWN": 229, "KEY_KBDILLUMUP": 230, "KEY_SEND": 231,
    "KEY_REPLAY": 232, "KEY_FORWARDMAIL": 233, "KEY_SAVE": 234,
    "KEY_DOCUMENTS": 235, "KEY_BATTERY": 236, "KEY_BLUETOOTH": 237,
    "KEY_WLAN": 238, "KEY_UWB": 239, "KEY_UNKNOWN": 240,
    "KEY_VIDEO_NEXT": 241, "KEY_VIDEO_PREV": 242,
    "KEY_BRIGHTNESS_CYCLE": 243, "KEY_BRIGHTNESS_AUTO": 244,
    "KEY_DISPLAY_OFF": 245, "KEY_WWAN": 246, "KEY_RFKILL": 247,
    "KEY_MICMUTE": 248,
}

CODE_TO_KEY: dict[int, str] = {code: name for name, code in _EVDEV_CODES.items()}
KEY_TO_CODE: dict[str, int] = dict(_EVDEV_CODES)

# X11/keysym names -> evdev names.  Xkb group 0 is the US layout; this makes
# the fallback physical rather than character based.
KEYSYM_TO_KEY: dict[str, str] = {
    "Escape": "KEY_ESC",
    "BackSpace": "KEY_BACKSPACE",
    "Tab": "KEY_TAB",
    "Return": "KEY_ENTER",
    "Linefeed": "KEY_LINEFEED",
    "Control_L": "KEY_LEFTCTRL",
    "Control_R": "KEY_RIGHTCTRL",
    "Shift_L": "KEY_LEFTSHIFT",
    "Shift_R": "KEY_RIGHTSHIFT",
    "Alt_L": "KEY_LEFTALT",
    "Alt_R": "KEY_RIGHTALT",
    "ISO_Level3_Shift": "KEY_RIGHTALT",
    "ISO_Level5_Shift": "KEY_COMPOSE",
    "Super_L": "KEY_LEFTMETA",
    "Super_R": "KEY_RIGHTMETA",
    "Meta_L": "KEY_LEFTMETA",
    "Meta_R": "KEY_RIGHTMETA",
    "Caps_Lock": "KEY_CAPSLOCK",
    "Num_Lock": "KEY_NUMLOCK",
    "Scroll_Lock": "KEY_SCROLLLOCK",
    "Print": "KEY_SYSRQ",
    "Sys_Req": "KEY_SYSRQ",
    "Pause": "KEY_PAUSE",
    "Menu": "KEY_MENU",
    "space": "KEY_SPACE",
    "minus": "KEY_MINUS",
    "equal": "KEY_EQUAL",
    "bracketleft": "KEY_LEFTBRACE",
    "bracketright": "KEY_RIGHTBRACE",
    "semicolon": "KEY_SEMICOLON",
    "apostrophe": "KEY_APOSTROPHE",
    "grave": "KEY_GRAVE",
    "backslash": "KEY_BACKSLASH",
    "comma": "KEY_COMMA",
    "period": "KEY_DOT",
    "slash": "KEY_SLASH",
    "less": "KEY_102ND",
    "greater": "KEY_102ND",
    "KP_0": "KEY_KP0", "KP_Insert": "KEY_KP0",
    "KP_1": "KEY_KP1", "KP_End": "KEY_KP1",
    "KP_2": "KEY_KP2", "KP_Down": "KEY_KP2",
    "KP_3": "KEY_KP3", "KP_Next": "KEY_KP3",
    "KP_4": "KEY_KP4", "KP_Left": "KEY_KP4",
    "KP_5": "KEY_KP5", "KP_Begin": "KEY_KP5",
    "KP_6": "KEY_KP6", "KP_Right": "KEY_KP6",
    "KP_7": "KEY_KP7", "KP_Home": "KEY_KP7",
    "KP_8": "KEY_KP8", "KP_Up": "KEY_KP8",
    "KP_9": "KEY_KP9", "KP_Prior": "KEY_KP9",
    "KP_Decimal": "KEY_KPDOT", "KP_Delete": "KEY_KPDOT",
    "KP_Add": "KEY_KPPLUS",
    "KP_Subtract": "KEY_KPMINUS",
    "KP_Multiply": "KEY_KPASTERISK",
    "KP_Divide": "KEY_KPSLASH",
    "KP_Enter": "KEY_KPENTER",
    "KP_Equal": "KEY_KPEQUAL",
    "XF86AudioMute": "KEY_MUTE",
    "XF86AudioLowerVolume": "KEY_VOLUMEDOWN",
    "XF86AudioRaiseVolume": "KEY_VOLUMEUP",
    "XF86AudioPlay": "KEY_PLAYPAUSE",
    "XF86AudioPause": "KEY_PLAYPAUSE",
    "XF86AudioNext": "KEY_NEXTSONG",
    "XF86AudioPrev": "KEY_PREVSONG",
    "XF86AudioStop": "KEY_STOPCD",
    "XF86AudioRecord": "KEY_RECORD",
    "XF86AudioRewind": "KEY_REWIND",
    "XF86AudioForward": "KEY_FASTFORWARD",
    "XF86AudioMedia": "KEY_MEDIA",
    "XF86AudioMicMute": "KEY_MICMUTE",
    "XF86Mail": "KEY_MAIL",
    "XF86HomePage": "KEY_HOMEPAGE",
    "XF86Back": "KEY_BACK",
    "XF86Forward": "KEY_FORWARD",
    "XF86Search": "KEY_SEARCH",
    "XF86Calculator": "KEY_CALC",
    "XF86Sleep": "KEY_SLEEP",
    "XF86WakeUp": "KEY_WAKEUP",
    "XF86PowerOff": "KEY_POWER",
    "XF86Display": "KEY_SWITCHVIDEOMODE",
    "XF86MonBrightnessUp": "KEY_BRIGHTNESSUP",
    "XF86MonBrightnessDown": "KEY_BRIGHTNESSDOWN",
    "XF86KbdLightOnOff": "KEY_KBDILLUMTOGGLE",
    "XF86KbdBrightnessUp": "KEY_KBDILLUMUP",
    "XF86KbdBrightnessDown": "KEY_KBDILLUMDOWN",
    "XF86TouchpadToggle": "KEY_TOUCHPAD_TOGGLE",
    "XF86WLAN": "KEY_WLAN",
    "XF86Bluetooth": "KEY_BLUETOOTH",
}

for _c in "abcdefghijklmnopqrstuvwxyz":
    KEYSYM_TO_KEY[_c] = f"KEY_{_c.upper()}"
for _d in "0123456789":
    KEYSYM_TO_KEY[_d] = f"KEY_{_d}"
for _i in range(1, 25):
    KEYSYM_TO_KEY[f"F{_i}"] = f"KEY_F{_i}"

# Keys that count as modifiers for the global toggle and mute chord.
MODIFIER_KEYS = {
    "KEY_LEFTCTRL", "KEY_RIGHTCTRL",
    "KEY_LEFTSHIFT", "KEY_RIGHTSHIFT",
    "KEY_LEFTALT", "KEY_RIGHTALT",
    "KEY_LEFTMETA", "KEY_RIGHTMETA",
}

CTRL_KEYS = {"KEY_LEFTCTRL", "KEY_RIGHTCTRL"}
SHIFT_KEYS = {"KEY_LEFTSHIFT", "KEY_RIGHTSHIFT"}
ALT_KEYS = {"KEY_LEFTALT", "KEY_RIGHTALT"}

LETTER_KEYS = tuple(f"KEY_{c}" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
DIGIT_KEYS = tuple(f"KEY_{d}" for d in "1234567890")
FUNCTION_KEYS = tuple(f"KEY_F{i}" for i in range(1, 25))
NAVIGATION_KEYS = (
    "KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT",
    "KEY_HOME", "KEY_END", "KEY_PAGEUP", "KEY_PAGEDOWN",
    "KEY_INSERT", "KEY_DELETE",
)
NUMPAD_KEYS = (
    "KEY_NUMLOCK", "KEY_KPSLASH", "KEY_KPASTERISK", "KEY_KPMINUS",
    "KEY_KP7", "KEY_KP8", "KEY_KP9", "KEY_KPPLUS",
    "KEY_KP4", "KEY_KP5", "KEY_KP6", "KEY_KP1", "KEY_KP2", "KEY_KP3",
    "KEY_KP0", "KEY_KPDOT", "KEY_KPENTER", "KEY_KPEQUAL",
)
PUNCTUATION_KEYS = (
    "KEY_MINUS", "KEY_EQUAL", "KEY_LEFTBRACE", "KEY_RIGHTBRACE",
    "KEY_SEMICOLON", "KEY_APOSTROPHE", "KEY_GRAVE", "KEY_BACKSLASH",
    "KEY_COMMA", "KEY_DOT", "KEY_SLASH", "KEY_102ND",
)
CONTROL_KEYS = (
    "KEY_ESC", "KEY_TAB", "KEY_ENTER", "KEY_BACKSPACE", "KEY_SPACE",
    "KEY_SYSRQ", "KEY_SCROLLLOCK", "KEY_PAUSE", "KEY_MENU",
)
MEDIA_KEYS = (
    "KEY_MUTE", "KEY_VOLUMEDOWN", "KEY_VOLUMEUP", "KEY_PLAYPAUSE",
    "KEY_NEXTSONG", "KEY_PREVSONG", "KEY_STOPCD", "KEY_RECORD",
    "KEY_REWIND", "KEY_MAIL", "KEY_HOMEPAGE", "KEY_BACK", "KEY_FORWARD",
    "KEY_SEARCH", "KEY_CALC", "KEY_SLEEP", "KEY_WAKEUP", "KEY_POWER",
    "KEY_SWITCHVIDEOMODE", "KEY_BRIGHTNESSUP", "KEY_BRIGHTNESSDOWN",
    "KEY_WLAN", "KEY_BLUETOOTH", "KEY_MICMUTE",
)

GROUP_OF_KEY: dict[str, str] = {}
for _name in LETTER_KEYS:
    GROUP_OF_KEY[_name] = "letters"
for _name in DIGIT_KEYS:
    GROUP_OF_KEY[_name] = "digits"
for _name in FUNCTION_KEYS:
    GROUP_OF_KEY[_name] = "function"
for _name in NAVIGATION_KEYS:
    GROUP_OF_KEY[_name] = "navigation"
for _name in NUMPAD_KEYS:
    GROUP_OF_KEY[_name] = "numpad"
for _name in PUNCTUATION_KEYS:
    GROUP_OF_KEY[_name] = "punctuation"
for _name in MODIFIER_KEYS | {"KEY_CAPSLOCK"}:
    GROUP_OF_KEY[_name] = "modifiers"
for _name in CONTROL_KEYS:
    GROUP_OF_KEY[_name] = "controls"
for _name in MEDIA_KEYS:
    GROUP_OF_KEY[_name] = "media"

GROUP_LABELS = {
    "letters": "Letters",
    "digits": "Digits",
    "punctuation": "Punctuation",
    "modifiers": "Modifiers",
    "function": "Function keys",
    "navigation": "Navigation",
    "numpad": "Numpad",
    "controls": "Controls",
    "media": "Media & system",
}

# Human-friendly labels used in the inspector and on keycaps.
_LABELS = {
    "KEY_ESC": "Esc", "KEY_TAB": "Tab", "KEY_ENTER": "Enter",
    "KEY_BACKSPACE": "Backspace", "KEY_SPACE": "Space",
    "KEY_LEFTCTRL": "Ctrl", "KEY_RIGHTCTRL": "Ctrl",
    "KEY_LEFTSHIFT": "Shift", "KEY_RIGHTSHIFT": "Shift",
    "KEY_LEFTALT": "Alt", "KEY_RIGHTALT": "AltGr",
    "KEY_LEFTMETA": "Super", "KEY_RIGHTMETA": "Super",
    "KEY_CAPSLOCK": "Caps", "KEY_NUMLOCK": "Num", "KEY_SCROLLLOCK": "Scroll",
    "KEY_SYSRQ": "PrtSc", "KEY_PAUSE": "Pause", "KEY_MENU": "Menu",
    "KEY_HOME": "Home", "KEY_END": "End", "KEY_PAGEUP": "PgUp",
    "KEY_PAGEDOWN": "PgDn", "KEY_INSERT": "Ins", "KEY_DELETE": "Del",
    "KEY_UP": "↑", "KEY_DOWN": "↓", "KEY_LEFT": "←", "KEY_RIGHT": "→",
    "KEY_KPSLASH": "/", "KEY_KPASTERISK": "*", "KEY_KPMINUS": "−",
    "KEY_KPPLUS": "+", "KEY_KPENTER": "Enter", "KEY_KPDOT": ".",
    "KEY_KPEQUAL": "=", "KEY_102ND": "\\",
    "KEY_MINUS": "−", "KEY_EQUAL": "=", "KEY_LEFTBRACE": "[",
    "KEY_RIGHTBRACE": "]", "KEY_SEMICOLON": ";", "KEY_APOSTROPHE": "'",
    "KEY_GRAVE": "`", "KEY_BACKSLASH": "\\", "KEY_COMMA": ",",
    "KEY_DOT": ".", "KEY_SLASH": "/",
    "KEY_MUTE": "Mute", "KEY_VOLUMEDOWN": "Vol−", "KEY_VOLUMEUP": "Vol+",
    "KEY_PLAYPAUSE": "Play", "KEY_NEXTSONG": "Next", "KEY_PREVSONG": "Prev",
    "KEY_STOPCD": "Stop", "KEY_RECORD": "Rec", "KEY_REWIND": "Rew",
    "KEY_MAIL": "Mail", "KEY_HOMEPAGE": "Home", "KEY_BACK": "Back",
    "KEY_FORWARD": "Fwd", "KEY_SEARCH": "Search", "KEY_CALC": "Calc",
    "KEY_SLEEP": "Sleep", "KEY_WAKEUP": "Wake", "KEY_POWER": "Power",
    "KEY_SWITCHVIDEOMODE": "Display", "KEY_BRIGHTNESSUP": "Bri+",
    "KEY_BRIGHTNESSDOWN": "Bri−", "KEY_WLAN": "WiFi",
    "KEY_BLUETOOTH": "BT", "KEY_MICMUTE": "Mic",
}

for _d in "0123456789":
    _LABELS[f"KEY_{_d}"] = _d
for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    _LABELS[f"KEY_{_c}"] = _c
for _i in range(1, 25):
    _LABELS[f"KEY_F{_i}"] = f"F{_i}"
for _i in range(10):
    _LABELS[f"KEY_KP{_i}"] = str(_i)


def key_label(key_id: str) -> str:
    if key_id in _LABELS:
        return _LABELS[key_id]
    if key_id.startswith("KEY_"):
        return key_id[4:].replace("_", " ").title()
    return key_id


def key_group(key_id: str) -> str:
    return GROUP_OF_KEY.get(key_id, "controls")


def sorted_groups() -> list[str]:
    return list(GROUP_LABELS.keys())


def all_known_keys() -> Iterable[str]:
    return _EVDEV_CODES.keys()


@dataclass(frozen=True)
class Keycap:
    key_id: str
    label: str
    width: float = 1.0
    height: float = 1.0
    row: int = 0
    section: str = "main"
    accent: bool = False


def _cap(key_id: str, width: float = 1.0, accent: bool = False, label: str | None = None) -> Keycap:
    return Keycap(key_id, label or key_label(key_id), width=width, accent=accent)


def keyboard_layout() -> dict[str, list[list[Keycap]]]:
    """Return the visual 104-key layout used by the settings window.

    The three sections are laid out side by side by the UI.  Widths are in
    keycap units; the UI multiplies them by the current key size.
    """
    main: list[list[Keycap]] = []
    main.append([
        _cap("KEY_ESC"),
        _cap("KEY_F1"), _cap("KEY_F2"), _cap("KEY_F3"), _cap("KEY_F4"),
        _cap("KEY_F5"), _cap("KEY_F6"), _cap("KEY_F7"), _cap("KEY_F8"),
        _cap("KEY_F9"), _cap("KEY_F10"), _cap("KEY_F11"), _cap("KEY_F12"),
    ])
    main.append([
        _cap("KEY_GRAVE"), _cap("KEY_1"), _cap("KEY_2"), _cap("KEY_3"),
        _cap("KEY_4"), _cap("KEY_5"), _cap("KEY_6"), _cap("KEY_7"),
        _cap("KEY_8"), _cap("KEY_9"), _cap("KEY_0"), _cap("KEY_MINUS"),
        _cap("KEY_EQUAL"), _cap("KEY_BACKSPACE", 2.0),
    ])
    main.append([
        _cap("KEY_TAB", 1.5), _cap("KEY_Q"), _cap("KEY_W"), _cap("KEY_E"),
        _cap("KEY_R"), _cap("KEY_T"), _cap("KEY_Y"), _cap("KEY_U"),
        _cap("KEY_I"), _cap("KEY_O"), _cap("KEY_P"), _cap("KEY_LEFTBRACE"),
        _cap("KEY_RIGHTBRACE"), _cap("KEY_BACKSLASH", 1.5),
    ])
    main.append([
        _cap("KEY_CAPSLOCK", 1.75), _cap("KEY_A"), _cap("KEY_S"),
        _cap("KEY_D"), _cap("KEY_F"), _cap("KEY_G"), _cap("KEY_H"),
        _cap("KEY_J"), _cap("KEY_K"), _cap("KEY_L"), _cap("KEY_SEMICOLON"),
        _cap("KEY_APOSTROPHE"), _cap("KEY_ENTER", 2.25, True),
    ])
    main.append([
        _cap("KEY_LEFTSHIFT", 2.25), _cap("KEY_Z"), _cap("KEY_X"),
        _cap("KEY_C"), _cap("KEY_V"), _cap("KEY_B"), _cap("KEY_N"),
        _cap("KEY_M"), _cap("KEY_COMMA"), _cap("KEY_DOT"), _cap("KEY_SLASH"),
        _cap("KEY_RIGHTSHIFT", 2.75),
    ])
    main.append([
        _cap("KEY_LEFTCTRL", 1.25), _cap("KEY_LEFTMETA", 1.25),
        _cap("KEY_LEFTALT", 1.25), _cap("KEY_SPACE", 6.25, True),
        _cap("KEY_RIGHTALT", 1.25), _cap("KEY_RIGHTMETA", 1.25),
        _cap("KEY_MENU", 1.25), _cap("KEY_RIGHTCTRL", 1.25),
    ])

    nav = [
        [_cap("KEY_SYSRQ"), _cap("KEY_SCROLLLOCK"), _cap("KEY_PAUSE")],
        [_cap("KEY_INSERT"), _cap("KEY_HOME"), _cap("KEY_PAGEUP")],
        [_cap("KEY_DELETE"), _cap("KEY_END"), _cap("KEY_PAGEDOWN")],
        [],
        [_cap("KEY_UP")],
        [_cap("KEY_LEFT"), _cap("KEY_DOWN"), _cap("KEY_RIGHT")],
    ]

    numpad = [
        [_cap("KEY_NUMLOCK"), _cap("KEY_KPSLASH"), _cap("KEY_KPASTERISK"), _cap("KEY_KPMINUS")],
        [_cap("KEY_KP7"), _cap("KEY_KP8"), _cap("KEY_KP9")],
        [_cap("KEY_KP4"), _cap("KEY_KP5"), _cap("KEY_KP6"), _cap("KEY_KPPLUS")],
        [_cap("KEY_KP1"), _cap("KEY_KP2"), _cap("KEY_KP3")],
        [_cap("KEY_KP0", 2.0), _cap("KEY_KPDOT"), _cap("KEY_KPENTER")],
    ]
    return {"main": main, "nav": nav, "numpad": numpad}
