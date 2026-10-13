# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal Standard MIDI File (type 1) writer, no external dependencies."""

import struct

PPQ = 480
DRUM_CHANNEL = 9


def _vlq(value):
    value = int(value)
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))


def _chunk(kind, data):
    return kind + struct.pack(">I", len(data)) + data


def _track(events):
    """``events``: list of (tick, order, bytes). Order sorts same-tick events
    (note-offs before note-ons)."""
    data = bytearray()
    last = 0
    for tick, _order, payload in sorted(events, key=lambda e: (e[0], e[1])):
        data += _vlq(tick - last) + payload
        last = tick
    data += _vlq(0) + b"\xff\x2f\x00"
    return _chunk(b"MTrk", bytes(data))


def _meta_text(kind, text):
    raw = text.encode("utf-8")[:127]
    return bytes((0xFF, kind)) + _vlq(len(raw)) + raw


def build_midi(tracks, bpm):
    """Build a MIDI file.

    ``tracks``: list of dicts ``{"name": str, "program": int, "notes": [...]}``
    where ``program`` is a General MIDI program (0-based) or -1 for drums and
    each note has ``start``, ``end`` (seconds), ``pitch`` and ``velocity``.
    """
    seconds_to_ticks = PPQ * bpm / 60.0
    tempo = int(round(60_000_000 / max(bpm, 1e-6)))
    conductor = [
        (0, 0, _meta_text(0x03, "Grease Pencil to Music")),
        (0, 1, b"\xff\x51\x03" + tempo.to_bytes(3, "big")),
        (0, 2, b"\xff\x58\x04\x04\x02\x18\x08"),
    ]
    chunks = [_track(conductor)]

    melodic_channels = [c for c in range(16) if c != DRUM_CHANNEL]
    next_channel = 0
    for track in tracks:
        if track["program"] < 0:
            channel = DRUM_CHANNEL
        else:
            channel = melodic_channels[next_channel % len(melodic_channels)]
            next_channel += 1
        events = [(0, 0, _meta_text(0x03, track["name"]))]
        if track["program"] >= 0:
            events.append((0, 1, bytes((0xC0 | channel, track["program"] & 0x7F))))
        for note in track["notes"]:
            start = int(round(note.start * seconds_to_ticks))
            end = max(start + 1, int(round(note.end * seconds_to_ticks)))
            pitch = int(min(max(note.pitch, 0), 127))
            velocity = int(min(max(note.velocity, 1), 127))
            events.append((start, 3, bytes((0x90 | channel, pitch, velocity))))
            events.append((end, 2, bytes((0x80 | channel, pitch, 0))))
        chunks.append(_track(events))

    header = _chunk(b"MThd", struct.pack(">HHH", 1, len(chunks), PPQ))
    return header + b"".join(chunks)


def write_midi(path, tracks, bpm):
    with open(path, "wb") as handle:
        handle.write(build_midi(tracks, bpm))
