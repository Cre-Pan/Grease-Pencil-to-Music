# SPDX-License-Identifier: GPL-3.0-or-later
"""Render layers of strokes into one stereo loop, with per-stroke caching.

Pure Python + NumPy: no ``bpy`` import.
"""

import hashlib
from collections import OrderedDict
from dataclasses import astuple, dataclass, field

import numpy as np

from . import effects, interpret, synth


@dataclass
class LayerFx:
    delay_mix: float = 0.0
    delay_beats: float = 0.75
    delay_feedback: float = 0.35
    reverb_mix: float = 0.0
    reverb_size: float = 0.5
    lofi: float = 0.0


@dataclass
class LayerInput:
    name: str
    strokes: list  # list of interpret.StrokeData
    mode: str = "QUANTIZED"
    fill_mode: str = "TONAL"
    glide: float = 0.12
    gain: float = 1.0
    fx: LayerFx = field(default_factory=LayerFx)


@dataclass
class RenderResult:
    audio: np.ndarray  # (n, 2) float32
    sample_rate: int
    notes: list  # interpret.MidiNote, all layers
    key: str  # changes whenever the audio would change
    voice_count: int = 0
    curves: list = field(default_factory=list)  # (start, pitch curve, instrument) glides


class _LRU:
    def __init__(self, size):
        self.size = size
        self.data = OrderedDict()

    def get(self, key):
        if key in self.data:
            self.data.move_to_end(key)
            return self.data[key]
        return None

    def put(self, key, value):
        self.data[key] = value
        self.data.move_to_end(key)
        while len(self.data) > self.size:
            self.data.popitem(last=False)

    def clear(self):
        self.data.clear()


_stroke_cache = _LRU(2048)
_layer_cache = _LRU(64)


def clear_cache():
    _stroke_cache.clear()
    _layer_cache.clear()


def _stroke_key(stroke, context_key):
    h = hashlib.blake2b(digest_size=16)
    for arr in (stroke.x, stroke.z, stroke.radius, stroke.opacity, stroke.color):
        if arr is None:
            h.update(b"-")
        else:
            h.update(np.ascontiguousarray(arr, dtype=np.float32).tobytes())
    h.update(repr((stroke.softness, stroke.instrument, round(stroke.gain, 4), stroke.filled,
                   stroke.fx, stroke.cyclic, context_key)).encode())
    return h.hexdigest()


def _render_stroke(stroke, spec, mapping, mode, fill_mode, radius_ref, sample_rate,
                   context_key, glide=0.12):
    key = _stroke_key(stroke, (context_key, mode, fill_mode, round(glide, 4)))
    cached = _stroke_cache.get(key)
    if cached is not None:
        return key, cached
    interp = interpret.interpret_stroke(stroke, spec, mapping, mode, radius_ref, fill_mode,
                                        glide)
    rendered = [synth.render_voice(v, sample_rate, mapping.vibrato_rate) for v in interp.voices]
    curves = [(v.start, v.pitch[::4].astype(np.float32), v.instrument) for v in interp.voices
              if len(v.pitch) > 1 and float(np.ptp(v.pitch)) > 0.05]
    value = (rendered, interp.notes, curves)
    _stroke_cache.put(key, value)
    return key, value


def _sum(rendered, length):
    end = max([offset + len(buf) for offset, buf in rendered], default=0)
    out = np.zeros((max(end, length), 2), dtype=np.float32)
    for offset, buf in rendered:
        start = max(offset, 0)
        clip = buf[start - offset:]
        out[start:start + len(clip)] += clip
    return out


def _add(a, b):
    if len(b) > len(a):
        a, b = b, a
    a = a.copy()
    a[:len(b)] += b
    return a


def render(layers, spec, mapping, sample_rate=44100, loop=True, master_volume=0.8):
    """Render a list of :class:`LayerInput` into a :class:`RenderResult`."""
    loop_n = max(1, int(round(spec.length * sample_rate)))
    all_strokes = [s for layer in layers for s in layer.strokes]
    radius_ref = max((float(np.max(s.radius)) for s in all_strokes if len(s.radius)),
                     default=0.0)
    context_key = (astuple(spec), astuple(mapping), round(radius_ref, 6), sample_rate)

    master = np.zeros((loop_n, 2), dtype=np.float32)
    notes = []
    curves = []
    layer_keys = []
    voice_count = 0
    for layer in layers:
        stroke_keys = []
        stroke_results = []
        for stroke in layer.strokes:
            key, value = _render_stroke(stroke, spec, mapping, layer.mode, layer.fill_mode,
                                        radius_ref, sample_rate, context_key, layer.glide)
            stroke_keys.append(key)
            stroke_results.append(value)
            notes.extend(value[1])
            curves.extend(value[2])
            voice_count += len(value[0])

        layer_key = hashlib.blake2b(
            repr((stroke_keys, astuple(layer.fx), spec.bpm, sample_rate)).encode(),
            digest_size=16).hexdigest()
        buffer = _layer_cache.get(layer_key)
        if buffer is None:
            # Strokes are summed per instrument effect chain first...
            groups = {}
            for stroke, (rendered, _n, _c) in zip(layer.strokes, stroke_results):
                groups.setdefault(stroke.fx, []).extend(rendered)
            buffer = np.zeros((loop_n, 2), dtype=np.float32)
            for fx, rendered in groups.items():
                part = _sum(rendered, loop_n)
                if fx is not None:
                    part = effects.apply_chain(part, sample_rate, LayerFx(*fx), spec.bpm)
                buffer = _add(buffer, part)
            # ...then the layer effects.
            buffer = effects.apply_chain(buffer, sample_rate, layer.fx, spec.bpm)
            _layer_cache.put(layer_key, buffer)
        layer_keys.append((layer_key, round(layer.gain, 4)))

        scaled = buffer * layer.gain
        if loop:
            # Fold echo/reverb/release tails back onto the start of the loop.
            for begin in range(0, len(scaled), loop_n):
                chunk = scaled[begin:begin + loop_n]
                master[:len(chunk)] += chunk
        else:
            if len(scaled) > len(master):
                master = np.concatenate(
                    (master, np.zeros((len(scaled) - len(master), 2), dtype=np.float32)))
            master[:len(scaled)] += scaled

    master *= master_volume
    peak = float(np.max(np.abs(master))) if len(master) else 0.0
    if peak > 0.98:
        master *= 0.98 / peak

    key = hashlib.blake2b(
        repr((layer_keys, loop, round(master_volume, 4), context_key)).encode(),
        digest_size=16).hexdigest()
    return RenderResult(master.astype(np.float32), sample_rate, notes, key, voice_count,
                        curves)
