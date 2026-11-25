# SPDX-License-Identifier: GPL-3.0-or-later
"""Instrument icons, in the style of Blender's own: flat, monochrome silhouettes with
transparent cut-outs, readable at 16 px. Drawn on a 64-unit grid.

Used by tools/build_icons.py (``ICONS``: name -> function(color) -> 64 px image).
"""

import math

from PIL import Image, ImageDraw

SIZE = 64
SS = 4  # supersampling
CLEAR = (0, 0, 0, 0)


class Pen:
    """Drawing in 64-unit coordinates; ``clear=True`` cuts a hole."""

    def __init__(self, color):
        self.color = color
        self.img = Image.new("RGBA", (SIZE * SS, SIZE * SS), CLEAR)
        self.d = ImageDraw.Draw(self.img)

    def _c(self, clear):
        return CLEAR if clear else self.color

    @staticmethod
    def _p(points):
        return [(x * SS, y * SS) for x, y in points]

    def rect(self, x0, y0, x1, y1, r=0, clear=False):
        box = (x0 * SS, y0 * SS, x1 * SS, y1 * SS)
        if r:
            self.d.rounded_rectangle(box, r * SS, fill=self._c(clear))
        else:
            self.d.rectangle(box, fill=self._c(clear))

    def ellipse(self, x0, y0, x1, y1, clear=False):
        self.d.ellipse((x0 * SS, y0 * SS, x1 * SS, y1 * SS), fill=self._c(clear))

    def circle(self, cx, cy, r, clear=False):
        self.ellipse(cx - r, cy - r, cx + r, cy + r, clear)

    def ring(self, cx, cy, r, w):
        self.circle(cx, cy, r)
        self.circle(cx, cy, r - w, clear=True)

    def poly(self, points, clear=False):
        self.d.polygon(self._p(points), fill=self._c(clear))

    def stick(self, x0, y0, x1, y1, w, clear=False):
        """A line with round ends."""
        self.d.line((x0 * SS, y0 * SS, x1 * SS, y1 * SS), fill=self._c(clear),
                    width=int(w * SS))
        self.circle(x0, y0, w / 2, clear)
        self.circle(x1, y1, w / 2, clear)

    def path(self, points, w, clear=False):
        """A polyline with round joints."""
        for a, b in zip(points, points[1:]):
            self.stick(*a, *b, w, clear)

    def arc(self, x0, y0, x1, y1, start, end, w, clear=False):
        self.d.arc((x0 * SS, y0 * SS, x1 * SS, y1 * SS), start, end, fill=self._c(clear),
                   width=int(w * SS))

    def done(self, angle=0.0):
        img = self.img
        if angle:
            img = img.rotate(angle, resample=Image.BICUBIC, center=(SIZE * SS / 2,) * 2)
        return img.resize((SIZE, SIZE), Image.LANCZOS)


def _curve(fn, x0, x1, steps=48):
    return [(x0 + (x1 - x0) * i / steps, fn(i / steps)) for i in range(steps + 1)]


# --- Keyboards -------------------------------------------------------------------------------

def keys(color):
    p = Pen(color)
    p.rect(5, 12, 59, 52, r=4)
    for x in (18.5, 32, 45.5):  # gaps between the white keys
        p.rect(x - 1.2, 12, x + 1.2, 52, clear=True)
    for x in (18.5, 45.5):  # black keys, each with a thin gap around it
        p.rect(x - 6.5, 9, x + 6.5, 36, clear=True)
        p.rect(x - 4.5, 12, x + 4.5, 34, r=1.5)
    return p.done()


def organ(color):
    p = Pen(color)
    for x, top in ((6, 24), (16, 14), (26, 6), (36, 6), (46, 14), (56, 24)):
        p.rect(x - 4, top, x + 4, 50, r=1)
        p.poly([(x - 4, top + 8), (x + 4, top + 8), (x, top + 13)], clear=True)  # mouth
    p.rect(2, 52, 62, 59, r=2)
    return p.done()


# --- Tuned percussion ------------------------------------------------------------------------

def mallets(color):
    p = Pen(color)
    for i, x in enumerate((7, 17, 27, 37, 47)):
        h = 22 - i * 3.2
        p.rect(x, 32 - h, x + 7.5, 32 + h, r=2)
    p.rect(2, 22, 58, 24, clear=True)  # the rails show as gaps through the bars
    p.rect(2, 40, 58, 42, clear=True)
    p.stick(36, 58, 58, 36, 9, clear=True)  # mallet, cut free from the bars
    p.stick(38, 56, 54, 40, 3.5)
    p.circle(56, 38, 6)
    return p.done()


def bell(color):
    p = Pen(color)
    pts = [(32, 6)]
    # Right side of the bell: narrow shoulder, flaring lip.
    for i in range(25):
        t = i / 24
        y = 10 + t * 36
        x = 32 + 10 + 7 * t ** 2.2 + (6 if t > 0.92 else 0)
        pts.append((x, y))
    pts.append((56, 48))
    left = [(64 - x, y) for x, y in reversed(pts)]
    p.poly(pts + left)
    p.ellipse(18, 6, 46, 20)
    p.circle(32, 54, 6)
    p.rect(6, 47, 58, 50, clear=True)
    p.circle(32, 5, 3)
    return p.done()


# --- Strings ---------------------------------------------------------------------------------

def violin(color):
    p = Pen(color)
    p.ellipse(20, 16, 44, 36)  # upper bout
    p.ellipse(16, 32, 48, 60)  # lower bout
    p.ellipse(11, 31, 22, 42, clear=True)  # C-bouts (waist)
    p.ellipse(42, 31, 53, 42, clear=True)
    p.rect(29.5, 2, 34.5, 26, r=2)  # neck
    p.circle(32, 4, 3.5)  # scroll
    p.rect(26, 44, 38, 47, r=1.5, clear=True)  # bridge
    for x in (26, 38):  # f-holes
        p.stick(x, 36, x, 44, 2, clear=True)
    p.stick(31.6, 28, 31.6, 44, 1.2, clear=True)  # strings cut
    p.stick(32.4, 47, 32.4, 54, 1.2, clear=True)
    return p.done()


def guitar(color):
    p = Pen(color)
    p.ellipse(19, 20, 45, 42)
    p.ellipse(14, 34, 50, 62)
    p.ellipse(9, 33, 20, 44, clear=True)
    p.ellipse(44, 33, 55, 44, clear=True)
    p.ring(32, 38, 6.5, 2.2)
    p.circle(32, 38, 4.3, clear=True)
    p.rect(29.5, 0, 34.5, 32)
    p.rect(27.5, 0, 36.5, 8, r=2)  # head
    p.rect(25, 51, 39, 54, r=1.5, clear=True)  # bridge
    return p.done(angle=-38)


def harp(color):
    p = Pen(color)
    p.stick(10, 10, 10, 58, 7)  # column
    p.poly([(8, 12), (22, 6), (38, 14), (56, 10), (58, 15), (38, 21), (22, 13), (8, 19)])
    p.stick(57, 13, 14, 56, 6)  # soundboard
    p.rect(8, 54, 26, 60, r=2)  # foot
    for x in (20, 28, 36, 44):
        top = 14 + (x - 20) * 0.05
        bottom = 56 - (x - 14) * (42 / 43)
        p.stick(x, top + 4, x, bottom - 1, 2)
    return p.done()


# --- Woodwinds -------------------------------------------------------------------------------

def clarinet(color):
    p = Pen(color)
    p.poly([(29, 2), (35, 2), (34.5, 10), (29.5, 10)])  # mouthpiece
    p.rect(28, 10, 36, 48, r=1)
    p.poly([(28, 46), (36, 46), (44, 61), (20, 61)])  # bell
    p.rect(26, 15, 38, 17.5)  # barrel ring
    for y in (22, 29, 36):
        p.circle(32, y, 2.2, clear=True)
    return p.done(angle=-40)


def flute(color):
    p = Pen(color)
    p.rect(28, 1, 36, 63, r=3)
    p.ellipse(29.5, 6, 34.5, 11, clear=True)  # embouchure
    for y in (24, 31, 38, 47, 54):
        p.circle(32, y, 2.2, clear=True)
    p.rect(27, 17, 37, 18.8, clear=True)
    return p.done(angle=-45)


def ocarina(color):
    p = Pen(color)
    p.ellipse(6, 16, 54, 52)
    p.poly([(44, 22), (60, 14), (62, 22), (52, 34)])  # mouthpiece
    p.rect(44, 15, 52, 20, clear=True)
    for cx, cy in ((19, 30), (28, 26), (37, 28), (24, 40), (34, 40)):
        p.circle(cx, cy, 3, clear=True)
    return p.done()


def sax(color):
    p = Pen(color)
    p.stick(22, 14, 22, 44, 9)  # body
    p.arc(14, 32, 46, 60, 0, 180, 9)  # bow
    p.stick(41.5, 46, 42, 28, 9)  # up to the bell
    p.poly([(36, 30), (48, 30), (54, 18), (30, 18)])  # bell
    p.path([(22, 12), (24, 6), (34, 4)], 4)  # neck
    p.rect(30, 1.5, 38, 6.5, r=1.5)  # mouthpiece
    for y in (22, 30, 38):
        p.circle(22, y, 2, clear=True)
    return p.done()


def harmonica(color):
    p = Pen(color)
    p.rect(3, 20, 61, 44, r=4)
    p.rect(3, 31, 61, 33, clear=True)
    for x in range(9, 58, 7):
        p.rect(x - 2, 35, x + 2, 41, r=0.8, clear=True)
    return p.done()


# --- Brass -----------------------------------------------------------------------------------

def trumpet(color):
    p = Pen(color)
    p.rect(2, 33, 8, 38, r=1)  # mouthpiece
    p.rect(6, 34, 44, 37.5)  # lead pipe
    p.poly([(42, 34), (52, 28), (62, 20), (62, 51), (52, 43), (42, 37.5)])  # bell
    p.arc(14, 30, 46, 52, 0, 180, 4.5)  # lower loop
    p.rect(13, 34, 18, 44)
    for x in (22, 29, 36):  # valves
        p.rect(x - 2.5, 22, x + 2.5, 41, r=1)
        p.rect(x - 4, 19, x + 4, 23, r=1.5)
    return p.done()


def horn(color):
    p = Pen(color)
    p.ring(28, 34, 21, 6)
    p.ring(28, 34, 11, 4)
    p.poly([(38, 46), (47, 39), (63, 53), (63, 63), (49, 63), (40, 54)])  # bell
    p.stick(10, 14, 20, 22, 4)  # lead pipe
    p.rect(6, 9, 12, 15, r=1.5)
    return p.done()


# --- Voices and synths -----------------------------------------------------------------------

def choir(color):
    p = Pen(color)
    for cx, cy, s in ((16, 22, 0.8), (48, 22, 0.8)):  # back row
        p.circle(cx, cy, 7 * s)
        p.ellipse(cx - 13 * s, cy + 9 * s, cx + 13 * s, cy + 37 * s)
    p.circle(32, 31, 10.5, clear=True)  # front singer, cut free
    p.ellipse(13, 42, 51, 74, clear=True)
    p.circle(32, 31, 8)
    p.ellipse(16, 44, 48, 72)
    p.rect(0, 60, 64, 64, clear=True)
    return p.done()


def pad(color):
    p = Pen(color)
    for k, y in enumerate((18, 32, 46)):
        amp = 7 - k * 1.5
        pts = _curve(lambda t, y=y, amp=amp, k=k: y + amp * math.sin(t * 2 * math.pi + k), 5, 59)
        p.path(pts, 5)
    return p.done()


def saw(color):
    p = Pen(color)
    p.path([(4, 46), (22, 16), (22, 46), (42, 16), (42, 46), (60, 16)], 6)
    return p.done()


def square(color):
    p = Pen(color)
    p.path([(4, 46), (4, 18), (22, 18), (22, 46), (42, 46), (42, 18), (60, 18), (60, 46)], 6)
    return p.done()


# --- Drums -----------------------------------------------------------------------------------

def snare(color):
    p = Pen(color)
    p.rect(8, 32, 56, 54)
    p.ellipse(8, 47, 56, 61)  # bottom
    p.ellipse(8, 25, 56, 39)  # head
    p.ellipse(6, 23, 58, 41, clear=True)
    p.ellipse(8, 25, 56, 39)
    p.ellipse(11, 27, 53, 37, clear=True)  # head ring
    p.ellipse(13, 28.5, 51, 35.5)
    for x in (18, 32, 46):  # tension rods
        p.rect(x - 1.2, 42, x + 1.2, 56, clear=True)
    p.stick(10, 4, 30, 24, 4)  # sticks
    p.stick(54, 4, 36, 24, 4)
    return p.done()


def kick(color):
    p = Pen(color)
    p.ring(32, 30, 25, 6)
    p.circle(32, 30, 12)
    p.circle(32, 30, 5, clear=True)
    p.stick(14, 50, 8, 61, 4)  # spurs
    p.stick(50, 50, 56, 61, 4)
    return p.done()


def clap(color):
    p = Pen(color)
    p.rect(18, 28, 46, 58, r=9)  # palm
    for x, top in ((21, 10), (28.5, 6), (36, 8), (43, 14)):
        p.rect(x - 3.2, top, x + 3.2, 36, r=3.2)
    p.stick(14, 44, 8, 30, 7)  # thumb
    p.stick(6, 12, 10, 20, 3)  # impact
    p.stick(54, 6, 52, 2, 3)
    p.stick(56, 18, 61, 15, 3)
    return p.done()


def cymbal(color):
    p = Pen(color)
    p.poly([(4, 24), (24, 18), (40, 18), (60, 24), (40, 27), (24, 27)])
    p.ellipse(25, 11, 39, 23)  # bell
    p.stick(32, 26, 32, 52, 4)  # stand
    p.path([(32, 50), (16, 61)], 4)
    p.path([(32, 50), (48, 61)], 4)
    p.stick(32, 50, 32, 61, 4)
    return p.done()


def conga(color):
    p = Pen(color)
    p.poly([(14, 14), (50, 14), (54, 26), (52, 40), (44, 60), (20, 60), (12, 40), (10, 26)])
    p.ellipse(12, 6, 52, 20)
    p.rect(8, 18, 56, 20.5, clear=True)
    p.rect(8, 42, 56, 44.5, clear=True)
    p.ellipse(16, 9, 48, 17, clear=True)
    p.ellipse(19, 10.5, 45, 15.5)
    return p.done()


# --- Metals ----------------------------------------------------------------------------------

def gong(color):
    p = Pen(color)
    p.stick(6, 6, 6, 62, 5)
    p.stick(58, 6, 58, 62, 5)
    p.stick(6, 6, 58, 6, 5)
    p.stick(22, 8, 26, 16, 2)
    p.stick(42, 8, 38, 16, 2)
    p.circle(32, 36, 20)
    p.circle(32, 36, 15, clear=True)  # a groove around the face
    p.circle(32, 36, 13)
    p.circle(32, 36, 6, clear=True)
    p.circle(32, 36, 4)
    return p.done()


def triangle(color):
    p = Pen(color)
    p.path([(26, 8), (6, 54), (56, 54), (34, 10)], 6)
    p.stick(42, 20, 62, 36, 3)  # beater
    p.circle(30, 4, 2.5)
    return p.done()


def cowbell(color):
    p = Pen(color)
    p.poly([(22, 18), (42, 18), (52, 58), (12, 58)])
    p.arc(24, 4, 40, 26, 180, 360, 4.5)  # handle
    p.poly([(15, 52), (49, 52), (50.5, 58), (13.5, 58)], clear=True)
    p.ellipse(14, 52, 50, 58)
    p.ellipse(18, 53.5, 46, 56.5, clear=True)
    return p.done()


def jingle(color):
    p = Pen(color)
    p.arc(4, 8, 60, 56, 200, 340, 4)  # strap
    for cx, cy, r in ((14, 34, 9), (32, 42, 10), (50, 34, 9)):
        p.circle(cx, cy, r + 2, clear=True)
        p.circle(cx, cy, r)
        p.stick(cx - r + 3, cy + 2, cx + r - 3, cy + 2, 2, clear=True)
        p.circle(cx, cy + 5, 2, clear=True)
    return p.done()


def tambourine(color):
    p = Pen(color)
    p.ring(32, 32, 27, 8)
    for k in range(6):
        a = math.radians(k * 60 + 30)
        cx, cy = 32 + 23 * math.cos(a), 32 + 23 * math.sin(a)
        p.circle(cx, cy, 5, clear=True)
        p.ellipse(cx - 4.5, cy - 2, cx + 4.5, cy + 2)
    return p.done()


# --- Woods, shakers, objects -----------------------------------------------------------------

def block(color):
    p = Pen(color)
    p.rect(4, 22, 60, 48, r=5)
    p.rect(10, 32, 54, 37, r=2.5, clear=True)
    p.stick(40, 8, 58, 2, 3.5)
    p.circle(38, 9, 5)
    return p.done()


def claves(color):
    p = Pen(color)
    p.stick(10, 54, 54, 10, 9)
    p.stick(10, 10, 54, 54, 13, clear=True)
    p.stick(10, 10, 54, 54, 9)
    return p.done()


def maracas(color):
    p = Pen(color)
    p.ellipse(4, 4, 30, 34)
    p.stick(19, 30, 30, 58, 5)
    p.ellipse(32, 4, 60, 34)
    p.stick(45, 30, 34, 58, 9, clear=True)
    p.stick(45, 30, 34, 58, 5)
    p.stick(12, 14, 16, 10, 2.5, clear=True)
    p.stick(41, 14, 45, 10, 2.5, clear=True)
    return p.done()


def hammer(color):
    p = Pen(color)
    p.stick(14, 58, 42, 22, 7)
    p.poly([(30, 4), (58, 26), (50, 36), (22, 14)])
    p.poly([(20, 12), (30, 4), (26, 2), (16, 8)])
    return p.done()


def bubbles(color):
    p = Pen(color)
    for cx, cy, r in ((24, 38, 18), (48, 18, 10), (52, 50, 7)):
        p.ring(cx, cy, r, 4.5)
    p.arc(12, 26, 30, 44, 190, 260, 3.5)
    return p.done()


def glass(color):
    p = Pen(color)
    p.poly(_curve(lambda t: 4 + 22 * math.sin(t * math.pi) ** 0.6, 12, 52) + [(12, 4)])
    p.poly([(14, 6), (50, 6), (50, 14), (14, 14)], clear=True)  # the empty top
    p.rect(12, 4, 52, 8)
    p.rect(29.5, 26, 34.5, 54)
    p.ellipse(16, 52, 48, 60)
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
