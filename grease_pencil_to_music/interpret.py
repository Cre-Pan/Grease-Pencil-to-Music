# SPDX-License-Identifier: GPL-3.0-or-later
"""Turn Grease Pencil strokes into musical voices.

The board lives in the object's local X-Z plane:

* X is time: ``seconds = x / seconds_width`` (x = 0 is the loop start).
* Z is pitch: each row of height ``row_height`` is one semitone, the bottom
  row (``0 <= z < row_height``) is ``low_note``.

Two reading modes exist per layer:

* ``QUANTIZED``: the stroke is split into notes every time it crosses a row;
  pitches snap to the chosen scale, start/end snap to the rhythmic grid.
* ``OPTICAL``: McLaren style; the pitch follows the line continuously.

Pure Python + NumPy: no ``bpy`` import.
"""

from dataclasses import dataclass, field

import numpy as np

from . import music

CONTROL_RATE = 200.0  # control curves are sampled at this rate (Hz)


@dataclass
class StrokeData:
    """Raw per-point data of one stroke, in board (object local) space."""

    x: np.ndarray
    z: np.ndarray
    radius: np.ndarray
    opacity: np.ndarray
    color: np.ndarray = None  # (N, 4) linear RGBA vertex color, optional
    softness: float = 0.0
    instrument: str = "SINE"
    layer: str = ""
    gain: float = 1.0  # instrument (material) volume
    filled: bool = False  # filled shape: read as a cluster


@dataclass
class BoardSpec:
    low_note: int = 48
    row_height: float = 0.12
    seconds_width: float = 1.0
    length: float = 8.0
    bpm: float = 120.0
    scale: str = "CHROMATIC"
    root: int = 0
    time_grid: str = "OFF"
    min_note: float = 0.06
    swing: float = 0.0


@dataclass
class Mapping:
    """How stroke attributes become sound (set in the add-on preferences)."""

    thickness: str = "VOLUME"  # VOLUME, VOLUME_VIBRATO, VIBRATO, BRIGHTNESS, NONE
    opacity: str = "BRIGHTNESS"  # VOLUME, BRIGHTNESS, NONE
    vertex_color: str = "NONE"  # PAN, BRIGHTNESS, NONE
    softness: str = "ATTACK"  # ATTACK, NONE
    vibrato_depth: float = 0.6  # semitones at full jitter
    vibrato_rate: float = 5.5  # Hz


@dataclass
class Voice:
    """One sounding event. Curves are sampled at CONTROL_RATE from ``start``."""

    start: float
    duration: float
    pitch: np.ndarray
    amp: np.ndarray
    vibrato: np.ndarray
    brightness: np.ndarray
    pan: np.ndarray
    attack: float = 0.005
    instrument: str = "SINE"
    band_low: np.ndarray = None  # noise band edges (MIDI pitch), NOISE clusters only
    band_high: np.ndarray = None


NOISE_BAND = "NOISE_BAND"  # internal instrument of noise clusters


@dataclass
class MidiNote:
    start: float
    end: float
    pitch: int
    velocity: int
    instrument: str = "SINE"
    layer: str = ""


@dataclass
class Interpretation:
    voices: list = field(default_factory=list)
    notes: list = field(default_factory=list)


DEFAULT_BRIGHTNESS = 0.7
SHORT_NOTE = 0.15  # duration of a dot / vertical tap when no grid is set


def _moving_average(values, window):
    window = int(max(1, min(window, len(values))))
    if window % 2 == 0:
        window -= 1
    if window <= 1:
        return values.astype(np.float64)
    pad = window // 2
    padded = np.pad(values.astype(np.float64), pad, mode="edge")
    return np.convolve(padded, np.ones(window) / window, mode="valid")


def _monotonic(x, arrays):
    """Keep the stroke readable left to right.

    Strokes drawn right to left are reversed; points that go back in time
    (loops, scribbles) are dropped, like a reader head that only moves forward.
    """
    if len(x) > 1 and x[-1] < x[0]:
        x = x[::-1]
        arrays = [None if a is None else a[::-1] for a in arrays]
    running_max = np.maximum.accumulate(x)
    keep = np.ones(len(x), dtype=bool)
    keep[1:] = x[1:] > running_max[:-1]
    return x[keep], [None if a is None else a[keep] for a in arrays]


def _point_channels(stroke, x_keep, arrays, mapping, radius_ref):
    """Compute per-point control channels from the stroke attributes."""
    _z, radius, opacity, color = arrays
    n = len(x_keep)
    window = 9 if n >= 9 else max(1, n | 1)

    radius_slow = _moving_average(radius, window)
    radius_fast = radius - radius_slow
    mean_radius = max(float(np.mean(radius_slow)), 1e-9)
    jitter = _moving_average(np.abs(radius_fast), window) / mean_radius
    ref = radius_ref if radius_ref > 0 else max(float(np.max(radius)), 1e-9)

    amp = np.ones(n)
    vibrato = np.zeros(n)
    brightness = None
    pan = np.zeros(n)

    def add_brightness(value):
        nonlocal brightness
        brightness = value if brightness is None else brightness * value

    if mapping.thickness == "VOLUME_VIBRATO":
        amp *= radius_slow / ref
        vibrato = jitter
    elif mapping.thickness == "VOLUME":
        amp *= radius / ref
    elif mapping.thickness == "VIBRATO":
        vibrato = jitter
    elif mapping.thickness == "BRIGHTNESS":
        add_brightness(radius_slow / ref)

    if mapping.opacity == "VOLUME":
        amp *= opacity
    elif mapping.opacity == "BRIGHTNESS":
        add_brightness(opacity)

    if color is not None and mapping.vertex_color != "NONE":
        alpha = color[:, 3]
        if mapping.vertex_color == "PAN":
            # Red pushes left, blue pushes right, weighted by vertex color alpha.
            pan = np.clip((color[:, 2] - color[:, 0]) * alpha, -1.0, 1.0)
        elif mapping.vertex_color == "BRIGHTNESS":
            luminance = color[:, :3] @ np.array([0.2126, 0.7152, 0.0722])
            base = DEFAULT_BRIGHTNESS if brightness is None else brightness
            brightness = base * (1.0 - alpha) + luminance * alpha

    if brightness is None:
        brightness = np.full(n, DEFAULT_BRIGHTNESS)

    # Clean strokes have a tiny jitter from tablet noise: ignore it.
    vibrato_amount = np.clip((vibrato - 0.03) * 2.2, 0.0, 1.0) * mapping.vibrato_depth

    amp = amp * float(stroke.gain)
    return {
        "amp": np.clip(amp, 0.0, 3.0),
        "vibrato": vibrato_amount,
        "brightness": np.clip(brightness, 0.0, 1.0),
        "pan": pan,
    }


def _segments(pitches, min_len):
    """Split a pitch curve into constant-pitch runs; absorb runs shorter than
    ``min_len`` samples so that wobbling on a row boundary does not stutter."""
    n = len(pitches)
    change = np.flatnonzero(np.diff(pitches) != 0) + 1
    bounds = np.concatenate(([0], change, [n]))
    raw = [(int(bounds[i]), int(bounds[i + 1]), int(pitches[bounds[i]]))
           for i in range(len(bounds) - 1)]

    merged = []
    carry_start = None
    for start, end, pitch in raw:
        if carry_start is not None:
            start, carry_start = carry_start, None
        if end - start < min_len and len(raw) > 1:
            if merged:
                prev = merged[-1]
                merged[-1] = (prev[0], end, prev[2])
            else:
                carry_start = start
            continue
        if merged and merged[-1][2] == pitch:
            merged[-1] = (merged[-1][0], end, pitch)
        else:
            merged.append((start, end, pitch))
    if carry_start is not None:
        if merged:
            prev = merged[-1]
            merged[-1] = (prev[0], n, prev[2])
        else:
            merged.append((carry_start, n, int(pitches[carry_start])))
    return merged


def _resample(curve, count):
    if len(curve) == count:
        return curve.astype(np.float64)
    if len(curve) == 1:
        return np.full(count, float(curve[0]))
    src = np.linspace(0.0, 1.0, len(curve))
    dst = np.linspace(0.0, 1.0, count)
    return np.interp(dst, src, curve)


def _make_voice(start, duration, pitch, channels, i0, i1, attack, instrument):
    count = max(2, int(round(duration * CONTROL_RATE)) + 1)
    curves = {k: _resample(v[i0:i1], count) for k, v in channels.items()}
    if np.isscalar(pitch):
        pitch_curve = np.full(count, float(pitch))
    else:
        pitch_curve = _resample(pitch[i0:i1], count)
    return Voice(
        start=float(start),
        duration=float(duration),
        pitch=pitch_curve,
        amp=curves["amp"],
        vibrato=curves["vibrato"],
        brightness=curves["brightness"],
        pan=curves["pan"],
        attack=attack,
        instrument=instrument,
    )


def _snap(seconds, step, swing):
    """Snap to the rhythmic grid; odd grid steps are delayed by the swing."""
    if not step:
        return float(seconds)
    k = int(round(seconds / step))
    return k * step + (swing * step if k % 2 else 0.0)


def _velocity(amp):
    return int(np.clip(round(float(np.mean(amp)) * 127), 1, 127))


def _fill_bounds(x, z, tc):
    """Lower and upper edge (z) of a closed shape at each time in ``tc``."""
    x0, z0 = x, z
    x1, z1 = np.roll(x, -1), np.roll(z, -1)
    t = tc[:, None]
    inside = ((x0[None, :] <= t) & (t < x1[None, :])) | ((x1[None, :] <= t) & (t < x0[None, :]))
    dx = np.where(np.abs(x1 - x0) < 1e-12, 1e-12, x1 - x0)
    zt = z0[None, :] + (t - x0[None, :]) * ((z1 - z0) / dx)[None, :]
    low = np.where(inside, zt, np.inf).min(axis=1)
    high = np.where(inside, zt, -np.inf).max(axis=1)
    return low, high


def _interpret_fill(stroke, spec, mapping, fill_mode, radius_ref):
    """A filled shape is a cluster: every note it covers (TONAL) or a band of
    noise between its lower and upper edge (NOISE), like the ANS synthesizer."""
    result = Interpretation()
    sw = max(spec.seconds_width, 1e-9)
    h = max(spec.row_height, 1e-9)
    t = np.asarray(stroke.x, dtype=np.float64) / sw
    rows = np.asarray(stroke.z, dtype=np.float64) / h
    t0, t1 = max(float(t.min()), 0.0), min(float(t.max()), spec.length)
    if t1 - t0 < 1.0 / CONTROL_RATE:
        return result
    count = max(2, int(np.ceil((t1 - t0) * CONTROL_RATE)) + 1)
    tc = np.linspace(t0, t1, count)
    low, high = _fill_bounds(t, rows, tc)
    active = np.isfinite(low) & np.isfinite(high) & (high > low)
    if not np.any(active):
        return result

    ref = radius_ref if radius_ref > 0 else max(float(np.max(stroke.radius)), 1e-9)
    level = float(stroke.gain)
    if mapping.thickness in ("VOLUME", "VOLUME_VIBRATO"):
        level *= float(np.clip(np.mean(stroke.radius) / ref, 0.0, 1.5))
    if mapping.opacity == "VOLUME":
        level *= float(np.mean(stroke.opacity))
    attack = 0.005 + float(stroke.softness) * 0.4 if mapping.softness == "ATTACK" else 0.005
    min_len = max(1, int(round(spec.min_note * CONTROL_RATE)))

    if fill_mode == "NOISE":
        fill_low = np.where(active, low, 0.0)
        fill_high = np.where(active, high, 0.0)
        amp = np.where(active, level, 0.0)
        n = count
        zeros = np.zeros(n)
        result.voices.append(Voice(
            start=t0, duration=t1 - t0,
            pitch=spec.low_note + (fill_low + fill_high) / 2.0 - 0.5,
            amp=amp, vibrato=zeros, brightness=np.full(n, DEFAULT_BRIGHTNESS), pan=zeros,
            attack=attack, instrument=NOISE_BAND,
            band_low=spec.low_note + fill_low - 0.5,
            band_high=spec.low_note + fill_high - 0.5))
        return result

    lookup = music.scale_lookup(spec.scale, spec.root)
    step = music.grid_step_seconds(spec.bpm, spec.time_grid)
    first = int(np.floor(np.min(low[active])))
    last = int(np.ceil(np.max(high[active])))
    pitches = [spec.low_note + r for r in range(first, last + 1)
               if 0 <= spec.low_note + r <= 127
               and lookup[spec.low_note + r] == spec.low_note + r][:48]
    masks = {p: active & (low <= p - spec.low_note + 0.5) & (p - spec.low_note + 0.5 <= high)
             for p in pitches}
    voices_at_once = max(1, int(np.max(np.sum([m for m in masks.values()], axis=0)))
                         if masks else 1)
    note_level = level / np.sqrt(voices_at_once)
    zeros = np.zeros(count)
    channels = {"amp": np.full(count, note_level), "vibrato": zeros,
                "brightness": np.full(count, DEFAULT_BRIGHTNESS), "pan": zeros}
    for pitch, mask in masks.items():
        for i0, i1, on in _segments(mask.astype(np.int64), min_len):
            if not on:
                continue
            start = _snap(float(tc[i0]), step, spec.swing)
            end = _snap(float(tc[i1]) if i1 < count else t1, step, spec.swing)
            if end <= start or start >= spec.length:
                continue
            voice = _make_voice(start, end - start, pitch, channels, i0, max(i1, i0 + 1),
                                attack, stroke.instrument)
            result.voices.append(voice)
            result.notes.append(MidiNote(start, end, pitch, _velocity(voice.amp),
                                         stroke.instrument, stroke.layer))
    return result


def interpret_stroke(stroke, spec, mapping, mode="QUANTIZED", radius_ref=0.0,
                     fill_mode="TONAL"):
    """Return an :class:`Interpretation` (voices to synthesize + MIDI notes)."""
    result = Interpretation()
    if len(stroke.x) == 0:
        return result
    if stroke.filled:
        return _interpret_fill(stroke, spec, mapping, fill_mode, radius_ref)

    x, arrays = _monotonic(
        np.asarray(stroke.x, dtype=np.float64),
        [np.asarray(stroke.z, dtype=np.float64),
         np.asarray(stroke.radius, dtype=np.float64),
         np.asarray(stroke.opacity, dtype=np.float64),
         None if stroke.color is None else np.asarray(stroke.color, dtype=np.float64)],
    )
    z = arrays[0]
    channels_pts = _point_channels(stroke, x, arrays, mapping, radius_ref)
    attack = 0.005 + float(stroke.softness) * 0.4 if mapping.softness == "ATTACK" else 0.005

    t = x / max(spec.seconds_width, 1e-9)
    row = z / max(spec.row_height, 1e-9)
    midi_cont = spec.low_note + row - 0.5
    midi_row = spec.low_note + np.floor(row)
    lookup = music.scale_lookup(spec.scale, spec.root)
    step = music.grid_step_seconds(spec.bpm, spec.time_grid)

    def snapped(values):
        return lookup[np.clip(values.astype(np.int64), 0, 127)]

    t0, t1 = float(t[0]), float(t[-1])
    if t1 < 0.0 or t0 >= spec.length:
        return result

    # A dot or a vertical tap: one short note at the median height.
    if t1 - t0 < max(spec.min_note, 1.0 / CONTROL_RATE):
        start = _snap(max(t0, 0.0), step, spec.swing)
        if start >= spec.length:
            return result
        duration = step if step else SHORT_NOTE
        if mode == "OPTICAL":
            pitch = float(np.median(midi_cont))
        else:
            pitch = int(snapped(np.array([np.median(midi_row)]))[0])
        channels = {k: np.array([float(np.mean(v))]) for k, v in channels_pts.items()}
        voice = _make_voice(start, duration, pitch, channels, 0, 1, attack, stroke.instrument)
        result.voices.append(voice)
        result.notes.append(MidiNote(start, start + duration, int(round(pitch)),
                                     _velocity(voice.amp), stroke.instrument, stroke.layer))
        return result

    # Sample every channel on a regular control grid inside the loop.
    t0c, t1c = max(t0, 0.0), min(t1, spec.length)
    count = max(2, int(np.ceil((t1c - t0c) * CONTROL_RATE)) + 1)
    tc = np.linspace(t0c, t1c, count)
    channels = {k: np.interp(tc, t, v) for k, v in channels_pts.items()}
    cont = np.interp(tc, t, midi_cont)
    rows = spec.low_note + np.floor(np.interp(tc, t, row))
    min_len = max(1, int(round(spec.min_note * CONTROL_RATE)))

    def note_end(i1):
        return float(tc[i1]) if i1 < count else t1c

    if mode == "OPTICAL":
        result.voices.append(
            _make_voice(t0c, t1c - t0c, cont, channels, 0, count, attack, stroke.instrument))
        for i0, i1, pitch in _segments(np.round(cont).astype(np.int64), min_len):
            amp = channels["amp"][i0:i1]
            result.notes.append(MidiNote(float(tc[i0]), note_end(i1), pitch, _velocity(amp),
                                         stroke.instrument, stroke.layer))
        return result

    pitches = snapped(rows)
    for i0, i1, pitch in _segments(pitches, min_len):
        start, end = float(tc[i0]), note_end(i1)
        if step:
            start = _snap(start, step, spec.swing)
            end = _snap(end, step, spec.swing)
            if end <= start:
                continue
        if start >= spec.length:
            continue
        voice = _make_voice(start, end - start, pitch, channels, i0, max(i1, i0 + 1),
                            attack, stroke.instrument)
        result.voices.append(voice)
        result.notes.append(MidiNote(start, end, pitch, _velocity(voice.amp),
                                     stroke.instrument, stroke.layer))
    # Grid snapping may have swallowed every note of a very short stroke.
    if step and not result.voices:
        pitch = int(pitches[0])
        start = _snap(t0c, step, spec.swing)
        if start < spec.length:
            voice = _make_voice(start, step, pitch, channels, 0, count, attack,
                                stroke.instrument)
            result.voices.append(voice)
            result.notes.append(MidiNote(start, start + step, pitch, _velocity(voice.amp),
                                         stroke.instrument, stroke.layer))
    return result
