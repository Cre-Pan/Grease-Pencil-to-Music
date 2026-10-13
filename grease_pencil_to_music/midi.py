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


# --- Reading ---------------------------------------------------------------------

class MidiError(ValueError):
    pass


def _read_vlq(data, pos):
    value = 0
    for _ in range(4):
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, pos
    raise MidiError("lunghezza variabile non valida")


def _read_track(data):
    """Raw events of one track: (tick, kind, channel, a, b, payload)."""
    events = []
    pos, tick, status = 0, 0, None
    while pos < len(data):
        delta, pos = _read_vlq(data, pos)
        tick += delta
        byte = data[pos]
        if byte == 0xFF:  # meta event
            kind = data[pos + 1]
            length, pos = _read_vlq(data, pos + 2)
            events.append((tick, "meta", kind, 0, 0, bytes(data[pos:pos + length])))
            pos += length
            if kind == 0x2F:
                break
            continue
        if byte in (0xF0, 0xF7):  # sysex
            length, pos = _read_vlq(data, pos + 1)
            pos += length
            continue
        if byte & 0x80:
            status = byte
            pos += 1
        elif status is None:
            raise MidiError("running status senza stato")
        kind, channel = status & 0xF0, status & 0x0F
        size = 1 if kind in (0xC0, 0xD0) else 2
        a = data[pos]
        b = data[pos + 1] if size == 2 else 0
        pos += size
        events.append((tick, kind, channel, a, b, b""))
    return events


def parse_midi(data):
    """Read a Standard MIDI File.

    Returns ``(tracks, bpm)`` where every track is a dict ``{"name", "channel",
    "program", "notes"}`` (one per MIDI track and channel) and each note is
    ``(start_seconds, end_seconds, pitch, velocity)``.
    """
    data = bytes(data)
    if data[:4] != b"MThd":
        raise MidiError("non è un file MIDI")
    header_len = struct.unpack(">I", data[4:8])[0]
    _fmt, count, division = struct.unpack(">HHH", data[8:14])
    ppq = division if not division & 0x8000 else PPQ  # SMPTE time: assume 480
    pos = 8 + header_len
    raw_tracks = []
    for _ in range(count):
        if data[pos:pos + 4] != b"MTrk":
            break
        length = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        raw_tracks.append(_read_track(data[pos + 8:pos + 8 + length]))
        pos += 8 + length

    tempos = sorted((tick, int.from_bytes(payload[:3], "big"))
                    for events in raw_tracks for tick, kind, sub, _a, _b, payload in events
                    if kind == "meta" and sub == 0x51 and len(payload) >= 3)
    if not tempos or tempos[0][0] > 0:
        tempos.insert(0, (0, 500000))
    # Seconds at every tempo change, for tick -> seconds conversion.
    marks, seconds = [], 0.0
    for i, (tick, tempo) in enumerate(tempos):
        if i:
            prev_tick, prev_tempo = tempos[i - 1]
            seconds += (tick - prev_tick) * prev_tempo / 1e6 / ppq
        marks.append((tick, seconds, tempo))

    def to_seconds(tick):
        base = marks[0]
        for mark in marks:
            if mark[0] <= tick:
                base = mark
            else:
                break
        return base[1] + (tick - base[0]) * base[2] / 1e6 / ppq

    tracks = []
    for index, events in enumerate(raw_tracks):
        name = f"Traccia {index + 1}"
        for _tick, kind, sub, _a, _b, payload in events:
            if kind == "meta" and sub == 0x03 and payload:
                name = payload.decode("utf-8", "replace").strip() or name
                break
        programs, open_notes, by_channel = {}, {}, {}
        for tick, kind, channel, a, b, _payload in events:
            if kind == 0xC0:
                programs[channel] = a
            elif kind == 0x90 and b > 0:
                open_notes.setdefault((channel, a), []).append((tick, b))
            elif kind == 0x80 or (kind == 0x90 and b == 0):
                stack = open_notes.get((channel, a))
                if stack:
                    start, velocity = stack.pop(0)
                    by_channel.setdefault(channel, []).append(
                        (to_seconds(start), to_seconds(max(tick, start + 1)), a, velocity))
        for channel, notes in sorted(by_channel.items()):
            label = name if len(by_channel) == 1 else f"{name} {channel + 1}"
            tracks.append({"name": label, "channel": channel,
                           "program": -1 if channel == DRUM_CHANNEL else programs.get(channel, 0),
                           "notes": sorted(notes)})
    bpm = 60_000_000 / tempos[0][1]
    return tracks, bpm


def read_midi(path):
    with open(path, "rb") as handle:
        return parse_midi(handle.read())
