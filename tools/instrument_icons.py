# SPDX-License-Identifier: GPL-3.0-or-later
"""Instrument icons: minimal two-tone silhouettes, like Blender's own two-tone icons. The
main shape is in the full color, one secondary part (neck, stand, sticks, strings...) in
the same color, dimmed. Few, large shapes on a 64-unit grid, readable at 16 px.

Used by tools/build_icons.py (``ICONS``: name -> function(color) -> 64 px image).
"""

import math

from PIL import Image, ImageDraw

SIZE = 64
SS = 4  # supersampling
CLEAR = (0, 0, 0, 0)
SECONDARY = 0.42  # opacity of the second tone


class Pen:
    """Drawing in 64-unit coordinates. ``t``: "p" main tone, "s" second tone, "x" hole.
    Later shapes replace what is under them."""

    def __init__(self, color):
        r, g, b, a = color
        self.tones = {"p": color, "s": (r, g, b, round(a * SECONDARY)), "x": CLEAR}
        self.img = Image.new("RGBA", (SIZE * SS, SIZE * SS), CLEAR)
        self.d = ImageDraw.Draw(self.img)

    def rect(self, x0, y0, x1, y1, r=0, t="p"):
        box = (x0 * SS, y0 * SS, x1 * SS, y1 * SS)
        if r:
            self.d.rounded_rectangle(box, r * SS, fill=self.tones[t])
        else:
            self.d.rectangle(box, fill=self.tones[t])

    def ellipse(self, x0, y0, x1, y1, t="p"):
        self.d.ellipse((x0 * SS, y0 * SS, x1 * SS, y1 * SS), fill=self.tones[t])

    def circle(self, cx, cy, r, t="p"):
        self.ellipse(cx - r, cy - r, cx + r, cy + r, t)

    def ring(self, cx, cy, r, w, t="p"):
        self.circle(cx, cy, r, t)
        self.circle(cx, cy, r - w, "x")

    def poly(self, points, t="p"):
        self.d.polygon([(x * SS, y * SS) for x, y in points], fill=self.tones[t])

    def arc(self, x0, y0, x1, y1, start, end, w, t="p"):
        self.d.arc((x0 * SS, y0 * SS, x1 * SS, y1 * SS), start, end, fill=self.tones[t],
                   width=round(w * SS))

    def stick(self, x0, y0, x1, y1, w, t="p"):
        """A line with round ends."""
        self.d.line((x0 * SS, y0 * SS, x1 * SS, y1 * SS), fill=self.tones[t],
                    width=round(w * SS))
        self.circle(x0, y0, w / 2, t)
        self.circle(x1, y1, w / 2, t)

    def path(self, points, w, t="p"):
        for a, b in zip(points[:-1], points[1:], strict=True):
            self.stick(*a, *b, w, t)

    def done(self, angle=0.0):
        img = self.img
        if angle:
            img = img.rotate(angle, resample=Image.BICUBIC, center=(SIZE * SS / 2,) * 2)
        return img.resize((SIZE, SIZE), Image.LANCZOS)


def _wave(y, amp, x0=6, x1=58, phase=0.0, steps=40):
    return [(x0 + (x1 - x0) * i / steps,
             y + amp * math.sin(i / steps * 2 * math.pi + phase)) for i in range(steps + 1)]


# --- Melodic ---------------------------------------------------------------------------------

def keys(color):
    p = Pen(color)
    p.rect(6, 12, 58, 52, r=5, t="s")
    for x in (19, 32, 45):
        p.rect(x - 4.5, 12, x + 4.5, 36, r=2)
    return p.done()


def organ(color):
    p = Pen(color)
    for x, top in ((14, 22), (26, 8), (38, 8), (50, 22)):
        p.rect(x - 4.5, top, x + 4.5, 48, r=2)
    p.rect(6, 52, 58, 58, r=3, t="s")
    return p.done()


def mallets(color):
    p = Pen(color)
    for i, x in enumerate((8, 20, 32)):
        h = 20 - i * 5
        p.rect(x - 4.5, 30 - h, x + 4.5, 30 + h, r=2.5, t="s")
    p.stick(30, 58, 52, 26, 5)
    p.circle(53, 22, 8)
    return p.done()


def bell(color):
    p = Pen(color)
    p.poly([(22, 14), (42, 14), (46, 36), (56, 48), (8, 48), (18, 36)])
    p.circle(32, 16, 10)
    p.circle(32, 54, 6, t="s")
    return p.done()


def violin(color):
    p = Pen(color)
    p.rect(29, 2, 35, 30, r=3, t="s")
    p.ellipse(19, 18, 45, 40)
    p.ellipse(15, 34, 49, 62)
    return p.done()


def guitar(color):
    p = Pen(color)
    p.rect(29, 0, 35, 30, r=3, t="s")
    p.ellipse(18, 20, 46, 42)
    p.ellipse(13, 34, 51, 63)
    p.circle(32, 40, 5.5, t="s")
    return p.done(angle=-38)


def harp(color):
    p = Pen(color)
    for x in (22, 30, 38, 46):
        p.stick(x, 16, x, 62 - x * 0.98, 3.5, t="s")
    p.path([(10, 58), (10, 10), (56, 12), (12, 58)], 6)
    return p.done()


def clarinet(color):
    p = Pen(color)
    p.poly([(26, 46), (38, 46), (46, 62), (18, 62)], t="s")
    p.rect(27.5, 2, 36.5, 48, r=3)
    return p.done(angle=-40)


def flute(color):
    p = Pen(color)
    p.rect(27, 1, 37, 63, r=5)
    for y in (24, 34, 44):
        p.circle(32, y, 2.6, t="s")
    return p.done(angle=-45)


def ocarina(color):
    p = Pen(color)
    p.ellipse(4, 16, 52, 52)
    p.poly([(42, 22), (60, 12), (62, 22), (50, 34)])
    for cx, cy in ((18, 34), (28, 30), (38, 34)):
        p.circle(cx, cy, 3.5, t="s")
    return p.done()


def sax(color):
    p = Pen(color)
    p.path([(22, 12), (25, 5), (36, 3)], 4.5, t="s")
    p.stick(22, 14, 22, 44, 10)
    p.arc(12, 30, 48, 60, 0, 180, 10)
    p.stick(43, 46, 43, 26, 10)
    p.poly([(37, 28), (49, 28), (56, 14), (30, 14)])
    return p.done()


def harmonica(color):
    p = Pen(color)
    p.rect(3, 20, 61, 44, r=6)
    for x in range(10, 58, 9):
        p.rect(x - 2.5, 28, x + 2.5, 36, r=1.5, t="s")
    return p.done()


def trumpet(color):
    p = Pen(color)
    for x in (18, 27, 36):
        p.rect(x - 3, 18, x + 3, 34, r=1.5, t="s")
    p.rect(2, 34, 46, 40, r=2)
    p.poly([(42, 34), (62, 18), (62, 56), (42, 40)])
    return p.done()


def horn(color):
    p = Pen(color)
    p.ring(26, 30, 20, 7)
    p.poly([(36, 42), (46, 34), (63, 52), (63, 63), (46, 63), (40, 50)], t="s")
    return p.done()


def choir(color):
    p = Pen(color)
    for cx in (14, 50):
        p.circle(cx, 20, 6.5, t="s")
        p.ellipse(cx - 11, 30, cx + 11, 58, t="s")
    p.circle(32, 26, 11.5, t="x")
    p.ellipse(13, 37, 51, 74, t="x")
    p.circle(32, 26, 8.5)
    p.ellipse(16, 40, 48, 72)
    p.rect(0, 60, 64, 64, t="x")
    return p.done()


def pad(color):
    p = Pen(color)
    p.path(_wave(18, 5, phase=1.0), 5, t="s")
    p.path(_wave(46, 5, phase=1.0), 5, t="s")
    p.path(_wave(32, 7), 6)
    return p.done()


def saw(color):
    p = Pen(color)
    p.stick(4, 54, 60, 54, 3.5, t="s")
    p.path([(6, 44), (22, 14), (22, 44), (40, 14), (40, 44), (58, 14)], 6)
    return p.done()


def square(color):
    p = Pen(color)
    p.stick(4, 54, 60, 54, 3.5, t="s")
    p.path([(6, 44), (6, 16), (24, 16), (24, 44), (40, 44), (40, 16), (58, 16), (58, 44)], 6)
    return p.done()


# --- Percussion ------------------------------------------------------------------------------

def snare(color):
    p = Pen(color)
    p.stick(10, 4, 28, 26, 4.5, t="s")
    p.stick(54, 4, 36, 26, 4.5, t="s")
    p.rect(8, 32, 56, 54)
    p.ellipse(8, 46, 56, 60)
    p.ellipse(8, 25, 56, 39)
    return p.done()


def kick(color):
    p = Pen(color)
    p.ring(32, 32, 27, 8)
    p.circle(32, 32, 11, t="s")
    return p.done()


def clap(color):
    p = Pen(color)
    for a, b, c, d in ((6, 14, 11, 22), (30, 2, 30, 7), (54, 10, 49, 16)):
        p.stick(a, b, c, d, 3.5, t="s")
    p.rect(17, 28, 47, 60, r=10)
    for x, top in ((21, 16), (28.5, 12), (36, 13), (43, 18)):
        p.rect(x - 3.4, top, x + 3.4, 36, r=3.4)
    return p.done()


def cymbal(color):
    p = Pen(color)
    p.stick(32, 26, 32, 52, 4.5, t="s")
    p.path([(16, 61), (32, 50), (48, 61)], 4.5, t="s")
    p.poly([(4, 26), (22, 18), (42, 18), (60, 26), (42, 30), (22, 30)])
    p.ellipse(25, 12, 39, 24)
    return p.done()


def conga(color):
    p = Pen(color)
    p.poly([(12, 16), (52, 16), (54, 32), (46, 60), (18, 60), (10, 32)])
    p.ellipse(12, 7, 52, 23, t="s")
    return p.done()


def gong(color):
    p = Pen(color)
    p.path([(6, 62), (6, 6), (58, 6), (58, 62)], 5, t="s")
    p.circle(32, 36, 20)
    return p.done()


def triangle(color):
    p = Pen(color)
    p.stick(40, 22, 62, 40, 4, t="s")
    p.path([(26, 8), (6, 54), (56, 54), (34, 10)], 6.5)
    return p.done()


def cowbell(color):
    p = Pen(color)
    p.arc(24, 4, 40, 26, 180, 360, 5, t="s")
    p.poly([(22, 16), (42, 16), (52, 58), (12, 58)])
    return p.done()


def jingle(color):
    p = Pen(color)
    p.arc(4, 8, 60, 56, 200, 340, 4, t="s")
    for cx, cy, r in ((14, 36, 9), (32, 44, 10), (50, 36, 9)):
        p.circle(cx, cy, r)
    return p.done()


def tambourine(color):
    p = Pen(color)
    p.ring(32, 32, 26, 8)
    for k in range(5):
        a = math.radians(k * 72 - 90)
        p.circle(32 + 22 * math.cos(a), 32 + 22 * math.sin(a), 5, t="s")
    return p.done()


def block(color):
    p = Pen(color)
    p.stick(40, 10, 58, 3, 4, t="s")
    p.circle(38, 11, 5.5, t="s")
    p.rect(4, 24, 60, 50, r=6)
    return p.done()


def claves(color):
    p = Pen(color)
    p.stick(10, 54, 54, 10, 9, t="s")
    p.stick(10, 10, 54, 54, 9)
    return p.done()


def maracas(color):
    p = Pen(color)
    p.ellipse(32, 4, 60, 34, t="s")
    p.stick(45, 30, 34, 58, 5, t="s")
    p.ellipse(4, 4, 30, 34)
    p.stick(19, 30, 30, 58, 5)
    return p.done()


def hammer(color):
    p = Pen(color)
    p.stick(12, 58, 38, 26, 7, t="s")
    p.poly([(30, 4), (60, 28), (52, 38), (20, 12)])
    return p.done()


def bubbles(color):
    p = Pen(color)
    p.circle(48, 16, 8, t="s")
    p.circle(52, 48, 6, t="s")
    p.ring(24, 38, 18, 5)
    return p.done()


def glass(color):
    p = Pen(color)
    p.rect(29.5, 26, 34.5, 54, t="s")
    p.ellipse(16, 52, 48, 60, t="s")
    p.poly([(12, 4), (52, 4), (32, 30)])
    return p.done()


ICONS = {
    "keys": keys, "organ": organ, "mallets": mallets, "bell": bell, "violin": violin,
    "guitar": guitar, "harp": harp, "clarinet": clarinet, "flute": flute, "ocarina": ocarina,
    "sax": sax, "harmonica": harmonica, "trumpet": trumpet, "horn": horn, "choir": choir,
    "pad": pad, "saw": saw, "square": square, "snare": snare, "kick": kick, "clap": clap,
    "cymbal": cymbal, "conga": conga, "gong": gong, "triangle": triangle, "cowbell": cowbell,
    "jingle": jingle, "tambourine": tambourine, "block": block, "claves": claves,
    "maracas": maracas, "hammer": hammer, "bubbles": bubbles, "glass": glass,
}
