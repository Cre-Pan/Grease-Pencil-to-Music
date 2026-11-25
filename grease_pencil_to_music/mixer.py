# SPDX-License-Identifier: GPL-3.0-or-later
"""Render layers of strokes into one stereo loop, with per-stroke caching.

Pure Python + NumPy: no ``bpy`` import.
"""

import hashlib
from collections import OrderedDict
from dataclasses import astuple, dataclass, field, replace

import numpy as np

from . import effects, interpret, layer_mods, music, synth


@dataclass
class LayerFx:
    delay_mix: float = 0.0
    delay_beats: float = 0.75
    delay_feedback: float = 0.35
    reverb_mix: float = 0.0
    reverb_size: float = 0.5
    lofi: float = 0.0


@dataclass
class MasterFx:
    """The master bus of a composition (effects.master)."""

    enabled: bool = True  # room, glue compressor, saturation and limiter
    ambience: float = 0.25  # how much of the shared hall is heard
    room: str = "HALL"  # effects.ROOMS: the response of every reverb of the composition


def _finish(master, sample_rate, settings, loop):
    """Master bus, or (without it) just a peak guard."""
    return finish_stems([master], sample_rate, settings, loop)[0]


def finish_stems(stems, sample_rate, settings, loop, want_stems=False, keys=None):
    """``(mix, processed stems)`` of a list of layer buffers.

    The master bus (or the peak guard) is computed on their sum and the same
    processing reaches every stem, so the processed stems add up to the mix.
    ``keys`` (one per stem, or None) cache the linear part of each stem: a key, or
    ``(key, scale)`` when the stem is a sound that only its volume ``scale`` tells
    apart (the linear part of the same sound at another volume is reused, scaled)."""
    length = max((len(stem) for stem in stems), default=0)
    stems = [_pad(stem, length) for stem in stems]
    if settings is not None and settings.enabled:
        if not want_stems:
            total = _total(stems, length)
            linear = effects.master_linear(total, sample_rate, settings.ambience, loop,
                                           settings.room)
            return effects.master_dynamics([linear], sample_rate, loop)[0], None
        linears = []
        for index, stem in enumerate(stems):
            entry = None if keys is None else keys[index]
            base, scale = entry if isinstance(entry, tuple) else (entry, None)
            key = None if base is None else (
                base, length, settings.ambience, settings.room, loop, sample_rate)
            cached = _linear_cache.get(key) if key is not None else None
            linear = None
            if cached is not None:
                linear, cached_scale = cached
                if scale is not None and scale != cached_scale:
                    # Linear: the same sound louder or softer has its room louder
                    # or softer (volume, opacity, master volume: no room again).
                    linear = (linear * (scale / cached_scale) if cached_scale
                              else None)
            if linear is None:
                linear = effects.master_linear(stem, sample_rate, settings.ambience, loop,
                                               settings.room)
                if key is not None and (cached is None or scale):
                    _linear_cache.put(key, (linear, scale))
            linears.append(linear)
        return effects.master_dynamics(linears, sample_rate, loop, want_stems=True)
    total = _total(stems, length)
    peak = float(np.max(np.abs(total))) if len(total) else 0.0
    scale = 0.98 / peak if peak > 0.98 else 1.0
    outs = [(stem * scale).astype(np.float32) for stem in stems] if want_stems else None
    return (total * scale).astype(np.float32), outs


def _pad(buffer, length):
    if len(buffer) >= length:
        return buffer
    return np.concatenate((buffer, np.zeros((length - len(buffer), 2), dtype=buffer.dtype)))


def _total(stems, length):
    total = np.zeros((length, 2), dtype=np.float32)
    for stem in stems:
        total[:len(stem)] += stem
    return total


def _master_key(settings):
    return None if settings is None else astuple(settings)


@dataclass
class LayerInput:
    name: str
    strokes: list  # list of interpret.StrokeData
    mode: str = "QUANTIZED"
    fill_mode: str = "TONAL"
    glide: float = 0.12
    gain: float = 1.0
    fx: LayerFx = field(default_factory=LayerFx)
    canon_voices: int = 1  # the layer repeated by later voices (a round)
    canon_delay: float = 2.0  # seconds between two entries
    canon_transpose: int = 0  # semitones from one voice to the next
    legato_gap: float = 1.0  # beats: in the legato modes closer strokes become one voice
    harmony: str = "OFF"  # music.HARMONIES: voices added in the scale
    mods: layer_mods.Stack = field(default_factory=layer_mods.Stack)  # modifiers that are on
    rows: int = 36  # semitones on the board (the centre of Simmetria in pitch)


def mods_board(spec, rows):
    """The :class:`layer_mods.Board` of a :class:`interpret.BoardSpec`."""
    return layer_mods.Board(low_note=spec.low_note, row_height=spec.row_height,
                            seconds_width=spec.seconds_width, length=spec.length,
                            bpm=spec.bpm, rows=rows, scale=spec.scale, root=spec.root)


def with_modifiers(layer, spec):
    """The layer with its strokes passed through its modifiers."""
    if not layer.mods:
        return layer
    return replace(layer, strokes=layer_mods.apply(layer.strokes, layer.mods,
                                                   mods_board(spec, layer.rows)))


@dataclass
class RenderResult:
    audio: np.ndarray  # (n, 2) float32
    sample_rate: int
    notes: list  # interpret.MidiNote, all layers
    key: str  # changes whenever the audio would change
    voice_count: int = 0
    curves: list = field(default_factory=list)  # (start, pitch curve, instrument) glides
    duration: float = 0.0  # seconds of music (without tails); 0 = one loop
    sections: tuple = ()  # start seconds of the keyframe sections (empty = one loop)
    errors: int = 0  # strokes / voices skipped because they could not be rendered
    stems: list = field(default_factory=list)  # [(layer name, audio)] when asked: they add up to audio
    layers: list = field(default_factory=list)  # [LayerSound] before the master bus (render only)


@dataclass
class LayerSound:
    """One layer rendered before the master bus (layer and master volume included)."""

    name: str
    audio: np.ndarray  # (n, 2) float32: one loop with folded tails, or the whole piece
    key: str  # changes whenever this audio would change
    notes: list = field(default_factory=list)
    curves: list = field(default_factory=list)
    voices: int = 0
    errors: int = 0
    base_key: str = ""  # like key, without the volume: the same sound at any volume
    scale: float = 1.0  # the volume of this sound (layer and master volume)


def _nbytes(value):
    """Rough memory held by a cached value (the audio buffers inside it)."""
    if isinstance(value, np.ndarray):
        return value.nbytes
    if isinstance(value, (list, tuple)):
        return sum(_nbytes(v) for v in value)
    return 0


class _LRU:
    """Least recently used cache, limited in entries and in bytes of audio."""

    def __init__(self, size, max_bytes=None):
        self.size = size
        self.max_bytes = max_bytes
        self.bytes = 0
        self.data = OrderedDict()

    def get(self, key):
        if key in self.data:
            self.data.move_to_end(key)
            return self.data[key][0]
        return None

    def put(self, key, value):
        if key in self.data:
            self.bytes -= self.data.pop(key)[1]
        weight = _nbytes(value)
        self.data[key] = (value, weight)
        self.bytes += weight
        while len(self.data) > 1 and (len(self.data) > self.size or (
                self.max_bytes is not None and self.bytes > self.max_bytes)):
            self.bytes -= self.data.popitem(last=False)[1][1]

    def clear(self):
        self.data.clear()
        self.bytes = 0


MB = 1024 * 1024
_interp_cache = _LRU(4096)
_stroke_cache = _LRU(2048, 512 * MB)
_layer_cache = _LRU(64, 256 * MB)
_linear_cache = _LRU(64, 256 * MB)  # layers through the room of the master bus
_mix_cache = _LRU(4, 128 * MB)  # finished mixes (and stems) of the last renders


def clear_cache():
    _interp_cache.clear()
    _stroke_cache.clear()
    _layer_cache.clear()
    _linear_cache.clear()
    _mix_cache.clear()


class _Errors:
    """Counts what could not be rendered; the first error of a render is printed."""

    def __init__(self):
        self.count = 0

    def add(self, error, what):
        if not self.count:
            print(f"[Doodle Music] {what} skipped: {error!r}")
        self.count += 1


def _render_voices(voices, sample_rate, vibrato_rate, errors):
    """Render each voice on its own: one broken voice does not silence the rest."""
    out = []
    for voice in voices:
        try:
            out.append(synth.render_voice(voice, sample_rate, vibrato_rate))
        except Exception as error:  # noqa: BLE001 - keep the other voices
            errors.add(error, "voice")
    return out


def _curves_of(voices):
    return [(v.start, v.pitch[::4].astype(np.float32), v.instrument) for v in voices
            if len(v.pitch) > 1 and float(np.ptp(v.pitch)) > 0.05]


def _stroke_key(stroke, context_key):
    h = hashlib.blake2b(digest_size=16)
    for arr in (stroke.x, stroke.z, stroke.radius, stroke.opacity, stroke.color, stroke.times):
        if arr is None:
            h.update(b"-")
        else:
            h.update(np.ascontiguousarray(arr, dtype=np.float32).tobytes())
    h.update(repr((stroke.softness, stroke.instrument, round(stroke.gain, 4), stroke.filled,
                   stroke.fx, stroke.cyclic, context_key)).encode())
    return h.hexdigest()


HARMONY_GAIN = 0.55  # added voices sit under the drawn one
HARMONY_PAN = 0.3


def harmonize(interp, harmony, spec):
    """Add the voices of ``harmony`` (music.HARMONIES) to an interpretation, in the scale
    of the board. Percussion and noise bands are left alone."""
    if not music.HARMONY_STEPS.get(harmony):
        return interp
    voices, notes = list(interp.voices), list(interp.notes)
    for voice in interp.voices:
        if voice.instrument == interpret.NOISE_BAND or synth.get_instrument(
                voice.instrument).percussive:
            continue
        shifted = music.harmony_pitches(voice.pitch, harmony, spec.scale, spec.root)
        for k, pitch in enumerate(shifted):
            side = HARMONY_PAN if k % 2 == 0 else -HARMONY_PAN
            voices.append(replace(voice, pitch=pitch, amp=voice.amp * HARMONY_GAIN,
                                  pan=np.clip(voice.pan + side, -1.0, 1.0)))
    for note in interp.notes:
        if synth.get_instrument(note.instrument).percussive:
            continue
        for pitch in music.harmony_pitches([note.pitch], harmony, spec.scale, spec.root):
            notes.append(replace(note, pitch=int(min(max(round(float(pitch[0])), 0), 127)),
                                 velocity=max(1, int(note.velocity * 0.75))))
    return interpret.Interpretation(voices, notes)


def _interpret_stroke(stroke, spec, mapping, mode, fill_mode, radius_ref, context_key,
                      glide=0.12, transpose=0, errors=None, harmony="OFF"):
    """``(key, Interpretation)`` of a stroke, cached."""
    key = _stroke_key(stroke, (context_key, mode, fill_mode, round(glide, 4), transpose,
                               harmony))
    interp = _interp_cache.get(key)
    if interp is not None:
        return key, interp
    try:
        interp = interpret.interpret_stroke(stroke, spec, mapping, mode, radius_ref,
                                            fill_mode, glide)
    except Exception as error:  # noqa: BLE001 - a broken stroke stays silent
        (errors or _Errors()).add(error, "stroke")
        return key, interpret.Interpretation()  # not cached: retried at the next render
    if transpose:
        interp.voices = [replace(v, pitch=v.pitch + transpose) for v in interp.voices]
        interp.notes = [replace(n, pitch=min(max(n.pitch + transpose, 0), 127))
                        for n in interp.notes]
    if not stroke.filled:  # a filled shape is already a chord
        interp = harmonize(interp, harmony, spec)
    _interp_cache.put(key, interp)
    return key, interp


AMP_CEILING = 3.0  # interpret clips the amplitude of a voice here


def _unit_gain(stroke, args):
    """The instrument volume (``stroke.gain``) only scales the amplitude of the voices,
    and the voices are linear in it, unless the amplitude reaches the ceiling where
    interpret clips it. ``(key, interpretation)`` of the stroke at volume 1 when its
    sound times the volume is the stroke's own sound, else None.

    ``args``: the arguments of :func:`_interpret_stroke` after the stroke."""
    gain = float(stroke.gain)
    if gain == 1.0 or not gain > 0.0:
        return None
    key, interp = _interpret_stroke(replace(stroke, gain=1.0), *args)
    peak = max((float(np.max(voice.amp)) for voice in interp.voices if len(voice.amp)),
               default=0.0)
    if peak * max(gain, 1.0) >= AMP_CEILING:
        return None
    return key, interp


def _scaled(rendered, gain):
    gain = np.float32(gain)
    return [(offset, buffer * gain) for offset, buffer in rendered]


def _render_stroke(stroke, spec, mapping, mode, fill_mode, radius_ref, sample_rate,
                   context_key, glide=0.12, transpose=0, errors=None, harmony="OFF"):
    errors = errors or _Errors()
    args = (spec, mapping, mode, fill_mode, radius_ref, context_key, glide, transpose,
            errors, harmony)
    key, interp = _interpret_stroke(stroke, *args)
    cached = _stroke_cache.get(key)
    if cached is not None:
        return key, cached
    unit = _unit_gain(stroke, args)
    if unit is not None:
        # Another instrument volume: the voices at volume 1, scaled (no synthesis
        # again while the volume slider moves). The notes keep their velocity.
        unit_key, unit_interp = unit
        rendered = _stroke_cache.get(unit_key)
        if rendered is None:
            before = errors.count
            voices = _render_voices(unit_interp.voices, sample_rate, mapping.vibrato_rate,
                                    errors)
            rendered = (voices, unit_interp.notes, _curves_of(unit_interp.voices))
            if errors.count == before:
                _stroke_cache.put(unit_key, rendered)
        return key, (_scaled(rendered[0], stroke.gain), interp.notes,
                     _curves_of(interp.voices))
    before = errors.count
    rendered = _render_voices(interp.voices, sample_rate, mapping.vibrato_rate, errors)
    value = (rendered, interp.notes, _curves_of(interp.voices))
    if errors.count == before:
        _stroke_cache.put(key, value)
    return key, value


def _joinable(voice):
    return not synth.get_instrument(voice.instrument).percussive


def _render_legato(layer, spec, mapping, radius_ref, sample_rate, context_key, transpose,
                   errors):
    """The strokes of a legato layer: voices of the same instrument (and effects)
    closer than ``layer.legato_gap`` beats join into one gliding voice.

    Returns ``(stroke keys, [(fx, rendered voices)], notes, curves, voice count)``."""
    gap = layer.legato_gap * 60.0 / max(spec.bpm, 1e-6)
    keys, notes, by_fx, filled = [], [], {}, set()
    args = (spec, mapping, layer.mode, layer.fill_mode, radius_ref, context_key, layer.glide,
            transpose, errors)
    # The instrument volume of a chain of effects: when every stroke of it has the same
    # one and the voices are linear in it (see _unit_gain), the voices are joined and
    # rendered at volume 1, then scaled.
    gains = {}
    for stroke in layer.strokes:
        gains.setdefault(stroke.fx, set()).add(float(stroke.gain))
    unit_fx = {fx for fx, values in gains.items()
               if len(values) == 1 and next(iter(values)) != 1.0
               and all(_unit_gain(stroke, args) is not None
                       for stroke in layer.strokes if stroke.fx == fx)}
    for stroke in layer.strokes:
        # Harmony is added after the join: the added voices must not be joined
        # with the melody they accompany.
        key, interp = _interpret_stroke(stroke, *args)
        keys.append(key)
        harmony = "OFF" if stroke.filled else layer.harmony
        notes.extend(harmonize(interpret.Interpretation([], interp.notes), harmony,
                               spec).notes)
        if stroke.fx in unit_fx:
            key, interp = _unit_gain(stroke, args)
        tags, voices = by_fx.setdefault(stroke.fx, ([], []))
        for index, voice in enumerate(interp.voices):
            tags.append((key, index))
            voices.append(voice)
        if stroke.filled:
            filled.add(key)
    parts, curves, count = [], [], 0
    for fx, (tags, voices) in by_fx.items():
        scale = next(iter(gains[fx])) if fx in unit_fx else None
        rendered = []
        for members, voice in interpret.legato_join(voices, gap, _joinable):
            vkey = hashlib.blake2b(repr(([tags[i] for i in members], round(gap, 6),
                                         layer.harmony)).encode(),
                                   digest_size=16).hexdigest()
            value = _stroke_cache.get(vkey)
            if value is None:
                before = errors.count
                drawn = any(tags[i][0] not in filled for i in members)
                with_harmony = harmonize(interpret.Interpretation([voice], []),
                                         layer.harmony if drawn else "OFF", spec).voices
                value = _render_voices(with_harmony, sample_rate, mapping.vibrato_rate, errors)
                if errors.count == before:
                    _stroke_cache.put(vkey, value)
            rendered.extend(value if scale is None else _scaled(value, scale))
            curves.extend(_curves_of([voice]))
            count += len(value)
        parts.append((fx, rendered))
    return keys, parts, notes, curves, count


def _shift_notes(notes, seconds, length, loop):
    """Notes of a later canon voice; in a loop they wrap around like its sound."""
    out = []
    for note in notes:
        start, end = note.start + seconds, note.end + seconds
        if loop and length > 0:
            turns = int(start // length)
            start, end = start - turns * length, end - turns * length
        out.append(replace(note, start=start, end=end))
    return out


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


def context_key(spec, mapping, sample_rate):
    """What every stroke of a render depends on besides its own data."""
    return (astuple(spec), astuple(mapping), sample_rate)


def render_layers(layers, spec, mapping, sample_rate=44100, loop=True, master_volume=0.8,
                  room="HALL"):
    """Render each :class:`LayerInput` on its own: a list of :class:`LayerSound`.

    A layer never depends on the others (thickness is an absolute volume), so
    one layer can be rendered again while the others keep their sound."""
    loop_n = max(1, int(round(spec.length * sample_rate)))
    radius_ref = interpret.full_radius(spec.row_height)
    ctx_key = context_key(spec, mapping, sample_rate)
    errors = _Errors()
    sounds = []
    for layer in layers:
        layer = with_modifiers(layer, spec)
        stroke_keys = []
        stroke_results = []  # (instrument fx, rendered voices)
        notes, curves, voice_count = [], [], 0
        copies = [(k * layer.canon_transpose, int(round(k * layer.canon_delay * sample_rate)))
                  for k in range(max(1, layer.canon_voices))]
        legato = layer.mode in interpret.LEGATO_MODES
        errors_before = errors.count

        def add(fx, rendered, part_notes, part_curves, shift):
            nonlocal voice_count
            if shift:
                rendered = [(offset + shift, buf) for offset, buf in rendered]
                part_notes = _shift_notes(part_notes, shift / sample_rate, spec.length, loop)
                part_curves = [(start + shift / sample_rate, pitch, ident)
                               for start, pitch, ident in part_curves]
            stroke_results.append((fx, rendered))
            notes.extend(part_notes)
            curves.extend(part_curves)
            voice_count += len(rendered)

        for transpose, shift in copies:
            if legato:
                keys, parts, part_notes, part_curves, _count = _render_legato(
                    layer, spec, mapping, radius_ref, sample_rate, ctx_key, transpose,
                    errors)
                stroke_keys.extend((key, shift) for key in keys)
                for index, (fx, rendered) in enumerate(parts):
                    add(fx, rendered, part_notes if index == 0 else [],
                        part_curves if index == 0 else [], shift)
                if not parts:
                    add(None, [], part_notes, part_curves, shift)
                continue
            for stroke in layer.strokes:
                key, (rendered, stroke_notes, stroke_curves) = _render_stroke(
                    stroke, spec, mapping, layer.mode, layer.fill_mode, radius_ref,
                    sample_rate, ctx_key, layer.glide, transpose, errors, layer.harmony)
                stroke_keys.append((key, shift))
                add(stroke.fx, rendered, stroke_notes, stroke_curves, shift)

        layer_key = hashlib.blake2b(
            repr((stroke_keys, astuple(layer.fx), spec.bpm, sample_rate, room,
                  round(layer.legato_gap, 4) if legato else None, layer.harmony)).encode(),
            digest_size=16).hexdigest()
        buffer = _layer_cache.get(layer_key)
        if buffer is None:
            # Strokes are summed per instrument effect chain first...
            groups = {}
            for fx, rendered in stroke_results:
                groups.setdefault(fx, []).extend(rendered)
            buffer = np.zeros((loop_n, 2), dtype=np.float32)
            for fx, rendered in groups.items():
                part = _sum(rendered, loop_n)
                if fx is not None:
                    part = effects.apply_chain(part, sample_rate, LayerFx(*fx), spec.bpm, room)
                buffer = _add(buffer, part)
            # ...then the layer effects.
            buffer = effects.apply_chain(buffer, sample_rate, layer.fx, spec.bpm, room)
            if errors.count == errors_before:  # incomplete layers are rendered again
                _layer_cache.put(layer_key, buffer)

        scale = np.float32(layer.gain * master_volume)
        scaled = buffer * scale
        if loop:
            # Fold echo/reverb/release tails back onto the start of the loop.
            audio = np.zeros((loop_n, 2), dtype=np.float32)
            for begin in range(0, len(scaled), loop_n):
                chunk = scaled[begin:begin + loop_n]
                audio[:len(chunk)] += chunk
        else:
            audio = scaled.astype(np.float32)
        sound_key = hashlib.blake2b(
            repr((layer_key, round(layer.gain, 4), round(master_volume, 4), loop,
                  layer.name)).encode(), digest_size=16).hexdigest()
        base_key = hashlib.blake2b(repr((layer_key, loop, layer.name)).encode(),
                                   digest_size=16).hexdigest()
        sounds.append(LayerSound(layer.name, audio, sound_key, notes, curves, voice_count,
                                 errors.count - errors_before, base_key, float(scale)))
    return sounds


def mix_layers(sounds, spec, mapping, sample_rate=44100, loop=True, master_fx=None,
               stems=False):
    """Mix :class:`LayerSound` (from :func:`render_layers`) into a :class:`RenderResult`.

    With ``stems`` the result also has every layer after the master bus
    (``result.stems``): played together they are the mix."""
    loop_n = max(1, int(round(spec.length * sample_rate)))
    key = hashlib.blake2b(
        repr(([sound.key for sound in sounds], loop, context_key(spec, mapping, sample_rate),
              _master_key(master_fx))).encode(),
        digest_size=16).hexdigest()
    cached = _mix_cache.get((key, bool(stems)))
    if cached is not None:  # nothing changed (or undo): no master bus again
        mix, outs = cached
    else:
        buffers = [sound.audio for sound in sounds] or [np.zeros((loop_n, 2), np.float32)]
        buffers = [_pad(buffer, loop_n) for buffer in buffers]
        keys = ([(sound.base_key or sound.key, sound.scale if sound.base_key else None)
                 for sound in sounds] if sounds else None)
        mix, outs = finish_stems(buffers, sample_rate, master_fx, loop, stems, keys)
        mix = mix.astype(np.float32, copy=False)
        if not any(sound.errors for sound in sounds):  # incomplete mixes are rendered again
            for array in [mix] + list(outs or []):
                array.flags.writeable = False  # shared with the next renders
            _mix_cache.put((key, bool(stems)), (mix, outs))
    notes = [note for sound in sounds for note in sound.notes]
    curves = [curve for sound in sounds for curve in sound.curves]
    return RenderResult(
        mix, sample_rate, notes, key,
        sum(sound.voices for sound in sounds), curves,
        errors=sum(sound.errors for sound in sounds),
        stems=[(sound.name, out) for sound, out in zip(sounds, outs)] if stems else [],
        layers=list(sounds))


def render(layers, spec, mapping, sample_rate=44100, loop=True, master_volume=0.8,
           master_fx=None, stems=False, room=None):
    """Render a list of :class:`LayerInput` into a :class:`RenderResult`.

    ``master_fx``: :class:`MasterFx` of the finished mix, or None (peak guard only).
    ``stems``: also return each layer after the master bus (``result.stems``).
    ``room``: the room of the layer reverbs (default: the master bus's, or the hall)."""
    if room is None:
        room = master_fx.room if master_fx is not None else "HALL"
    sounds = render_layers(layers, spec, mapping, sample_rate, loop, master_volume, room)
    return mix_layers(sounds, spec, mapping, sample_rate, loop, master_fx, stems)


SECTION_FADE = 0.01  # seconds of fade where a section cuts a repetition short


def sequence(parts, length, sample_rate, loop=True, master_fx=None, stems=False):
    """Join keyframe sections into one piece.

    ``parts``: ``[(start, end, RenderResult)]`` sorted by start, each rendered
    with ``loop=False`` (one loop of ``length`` seconds plus its tails). Every
    section repeats its loop from ``start`` until ``end``; a repetition cut by
    the next section fades out quickly, a whole one keeps its tail.

    With ``stems`` the parts must have been rendered with ``stems=True``: every
    layer is joined on its own track and goes through the master bus as a stem.
    """
    loop_n = max(1, int(round(length * sample_rate)))
    total = max((end for _start, end, _r in parts), default=length)
    total_n = max(1, int(round(total * sample_rate)))
    tracks = {}  # layer name (None = the mix) -> audio
    notes, curves, keys, voices, errors = [], [], [], 0, 0
    fade_n = max(1, int(SECTION_FADE * sample_rate))

    def place(name, offset, chunk):
        track = tracks.get(name)
        if track is None:
            track = tracks[name] = np.zeros((total_n, 2), dtype=np.float32)
        if offset + len(chunk) > len(track):
            track = tracks[name] = np.concatenate(
                (track, np.zeros((offset + len(chunk) - len(track), 2), np.float32)))
        track[offset:offset + len(chunk)] += chunk

    for start, end, result in parts:
        keys.append((round(start, 6), round(end, 6), result.key))
        voices += result.voice_count
        errors += result.errors
        begin, stop = int(round(start * sample_rate)), int(round(end * sample_rate))
        span = end - start
        repeats = max(1, int(np.ceil(span / length - 1e-9)))
        sources = result.stems if stems else [(None, result.audio)]
        for k in range(repeats):
            offset = begin + k * loop_n
            for name, audio in sources:
                chunk = audio
                if offset + loop_n > stop:  # cut short by the next section
                    chunk = chunk[:max(stop - offset, 0)].copy()
                    ramp = min(fade_n, len(chunk))
                    if ramp:
                        chunk[-ramp:] *= np.linspace(1.0, 0.0, ramp, dtype=np.float32)[:, None]
                place(name, offset, chunk)
            shift, limit = start + k * length, end
            for note in result.notes:
                if shift + note.start < limit:
                    notes.append(replace(note, start=shift + note.start,
                                         end=min(shift + note.end, limit)))
            for c_start, pitch, ident in result.curves:
                if shift + c_start < limit:
                    curves.append((shift + c_start, pitch, ident))
    if not tracks:
        tracks[None] = np.zeros((total_n, 2), dtype=np.float32)
    for name, track in list(tracks.items()):
        if loop and len(track) > total_n:
            tail, track = track[total_n:], track[:total_n].copy()
            for begin in range(0, len(tail), total_n):
                chunk = tail[begin:begin + total_n]
                track[:len(chunk)] += chunk
            tracks[name] = track
    names = list(tracks)
    master, outs = finish_stems([tracks[name] for name in names], sample_rate, master_fx,
                                loop, stems)
    key = hashlib.blake2b(repr((keys, round(length, 6), loop, sample_rate,
                                _master_key(master_fx))).encode(),
                          digest_size=16).hexdigest()
    notes.sort(key=lambda n: (n.start, n.pitch))
    return RenderResult(master, sample_rate, notes, key, voices, curves, duration=total,
                        sections=tuple(start for start, _end, _r in parts), errors=errors,
                        stems=[(name, out) for name, out in zip(names, outs)
                               if name is not None] if stems else [])
