# SPDX-License-Identifier: GPL-3.0-or-later
"""Glue between Blender data and the audio renderer.

``regenerate`` reads the strokes, renders the loop, writes a WAV into a cache
folder and (re)places it as a sound strip in the Video Sequencer, so pressing
Play in Blender plays the drawing.
"""

import collections
import os
import queue
import re
import tempfile
import threading
import time
import traceback
import wave
from dataclasses import astuple

import aud
import bpy
import numpy as np

from . import beat, board, effects, interpret, midi, mixer, music, prefs, props, reader, synth

STRIP_PREFIX = "GP2M · "

# Runtime state per composition object name (not saved in the .blend file).
_state = {}


def state(obj):
    return _state.setdefault(obj.name, {})


# What the Sequencer read-back (seqsync) compares the clips with: how the add-on last
# placed them. A copy is kept in the file, on the composition, so that every Undo
# step has the one that goes with its clips: Ctrl+Shift+Z of a clip moved in the
# Sequencer gives back the moved clip with the place it had before, and the move is
# read again (otherwise the clip went back where it was).
SYNC_KEY = "gp2m_sync"
SYNC_STATE = ("meta_span", "had_meta", "bus", "tree", "layer_groups", "offset_frames",
              "delay_frames")


def _sync_value(key, value):
    if key in ("meta_span", "bus"):
        return tuple(value)
    if key == "tree":
        return [tuple(item) for item in value]
    if key == "layer_groups":
        return list(value)
    return value


def save_sync_state(obj):
    """Copy the read-back state of ``obj`` into the file (only when it changed)."""
    import json
    st = state(obj)
    data = {key: st[key] for key in SYNC_STATE if key in st}
    data["owner"] = obj.name  # a copy (Shift+D) starts without one
    data["order"] = clip_order(obj)
    try:
        text = json.dumps(data, sort_keys=True)
    except (TypeError, ValueError):
        return
    if obj.get(SYNC_KEY) != text:
        try:
            obj[SYNC_KEY] = text
        except (TypeError, AttributeError):
            pass  # linked data


def load_sync_state(obj):
    """After Ctrl+Z / Ctrl+Shift+Z: the read-back state of the step given back."""
    import json
    st = state(obj)
    for key in SYNC_STATE:
        st.pop(key, None)
    try:
        data = json.loads(obj.get(SYNC_KEY) or "{}")
    except (TypeError, ValueError):
        return
    if not isinstance(data, dict) or data.get("owner") != obj.name:
        return
    for key in SYNC_STATE:
        if key in data:
            try:
                st[key] = _sync_value(key, data[key])
            except (TypeError, ValueError):
                pass
    if isinstance(data.get("order"), dict):
        st["undo_order"] = data["order"]


def clip_order(obj):
    """The clips of the layers and groups of layers, by channel, inside the meta-clip
    of ``obj`` and the meta-clips of its groups ("" = the composition's meta-clip):
    saved with the Undo step, so that after Ctrl+Z / Ctrl+Shift+Z only clips moved
    since then are read as moved in the Sequencer (the step can hold layers moved on
    the board with their clips not placed again yet)."""
    scene = next((sc for sc in obj.users_scene if sc.sequence_editor is not None), None)
    meta = meta_strip(scene, obj) if scene is not None else None
    if meta is None:
        return {}
    order = {}
    containers = [("", meta)] + list(group_clips(scene, obj, meta).items())
    for key, container in containers:
        inside = [strip for strip in container.strips
                  if strip.get(LAYER_KEY) or strip.get(LAYER_GROUP_KEY)]
        order[key] = [strip.get(LAYER_KEY) or strip.get(LAYER_GROUP_KEY) for strip in
                      sorted(inside, key=lambda strip: (
                          strip.channel, strip.get(LAYER_KEY) or strip.get(LAYER_GROUP_KEY)))]
    return order


def board_spec(settings):
    if beat.is_beat(settings):
        # Bit: the strokes reach the reader on the row of their lane's pitch
        # (beat.read_strokes), on a chromatic board that starts at MIDI 0.
        return interpret.BoardSpec(
            low_note=0, row_height=settings.row_height,
            seconds_width=settings.seconds_width, length=settings.length,
            bpm=settings.bpm, scale="CHROMATIC", root=0, time_grid=settings.time_grid,
            min_note=settings.min_note, swing=settings.swing)
    return interpret.BoardSpec(
        low_note=settings.low_note,
        row_height=settings.row_height,
        seconds_width=settings.seconds_width,
        length=settings.length,
        bpm=settings.bpm,
        scale=settings.scale,
        root=music.NOTE_NAMES.index(settings.root),
        time_grid=settings.time_grid,
        min_note=settings.min_note,
        swing=settings.swing,
    )


def _layer_fx(settings):
    """The layer effects whose checkbox is on."""
    if settings is None:
        return mixer.LayerFx()
    return mixer.LayerFx(
        delay_mix=settings.delay_mix if settings.use_echo else 0.0,
        delay_beats=settings.delay_beats,
        delay_feedback=settings.delay_feedback,
        reverb_mix=settings.reverb_mix if settings.use_reverb else 0.0,
        reverb_size=settings.reverb_size,
        lofi=settings.lofi if settings.use_lofi else 0.0,
    )


def layer_mods(settings):
    """The :class:`layer_mods.Stack` of the modifiers that are on."""
    from . import layer_mods as lm
    if settings is None:
        return lm.Stack()
    s = settings
    return lm.Stack(
        array=lm.Array(count=s.array_count, fill=s.array_fill, beats=round(s.array_beats, 4),
                       pitch=s.array_pitch, unit=s.array_unit,
                       decay=round(s.array_decay, 4)) if s.use_array else None,
        mirror=lm.Mirror(time=s.mirror_time, pitch=s.mirror_pitch, keep=s.mirror_keep,
                         time_center=round(s.mirror_time_center, 4),
                         pitch_center=round(s.mirror_pitch_center, 4))
        if s.use_mirror else None,
        transpose=lm.Transpose(steps=s.transpose_steps, unit=s.transpose_unit)
        if s.use_transpose else None,
        fade=lm.Fade(direction=s.fade_direction, scope=s.fade_scope,
                     length=round(s.fade_length, 4), minimum=round(s.fade_minimum, 4))
        if s.use_fade else None,
        noise=lm.Noise(pitch=round(s.noise_pitch, 4), width=round(s.noise_width, 4),
                       time=round(s.noise_time, 4), scale=round(s.noise_scale, 4),
                       seed=s.noise_seed) if s.use_noise else None,
    )


def master_fx(settings):
    return mixer.MasterFx(enabled=settings.use_master, ambience=settings.ambience,
                          room=getattr(settings, "room", "HALL"))


MAX_SECTIONS = 24


def section_frames(obj, scene):
    """Scene frames where a keyframe section starts (the first is the scene start).

    Following the scene's In/Out, keyframes after the scene End are not heard."""
    start = scene.frame_start
    last = scene.frame_end if follows_scene(obj, scene) else None
    frames = {start}
    for layer in board.user_layers(obj.data):
        for frame in layer.frames:
            number = max(int(frame.frame_number), start)
            if last is None or number <= last:
                frames.add(number)
    return sorted(frames)[:MAX_SECTIONS]


def _shown_on_strokes(obj):
    """Layers whose modifiers are already in the evaluated strokes (stroke_mods)."""
    from . import stroke_mods
    return {m.name[len(stroke_mods.MODIFIER_PREFIX):] for m in obj.modifiers
            if stroke_mods.is_stroke_modifier(m) and m.show_viewport}


def _layer_inputs(obj, reads):
    seconds_per_beat = 60.0 / max(obj.gp2m.bpm, 1e-6)
    bit = beat.is_beat(obj.gp2m)
    rows = 128 if bit else board.dimensions(obj.gp2m)[0]
    # Reading the evaluated strokes ("Usa modificatori"), the layer modifiers shown on
    # the strokes are already in them: they must not be applied a second time.
    evaluated = _shown_on_strokes(obj) if obj.gp2m.use_modifiers else set()
    layers = []
    for read in reads:
        settings = props.find_layer_settings(obj.data, read.name)
        layers.append(mixer.LayerInput(
            name=read.name,
            strokes=beat.read_strokes(obj.gp2m, read.strokes) if bit else read.strokes,
            mode=settings.mode if settings else "QUANTIZED",
            fill_mode=settings.fill_mode if settings else "TONAL",
            glide=settings.glide if settings else 0.12,
            legato_gap=settings.legato_gap if settings else 1.0,
            gain=read.opacity,
            fx=_layer_fx(settings),
            canon_voices=settings.canon_voices if settings and settings.use_canon else 1,
            canon_delay=settings.canon_delay * seconds_per_beat if settings else 0.0,
            canon_transpose=settings.canon_transpose if settings else 0,
            harmony=settings.harmony if settings else "OFF",
            mods=layer_mods(None if read.name in evaluated else settings),
            rows=rows,
        ))
    return layers


def plan_composition(obj, scene, stems=False):
    """Read everything a render needs from Blender: ``(compute, reads)``.

    ``compute()`` returns the :class:`mixer.RenderResult` and touches no Blender
    data, so it may run in another thread (see :func:`compute`)."""
    s = obj.gp2m
    spec, mapping, rate = board_spec(s), prefs.get_mapping(), int(s.sample_rate)
    fx = master_fx(s)
    effects.room_ir(fx.room, rate)  # a recorded room is read here, in Blender's thread
    loop, master_volume, length = s.loop, s.master_volume, s.length
    frames = section_frames(obj, scene) if s.use_sections else [scene.frame_start]
    # Following the scene, the last section repeats its loop until the scene End.
    until = scene_seconds(scene) if s.use_sections and follows_scene(obj, scene) else None
    if len(frames) == 1 and until is None:
        reads = reader.read_composition(obj, frames[0], use_modifiers=s.use_modifiers)
        inputs = _layer_inputs(obj, reads)

        def compute_one():
            result = mixer.render(inputs, spec, mapping, rate, loop=loop,
                                  master_volume=master_volume, master_fx=fx, stems=stems)
            result.duration = length
            return result
        return compute_one, reads
    times = [(frame - scene.frame_start) / _fps(scene) for frame in frames]
    plans, first_reads = [], None
    for i, frame in enumerate(frames):
        reads = reader.read_composition(obj, frame, use_modifiers=s.use_modifiers)
        first_reads = reads if first_reads is None else first_reads
        if i + 1 < len(times):
            end = times[i + 1]
        elif until is not None and until > times[i]:
            end = until
        else:
            end = times[i] + length
        plans.append((times[i], end, _layer_inputs(obj, reads)))

    def compute_sections():
        parts = [(start, end, mixer.render(inputs, spec, mapping, rate, loop=False,
                                           master_volume=master_volume, stems=stems,
                                           room=fx.room))
                 for start, end, inputs in plans]
        return mixer.sequence(parts, length, rate, loop=loop, master_fx=fx, stems=stems)
    return compute_sections, first_reads


_compute_lock = threading.Lock()  # the renderer's caches are not shared between threads


def compute(fn):
    """Run a ``compute`` of :func:`plan_composition` (any thread)."""
    with _compute_lock:
        return fn()


def render_composition(obj, scene, stems=False):
    """Render the loop drawn at the scene start, or every keyframe section.

    ``stems``: also render every layer on its own (``result.stems``)."""
    fn, reads = plan_composition(obj, scene, stems)
    return compute(fn), reads


# --- Scene In / Out ---------------------------------------------------------------

def follows_scene(obj, scene):
    """True when the composition takes its length from the scene Start and End (In and
    Out). Playing 'Una dopo l'altra' the compositions keep their own length."""
    return (bool(obj.gp2m.follow_scene) and scene is not None
            and scene.gp2m_play.mode != "SEQUENCE")


def scene_seconds(scene):
    """Seconds from the scene Start to the end of its End frame."""
    return (scene.frame_end - scene.frame_start + 1) / _fps(scene)


def _loop_frames(obj, fps):
    return max(1, int(round(obj.gp2m.length * fps)))


def _range_key(scene):
    return (scene.frame_start, scene.frame_end, round(_fps(scene), 6))


# What the compositions that follow the scene were last matched to, kept in the file
# (not in Python) so that Ctrl+Z and Ctrl+Shift+Z give it back with the settings: an
# Undo step saved before the scene End followed a new Durata must still read as "the
# Durata changed", not as "the scene End changed" (which shortened it back).
LINKED_RANGE_KEY = "gp2m_linked_range"  # on the scene: Start, End, fps
LINKED_FRAMES_KEY = "gp2m_linked_frames"  # on a composition: its loop, in frames


def _linked_range(scene):
    value = scene.get(LINKED_RANGE_KEY)
    try:
        return (int(value[0]), int(value[1]), round(float(value[2]), 6))
    except (TypeError, IndexError, KeyError, ValueError):
        return None


def _set_linked_range(scene):
    start, end, fps = _range_key(scene)
    if _linked_range(scene) != (start, end, fps):
        scene[LINKED_RANGE_KEY] = [float(start), float(end), float(fps)]


def _linked_frames(obj):
    value = obj.get(LINKED_FRAMES_KEY)
    return int(value) if isinstance(value, (int, float)) else None


def _set_linked_frames(obj, frames):
    if _linked_frames(obj) != int(frames):
        obj[LINKED_FRAMES_KEY] = int(frames)


def link_composition(obj, scene):
    """'Segui In/Out della scena' switched on (or a new composition).

    When no other composition of the scene follows it yet, the scene End moves to
    the end of this composition, so its sound does not change (as before 0.0.20);
    otherwise the composition takes the length of the scene, like the others."""
    if scene is None or not follows_scene(obj, scene):
        return
    fps = _fps(scene)
    others = [o for o in scene_compositions(scene) if o != obj and follows_scene(o, scene)]
    if not others:
        if obj.gp2m.use_sections:
            frames = max(1, int(round(duration(obj) * fps)))
        else:
            frames = _loop_frames(obj, fps)
        end = scene.frame_start + frames - 1
        if scene.frame_end != end:
            scene.frame_end = end
        _set_linked_frames(obj, _loop_frames(obj, fps))
        _set_linked_range(scene)


def _follow_scene(scene, linked):
    """The compositions that follow the scene last from its Start to its End.

    It works both ways: a new Start or End (or frame rate) changes their length,
    and a composition made longer or shorter (Durata, scaling the board, a MIDI
    import...) moves the scene End, then the others follow. With keyframe sections
    the loop keeps its length and the last section lasts until the End."""
    fps = _fps(scene)
    loops = [obj for obj in linked if not obj.gp2m.use_sections]
    if _linked_range(scene) == _range_key(scene):  # the scene did not change
        moved = [obj for obj in loops
                 if _linked_frames(obj) not in (None, _loop_frames(obj, fps))]
        if moved:
            active = _active_composition(scene)
            source = active if active in moved else moved[0]
            end = scene.frame_start + _loop_frames(source, fps) - 1
            if scene.frame_end != end:
                scene.frame_end = end
    seconds = min(max(scene_seconds(scene), 1.0), 300.0)
    target = max(1, int(round(seconds * fps)))
    for obj in loops:
        if _loop_frames(obj, fps) != target:
            obj.gp2m.length = target / fps
        _set_linked_frames(obj, target)
    _set_linked_range(scene)


def _context_signature(obj, scene):
    """What every layer of the composition depends on (besides its own settings)."""
    s = obj.gp2m
    return repr((astuple(board_spec(s)), astuple(prefs.get_mapping()), s.sample_rate, s.loop,
                 round(s.master_volume, 4), astuple(master_fx(s)), s.use_modifiers,
                 scene.frame_start, beat.is_beat(s) and tuple(beat.lane_drums(s))))


def _layer_signatures(obj, layers):
    """Settings of each audible layer (volume, reading, effects...), without its strokes."""
    stubs = [reader.LayerRead(name=layer.name, opacity=props.layer_volume(obj.data, layer))
             for layer in layers]
    return {item.name: repr(item) for item in _layer_inputs(obj, stubs)}


def _keep_info(obj, scene):
    """What :func:`render_active_layer` compares against next time (read now, with the
    strokes the render reads)."""
    if obj.gp2m.use_sections:
        return None
    return {"context": _context_signature(obj, scene),
            "signatures": _layer_signatures(obj, reader.audible_layers(obj.data)),
            "fingerprints": reader.layer_fingerprints(obj, scene.frame_start,
                                                      obj.gp2m.use_modifiers)}


def plan_active_layer(obj, scene):
    """Like :func:`plan_composition` for the active layer alone, mixed with the sound
    the other layers had: ``(compute, reads)``, or ``(None, None)`` when everything
    must be rendered again: keyframe sections, no sound kept yet, a layer added,
    removed, muted, or with other settings, or a change of the whole composition.
    ``compute()`` returns None if the active layer could not be rendered alone."""
    s = obj.gp2m
    st = state(obj)
    kept = st.get("layers")
    active = obj.data.layers.active
    if s.use_sections or not kept or active is None:
        return None, None
    layers = reader.audible_layers(obj.data)
    names = [layer.name for layer in layers]
    if active.name not in names or names != list(kept):
        return None, None
    context = _context_signature(obj, scene)
    if st.get("context") != context:
        return None, None
    signatures = _layer_signatures(obj, layers)
    previous = st.get("signatures") or {}
    if any(signatures[name] != previous.get(name) for name in names if name != active.name):
        return None, None
    # Edit and Sculpt Mode (and the object's modifiers) can change the strokes of
    # every layer, not only the active one: those layers must be rendered again.
    fingerprints = reader.layer_fingerprints(obj, scene.frame_start, s.use_modifiers)
    kept_prints = st.get("fingerprints") or {}
    if any(fingerprints.get(name) != kept_prints.get(name)
           for name in names if name != active.name):
        return None, None
    reads = reader.read_composition(obj, scene.frame_start, use_modifiers=s.use_modifiers,
                                    only={active.name})
    spec, mapping, rate = board_spec(s), prefs.get_mapping(), int(s.sample_rate)
    fx = master_fx(s)
    effects.room_ir(fx.room, rate)
    inputs = _layer_inputs(obj, reads)
    loop, master_volume, length = s.loop, s.master_volume, s.length
    others = dict(kept)
    active_name = active.name

    def compute_active():
        fresh = mixer.render_layers(inputs, spec, mapping, rate, loop, master_volume, fx.room)
        if len(fresh) != 1:
            return None
        sounds = [fresh[0] if name == active_name else others[name] for name in names]
        result = mixer.mix_layers(sounds, spec, mapping, rate, loop, fx, stems=True)
        result.duration = length
        return result
    # What _keep_info() would read again after the render.
    compute_active.keep = {"context": context, "signatures": signatures,
                           "fingerprints": fingerprints}
    return compute_active, reads


def render_active_layer(obj, scene):
    """Render only the active layer (see :func:`plan_active_layer`): ``(result, reads)``
    or ``(None, None)``."""
    fn, reads = plan_active_layer(obj, scene)
    result = compute(fn) if fn is not None else None
    return (result, reads) if result is not None else (None, None)


def _keep_layers(obj, scene, result, info=None):
    """Remember each layer's sound, for :func:`render_active_layer`."""
    st = state(obj)
    if obj.gp2m.use_sections or not result.layers:
        st["layers"] = None
        return
    info = info if info is not None else _keep_info(obj, scene)
    if info is None:
        st["layers"] = None
        return
    st["layers"] = {sound.name: sound for sound in result.layers}
    st.update(info)


def duration(obj):
    """Seconds the composition lasts in the scene (one loop, or all its sections)."""
    return state(obj).get("duration") or obj.gp2m.length


def locate(obj, seconds):
    """``(section start frame offset in seconds, seconds inside the loop)`` for a time
    of the composition: where a note played at that moment belongs on the board."""
    sections = state(obj).get("sections") or (0.0,)
    length = obj.gp2m.length
    start = max([t for t in sections if t <= seconds + 1e-9], default=sections[0])
    return start, (seconds - start) % length if length > 0 else 0.0


# --- Files -------------------------------------------------------------------

AUDIO_FORMATS = {
    "WAV": (aud.CONTAINER_WAV, aud.CODEC_PCM, ".wav"),
    "MP3": (aud.CONTAINER_MP3, aud.CODEC_MP3, ".mp3"),
}


def _write_wav(path, audio, sample_rate):
    """16-bit PCM WAV with Python's wave module: no FFmpeg involved.

    Blender's FFmpeg writer fails on some lengths/rates ("filling the audio
    frame failed with ffmpeg"), so WAV files never go through it.
    """
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(path, "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes(pcm.tobytes())


def write_audio(path, audio, sample_rate, fmt="WAV", bitrate_kbps=192):
    data = np.ascontiguousarray(audio, dtype=np.float32)
    if data.ndim != 2 or len(data) == 0:
        data = np.zeros((max(1, len(data)), 2), dtype=np.float32)
    if fmt == "WAV":
        _write_wav(path, data, sample_rate)
        return
    container, codec, _ext = AUDIO_FORMATS[fmt]
    errors = []
    # FFmpeg encoders work in fixed frames: retry with the length padded to a
    # whole number of MP3 frames (1152 samples) and with other sample formats.
    padded = np.concatenate((data, np.zeros(((-len(data)) % 1152 or 1152, 2), np.float32)))
    for candidate, sample_format in ((data, aud.FORMAT_S16), (padded, aud.FORMAT_S16),
                                     (padded, aud.FORMAT_FLOAT32)):
        try:
            aud.Sound.buffer(candidate, float(sample_rate)).write(
                path, rate=int(sample_rate), channels=aud.CHANNELS_STEREO,
                format=sample_format, container=container, codec=codec,
                bitrate=int(bitrate_kbps) * 1000)
            return
        except Exception as error:  # aud raises plain Exception subclasses
            errors.append(str(error))
    raise RuntimeError(f"FFmpeg di Blender non riesce a scrivere {fmt}: {errors[-1]} "
                       "(prova WAV, oppure 44.1 kHz)")


def cache_dir():
    base = bpy.app.tempdir or tempfile.gettempdir()
    path = os.path.join(base, "gp2music")
    os.makedirs(path, exist_ok=True)
    return path


def _safe(name):
    return re.sub(r"[^\w\-]+", "_", name).strip("_") or "composizione"


def midi_tracks(notes):
    """Group notes by (layer, instrument) into MIDI tracks."""
    groups = {}
    for note in notes:
        groups.setdefault((note.layer, note.instrument), []).append(note)
    tracks = []
    for (layer, ident), group in groups.items():
        inst = synth.get_instrument(ident)
        if inst.percussive:
            group = [interpret.MidiNote(n.start, n.end, synth.midi_drum_note(ident, n.pitch),
                                        n.velocity, n.instrument, n.layer) for n in group]
        tracks.append({"name": f"{layer} - {inst.label}", "program": inst.gm_program,
                       "notes": group})
    return tracks


def _clip_mix(obj, result, scene=None):
    """The mix as the Sequencer plays it: every layer with its clip volume and pan, and
    those of its groups (of layers and of compositions)."""
    gains = {}
    for name, _audio in result.stems:
        item = props.find_layer_settings(obj.data, name)
        volume, pan = strip_bus(scene, obj, name) if scene is not None else layer_bus(obj, name)
        if item is not None:
            gains[name] = (item.clip_volume * volume, min(max(item.clip_pan + pan, -1.0), 1.0))
        else:
            gains[name] = (volume, min(max(pan, -1.0), 1.0))
    if all(abs(v - 1.0) < 1e-6 and abs(p) < 1e-6 for v, p in gains.values()):
        return result.audio
    total = np.zeros_like(result.audio, dtype=np.float32)
    for name, audio in result.stems:
        volume, pan = gains.get(name, (1.0, 0.0))
        audio = np.asarray(audio, dtype=np.float32) * volume
        if audio.ndim == 2 and audio.shape[1] == 2 and abs(pan) > 1e-6:
            audio = audio * np.array([min(1.0, 1.0 - pan), min(1.0, 1.0 + pan)],
                                     dtype=np.float32)
        count = min(len(total), len(audio))
        total[:count] += audio[:count]
    return np.clip(total, -1.0, 1.0)


def export(obj, scene, path, fmt):
    per_layer = obj.gp2m.layer_channels
    result, _reads = render_composition(obj, scene, stems=per_layer)
    if fmt == "MIDI":
        midi.write_midi(path, midi_tracks(result.notes), obj.gp2m.bpm)
    else:
        if per_layer and result.stems:
            audio = _clip_mix(obj, result, scene)
        else:
            audio = result.audio
            volume, pan = strip_bus(scene, obj) if scene is not None else (1.0, 0.0)
            if abs(volume - 1.0) > 1e-6 or abs(pan) > 1e-6:
                audio = np.asarray(audio, dtype=np.float32) * volume
                if audio.ndim == 2 and audio.shape[1] == 2 and abs(pan) > 1e-6:
                    pan = min(max(pan, -1.0), 1.0)
                    audio = audio * np.array([min(1.0, 1.0 - pan), min(1.0, 1.0 + pan)],
                                             dtype=np.float32)
                audio = np.clip(audio, -1.0, 1.0)
        write_audio(path, audio, result.sample_rate, fmt, prefs.get_prefs().mp3_bitrate)
    return result


# --- Video Sequencer -----------------------------------------------------------

def scene_of(obj):
    """The scene that shows the composition (the active one if it is there)."""
    current = getattr(bpy.context, "scene", None)
    users = obj.users_scene
    if current is not None and (not users or current in users):
        return current
    if users:
        return users[0]
    return bpy.data.scenes[0] if bpy.data.scenes else None  # timers with no window


def cleanup_orphans():
    """Remove what deleted compositions left behind: their sound strips and
    their (now unparented) board, labels and playhead of version 0.0.1."""
    from .board import LEGACY_ROLE as ROLE
    from . import rig
    rig.remove_orphans()
    for scene in bpy.data.scenes:
        editor = scene.sequence_editor
        if editor is None:
            continue
        for strip in [strip for strips in _containers(editor) for strip in strips]:
            if is_group_meta(strip) or not _is_composition_strip(strip):
                continue
            owner = bpy.data.objects.get(strip.get(OWNER_KEY)
                                         or strip.name[len(STRIP_PREFIX):])
            if owner is None or not owner.gp2m.is_composition or scene not in owner.users_scene:
                _remove_strip(editor, strip)
    for obj in list(bpy.data.objects):
        # The grid of a deleted composition, or a copy of a grid (Shift+D).
        if board.is_grid(obj):
            owner = board.grid_owner(obj)
            if owner is None or owner.gp2m.grid != obj:
                data = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if data is not None and data.users == 0:
                    bpy.data.grease_pencils.remove(data)
            continue
        if obj.get(ROLE) in ("board", "label", "playhead") and obj.parent is None:
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data is not None and data.users == 0:
                if isinstance(data, bpy.types.GreasePencil):
                    bpy.data.grease_pencils.remove(data)
                elif isinstance(data, bpy.types.Curve):
                    bpy.data.curves.remove(data)


OWNER_KEY = "gp2m_composition"  # custom properties of the strips (names get cut at 63 bytes)
LAYER_KEY = "gp2m_layer"
GROUP_KEY = "gp2m_group"  # a group of compositions (Ctrl+G in the Sequencer); on the
#                           group's meta-clip and on the compositions inside it
LAYER_GROUP_KEY = "gp2m_layer_group"  # the meta-clip of a group of layers
OWN_CLIP_KEY = "gp2m_own_clip"  # a group of layers with a clip of its own, out of the
#                                 composition's meta-clip (next to it, one channel up)
BUS_VOLUME, BUS_PAN = "gp2m_volume", "gp2m_pan"  # a group's volume and pan (a bus)


def is_group_meta(strip):
    return strip.type == "META" and strip.get(GROUP_KEY) is not None


def group_metas(editor):
    """Every group of compositions in the Sequencer, the outer ones first."""
    found = []
    if editor is None:
        return found
    level = [strip for strip in editor.strips if is_group_meta(strip)]
    while level:
        found.extend(level)
        level = [strip for meta in level for strip in meta.strips if is_group_meta(strip)]
    return found


def _containers(editor):
    """Where compositions' clips can be: the top of the Sequencer and the groups."""
    if editor is None:
        return []
    return [editor.strips] + [meta.strips for meta in group_metas(editor)]


def find_group(editor, key):
    return next((meta for meta in group_metas(editor) if meta[GROUP_KEY] == key), None)


def composition_group(scene, obj):
    """The group (meta-clip) the composition is in, or None."""
    key = obj.get(GROUP_KEY)
    return find_group(scene.sequence_editor, key) if key else None


def _container_meta(scene, obj):
    """The group the composition's clip goes in (None: the top of the Sequencer); a
    group that is gone is forgotten."""
    group = composition_group(scene, obj)
    if group is None and obj.get(GROUP_KEY) is not None:
        del obj[GROUP_KEY]
    return group


def _container_strips(scene, obj):
    group = _container_meta(scene, obj)
    editor = scene.sequence_editor or scene.sequence_editor_create()
    return group.strips if group is not None else editor.strips


def group_bus(scene, obj):
    """``(volume, pan, muted)`` of the groups of compositions around the composition."""
    volume, pan, muted = 1.0, 0.0, False
    top = top_strip(scene, obj)
    group = top.parent_meta() if top is not None else composition_group(scene, obj)
    while group is not None and is_group_meta(group):
        volume *= float(group.get(BUS_VOLUME, 1.0))
        pan += float(group.get(BUS_PAN, 0.0))
        muted = muted or group.mute
        group = group.parent_meta()
    return volume, pan, muted


def layer_bus(obj, layer_name):
    """``(volume, pan)`` of the groups of layers around a layer ("Volume clip" and
    "Pan" of each group)."""
    volume, pan = 1.0, 0.0
    layer = obj.data.layers.get(layer_name)
    group = layer.parent_group if layer is not None else None
    while group is not None:
        item = props.find_layer_settings(obj.data, group.name)
        if item is not None:
            volume *= item.clip_volume
            pan += item.clip_pan
        group = group.parent_group
    return volume, pan


def strip_bus(scene, obj, layer_name=None):
    """``(volume, pan)`` the groups add to a strip of the composition."""
    volume, pan, _muted = group_bus(scene, obj)
    if layer_name is not None:
        layer_volume, layer_pan = layer_bus(obj, layer_name)
        volume, pan = volume * layer_volume, pan + layer_pan
    return volume, pan


def muted_by_group(scene, obj):
    return group_bus(scene, obj)[2]


def strip_name(obj, layer=None):
    """Name of the composition's mix strip, or of the strip of one of its layers."""
    return STRIP_PREFIX + obj.name if layer is None else f"{STRIP_PREFIX}{obj.name} · {layer}"


def _owned(strip, obj):
    owner = strip.get(OWNER_KEY)
    if owner is not None:
        return owner == obj.name
    return strip.name == strip_name(obj)  # strips of 0.0.12 and earlier


def _top_strips(editor, obj):
    """The composition's strips at the top of the Sequencer: its meta-clip (with one
    strip per layer inside) or its mix strip, plus layer strips of 0.0.21 and earlier."""
    if editor is None:
        return []
    return [strip for strips in _containers(editor) for strip in strips
            if not is_group_meta(strip) and strip.get(OWN_CLIP_KEY) is None
            and (strip.get(OWNER_KEY) is not None or strip.name.startswith(STRIP_PREFIX))
            and _owned(strip, obj)]


def own_clip_groups(obj):
    """Groups of layers that have a clip of their own ("Clip propria"), bottom first
    (the order of their channels above the composition's); a group inside one of them
    stays inside its clip. Only with 'Un canale per livello'."""
    if not obj.gp2m.layer_channels:
        return []
    gp = obj.data
    names = []
    for node, _depth in reversed(board.user_tree(gp)):
        if not board.is_group(node):
            continue
        item = props.find_layer_settings(gp, node.name)
        if item is None or not item.own_clip:
            continue
        outer = [props.find_layer_settings(gp, group.name) for group in board.ancestors(node)]
        if not any(other is not None and other.own_clip for other in outer):
            names.append(node.name)
    return names


def _own_clips_all(editor, obj):
    """Every clip of a group of layers of ``obj`` out of its meta-clip (copies too)."""
    if editor is None:
        return []
    return [strip for strips in _containers(editor) for strip in strips
            if strip.type == "META" and strip.get(OWN_CLIP_KEY) is not None
            and strip.get(OWNER_KEY) == obj.name and strip.get(LAYER_GROUP_KEY)]


def own_clips(scene, obj):
    """``{group name: meta-clip}`` of the groups of layers with a clip of their own:
    for each group the one next to the composition's meta-clip (a copy made with
    Shift+D, or one left elsewhere, goes at the next arrangement)."""
    editor = scene.sequence_editor if scene is not None else None
    found = _own_clips_all(editor, obj)
    if not found:
        return {}
    meta = meta_strip(scene, obj)
    home = meta.parent_meta() if meta is not None else None

    def rank(strip):
        parent = strip.parent_meta()
        same = (parent is None and home is None) or _same_meta(parent, home)
        return (not same, strip.name != strip_name(obj, strip[LAYER_GROUP_KEY]))

    clips = {}
    for strip in sorted(found, key=rank):
        clips.setdefault(strip[LAYER_GROUP_KEY], strip)
    return clips


def own_clip_channel(obj, meta, name):
    """Channel of the clip of the group ``name``: above the composition's meta-clip."""
    names = own_clip_groups(obj)
    index = names.index(name) if name in names else len(names)
    base = obj.gp2m.channel or (meta.channel if meta is not None else 1)
    return min(base + 1 + index, MAX_CHANNEL)


def group_clips(scene, obj, meta=None):
    """``{group name: meta-clip}`` of every group of layers of the composition: inside
    its meta-clip, and the clips of their own (with the groups inside them)."""
    if meta is None:
        meta = meta_strip(scene, obj) if scene is not None else None
    found = layer_group_metas(meta) if meta is not None else {}
    for name, clip in own_clips(scene, obj).items():
        found[name] = clip
        found.update(layer_group_metas(clip))
    return found


def _main(strips, obj):
    """The composition's own clip among copies (Shift+D gives them a .001 name)."""
    return next((strip for strip in strips if strip.name == strip_name(obj)), strips[0])


def meta_strip(scene, obj):
    """The meta-clip of a composition with 'Un canale per livello', or None."""
    metas = [strip for strip in _top_strips(scene.sequence_editor, obj)
             if strip.type == "META"]
    return _main(metas, obj) if metas else None


def top_strip(scene, obj):
    """What the composition shows on its channel: its meta-clip or its mix strip."""
    meta = meta_strip(scene, obj)
    if meta is not None:
        return meta
    strips = _top_strips(scene.sequence_editor, obj)
    return min(strips, key=lambda strip: strip.channel) if strips else None


def meta_sounds(meta):
    """The sound strips inside a meta-clip, also inside the meta-clips of its groups of
    layers."""
    found = []
    for strip in meta.strips:
        if strip.type == "SOUND":
            found.append(strip)
        elif strip.type == "META":
            found.extend(meta_sounds(strip))
    return found


def layer_group_metas(meta):
    """``{group name: meta-clip}`` of the groups of layers inside a composition's
    meta-clip (at any depth)."""
    found = {}
    for strip in meta.strips:
        if strip.type == "META":
            if strip.get(LAYER_GROUP_KEY) is not None:
                found[strip[LAYER_GROUP_KEY]] = strip
            found.update(layer_group_metas(strip))
    return found


def composition_strips(scene, obj):
    """Every sound strip of a composition: its mix, or one per layer (inside its
    meta-clip, and inside the meta-clips of its groups of layers)."""
    strips = []
    for strip in _top_strips(scene.sequence_editor, obj):
        if strip.type == "META":
            strips.extend(inner for inner in meta_sounds(strip) if _owned(inner, obj))
        else:
            strips.append(strip)
    for clip in own_clips(scene, obj).values():
        strips.extend(inner for inner in meta_sounds(clip) if _owned(inner, obj))
    return strips


def layer_strips(scene, obj):
    """``{layer name: strip}`` of a composition with 'Un canale per livello'."""
    return {strip[LAYER_KEY]: strip for strip in composition_strips(scene, obj)
            if strip.get(LAYER_KEY) is not None}


def find_strip(scene, obj):
    """The composition's mix strip, or the strip of its first layer."""
    strips = composition_strips(scene, obj)
    for strip in strips:
        if strip.get(LAYER_KEY) is None:
            return strip
    return min(strips, key=lambda strip: strip.channel) if strips else None


MAX_CHANNEL = 128


def _is_composition_strip(strip):
    return strip.get(OWNER_KEY) is not None or strip.name.startswith(STRIP_PREFIX)


def foreign_channels(editor, strips=None):
    """Channels holding strips that belong to no composition (videos, images, sounds
    added by hand, groups): a composition never shares them. Only the top of the
    Sequencer (or of a group, ``strips``) counts: strips inside a meta-clip have
    channels of their own."""
    if strips is None:
        if editor is None:
            return set()
        strips = editor.strips
    return {strip.channel for strip in strips if not _is_composition_strip(strip)}


def _block_from(start, count, used):
    """First block of ``count`` channels from ``start`` up that avoids ``used``;
    when the top of the Sequencer is reached, the first gap from channel 1."""
    count = max(1, count)
    for first in (max(1, start), 1):
        base = first
        while base + count - 1 <= MAX_CHANNEL:
            if not any(channel in used for channel in range(base, base + count)):
                return base
            base += 1
    return min(max(1, start), MAX_CHANNEL - count + 1)  # full: overlap rather than fail


def _channel_block(editor, obj, count):
    """First of ``count`` consecutive channels for the composition: its 'Canale'
    when the whole block is free, otherwise the next free block above it (a
    composition never lands on a channel with other clips)."""
    group = composition_group(editor.id_data, obj)
    strips = group.strips if group is not None else editor.strips
    used = {strip.channel for strip in strips
            if not (_is_composition_strip(strip) and _owned(strip, obj))}
    return _block_from(obj.gp2m.channel or 1, count, used)


def new_composition_channel(scene, count):
    """Channel of a new composition: a new level of the timeline, above every other
    composition, skipping channels that already hold clips."""
    editor = scene.sequence_editor
    used = set()
    top = 0
    if editor is not None:
        for strip in editor.strips:
            used.add(strip.channel)
            if _is_composition_strip(strip):
                top = max(top, strip.channel)
    for obj in scene_compositions(scene):
        if obj.gp2m.channel and composition_group(scene, obj) is None:
            span = range(obj.gp2m.channel, obj.gp2m.channel + _channel_count(scene, obj))
            used.update(span)
            top = max(top, span[-1])
    return _block_from(top + 1, count, used)


def _remove_strip(editor, strip):
    """Remove a strip (inside a meta-clip too); a meta-clip goes with its strips. Sounds
    nobody uses any more are removed."""
    sounds = []
    if strip.type == "META":
        sounds = [inner.sound for inner in meta_sounds(strip) if getattr(inner, "sound", None)]
    elif getattr(strip, "sound", None) is not None:
        sounds = [strip.sound]
    parent = strip.parent_meta()
    (parent.strips if parent is not None else editor.strips).remove(strip)
    for sound in sounds:
        if sound.users == 0:
            bpy.data.sounds.remove(sound)


def _new_strip(scene, name, path, channel, old=None, tags=None, meta=None, frame=None):
    """A new sound strip (inside ``meta`` when given); the volume, pan and mute of
    ``old`` (removed) are kept."""
    editor = scene.sequence_editor or scene.sequence_editor_create()
    keep = {}
    if old is not None:
        for attr in ("volume", "pan", "mute", "color_tag"):
            if hasattr(old, attr):
                keep[attr] = getattr(old, attr)
        _remove_strip(editor, old)
    container = meta.strips if meta is not None else editor.strips
    strip = container.new_sound(name, path, channel,
                                scene.frame_start if frame is None else int(frame))
    strip.sound.name = name
    strip.sound.use_memory_cache = True  # play from RAM: smoother playback
    for key, value in (tags or {}).items():
        strip[key] = value
    for attr, value in keep.items():
        try:
            setattr(strip, attr, value)
        except (AttributeError, TypeError, ValueError):
            pass
    return strip


def _place_strip(scene, obj, path, frames):
    """Point the composition's strip to a new sound file.

    When the length is unchanged only the file of the sound datablock is
    swapped (no strip is removed, so playback is not disturbed); otherwise the
    strip is recreated with the new length.
    """
    editor = scene.sequence_editor or scene.sequence_editor_create()
    meta = meta_strip(scene, obj)
    remove_own_clips(scene, obj)
    if meta is not None:
        if obj.gp2m.channel == 0:
            obj.gp2m.channel = meta.channel
        _remove_strip(editor, meta)
    state(obj).pop("had_meta", None)
    old = find_strip(scene, obj)
    if old is not None and old.get(LAYER_KEY) is not None:
        old = None
    if (old is not None and old.sound is not None and old.sound.users == 1
            and old.duration == frames):
        old.sound.filepath = path  # reloads the audio
        return old
    if obj.gp2m.channel == 0 and old is not None:
        obj.gp2m.channel = old.channel
    channel = _channel_block(editor, obj, 1)
    if obj.gp2m.channel != channel:
        obj.gp2m.channel = channel
    if old is not None:
        _remove_strip(editor, old)
    return _new_strip(scene, strip_name(obj), path, channel, tags={OWNER_KEY: obj.name},
                      meta=_container_meta(scene, obj))


def _remove_layer_strips(scene, obj, keep=()):
    editor = scene.sequence_editor
    for strip in composition_strips(scene, obj):
        if strip.get(LAYER_KEY) is not None and strip[LAYER_KEY] not in keep:
            _remove_strip(editor, strip)
    for clip in _own_clips_all(editor, obj):
        if not meta_sounds(clip):
            _remove_strip(editor, clip)
    meta = meta_strip(scene, obj)
    if meta is not None and not len(meta.strips):
        _remove_strip(editor, meta)


def remove_own_clips(scene, obj):
    """The clips of the groups of layers out of the meta-clip go (mix strip only)."""
    editor = scene.sequence_editor
    for clip in _own_clips_all(editor, obj):
        _remove_strip(editor, clip)


def _same_audio(previous, audio):
    """True when a layer sounds exactly as before (cheaper than hashing the samples)."""
    if previous is None:
        return False
    return previous is audio or (previous.shape == audio.shape
                                 and bool(np.array_equal(previous, audio)))


TRASH_FILES = 160  # sound files no strip plays any more, kept for Ctrl+Z ...
TRASH_BYTES = 768 * 1024 * 1024  # ... up to this much disk (the oldest go first)
_trash = collections.deque()  # (path, bytes), oldest first


def _norm(path):
    return os.path.normcase(os.path.abspath(bpy.path.abspath(path)))


def _forget_file(path):
    """A sound file no strip plays any more. It stays on disk for a while: Ctrl+Z and
    Ctrl+Shift+Z give back strips that play the files of that moment (a muted layer
    is not rendered again, so it would keep a deleted file and stay silent with
    'missing file'). The oldest go once there are too many or they take too much
    room, never one that a sound still uses; the session's temporary folder, where
    they are, is emptied by Blender on quit."""
    if not path:
        return
    try:
        size = os.path.getsize(path)
    except OSError:
        return  # already gone
    key = _norm(path)
    if any(_norm(old) == key for old, _size in _trash):
        return
    _trash.append((path, size))
    _empty_trash()


def _empty_trash(files=TRASH_FILES, room=TRASH_BYTES):
    total = sum(size for _path, size in _trash)
    if len(_trash) <= files and total <= room:
        return
    used = {_norm(sound.filepath) for sound in bpy.data.sounds if sound.filepath and sound.users}
    kept = []
    while _trash and (len(_trash) + len(kept) > files or total > room):
        path, size = _trash.popleft()
        if _norm(path) in used:
            kept.append((path, size))  # a strip plays it again (after Ctrl+Z)
            continue
        total -= size
        try:
            os.remove(path)
        except OSError:
            pass  # still in use (Windows) or already gone
    _trash.extendleft(reversed(kept))


def _ensure_meta(scene, obj, start):
    """The composition's meta-clip: one channel of the Sequencer, the layers inside."""
    editor = scene.sequence_editor or scene.sequence_editor_create()
    meta = meta_strip(scene, obj)
    channel = _channel_block(editor, obj, _channel_count(scene, obj))
    if meta is None:
        for strip in _top_strips(editor, obj):  # the mix strip, layers go inside
            if strip.get(LAYER_KEY) is None:
                _remove_strip(editor, strip)
        meta = _container_strips(scene, obj).new_meta(strip_name(obj), channel, int(start))
        meta[OWNER_KEY] = obj.name
    elif meta.channel != channel:
        meta.channel = channel
    if obj.gp2m.channel != channel:
        obj.gp2m.channel = channel
    return meta


def fit_meta(meta):
    """The meta-clip spans its strips (Blender does not resize it by itself)."""
    inner = list(meta.strips)
    if not inner:
        return
    start = min(strip.left_handle for strip in inner)
    end = max(strip.right_handle for strip in inner)
    if meta.right_handle < start:  # never cross the handles over
        meta.right_handle = end
        meta.left_handle = start
    else:
        if meta.left_handle != start:
            meta.left_handle = start
        if meta.right_handle != end:
            meta.right_handle = end


def rename_composition(obj, name):
    """Rename a composition and everything that carries its name (its clips, its
    state); the grid follows at the next rebuild. Returns the name it got."""
    old = obj.name
    obj.name = name
    new = obj.name
    if new == old:
        return new
    if old in _state:
        _state[new] = _state.pop(old)
    for scene in obj.users_scene:
        editor = scene.sequence_editor
        if editor is None:
            continue
        for strip in [strip for strips in _containers(editor) for strip in strips]:
            if strip.get(OWNER_KEY) != old:
                continue
            strip[OWNER_KEY] = new
            strip.name = strip_name(obj, strip.get(LAYER_GROUP_KEY))
            if strip.type == "META":
                for inner in meta_sounds(strip) + list(layer_group_metas(strip).values()):
                    if inner.get(OWNER_KEY) == old:
                        inner[OWNER_KEY] = new
                        layer = inner.get(LAYER_KEY) or inner.get(LAYER_GROUP_KEY)
                        inner.name = strip_name(obj, layer) if layer else strip_name(obj)
    board.request_rebuild(obj)
    return new


def silent_layers(obj):
    """User layers that are not heard (muted, hidden or silenced by a Solo): their
    strip stays in the meta-clip, muted, so the Sequencer shows every layer."""
    from .reader import audible_layers
    audible = {layer.name for layer in audible_layers(obj.data)}
    return {layer.name for layer in board.user_layers(obj.data) if layer.name not in audible}


def _user_roots(gp):
    return [node for node in gp.root_nodes
            if not (board.is_group(node) and board.is_board_group(node))
            and not (not board.is_group(node) and board.is_board_layer(node))]


def layer_targets(obj, names):
    """Where the strips of the layers ``names`` go inside the composition's meta-clip:
    ``({layer: (groups, channel)}, {groups: channel})``, ``groups`` being the path of
    group names (outer first; () = right inside the meta-clip). A group of layers is a
    meta-clip of its own; channel 1 = the bottom node among its siblings. Groups
    without strips get no meta-clip."""
    names = set(names)
    layers, groups = {}, {}

    def heard(node):
        if board.is_group(node):
            return any(heard(child) for child in node.children)
        return node.name in names

    def walk(nodes, path):
        channel = 0
        for node in nodes:
            if not heard(node):
                continue
            channel += 1
            if board.is_group(node):
                groups[path + (node.name,)] = channel
                walk(list(node.children), path + (node.name,))
            else:
                layers[node.name] = (path, channel)
        return channel

    top = walk(_user_roots(obj.data), ())
    for name in sorted(names - set(layers)):  # not on the board (should not happen)
        top += 1
        layers[name] = ((), top)
    return layers, groups


def tree_signature(obj):
    """Which group each user layer and group is in."""
    gp = obj.data
    nodes = [node for node in list(gp.layers) + list(gp.layer_groups)
             if not (board.is_group(node) and board.is_board_group(node))
             and not (not board.is_group(node) and board.is_board_layer(node))]
    return sorted((node.name, node.parent_group.name if node.parent_group else "")
                  for node in nodes)


def _same_meta(a, b):
    return a is not None and b is not None and a.name == b.name


def _group_container(obj, meta, path, groups, start):
    """The meta-clip of the group of layers ``path`` inside ``meta`` (made when
    missing)."""
    container = meta
    own = set(own_clip_groups(obj))
    for depth in range(len(path)):
        name = path[depth]
        if container == meta and name in own:
            container = _own_clip(obj, meta, name, start)
            continue
        found = next((strip for strip in container.strips if strip.type == "META"
                      and strip.get(LAYER_GROUP_KEY) == name), None)
        if found is None:
            found = container.strips.new_meta(strip_name(obj, name),
                                              groups.get(path[:depth + 1], 1), int(start))
            found[OWNER_KEY] = obj.name
            found[LAYER_GROUP_KEY] = name
        container = found
    return container


def _own_clip(obj, meta, name, start):
    """The clip of its own of the group ``name``, next to the composition's meta-clip
    (made when missing)."""
    scene = meta.id_data
    home = meta.parent_meta()
    for strip in _own_clips_all(scene.sequence_editor, obj):
        parent = strip.parent_meta()
        if strip[LAYER_GROUP_KEY] == name and ((parent is None and home is None)
                                               or _same_meta(parent, home)):
            return strip
    strips = home.strips if home is not None else scene.sequence_editor.strips
    clip = strips.new_meta(strip_name(obj, name), own_clip_channel(obj, meta, name),
                           int(start))
    clip[OWNER_KEY] = obj.name
    clip[LAYER_GROUP_KEY] = name
    clip[OWN_CLIP_KEY] = True
    return clip


def _fit_tree(meta):
    """The meta-clips of the groups of layers span their strips (inner ones first),
    then the composition's."""
    for strip in meta.strips:
        if strip.type == "META":
            _fit_tree(strip)
    fit_meta(meta)


def layout_layers(scene, obj, meta):
    """Every layer strip in the meta-clip of its group, on its channel; the groups'
    meta-clips on theirs, muted with their group; meta-clips of groups that are gone
    removed. Remembers the tree it laid out (see seqsync)."""
    strips = layer_strips(scene, obj)
    if not strips:
        return
    targets, groups = layer_targets(obj, list(strips))
    start = min(strip.content_start for strip in strips.values())
    for name, strip in strips.items():
        path, channel = targets[name]
        container = _group_container(obj, meta, path, groups, start)
        if _same_meta(strip.parent_meta(), container) and strip.channel == channel:
            continue
        if strip.sound is None:
            _remove_strip(scene.sequence_editor, strip)
            continue
        # Setting .channel shuffles a strip that would overlap another one: the strip
        # is created again where it goes (temporary overlaps are allowed).
        _new_strip(scene, strip.name, strip.sound.filepath, channel, old=strip,
                   tags={OWNER_KEY: obj.name, LAYER_KEY: name}, meta=container,
                   frame=strip.content_start)
    wanted = {path[-1]: path for path in groups}
    own = own_clip_groups(obj)

    def misplaced(name, group_meta):
        if name not in wanted or not meta_sounds(group_meta):
            return True
        path = wanted[name]
        first_own = next((depth for depth, group in enumerate(path) if group in own), None)
        should_own = first_own == len(path) - 1
        return should_own != (group_meta.get(OWN_CLIP_KEY) is not None)

    while True:  # removing a meta-clip removes the ones inside: look again each time
        clips = own_clips(scene, obj)
        pairs = list(layer_group_metas(meta).items())
        for name, clip in clips.items():
            pairs += [(name, clip)] + list(layer_group_metas(clip).items())
        chosen = {clip.name for clip in clips.values()}  # strip names are unique
        stale = [clip for clip in _own_clips_all(scene.sequence_editor, obj)
                 if clip.name not in chosen]
        stale += [clip for name, clip in pairs if misplaced(name, clip)]
        if not stale:
            break
        _remove_strip(scene.sequence_editor, stale[0])
    metas = group_clips(scene, obj, meta)
    for name, group_meta in metas.items():
        if group_meta.get(OWN_CLIP_KEY) is not None:
            channel = own_clip_channel(obj, meta, name)
        else:
            channel = groups[wanted[name]]
        if group_meta.channel != channel:
            group_meta.channel = channel
        item = props.find_layer_settings(obj.data, name)
        set_clip_mute(group_meta, _group_clip_mute(meta, group_meta, item))
        if group_meta.name != strip_name(obj, name):
            group_meta.name = strip_name(obj, name)
    st = state(obj)
    st["tree"] = tree_signature(obj)
    st["layer_groups"] = sorted(metas)


def _group_clip_mute(meta, group_meta, item):
    """A group's clip is muted with the group; a clip of its own also with the
    composition (it is not inside the composition's meta-clip any more)."""
    muted = bool(item is not None and item.mute)
    if group_meta.get(OWN_CLIP_KEY) is not None and meta is not None:
        muted = muted or meta.mute
    return muted


def layer_channel_order(obj, names):
    """``names`` in the order of the layers (bottom first): channel 1, 2, ... inside
    the meta-clip."""
    order = [layer.name for layer in board.user_layers(obj.data)]
    return sorted(names, key=lambda name: order.index(name) if name in order else len(order))


MUTE_KEY = "gp2m_mute"  # the mute the add-on last gave a strip (layer or composition)


def set_clip_mute(strip, mute):
    """Mute a layer strip, remembering it was the add-on (a different value later
    means it was changed in the Sequencer)."""
    if strip.mute != mute:
        strip.mute = mute
    if strip.get(MUTE_KEY) != mute:
        strip[MUTE_KEY] = mute


def clip_mute_changed_by_hand(strip):
    return strip.get(MUTE_KEY) is not None and bool(strip[MUTE_KEY]) != strip.mute


def sync_layer_mutes(scene, obj):
    """Every layer strip muted exactly when its layer is not heard (instant: no new
    sound is needed to mute or unmute a layer)."""
    silent = silent_layers(obj)
    for name, strip in layer_strips(scene, obj).items():
        set_clip_mute(strip, name in silent)
    meta = meta_strip(scene, obj)
    for name, group_meta in (group_clips(scene, obj, meta) if meta is not None else {}).items():
        item = props.find_layer_settings(obj.data, name)
        set_clip_mute(group_meta, _group_clip_mute(meta, group_meta, item))


def _place_layer_strips(scene, obj, result):
    """One strip per layer inside the composition's meta-clip (channel 1 = first
    layer): a file is written only for the layers whose sound changed, a strip is
    recreated only when its length or channel changed (volume, pan and mute set in
    the Sequencer are kept). Layer strips of 0.0.21 and earlier move inside."""
    editor = scene.sequence_editor or scene.sequence_editor_create()
    st = state(obj)
    names = [name for name, _audio in result.stems]
    strips = layer_strips(scene, obj)
    start = min((strip.content_start for strip in strips.values()),
                default=scene.frame_start + st.get("offset_frames", 0))
    meta = _ensure_meta(scene, obj, start)
    silent = silent_layers(obj)
    for strip in composition_strips(scene, obj):  # layers gone (silent ones stay, muted)
        layer = strip.get(LAYER_KEY)
        if layer is not None and layer not in names and layer not in silent:
            _remove_strip(editor, strip)
    strips = layer_strips(scene, obj)
    for name, strip in strips.items():  # 0.0.21: the volume and pan set on the strip
        item = props.find_layer_settings(obj.data, name)
        if item is not None and strip.parent_meta() is None:
            item["clip_volume"] = min(max(strip.volume, 0.0), 10.0)
            item["clip_pan"] = min(max(strip.pan, -1.0), 1.0)
    kept = [name for name in strips if name not in names]
    targets, groups = layer_targets(obj, names + kept)
    channels = {name: target[1] for name, target in targets.items()}
    containers = {name: _group_container(obj, meta, targets[name][0], groups, start)
                  for name in names + kept}
    for name in kept:
        strip = strips[name]
        if strip.channel != channels[name] or not _same_meta(strip.parent_meta(),
                                                             containers[name]):
            if strip.sound is None:
                _remove_strip(editor, strip)
                continue
            strip = _new_strip(scene, strip.name, strip.sound.filepath, channels[name],
                               old=strip, tags={OWNER_KEY: obj.name, LAYER_KEY: name},
                               meta=containers[name], frame=strip.content_start)
        set_clip_mute(strip, True)
    # The audio of each layer file (read-only arrays, shared with the mixer's cache).
    paths, sounds = st.setdefault("layer_paths", {}), st.setdefault("layer_audio", {})
    fps = scene.render.fps / scene.render.fps_base
    for index, (name, audio) in enumerate(result.stems):
        strip, channel = strips.get(name), channels[name]
        inside = strip is not None and _same_meta(strip.parent_meta(), containers[name])
        frames = max(1, int(round(len(audio) / result.sample_rate * fps)))
        # The strip must still play the file written for that audio: undo can give
        # it back an older file (kept on disk when Windows could not delete it).
        same_sound = (_same_audio(sounds.get(name), audio) and _strip_file_ok(strip)
                      and _same_file(strip, paths.get(name)))
        placed = inside and strip.channel == channel and strip.duration == frames
        if same_sound and placed:
            _color_strip(obj, strip, name)
            set_clip_mute(strip, False)
            continue
        path = paths.get(name)
        if not same_sound:
            path = os.path.join(cache_dir(),
                                f"{_safe(obj.name)}_{_safe(name)}_{time.time_ns()}.wav")
            write_audio(path, audio, result.sample_rate, "WAV")
        if placed and strip.sound is not None and strip.sound.users == 1:
            strip.sound.filepath = path  # reloads the audio, playback goes on
        else:
            strip = _new_strip(scene, strip_name(obj, name), path, channel, old=strip,
                               tags={OWNER_KEY: obj.name, LAYER_KEY: name},
                               meta=containers[name], frame=start)
        _color_strip(obj, strip, name)
        set_clip_mute(strip, False)  # heard (a mute set in the Sequencer is the layer's)
        if paths.get(name) != path:
            _forget_file(paths.get(name))
        paths[name], sounds[name] = path, audio
    for name in [name for name in paths if name not in names and name not in kept]:
        _forget_file(paths.pop(name))
        sounds.pop(name, None)
    layout_layers(scene, obj, meta)
    _fit_tree(meta)
    for clip in own_clips(scene, obj).values():
        _fit_tree(clip)


def _color_strip(obj, strip, layer_name):
    dress_strip(obj, strip, layer_name)


def dress_strip(obj, strip, layer_name):
    """The strip of a layer has the layer's color, clip volume and pan (animated
    values are left to their keyframes)."""
    item = props.find_layer_settings(obj.data, layer_name)
    color = item.color if item is not None else "NONE"
    if strip.color_tag != color:
        strip.color_tag = color
    if item is None:
        return
    scene = strip.id_data
    volume, pan = strip_bus(scene, obj, layer_name)
    for attr, value in (("volume", item.clip_volume * volume),
                        ("pan", min(max(item.clip_pan + pan, -1.0), 1.0))):
        if not is_animated(scene, strip, attr) and abs(getattr(strip, attr) - value) > 1e-5:
            setattr(strip, attr, value)


def is_animated(scene, strip, attr):
    """True when the strip's ``attr`` has keyframes or a driver."""
    path = f'["{strip.name}"].{attr}'
    data = scene.animation_data
    if data is None:
        return False
    curves = list(data.drivers)
    action = data.action
    if action is not None:
        try:
            curves += list(action.fcurves)
        except AttributeError:  # slotted actions (Blender 5)
            for layer in getattr(action, "layers", ()):
                for strip_ in layer.strips:
                    for bag in strip_.channelbags:
                        curves += list(bag.fcurves)
    return any(curve.data_path.endswith(path) for curve in curves)


def _same_file(strip, path):
    if strip is None or strip.sound is None or not path:
        return False
    return os.path.normcase(os.path.abspath(bpy.path.abspath(strip.sound.filepath))) == \
        os.path.normcase(os.path.abspath(path))


def _strip_file_ok(strip):
    if strip is None or strip.sound is None:
        return False
    return os.path.exists(bpy.path.abspath(strip.sound.filepath))


def sound_files_ok(obj, scene):
    """True when every strip of the composition plays the file last written for it.

    Undo and redo give the strips back older files, which were deleted when a new
    sound replaced them: with automatic updates off they would play silence."""
    if scene is None:
        return True
    st = state(obj)
    strips = composition_strips(scene, obj)
    if not strips:
        return False
    paths = st.get("layer_paths") or {}
    for strip in strips:
        layer = strip.get(LAYER_KEY)
        path = st.get("path") if layer is None else paths.get(layer)
        if not _strip_file_ok(strip) or not _same_file(strip, path):
            return False
    return True


def scene_compositions(scene):
    comps = [obj for obj in scene.objects
             if obj.type == "GREASEPENCIL" and obj.gp2m.is_composition]
    return sorted(comps, key=lambda o: (o.gp2m.order, o.name))


def _fps(scene):
    return scene.render.fps / scene.render.fps_base


def _active_composition(scene):
    layer = bpy.context.view_layer if bpy.context.scene == scene else scene.view_layers[0]
    obj = layer.objects.active if layer is not None else None
    if obj is not None and obj.type == "GREASEPENCIL" and obj.gp2m.is_composition:
        return obj
    return None


def _channel_count(scene, obj):
    """Channels a composition takes in the Sequencer: always one (its mix strip, or
    the meta-clip with its layers inside), plus one per group of layers with a clip of
    its own."""
    return 1 + len(own_clip_groups(obj))


def resolve_channels(scene):
    """Every composition on channels of its own: duplicated compositions copy the
    channel, and a clip added by hand on a composition's channel pushes the
    composition up to the next free block (with 'Un canale per livello' a
    composition takes one channel per layer). The clips are never moved."""
    editor = scene.sequence_editor
    taken = {}  # per group (None: the top of the Sequencer): the channels in use
    for obj in sorted(scene_compositions(scene), key=lambda o: o.name):
        if not obj.gp2m.channel:
            continue
        group = composition_group(scene, obj) if editor is not None else None
        key = group.get(GROUP_KEY) if group is not None else None
        if key not in taken:
            taken[key] = foreign_channels(editor, group.strips if group is not None else None)
        used = taken[key]
        count = _channel_count(scene, obj)
        if set(range(obj.gp2m.channel, obj.gp2m.channel + count)) & used:
            obj.gp2m.channel = _block_from(obj.gp2m.channel, count, used)
        used |= set(range(obj.gp2m.channel, obj.gp2m.channel + count))


def arrange(scene):
    """Guarded: properties written while arranging call back into arrange_safe()."""
    if _arranging[0]:
        return
    _arranging[0] = True
    try:
        _arrange(scene)
        for obj in scene_compositions(scene):
            save_sync_state(obj)
    finally:
        _arranging[0] = False


def delay_frames(obj, scene):
    return max(0, int(round(obj.gp2m.start_delay * _fps(scene))))


def _arrange(scene):
    """Place, mute and time every composition of the scene for the play mode.

    Compositions with 'Segui In/Out della scena' last from the scene Start to its
    End (see :func:`_follow_scene`). TOGETHER: all start at the scene start. SOLO: only the active composition
    is heard. SEQUENCE: one after another, by "order" then name. The scene
    range follows (so playback loops on what you hear). Writes only changes.
    """
    comps = scene_compositions(scene)
    if not comps:
        return
    resolve_channels(scene)
    play = scene.gp2m_play
    fps = _fps(scene)
    linked = [obj for obj in comps if follows_scene(obj, scene)]
    if linked:
        _follow_scene(scene, linked)
    lengths = {obj.name: max(1, int(round(duration(obj) * fps))) for obj in comps}
    solo = _active_composition(scene) if play.mode == "SOLO" else None
    if play.mode == "SOLO" and solo is None:
        solo = next((o for o in comps if o.name == _last_solo.get(scene.name)),
                                 comps[0])
    if solo is not None:
        _last_solo[scene.name] = solo.name

    offset = 0
    ends = []
    for obj in comps:
        st = state(obj)
        delay = delay_frames(obj, scene)
        start_offset = (offset if play.mode == "SEQUENCE" else 0) + delay
        if play.mode == "SEQUENCE":
            offset = start_offset + lengths[obj.name]
        ends.append((obj, start_offset + lengths[obj.name]))
        st["offset_frames"] = start_offset
        st["delay_frames"] = delay
        board.set_playhead_offset(obj, start_offset, st.get("sections"))
        board.update_preview_shade(obj, scene)
        strips = composition_strips(scene, obj)
        if not strips:
            continue
        target = scene.frame_start + start_offset
        mute = obj.gp2m.mute or (solo is not None and obj != solo)
        layered = [strip for strip in strips if strip.get(LAYER_KEY) is not None]
        if layered:
            _arrange_layers(scene, obj, layered, target, mute)
            continue
        strip = strips[0]
        if strip.content_start != target:
            strip.content_start = target
        if strip.parent_meta() is not None:  # in a group: the group's volume and pan
            volume, pan = strip_bus(scene, obj)
            for attr, value in (("volume", volume), ("pan", min(max(pan, -1.0), 1.0))):
                if not is_animated(scene, strip, attr) and abs(getattr(strip, attr) - value) > 1e-5:
                    setattr(strip, attr, value)
        if obj.gp2m.channel == 0:
            obj.gp2m.channel = strip.channel  # show the automatic choice
        elif strip.channel != obj.gp2m.channel:
            strip.channel = obj.gp2m.channel
        set_clip_mute(strip, mute)  # H / Alt+H on it in the Sequencer: see seqsync

    fit_groups(scene)

    if play.fit_range and not linked:  # following the scene, the scene leads
        if play.mode == "SEQUENCE":
            total = offset
        elif solo is not None:
            total = next(end for obj, end in ends if obj == solo)
        else:
            total = max(end for _obj, end in ends)
        end = scene.frame_start + total - 1
        if scene.frame_end != end:
            scene.frame_end = end


def fit_groups(scene):
    """Every group of compositions spans its clips (the inner ones first); an empty
    group goes."""
    editor = scene.sequence_editor
    for group in reversed(group_metas(editor)):
        if not len(group.strips):
            _remove_strip(editor, group)
        elif not group.lock:
            fit_meta(group)


def _arrange_layers(scene, obj, strips, target, mute):
    """The meta-clip: on the composition's channel, starting at ``target``, muted with
    the composition; inside, one channel per layer in the order of the layers (a
    layer muted in the Sequencer stays muted)."""
    meta = meta_strip(scene, obj)
    if meta is None:
        return  # layer strips of 0.0.21: they move into a meta-clip at the next sound
    state(obj)["had_meta"] = True
    if meta.lock:  # locked in the Sequencer: the add-on leaves it where it is
        set_clip_mute(meta, mute)
        return
    if obj.gp2m.channel == 0:
        obj.gp2m.channel = meta.channel  # the automatic choice
    elif meta.channel != obj.gp2m.channel:
        meta.channel = obj.gp2m.channel
    layout_layers(scene, obj, meta)
    sync_layer_mutes(scene, obj)
    clips = own_clips(scene, obj)
    for container in [meta] + list(clips.values()):
        inner = meta_sounds(container)
        if not inner:
            continue
        shift = target - min(strip.content_start for strip in inner)
        if shift:
            container.content_start = container.content_start + shift  # with its strips
        for strip in meta_sounds(container):  # every layer starts with the composition
            if strip.content_start != target:
                strip.content_start = target
        _fit_tree(container)
    state(obj)["meta_span"] = (int(meta.left_handle), int(meta.right_handle))
    set_clip_mute(meta, mute)  # H / Alt+H on it in the Sequencer: see seqsync
    for name, clip in clips.items():
        set_clip_mute(clip, _group_clip_mute(meta, clip,
                                             props.find_layer_settings(obj.data, name)))


_last_solo = {}
_arranging = [False]


def arrange_safe(scene):
    try:
        arrange(scene)
        from . import timeline
        timeline.tag_redraw()
    except Exception:
        traceback.print_exc()


PEAKS_PER_SECOND = 100


def timeline_data(result, settings):
    """Waveform peaks and note blocks for the timeline overlay."""
    audio = result.audio
    hop = max(1, result.sample_rate // PEAKS_PER_SECOND)
    usable = len(audio) // hop * hop
    if usable:  # max |x| per block, without a copy of the whole buffer for abs()
        blocks = audio[:usable].reshape(-1, hop * audio.shape[1])
        peaks = np.maximum(blocks.max(axis=1), -blocks.min(axis=1))
    else:
        peaks = np.zeros(0)
    top = max(float(peaks.max()) if len(peaks) else 0.0, 1e-6)
    notes = [(n.start, n.end, n.pitch, synth.get_instrument(n.instrument).color)
             for n in result.notes]
    curves = [(start, pitch, synth.get_instrument(ident).color)
              for start, pitch, ident in result.curves]
    return {"peaks": (peaks / top).astype(np.float32), "rate": PEAKS_PER_SECOND,
            "notes": notes, "curves": curves, "curve_rate": interpret.CONTROL_RATE / 4,
            "low": 0 if beat.is_beat(settings) else settings.low_note,
            "high": 127 if beat.is_beat(settings) else settings.low_note + board.span(settings),
            "length": result.duration or settings.length}


class Job:
    """One render: planned in Blender's thread (:func:`prepare`), computed anywhere
    (:func:`run`), applied to the Sequencer in Blender's thread (:func:`apply`)."""

    def __init__(self, obj, scene, force, per_layer):
        self.name, self.scene_name = obj.name, scene.name
        self.force, self.per_layer = force, per_layer
        self.fn = self.reads = self.keep = self.result = self.error = None
        self.partial = False
        self.began = time.perf_counter()
        self.generation = 0
        self.epoch = _epoch[0]
        self.done = False

    def current(self):
        """False when a newer render of the same composition (or a new file) came."""
        return self.epoch == _epoch[0] and _generation.get(self.name) == self.generation


_generation = {}  # composition name -> number of its latest render (older ones are dropped)
_epoch = [0]  # a new file: renders of the previous one are dropped


def invalidate(name):
    """The composition changed again: a render of it still running is dropped."""
    if any(job.name == name for job in _pending):
        _generation[name] = _generation.get(name, 0) + 1


def prepare(obj, scene=None, force=False, only_active=False):
    """Read what the render needs (Blender's thread). None when nothing must be
    rendered (a muted composition keeps its muted clips)."""
    scene = scene or scene_of(obj)
    s = obj.gp2m
    if not s.is_composition:
        return None
    # A render still running for this composition is old now.
    generation = _generation[obj.name] = _generation.get(obj.name, 0) + 1
    props.ensure_layer_settings(obj.data)
    if (s.mute or muted_by_group(scene, obj)) and not force and composition_strips(scene, obj):
        arrange(scene)  # muted: its clips stay, muted, and nothing is rendered
        state(obj)["muted_stale"] = True
        return None
    state(obj).pop("muted_stale", None)
    per_layer = s.layer_channels
    job = Job(obj, scene, force, per_layer)
    job.generation = generation
    if only_active and per_layer and not force:
        job.fn, job.reads = plan_active_layer(obj, scene)
        job.partial = job.fn is not None
    if job.fn is None:
        job.fn, job.reads = plan_composition(obj, scene, stems=per_layer)
    if per_layer:
        job.keep = getattr(job.fn, "keep", None) or _keep_info(obj, scene)
    return job


def run(job):
    """Compute the sound of ``job`` (any thread: no Blender data is touched)."""
    try:
        job.result = compute(job.fn)
    except Exception as error:  # noqa: BLE001 - raised again by apply()
        job.error = (error, traceback.format_exc())
    job.done = True
    return job


def apply(job):
    """Write the sound of a computed ``job`` and update its strips (Blender's thread)."""
    obj = bpy.data.objects.get(job.name)
    scene = bpy.data.scenes.get(job.scene_name)
    if obj is None or scene is None or not obj.gp2m.is_composition:
        return None
    if job.error is not None:
        print(job.error[1], end="")
        raise job.error[0]
    result = job.result
    if result is None:  # the active layer could not be rendered alone: all of them
        full = prepare(obj, scene, job.force, only_active=False)
        return apply(run(full)) if full is not None else None
    s = obj.gp2m
    per_layer = job.per_layer
    st = state(obj)
    key = (result.key, per_layer)
    if per_layer:
        strips = layer_strips(scene, obj)
        paths = st.get("layer_paths") or {}
        silent = silent_layers(obj)
        files_ok = ({name for name in strips if name not in silent}
                    == {name for name, _audio in result.stems}
                    and all(_strip_file_ok(strip) and _same_file(strip, paths.get(name))
                            for name, strip in strips.items())
                    and len(composition_strips(scene, obj)) == len(strips))
    else:
        strip = find_strip(scene, obj)
        files_ok = (_strip_file_ok(strip) and strip.get(LAYER_KEY) is None
                    and _same_file(strip, st.get("path"))
                    and len(composition_strips(scene, obj)) == 1)
    if job.force or st.get("key") != key or not files_ok:
        if per_layer:
            _place_layer_strips(scene, obj, result)
            _forget_file(st.pop("path", None))
        else:
            path = os.path.join(cache_dir(), f"{_safe(obj.name)}_{time.time_ns()}.wav")
            write_audio(path, result.audio, result.sample_rate, "WAV")
            fps = scene.render.fps / scene.render.fps_base
            frames = max(1, int(round(len(result.audio) / result.sample_rate * fps)))
            _remove_layer_strips(scene, obj)
            _place_strip(scene, obj, path, frames)
            old_path = st.get("path")
            if old_path and old_path != path:
                _forget_file(old_path)
            st["path"] = path
            for name in list(st.get("layer_paths", {})):
                _forget_file(st["layer_paths"].pop(name))
            st.get("layer_audio", {}).clear()
        st["key"] = key
        st["sections"] = result.sections
        st["duration"] = result.duration or s.length
        st["timeline"] = timeline_data(result, s)
        from . import timeline
        timeline.tag_redraw()
    if per_layer:
        _keep_layers(obj, scene, result, job.keep)
    else:
        st["layers"] = None
    arrange(scene)
    st["stats"] = {
        "notes": len(result.notes),
        "voices": result.voice_count,
        "seconds": time.perf_counter() - job.began,
        "multi_keyframes": [] if s.use_sections else [
            layer.name for layer in reader.audible_layers(obj.data) if len(layer.frames) > 1],
        "sections": len(result.sections),
        "skipped": result.errors,
        "layers": len(result.stems),
        "only_active": job.partial,
    }
    st["error"] = None
    return result


def regenerate(obj, scene=None, force=False, only_active=False):
    """Render the composition and update its sound strip(s).

    Writes nothing when the sound did not change, so it is safe to call from
    depsgraph handlers without creating update loops. ``only_active``: render
    only the active layer when the others can keep their sound (with
    'Un canale per livello'; otherwise, or when not possible, everything).
    """
    job = prepare(obj, scene, force, only_active)
    if job is None:
        return None
    return apply(run(job))


def regenerate_safe(obj, scene=None, force=False, only_active=False):
    try:
        return regenerate(obj, scene, force, only_active)
    except Exception as error:
        traceback.print_exc()
        state(obj)["error"] = f"{type(error).__name__}: {error}"
        return None


# --- Rendering in the background ------------------------------------------------------
#
# Automatic updates compute the sound in a worker thread: Blender's thread only
# reads the strokes before and writes the files after, so drawing, editing and
# sculpting are not held up while the mix and the master bus are computed.
# The sound is exactly the one regenerate() would make.

_queue = queue.Queue()
_pending = []  # jobs handed to the worker; _apply_tick applies them when computed
_worker = [None]
APPLY_POLL = 0.02  # seconds between checks for a finished render


def _work():
    while True:
        job = _queue.get()
        if job is None:  # stop_background()
            return
        if job.current():
            run(job)
        else:
            job.done = True  # a newer render of the same composition is on its way


def _apply_tick():
    from .handlers import brush_running, transform_running
    done = [job for job in _pending if job.done]
    if done and (transform_running() or brush_running()):
        return 0.1  # strips are not touched while G or a brush stroke is going on
    for job in done:
        _pending.remove(job)
        if not job.current():
            continue
        try:
            apply(job)
        except Exception as error:
            obj = bpy.data.objects.get(job.name)
            if obj is not None:
                state(obj)["error"] = f"{type(error).__name__}: {error}"
    return APPLY_POLL if _pending else None


def regenerate_background(obj, only_active=False):
    """Like :func:`regenerate_safe`, with the sound computed in the worker thread."""
    try:
        job = prepare(obj, None, False, only_active)
    except Exception as error:
        traceback.print_exc()
        state(obj)["error"] = f"{type(error).__name__}: {error}"
        return
    if job is None:
        return
    if _worker[0] is None or not _worker[0].is_alive():
        _worker[0] = threading.Thread(target=_work, name="Doodle Music render", daemon=True)
        _worker[0].start()
    _pending.append(job)
    _queue.put(job)
    if not bpy.app.timers.is_registered(_apply_tick):
        bpy.app.timers.register(_apply_tick, first_interval=APPLY_POLL)


def wait_background(timeout=30.0):
    """Wait for the renders in progress and apply them (tests, saving, exporting)."""
    end = time.monotonic() + timeout
    while _pending and time.monotonic() < end:
        if all(job.done for job in _pending):
            from .handlers import brush_running, transform_running
            if transform_running() or brush_running():
                return False
            _apply_tick()
        else:
            time.sleep(0.005)
    return not _pending


def new_file():
    """A file was loaded: renders of the previous one are dropped."""
    _epoch[0] += 1
    _pending.clear()
    _generation.clear()


def stop_background():
    if bpy.app.timers.is_registered(_apply_tick):
        bpy.app.timers.unregister(_apply_tick)
    _pending.clear()
    if _worker[0] is not None and _worker[0].is_alive():
        _queue.put(None)
    _worker[0] = None
