# SPDX-License-Identifier: GPL-3.0-or-later
"""The Bit composition: a rhythm board of horizontal lanes, one percussion each.

A stroke plays the drum of the lane it lies in; where it is inside the lane does
not change the sound. Lane 0 is the bottom one. Pure Python (no ``bpy``): the
settings only need ``kind``, ``lanes``, ``lane_drums`` (items with ``drum``) and
``row_height``.
"""

from dataclasses import replace

import numpy as np

from . import synth

NOTES, BEAT = "NOTES", "BEAT"
KIND_ITEMS = (
    (NOTES, "Note", "Tavola con la tastiera: l'altezza del tratto è la nota"),
    (BEAT, "Ritmica", "Tavola del ritmo: una percussione per corsia"),
)

# Figma "Composizione Bit": 8 lanes in the 630 px of the window (3 octaves of the
# note board), so one lane is 630 / 8 = 78.75 design px = 4.5 rows of 17.5 px.
LANE_ROWS = 4.5
MIN_LANES, MAX_LANES, DEFAULT_LANES = 1, 16, 8
# From the bottom up, like a drum machine read from the floor.
DEFAULT_DRUMS = ("KICK", "SNARE", "CLAP", "TOM", "RIM", "HIHAT", "OPENHAT", "CRASH",
                 "SHAKER", "COWBELL", "DRUM")
NEUTRAL_PITCH = 60  # the drums sound as designed (no retuning by the row)
LANE_PITCH = {"TOM": 57}  # a mid tom


def percussions():
    """The percussive instruments (synth and recorded hits), in menu order."""
    return [inst for inst in synth.INSTRUMENTS if inst.percussive]


def drum_items():
    return [(inst.ident, inst.label, inst.description) for inst in percussions()]


def is_beat(settings):
    return getattr(settings, "kind", NOTES) == BEAT


def lane_height(settings):
    return LANE_ROWS * settings.row_height


def lane_count(settings):
    return max(MIN_LANES, min(MAX_LANES, int(settings.lanes)))


def default_drum(index, used=()):
    """The drum of a new lane: the next of :data:`DEFAULT_DRUMS` not used yet."""
    for ident in DEFAULT_DRUMS:
        if ident not in used:
            return ident
    return DEFAULT_DRUMS[index % len(DEFAULT_DRUMS)]


def lane_drum(settings, index):
    items = settings.lane_drums
    if 0 <= index < len(items) and items[index].drum:
        return items[index].drum
    return DEFAULT_DRUMS[index % len(DEFAULT_DRUMS)]


def lane_drums(settings):
    return [lane_drum(settings, i) for i in range(lane_count(settings))]


def lane_at(settings, z):
    """Index of the lane at local height ``z`` (None outside the board)."""
    h = lane_height(settings)
    if h <= 0.0 or z < 0.0 or z >= lane_count(settings) * h:
        return None
    return int(z // h)


def lane_pitch(ident):
    """The MIDI pitch a lane plays: fixed, whatever the height of the stroke."""
    return LANE_PITCH.get(ident, NEUTRAL_PITCH)


def stroke_lane(settings, z):
    """The lane of a stroke: where most of it lies (its median height), clamped to
    the board."""
    h = lane_height(settings)
    lane = int(np.floor(float(np.median(z)) / max(h, 1e-9)))
    return max(0, min(lane_count(settings) - 1, lane))


def read_strokes(settings, strokes):
    """The strokes of a Bit composition as the reader of the notes sees them: each one
    takes the drum of its lane and a flat height on the row of that drum's pitch
    (the board spec of a Bit composition starts at MIDI 0, chromatic)."""
    drums = lane_drums(settings)
    h = settings.row_height
    out = []
    for stroke in strokes:
        if not len(stroke.z):
            continue
        ident = drums[stroke_lane(settings, stroke.z)]
        z = np.full(len(stroke.z), (lane_pitch(ident) + 0.5) * h)
        out.append(replace(stroke, z=z, instrument=ident, filled=False, cyclic=False))
    return out
