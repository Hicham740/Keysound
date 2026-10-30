"""Command-line entry point."""
from __future__ import annotations

import argparse
import logging
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="keysound",
        description="Per-key keyboard sounds for Kali Linux (X11 and Wayland).",
    )
    parser.add_argument("--minimized", action="store_true", help="start hidden in the tray")
    parser.add_argument("--no-tray", action="store_true", help="run without a tray indicator")
    parser.add_argument("--diagnose", action="store_true", help="print environment diagnostics and exit")
    parser.add_argument("--screenshot", metavar="PATH", help=argparse.SUPPRESS)
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    args, _unknown = parser.parse_known_args(argv)

    if args.version:
        from .paths import VERSION
        print(f"KeySound {VERSION} (Kali Linux edition)")
        return 0
    if args.diagnose:
        from .app import diagnose
        return diagnose()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    from .app import KeySoundApp

    app = KeySoundApp(
        start_minimized=args.minimized,
        use_tray=not args.no_tray,
        screenshot=args.screenshot,
    )
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    raise SystemExit(main())
