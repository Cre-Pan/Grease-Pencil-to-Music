# SPDX-License-Identifier: GPL-3.0-or-later
"""Text as Grease Pencil fills: the board's labels with Blender's own font.

The names of the lanes and keys, the composition's name under the board and the
frame number on the playhead are part of the board itself (filled strokes of the
grid object), so they move and turn with the composition and show in renders.

Their outlines come from a Text object of Blender's built-in font (the font of the
interface), converted to curves and sampled into polylines. The Text object is only
a temporary helper: it is never linked to a scene and is removed after use.
Outlines are cached per string (and per character for the frame number).

Blender refuses to write to a data-block while it draws (gizmos, panels): there the
helper cannot be used. The frame number's digits and the font metrics are then
estimated for that one call and laid out right after by a timer, outside the draw
(see :func:`warm_up`); the 3D views are redrawn with the real widths.
"""

import bpy
from mathutils.geometry import interpolate_bezier

RESOLUTION = 5  # points per Bézier segment
CACHE_LIMIT = 4000

_strings = {}  # text -> (contours, width)
_chars = {}  # character -> (contours, advance)
_metrics = {}

# Fallbacks while the font cannot be laid out (drawing): size-1 estimates.
FALLBACK_ADVANCE = 0.6
FALLBACK_METRICS = {"cap": 0.7, "digit": 0.7}
DIGITS = "0123456789-"


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


def _layout_metrics():
    with _Helper() as helper:
        for key, sample in (("cap", "H"), ("digit", "0")):
            lines = helper.contours(sample)
            ys = [y for line in lines for _x, y in line]
            _metrics[key] = (max(ys) if ys else 0.7) or 0.7


def metrics():
    """``{"cap": height of a capital, "digit": height of a digit}`` at size 1."""
    if not _metrics:
        try:
            _layout_metrics()
        except (AttributeError, RuntimeError):  # drawing: no data-block writes
            _metrics.clear()
            schedule_warm_up()
            return FALLBACK_METRICS
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


def _layout_chars(chars):
    with _Helper() as helper:
        for ch in chars:
            single = helper.contours(ch)
            double = helper.contours(ch + ch)
            if single and len(double) >= 2 * len(single):
                advance = double[len(single)][0][0] - single[0][0][0]
            else:
                advance = FALLBACK_ADVANCE
            _chars[ch] = (single, advance)


def _char(c):
    """``(contours, advance)`` of one character, from "cc" laid out by the font."""
    found = _chars.get(c)
    if found is not None:
        return found
    try:
        _layout_chars({c, *DIGITS} - set(_chars))
    except (AttributeError, RuntimeError):  # drawing: no data-block writes
        _pending.add(c)
        schedule_warm_up()
        return [], FALLBACK_ADVANCE
    return _chars[c]


# --- Laying out later, outside the draw -------------------------------------------

_pending = set()  # characters asked for while drawing
_tries = [0]
MAX_TRIES = 20


def warm_up():
    """Lay out the digits and the metrics now (a context that may write data-blocks).
    Returns ``None``: as a timer it runs once."""
    try:
        missing = ({*DIGITS} | _pending) - set(_chars)
        if missing:
            _layout_chars(missing)
        if not _metrics:
            _layout_metrics()
        _pending.clear()
    except (AttributeError, RuntimeError, ReferenceError):
        _tries[0] += 1
        return 0.5 if _tries[0] < MAX_TRIES else None  # not allowed yet: again shortly
    _tries[0] = 0
    _redraw()
    return None


def schedule_warm_up():
    """Lay out the digits and the metrics as soon as Blender is idle."""
    try:
        if not bpy.app.timers.is_registered(warm_up):
            bpy.app.timers.register(warm_up, first_interval=0.0)
    except (AttributeError, RuntimeError, ValueError):
        pass


def _redraw():
    """Redraw the 3D views: the gizmos ask again for the real widths."""
    wm = getattr(bpy.context, "window_manager", None)
    for window in getattr(wm, "windows", ()):
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def unregister():
    if bpy.app.timers.is_registered(warm_up):
        bpy.app.timers.unregister(warm_up)


def number_outline(text):
    """``(contours, width)`` of a frame number, from cached digits (no new layout per
    frame while playing)."""
    out, x, estimated = [], 0.0, False
    for c in text:
        lines, advance = _char(c)
        estimated = estimated or not lines
        out.extend([[(px + x, py) for px, py in line] for line in lines])
        x += advance
    # A character not laid out yet (while drawing) still takes its estimated room.
    return out, max(_width(out), x) if estimated else _width(out)


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
