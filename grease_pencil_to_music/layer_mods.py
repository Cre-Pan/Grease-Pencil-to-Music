# SPDX-License-Identifier: GPL-3.0-or-later
"""Non-destructive modifiers of a layer, as in the web app.

They change the strokes on their way to the sound: the strokes drawn in
Blender stay as they are, and every modifier can be turned off at any time.
``stroke_mods.py`` shows the same changes on the drawing (Geometry Nodes).
They always run in the order of the panels: Array, Simmetria, Trasponi, Fade,
Noise (copies made by Array are mirrored, faded and roughened one by one).

Strokes are :class:`interpret.StrokeData` in board space: X is time
(``seconds * seconds_width``), Z is pitch (one row of ``row_height`` per
semitone, the bottom row is ``low_note``).

Pure Python + NumPy: no ``bpy`` import.
"""

import hashlib
from dataclasses import dataclass, replace

import numpy as np

from . import music

MAX_COPIES = 64  # strokes one stroke may become (as in the web app)


@dataclass(frozen=True)
class Array:
    count: int = 4
    fill: bool = False  # as many copies as fit in the loop
    beats: float = 1.0  # time between two copies
    pitch: int = 0  # each copy moves by this much
    unit: str = "SCALE"  # SCALE (degrees of the scale) or SEMITONES
    decay: float = 0.0  # each copy is this much softer than the previous one


@dataclass(frozen=True)
class Mirror:
    time: bool = True  # retrograde: the stroke runs backwards
    pitch: bool = False  # inversion: high notes become low
    keep: bool = True  # keep the original next to the mirrored copy
    time_center: float = 0.5  # 0..1 of the loop
    pitch_center: float = 0.5  # 0..1 of the board height


@dataclass(frozen=True)
class Transpose:
    steps: int = 2
    unit: str = "SCALE"


@dataclass(frozen=True)
class Fade:
    direction: str = "IN"  # IN, OUT, BOTH
    scope: str = "STROKE"  # STROKE (every stroke) or SONG (the whole loop)
    length: float = 0.5  # 0..1 of the stroke (or of the loop)
    minimum: float = 0.05  # volume left at the thin end


@dataclass(frozen=True)
class Noise:
    pitch: float = 0.15  # semitones
    width: float = 0.25  # 0..1 of the thickness (volume)
    time: float = 0.04  # beats: each stroke moves a little early or late
    scale: float = 6.0  # wobbles per beat
    seed: int = 1


@dataclass(frozen=True)
class Board:
    """The parts of the board the modifiers need."""

    low_note: int = 48
    row_height: float = 0.12
    seconds_width: float = 1.0
    length: float = 8.0  # seconds of the loop
    bpm: float = 120.0
    rows: int = 36  # semitones on the board
    scale: str = "CHROMATIC"
    root: int = 0

    @property
    def beat(self):
        """Board units of one beat."""
        return 60.0 / max(self.bpm, 1e-6) * self.seconds_width

    @property
    def loop(self):
        return self.length * self.seconds_width


# --- Helpers ---------------------------------------------------------------------------

def _noise1(t, seed):
    """Smooth 1-D value noise in [-1, 1] (the web app's ``noise1``)."""
    t = np.asarray(t, dtype=np.float64)

    def h(n):
        x = np.sin((n + seed * 57.13) * 127.1) * 43758.5453
        return x - np.floor(x)

    i = np.floor(t)
    f = t - i
    u = f * f * (3 - 2 * f)
    return (h(i) * (1 - u) + h(i + 1) * u) * 2 - 1


def _hash01(*parts):
    digest = hashlib.blake2b(repr(parts).encode(), digest_size=8).digest()
    return int.from_bytes(digest, "little") / 2.0 ** 64


def _arc(stroke, board):
    """Distance along the stroke at each point, in beats (a semitone counts 1/4)."""
    dx = np.diff(stroke.x) / board.beat
    dz = np.diff(stroke.z) / max(board.row_height, 1e-9) * 0.25
    return np.concatenate(([0.0], np.cumsum(np.hypot(dx, dz))))


def _shift_z(z, steps, unit, board):
    """Z moved by ``steps`` scale degrees or semitones."""
    if not steps:
        return z
    rh = max(board.row_height, 1e-9)
    if unit == "SEMITONES" or board.scale == "CHROMATIC":
        return z + steps * rh
    pitch = board.low_note + z / rh - 0.5  # the middle of a row is a whole note
    moved = music.diatonic_shift(pitch, steps, board.scale, board.root)
    return (moved + 0.5 - board.low_note) * rh


def _copy(stroke, **changes):
    return replace(stroke, **changes)


def _reversed(stroke, x):
    """The stroke running backwards in time, with its new ``x``."""
    times = None
    if stroke.times is not None and len(stroke.times):
        times = (stroke.times[-1] - stroke.times)[::-1].copy()
    return _copy(stroke, x=x[::-1].copy(), z=stroke.z[::-1].copy(),
                 radius=stroke.radius[::-1].copy(), opacity=stroke.opacity[::-1].copy(),
                 color=None if stroke.color is None else stroke.color[::-1].copy(),
                 times=times)


# --- The modifiers ------------------------------------------------------------------------

def _array(stroke, mod, board, tag):
    step = float(np.clip(mod.beats, -64.0, 64.0)) * board.beat
    count = int(np.clip(round(mod.count), 1, MAX_COPIES))
    if mod.fill and step > 0:
        start = float(np.min(stroke.x))
        count = int(np.clip((board.loop - 1e-6 - start) // step + 1, 1, MAX_COPIES))
    out = [(stroke, tag)]
    decay = 1.0 - float(np.clip(mod.decay, 0.0, 0.95))
    for k in range(1, count):
        out.append((_copy(stroke, x=stroke.x + step * k,
                          z=_shift_z(stroke.z, int(mod.pitch) * k, mod.unit, board),
                          radius=stroke.radius * decay ** k), f"{tag}a{k}"))
    return out


def _mirror(stroke, mod, board, tag):
    tc = float(np.clip(mod.time_center, 0.0, 1.0)) * board.loop
    pc = float(np.clip(mod.pitch_center, 0.0, 1.0)) * board.rows * board.row_height

    def flip_t(s):
        return _reversed(s, 2 * tc - s.x)

    def flip_p(s):
        return _copy(s, z=2 * pc - s.z)

    out = [(stroke, tag)] if mod.keep else []
    if mod.time:
        out.append((flip_t(stroke), tag + "t"))
    if mod.pitch:
        out.append((flip_p(stroke), tag + "p"))
    if mod.time and mod.pitch:
        out.append((flip_p(flip_t(stroke)), tag + "tp"))
    return out or [(stroke, tag)]


def _transpose(stroke, mod, board, tag):
    steps = int(round(mod.steps))
    if not steps:
        return [(stroke, tag)]
    return [(_copy(stroke, z=_shift_z(stroke.z, steps, mod.unit, board)), tag)]


def _ease(u):
    u = np.clip(u, 0.0, 1.0)
    return u * u * (3 - 2 * u)


def _fade(stroke, mod, board, tag):
    length = float(np.clip(mod.length, 0.02, 1.0))
    low = float(np.clip(mod.minimum, 0.0, 1.0))
    if mod.scope == "SONG":
        u = np.clip(stroke.x / max(board.loop, 1e-9), 0.0, 1.0)
    else:
        if len(stroke.x) < 2:
            return [(stroke, tag)]
        arc = _arc(stroke, board)
        total = arc[-1]
        if total <= 0:
            return [(stroke, tag)]
        u = arc / total
    gain = np.ones_like(u, dtype=np.float64)
    if mod.direction in ("IN", "BOTH"):
        gain *= _ease(u / length)
    if mod.direction in ("OUT", "BOTH"):
        gain *= _ease((1 - u) / length)
    gain = low + (1 - low) * gain
    return [(_copy(stroke, radius=stroke.radius * gain), tag)]


def _noise(stroke, mod, board, tag):
    # The seed comes from where the stroke starts: adding or removing other
    # strokes does not change the wobble of this one.
    first = (round(float(stroke.x[0]), 4), round(float(stroke.z[0]), 4), len(stroke.x))
    seed = _hash01(first, int(mod.seed)) * 1000.0
    shift = (_hash01(seed, "t") * 2 - 1) * float(mod.time) * board.beat
    u = _arc(stroke, board) * max(float(mod.scale), 0.0)
    z = stroke.z + float(mod.pitch) * board.row_height * _noise1(u, seed + 1)
    radius = stroke.radius * (1 + float(mod.width) * _noise1(u * 1.3, seed + 2))
    radius = np.maximum(radius, 0.01 * board.row_height)
    return [(_copy(stroke, x=stroke.x + shift, z=z, radius=radius), tag)]


@dataclass(frozen=True)
class Stack:
    """The modifiers of one layer that are on (None = off)."""

    array: Array = None
    mirror: Mirror = None
    transpose: Transpose = None
    fade: Fade = None
    noise: Noise = None

    def __bool__(self):
        return any(m is not None for m in
                   (self.array, self.mirror, self.transpose, self.fade, self.noise))


def apply(strokes, stack, board):
    """The strokes of a layer after its modifiers (a new list; the input is untouched)."""
    if not stack or not strokes:
        return list(strokes)
    items = [(stroke, f"s{index}") for index, stroke in enumerate(strokes)
             if len(stroke.x)]
    limit = len(items) * MAX_COPIES
    steps = (
        (stack.array, _array),
        (stack.mirror, _mirror),
        (stack.transpose, _transpose),
        (stack.fade, _fade),
    )
    for mod, fn in steps:
        if mod is None:
            continue
        nxt = []
        for stroke, tag in items:
            nxt.extend(fn(stroke, mod, board, tag))
        items = nxt[:limit]
    if stack.noise is not None:
        items = [pair for stroke, tag in items
                 for pair in _noise(stroke, stack.noise, board, tag)]
    return [stroke for stroke, _tag in items]
