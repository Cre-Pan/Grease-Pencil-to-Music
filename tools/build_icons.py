# SPDX-License-Identifier: GPL-3.0-or-later
"""Draw the add-on's own UI icons (Blender has no headphones icon).

    python tools/build_icons.py      # -> grease_pencil_to_music/icons/*.png

Needs Pillow (development only: the PNGs are committed and shipped in the zip).
White shapes on transparent, like Blender's icons; "off" is the same shape, dimmed.
"""

import pathlib

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "grease_pencil_to_music" / "icons"
SIZE = 64
SS = 4  # supersampling


def headphones(color):
    s = SIZE * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = int(5.5 * SS)  # band thickness
    # Head band: upper half of a circle.
    m = int(9 * SS)
    d.arc((m, int(8 * SS), s - m, s - int(10 * SS)), 180, 360, fill=color, width=w)
    # Band sides down to the ear cups.
    mid = (int(8 * SS) + s - int(10 * SS)) // 2
    d.rectangle((m, mid, m + w, int(42 * SS)), fill=color)
    d.rectangle((s - m - w, mid, s - m, int(42 * SS)), fill=color)
    # Ear cups.
    cup_w, cup_h, r = int(15 * SS), int(24 * SS), int(5 * SS)
    top = int(33 * SS)
    d.rounded_rectangle((int(5 * SS), top, int(5 * SS) + cup_w, top + cup_h), r, fill=color)
    d.rounded_rectangle((s - int(5 * SS) - cup_w, top, s - int(5 * SS), top + cup_h), r,
                        fill=color)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    headphones((255, 255, 255, 255)).save(OUT / "solo_on.png")
    headphones((230, 230, 230, 120)).save(OUT / "solo_off.png")
    print(f"Icons written to {OUT}")


if __name__ == "__main__":
    main()
