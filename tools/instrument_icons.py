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



# --- Melodic ---------------------------------------------------------------------------------

def keys(color):
    """Three white keys, divided, and the two black keys between them (cut out)."""
    p = Pen(color)
    gap = 3
    w = (58 - 6 - gap * 2) / 3
    for i in range(3):
        x = 6 + i * (w + gap)
        p.rect(x, 8, x + w, 56, r=3)
    for i in (1, 2):
        m = 6 + i * w + (i - 0.5) * gap
        p.rect(m - 5.5, 4, m + 5.5, 35, r=2, t="x")
    return p.done()


def organ(color):
    p = Pen(color)
    for x, top in ((14, 22), (26, 8), (38, 8), (50, 22)):
        p.rect(x - 4.5, top, x + 4.5, 48, r=2)
    p.rect(6, 52, 58, 58, r=3, t="s")
    return p.done()


def mallets(color):
    """Bars seen from above, shorter and shorter, and a mallet striking them."""
    p = Pen(color)
    for y, (a, b) in ((8, (6, 58)), (22, (11, 53)), (36, (16, 48))):
        p.rect(a, y, b, y + 9, r=2, t="s")
    p.stick(14, 58, 34, 34, 7, t="x")
    p.stick(14, 58, 34, 34, 4.5)
    p.circle(38, 29, 9, t="x")
    p.circle(38, 29, 7)
    return p.done()


def bell(color):
    p = Pen(color)
    p.circle(32, 22, 13)
    p.poly([(19, 22), (45, 22), (52, 46), (12, 46)])
    p.rect(8, 42, 56, 49, r=3.5)
    p.circle(32, 55, 5.5, t="s")
    return p.done()


def violin(color):
    """A violin with its bow across."""
    p = Pen(color)
    p.ellipse(19, 30, 45, 56)
    p.ellipse(22, 14, 42, 34)
    p.circle(19, 33, 4, t="x")
    p.circle(45, 33, 4, t="x")
    p.rect(30, 2, 34, 22, r=2)
    p.circle(32, 4, 3)
    p.stick(4, 46, 60, 28, 7.5, t="x")
    p.stick(4, 46, 60, 28, 4.5, t="s")
    return p.done()


def guitar(color):
    """The head of a guitar, three pegs a side, leaning the other way from the violin."""
    p = Pen(color)
    p.rect(22, 4, 42, 42, r=10)
    p.rect(27, 40, 37, 62, t="s")
    for y in (12, 22, 32):
        p.circle(16, y, 3.8)
        p.circle(48, y, 3.8)
    return p.done(angle=30)


def harp(color):
    """A lyre: the harps, and every plucked instrument that is not a guitar."""
    p = Pen(color)
    p.arc(12, -8, 52, 58, 0, 180, 5)
    p.stick(14.5, 25, 13, 10, 5)
    p.stick(49.5, 25, 51, 10, 5)
    p.stick(14, 16, 50, 16, 4.5)
    for x in (26, 32, 38):
        p.stick(x, 17, x, 54 if x == 32 else 52, 2.5, t="s")
    return p.done()


def _gust(x0, y, x1, r, up, turn=250, steps=40):
    """A line of wind: straight, then a round hook up or down."""
    points = [(x0, y), (x1, y)]
    cy = y - r if up else y + r
    for i in range(1, steps + 1):
        a = math.radians(90 - turn * i / steps if up else -90 + turn * i / steps)
        points.append((x1 + r * math.cos(a), cy + r * math.sin(a)))
    return points


def wind(color):
    """A gust of wind: every woodwind (flutes, reeds, ocarina, harmonica)."""
    p = Pen(color)
    p.path(_gust(8, 24, 40, 8, up=True), 5)
    p.path(_gust(8, 34, 48, 9, up=False), 5)
    p.path(_gust(8, 44, 26, 7, up=False), 5)
    return p.done()






def _flare(p, x0, x1, cy, h0, h1, steps=24):
    top, bottom = [], []
    for i in range(steps + 1):
        f = i / steps
        h = h0 + (h1 - h0) * f ** 2.4
        x = x0 + (x1 - x0) * f
        top.append((x, cy - h))
        bottom.append((x, cy + h))
    p.poly(top + bottom[::-1])


def trumpet(color):
    """A trumpet: every brass instrument (and the saxophone)."""
    p = Pen(color)
    p.stick(6, 34, 40, 34, 5)
    _flare(p, 34, 58, 34, 2.5, 13)
    for x in (13, 22, 31):
        p.stick(x, 22, x, 34, 4)
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
    """Three long held notes."""
    p = Pen(color)
    p.rect(6, 14, 46, 22, r=4)
    p.rect(12, 28, 58, 36, r=4)
    p.rect(6, 42, 50, 50, r=4)
    return p.done()


def saw(color):
    p = Pen(color)
    p.path([(6, 46), (32, 18), (32, 46), (58, 18), (58, 46)], 5.5)
    return p.done()


def square(color):
    p = Pen(color)
    p.path([(6, 44), (18, 44), (18, 20), (46, 20), (46, 44), (58, 44)], 5.5)
    return p.done()


# --- Percussion ------------------------------------------------------------------------------

def snare(color):
    """A drum with two sticks crossed on its head: the drum kit."""
    p = Pen(color)
    p.rect(10, 36, 54, 52)
    p.ellipse(10, 46, 54, 58)
    p.ellipse(10, 30, 54, 42, t="s")
    p.stick(12, 6, 36, 34, 5)
    p.stick(52, 6, 28, 34, 5)
    return p.done()




def cymbal(color):
    p = Pen(color)
    p.stick(32, 26, 32, 52, 4.5, t="s")
    p.path([(16, 61), (32, 50), (48, 61)], 4.5, t="s")
    p.poly([(4, 26), (22, 18), (42, 18), (60, 26), (42, 30), (22, 30)])
    p.ellipse(25, 12, 39, 24)
    return p.done()











def found(color):
    """A bottle: every found object (concrete sounds)."""
    p = Pen(color)
    p.rect(27, 4, 37, 10, r=2, t="s")
    p.rect(28, 8, 36, 22)
    p.poly([(28, 20), (36, 20), (44, 30), (20, 30)])
    p.rect(20, 28, 44, 60, r=5)
    p.rect(20, 36, 44, 46, t="s")
    return p.done(angle=-15)




ICONS = {
    "keys": keys, "organ": organ, "mallets": mallets, "bell": bell, "violin": violin,
    "guitar": guitar, "harp": harp, "wind": wind, "trumpet": trumpet, "choir": choir,
    "pad": pad, "saw": saw, "square": square, "snare": snare,
    "cymbal": cymbal, "found": found,
}
