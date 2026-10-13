# SPDX-License-Identifier: GPL-3.0-or-later
"""Music theory helpers: note names, frequencies, scales and time grids.

Pure Python + NumPy: no ``bpy`` import, so it can be unit tested outside Blender.
"""

import numpy as np

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
NOTE_NAMES_IT = ("Do", "Do#", "Re", "Re#", "Mi", "Fa", "Fa#", "Sol", "Sol#", "La", "La#", "Si")
NAMING_STYLES = {"EN": NOTE_NAMES, "IT": NOTE_NAMES_IT}
BLACK_PITCH_CLASSES = frozenset((1, 3, 6, 8, 10))

# (identifier, label, intervals from the root)
SCALES = (
    ("CHROMATIC", "Cromatica", (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)),
    ("MAJOR", "Maggiore", (0, 2, 4, 5, 7, 9, 11)),
    ("MINOR", "Minore naturale", (0, 2, 3, 5, 7, 8, 10)),
    ("PENTA_MAJOR", "Pentatonica maggiore", (0, 2, 4, 7, 9)),
    ("PENTA_MINOR", "Pentatonica minore", (0, 3, 5, 7, 10)),
    ("BLUES", "Blues", (0, 3, 5, 6, 7, 10)),
    ("DORIAN", "Dorica", (0, 2, 3, 5, 7, 9, 10)),
)
SCALE_INTERVALS = {ident: intervals for ident, _label, intervals in SCALES}

# (identifier, label, subdivisions per beat; 0 = no quantization)
TIME_GRIDS = (
    ("OFF", "Libero", 0),
    ("1_4", "1/4", 1),
    ("1_8", "1/8", 2),
    ("1_8T", "1/8 terzina", 3),
    ("1_16", "1/16", 4),
    ("1_16T", "1/16 terzina", 6),
    ("1_32", "1/32", 8),
)
TIME_GRID_DIVISIONS = {ident: div for ident, _label, div in TIME_GRIDS}


def note_name(midi, style="EN"):
    """Scientific pitch notation: 60 -> 'C4' (or 'Do4' with style 'IT')."""
    midi = int(midi)
    names = NAMING_STYLES.get(style, NOTE_NAMES)
    return f"{names[midi % 12]}{midi // 12 - 1}"


def is_black(midi):
    return int(midi) % 12 in BLACK_PITCH_CLASSES


def midi_to_freq(midi):
    """Works on scalars and NumPy arrays; accepts fractional MIDI pitches."""
    return 440.0 * np.power(2.0, (np.asarray(midi, dtype=np.float64) - 69.0) / 12.0)


def scale_lookup(scale="CHROMATIC", root=0):
    """Table mapping every MIDI note 0..127 to the nearest note of the scale.

    Ties are resolved downwards, so a note exactly between two scale notes
    falls on the lower one.
    """
    intervals = SCALE_INTERVALS.get(scale, SCALE_INTERVALS["CHROMATIC"])
    allowed_pcs = {(int(root) + i) % 12 for i in intervals}
    allowed = np.array([m for m in range(-12, 140) if m % 12 in allowed_pcs])
    notes = np.arange(128)
    dist = np.abs(notes[:, None] - allowed[None, :])
    # argmin returns the first (lowest) candidate on ties.
    return allowed[np.argmin(dist, axis=1)]


def snap_to_scale(midi, scale="CHROMATIC", root=0):
    table = scale_lookup(scale, root)
    idx = np.clip(np.asarray(midi, dtype=np.int64), 0, 127)
    return table[idx]


def grid_step_seconds(bpm, grid):
    """Length in seconds of one cell of the rhythmic grid, or 0 when free."""
    div = TIME_GRID_DIVISIONS.get(grid, 0)
    if div <= 0 or bpm <= 0:
        return 0.0
    return 60.0 / bpm / div


def quantize_time(seconds, step):
    if step <= 0:
        return np.asarray(seconds, dtype=np.float64)
    return np.round(np.asarray(seconds, dtype=np.float64) / step) * step
