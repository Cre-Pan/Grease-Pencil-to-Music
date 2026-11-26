# SPDX-License-Identifier: GPL-3.0-or-later
"""Draw the add-on's own UI icons (Blender has no headphones icon, nor instruments).

    python tools/build_icons.py      # -> grease_pencil_to_music/icons/*.png

Needs Pillow (development only: the PNGs are committed and shipped in the zip).
White shapes on transparent, like Blender's icons; "off" is the same shape, dimmed.
The instrument icons (``inst_<name>.png``) are drawn in tools/instrument_icons.py.
"""

import pathlib
import sys

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "grease_pencil_to_music" / "icons"
sys.path.insert(0, str(ROOT / "tools"))
import instrument_icons  # noqa: E402
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


def speaker(color, crossed=False):
    """A loudspeaker with sound waves (on) or with an X (off)."""
    s = SIZE * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = SS
    # Box and cone.
    d.rectangle((6 * u, 24 * u, 17 * u, 40 * u), fill=color)
    d.polygon([(15 * u, 24 * u), (31 * u, 10 * u), (31 * u, 54 * u), (15 * u, 40 * u)],
              fill=color)
    w = int(4.5 * u)
    if crossed:
        d.line((39 * u, 22 * u, 57 * u, 42 * u), fill=color, width=w)
        d.line((39 * u, 42 * u, 57 * u, 22 * u), fill=color, width=w)
    else:
        d.arc((22 * u, 18 * u, 46 * u, 46 * u), 300, 60, fill=color, width=w)
        d.arc((18 * u, 8 * u, 58 * u, 56 * u), 305, 55, fill=color, width=w)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def composition_notes(color):
    """Composizione Musicale: a piano roll, the keys on the left and a melody of notes."""
    s = SIZE * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = SS
    # The keys: a rounded strip cut by three gaps.
    d.rounded_rectangle((4 * u, 6 * u, 15 * u, 58 * u), 3 * u, fill=color)
    for y in (18, 31, 44):
        d.rectangle((4 * u, y * u, 15 * u, (y + 3) * u), fill=(0, 0, 0, 0))
    # The notes: bars at different heights, like a short tune.
    for x0, x1, y in ((21, 33, 40), (35, 45, 26), (47, 60, 10), (47, 60, 46)):
        d.rounded_rectangle((x0 * u, y * u, x1 * u, (y + 9) * u), 4 * u, fill=color)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def composition_beat(color):
    """Composizione Ritmica: three lanes of a step sequencer, with their hits."""
    s = SIZE * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = SS
    dim = color[:3] + (int(color[3] * 0.35),)
    hits = ((1, 0, 1, 0), (0, 1, 0, 1), (1, 1, 0, 1))
    for row, pattern in enumerate(hits):
        y = (6 + row * 18) * u
        for col, on in enumerate(pattern):
            x = (4 + col * 15) * u
            d.rounded_rectangle((x, y, x + 12 * u, y + 15 * u), 3 * u, fill=color if on else dim)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    headphones((255, 255, 255, 255)).save(OUT / "solo_on.png")
    headphones((230, 230, 230, 120)).save(OUT / "solo_off.png")
    speaker((255, 255, 255, 255)).save(OUT / "audio_on.png")
    speaker((230, 230, 230, 120), crossed=True).save(OUT / "audio_off.png")
    composition_notes((255, 255, 255, 255)).save(OUT / "comp_notes.png")
    composition_beat((255, 255, 255, 255)).save(OUT / "comp_beat.png")
    for name, draw in instrument_icons.ICONS.items():
        draw((255, 255, 255, 255)).save(OUT / f"inst_{name}.png", optimize=True)
    print(f"Icons written to {OUT}")


if __name__ == "__main__":
    main()
