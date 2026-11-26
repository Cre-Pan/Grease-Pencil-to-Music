# SPDX-License-Identifier: GPL-3.0-or-later
"""Text as Grease Pencil fills: the board's labels with Blender's own font.

The names of the lanes and keys, the composition's name under the board and the
frame number on the playhead are part of the board itself (filled strokes of the
grid object), so they move and turn with the composition and show in renders.

Their outlines come from a Text object of Blender's built-in font (the font of the
interface), converted to curves and sampled into polylines. The Text object is only
a temporary helper: it is never linked to a scene and is removed after use.
Outlines are cached per string (and per character for the frame number).
"""

import bpy
from mathutils.geometry import interpolate_bezier

RESOLUTION = 5  # points per Bézier segment
CACHE_LIMIT = 4000

_strings = {}  # text -> (contours, width)
_chars = {}  # character -> (contours, advance)
_metrics = {}


class _Helper:
    """A Text object outside the scene, removed on exit."""

    def __enter__(self):
        self.curve = bpy.data.curves.new("GP2M Testo (temporaneo)", "FONT")
        self.obj = bpy.data.objects.new("GP2M Testo (temporaneo)", self.curve)
        return self

    def contours(self, text):
        """Outlines of ``text`` (size 1, baseline at 0, starting at x = 0)."""
        self.curve.body = text
        try:
            depsgraph = bpy.context.evaluated_depsgraph_get()
        except (AttributeError, RuntimeError):
            depsgraph = None
        curve = self.obj.to_curve(depsgraph, apply_modifiers=False)
        out = []
        try:
            for spline in curve.splines:
                points = spline.bezier_points
                n = len(points)
                if n < 2:
                    continue
                line = []
                for i in range(n):
                    a, b = points[i], points[(i + 1) % n]
                    seg = interpolate_bezier(a.co, a.handle_right, b.handle_left, b.co,
                                             RESOLUTION + 1)
                    line.extend((p.x, p.y) for p in seg[:-1])
                out.append(line)
        finally:
            self.obj.to_curve_clear()
        return out

    def __exit__(self, *_exc):
        try:
            bpy.data.objects.remove(self.obj)
        except (ReferenceError, RuntimeError):
            pass
        try:
            bpy.data.curves.remove(self.curve)
        except (ReferenceError, RuntimeError):
            pass
        return False


def _width(contours):
    return max((x for line in contours for x, _y in line), default=0.0)


def _remember(cache, key, value):
    if len(cache) >= CACHE_LIMIT:
        cache.clear()
    cache[key] = value
    return value


def metrics():
    """``{"cap": height of a capital, "digit": height of a digit}`` at size 1."""
    if not _metrics:
        with _Helper() as helper:
            for key, sample in (("cap", "H"), ("digit", "0")):
                lines = helper.contours(sample)
                ys = [y for line in lines for _x, y in line]
                _metrics[key] = (max(ys) if ys else 0.7) or 0.7
    return _metrics


def prepare(texts):
    """Lay out every string of ``texts`` not cached yet (one helper for all)."""
    missing = [t for t in dict.fromkeys(texts) if t and t not in _strings]
    if not missing:
        return
    with _Helper() as helper:
        for text in missing:
            lines = helper.contours(text)
            _remember(_strings, text, (lines, _width(lines)))


def outline(text):
    """``(contours, width)`` of ``text`` at size 1."""
    if not text:
        return [], 0.0
    if text not in _strings:
        prepare([text])
    return _strings[text]


def _char(c):
    """``(contours, advance)`` of one character, from "cc" laid out by the font."""
    found = _chars.get(c)
    if found is not None:
        return found
    with _Helper() as helper:
        for ch in {c, *"0123456789-"} - set(_chars):
            single = helper.contours(ch)
            double = helper.contours(ch + ch)
            if single and len(double) >= 2 * len(single):
                advance = double[len(single)][0][0] - single[0][0][0]
            else:
                advance = 0.6
            _chars[ch] = (single, advance)
    return _chars[c]


def number_outline(text):
    """``(contours, width)`` of a frame number, from cached digits (no new layout per
    frame while playing)."""
    out, x = [], 0.0
    for c in text:
        lines, advance = _char(c)
        out.extend([[(px + x, py) for px, py in line] for line in lines])
        x += advance
    return out, _width(out)


def place(contours, width, x, baseline, size, align="LEFT"):
    """The contours at ``(x, baseline)``, ``size`` tall per font unit: board points."""
    if align == "CENTER":
        x -= width * size / 2.0
    elif align == "RIGHT":
        x -= width * size
    return [[(x + px * size, baseline + py * size) for px, py in line] for line in contours]


def fit_size(width, size, room):
    """``size``, smaller when the text (``width`` at size 1) is wider than ``room``."""
    if room > 0 and width * size > room:
        return room / width
    return size


def specs(contours, material_index, group):
    """Stroke specs for :func:`board._add_strokes`: one fill (with its holes) per text."""
    return [(line, 0.001, material_index, "fill", group) for line in contours if len(line) > 2]
