#!/usr/bin/env python3
"""Generate KeySound PNG application/tray icons."""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "keysound" / "assets" / "icons"
OUT.mkdir(parents=True, exist_ok=True)
SS = 4


def rounded(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def make(size: int, simple: bool = False) -> Image.Image:
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Base tile
    pad = int(s * 0.035)
    rounded(d, (pad, pad, s - pad, s - pad), int(s * 0.22), (13, 17, 23, 255), (43, 57, 76, 255), max(1, s // 128))
    if simple:
        # High-contrast tray glyph: keycap + wave
        pass
    # Keycap body
    kx0, ky0, kx1, ky1 = int(s * 0.19), int(s * 0.22), int(s * 0.68), int(s * 0.78)
    rounded(d, (kx0, ky0 + int(s * 0.035), kx1, ky1 + int(s * 0.035)), int(s * 0.09), (8, 12, 18, 255))
    rounded(d, (kx0, ky0, kx1, ky1), int(s * 0.09), (29, 40, 55, 255), (74, 102, 135, 255), max(1, s // 160))
    # Keycap inner
    ix = int(s * 0.055)
    rounded(d, (kx0 + ix, ky0 + ix, kx1 - ix, ky1 - ix), int(s * 0.06), (20, 28, 39, 255), (52, 72, 96, 255), max(1, s // 220))
    # Letter K
    cx = (kx0 + kx1) // 2
    cy = (ky0 + ky1) // 2
    col = (230, 237, 247, 255)
    stem_w = max(2, int(s * 0.055))
    d.rounded_rectangle((cx - int(s * 0.12), cy - int(s * 0.15), cx - int(s * 0.12) + stem_w, cy + int(s * 0.15)), radius=stem_w // 2, fill=col)
    d.line((cx - int(s * 0.08), cy, cx + int(s * 0.05), cy - int(s * 0.15)), fill=col, width=stem_w)
    d.line((cx - int(s * 0.08), cy, cx + int(s * 0.05), cy + int(s * 0.15)), fill=col, width=stem_w)
    # Sound arcs / muzzle flash
    orange = (255, 107, 74, 255)
    blue = (63, 167, 255, 255)
    for i, (r, c, w) in enumerate(((0.13, orange, 0.022), (0.19, orange, 0.016), (0.25, blue, 0.012))):
        rr = int(s * r)
        bbox = (cx + int(s * 0.12) - rr, cy - rr, cx + int(s * 0.12) + rr, cy + rr)
        d.arc(bbox, start=-55, end=55, fill=c, width=max(2, int(s * w)))
    # Small status dot
    r = int(s * 0.045)
    d.ellipse((s - pad - int(s * 0.18), s - pad - int(s * 0.18), s - pad - int(s * 0.18) + 2 * r, s - pad - int(s * 0.18) + 2 * r), fill=blue)
    return img.resize((size, size), Image.Resampling.LANCZOS)


def main():
    master = make(512)
    master.save(OUT / "keysound.png")
    for size in (16, 24, 32, 48, 64, 128, 256):
        master.resize((size, size), Image.Resampling.LANCZOS).save(OUT / f"keysound-{size}.png")
    # Windows-style ICO is harmless to ship and useful if the project is ever reused.
    master.save(OUT / "keysound.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    # Tray uses a 32px image, which Xfce/StatusNotifier handles well.
    make(32).save(OUT / "keysound-tray.png")
    print("icons written to", OUT)


if __name__ == "__main__":
    main()
