# SPDX-License-Identifier: GPL-3.0-or-later
"""Glue between Blender data and the audio renderer.

``regenerate`` reads the strokes, renders the loop, writes a WAV into a cache
folder and (re)places it as a sound strip in the Video Sequencer, so pressing
Play in Blender plays the drawing.
"""

import os
import re
import tempfile
import time
import traceback
import wave
from dataclasses import astuple

import aud
import bpy
import numpy as np

from . import board, interpret, midi, mixer, music, prefs, props, reader, synth

STRIP_PREFIX = "GP2M · "

# Runtime state per composition object name (not saved in the .blend file).
_state = {}


def state(obj):
    return _state.setdefault(obj.name, {})


def board_spec(settings):
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


def _layer_inputs(obj, reads):
    beat = 60.0 / max(obj.gp2m.bpm, 1e-6)
    layers = []
    for read in reads:
        settings = props.find_layer_settings(obj.data, read.name)
        layers.append(mixer.LayerInput(
            name=read.name,
            strokes=read.strokes,
            mode=settings.mode if settings else "QUANTIZED",
            fill_mode=settings.fill_mode if settings else "TONAL",
            glide=settings.glide if settings else 0.12,
            legato_gap=settings.legato_gap if settings else 1.0,
            gain=read.opacity,
            fx=_layer_fx(settings),
            canon_voices=settings.canon_voices if settings and settings.use_canon else 1,
            canon_delay=settings.canon_delay * beat if settings else 0.0,
            canon_transpose=settings.canon_transpose if settings else 0,
            harmony=settings.harmony if settings else "OFF",
            mods=layer_mods(settings),
            rows=board.dimensions(obj.gp2m)[0],
        ))
    return layers


def render_composition(obj, scene, stems=False):
    """Render the loop drawn at the scene start, or every keyframe section.

    ``stems``: also render every layer on its own (``result.stems``)."""
    s = obj.gp2m
    spec, mapping, rate = board_spec(s), prefs.get_mapping(), int(s.sample_rate)
    frames = section_frames(obj, scene) if s.use_sections else [scene.frame_start]
    # Following the scene, the last section repeats its loop until the scene End.
    until = scene_seconds(scene) if s.use_sections and follows_scene(obj, scene) else None
    if len(frames) == 1 and until is None:
        reads = reader.read_composition(obj, frames[0], use_modifiers=s.use_modifiers)
        result = mixer.render(_layer_inputs(obj, reads), spec, mapping, rate, loop=s.loop,
                              master_volume=s.master_volume, master_fx=master_fx(s),
                              stems=stems)
        result.duration = s.length
        return result, reads
    times = [(frame - scene.frame_start) / _fps(scene) for frame in frames]
    parts, first_reads = [], None
    for i, frame in enumerate(frames):
        reads = reader.read_composition(obj, frame, use_modifiers=s.use_modifiers)
        first_reads = reads if first_reads is None else first_reads
        if i + 1 < len(times):
            end = times[i + 1]
        elif until is not None and until > times[i]:
            end = until
        else:
            end = times[i] + s.length
        parts.append((times[i], end, mixer.render(
            _layer_inputs(obj, reads), spec, mapping, rate, loop=False,
            master_volume=s.master_volume, stems=stems)))
    return mixer.sequence(parts, s.length, rate, loop=s.loop,
                          master_fx=master_fx(s), stems=stems), first_reads


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


_linked_range = {}  # scene name -> Start, End and fps the compositions were matched to


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
        state(obj)["linked_frames"] = _loop_frames(obj, fps)
        _linked_range[scene.name] = _range_key(scene)


def _follow_scene(scene, linked):
    """The compositions that follow the scene last from its Start to its End.

    It works both ways: a new Start or End (or frame rate) changes their length,
    and a composition made longer or shorter (Durata, scaling the board, a MIDI
    import...) moves the scene End, then the others follow. With keyframe sections
    the loop keeps its length and the last section lasts until the End."""
    fps = _fps(scene)
    loops = [obj for obj in linked if not obj.gp2m.use_sections]
    if _linked_range.get(scene.name) == _range_key(scene):  # the scene did not change
        moved = [obj for obj in loops
                 if state(obj).get("linked_frames") not in (None, _loop_frames(obj, fps))]
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
        state(obj)["linked_frames"] = target
    _linked_range[scene.name] = _range_key(scene)


def _context_signature(obj, scene):
    """What every layer of the composition depends on (besides its own settings)."""
    s = obj.gp2m
    return repr((astuple(board_spec(s)), astuple(prefs.get_mapping()), s.sample_rate, s.loop,
                 round(s.master_volume, 4), astuple(master_fx(s)), s.use_modifiers,
                 scene.frame_start))


def _layer_signatures(obj, layers):
    """Settings of each audible layer (volume, reading, effects...), without its strokes."""
    stubs = [reader.LayerRead(name=layer.name, opacity=props.layer_volume(obj.data, layer))
             for layer in layers]
    return {item.name: repr(item) for item in _layer_inputs(obj, stubs)}


def render_active_layer(obj, scene):
    """Render only the active layer and mix it with the sound the other layers had.

    Returns ``(result, reads)``, or ``(None, None)`` when everything must be
    rendered again: keyframe sections, no sound kept yet, a layer added, removed,
    muted, or with other settings, or a change of the whole composition."""
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
    if st.get("context") != _context_signature(obj, scene):
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
    fresh = mixer.render_layers(_layer_inputs(obj, reads), spec, mapping, rate, s.loop,
                                s.master_volume, fx.room)
    if len(fresh) != 1:
        return None, None
    sounds = [fresh[0] if name == active.name else kept[name] for name in names]
    result = mixer.mix_layers(sounds, spec, mapping, rate, s.loop, fx, stems=True)
    result.duration = s.length
    return result, reads


def _keep_layers(obj, scene, result):
    """Remember each layer's sound, for :func:`render_active_layer`."""
    st = state(obj)
    if obj.gp2m.use_sections or not result.layers:
        st["layers"] = None
        return
    st["layers"] = {sound.name: sound for sound in result.layers}
    st["context"] = _context_signature(obj, scene)
    st["signatures"] = _layer_signatures(obj, reader.audible_layers(obj.data))
    st["fingerprints"] = reader.layer_fingerprints(obj, scene.frame_start,
                                                   obj.gp2m.use_modifiers)


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


def export(obj, scene, path, fmt):
    result, _reads = render_composition(obj, scene)
    if fmt == "MIDI":
        midi.write_midi(path, midi_tracks(result.notes), obj.gp2m.bpm)
    else:
        write_audio(path, result.audio, result.sample_rate, fmt, prefs.get_prefs().mp3_bitrate)
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
    for scene in bpy.data.scenes:
        editor = scene.sequence_editor
        if editor is None:
            continue
        for strip in list(editor.strips):
            if not strip.name.startswith(STRIP_PREFIX):
                continue
            owner = bpy.data.objects.get(strip.get(OWNER_KEY)
                                         or strip.name[len(STRIP_PREFIX):])
            if owner is None or not owner.gp2m.is_composition or scene not in owner.users_scene:
                sound = strip.sound
                editor.strips.remove(strip)
                if sound is not None and sound.users == 0:
                    bpy.data.sounds.remove(sound)
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


def strip_name(obj, layer=None):
    """Name of the composition's mix strip, or of the strip of one of its layers."""
    return STRIP_PREFIX + obj.name if layer is None else f"{STRIP_PREFIX}{obj.name} · {layer}"


def _owned(strip, obj):
    owner = strip.get(OWNER_KEY)
    if owner is not None:
        return owner == obj.name
    return strip.name == strip_name(obj)  # strips of 0.0.12 and earlier


def composition_strips(scene, obj):
    """Every strip of a composition: its mix, or one per layer."""
    editor = scene.sequence_editor
    if editor is None:
        return []
    return [strip for strip in editor.strips
            if strip.name.startswith(STRIP_PREFIX) and _owned(strip, obj)]


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


def _free_channel(editor, exclude=None):
    """Lowest channel without strips (the composition's own strip excluded)."""
    used = {strip.channel for strip in editor.strips_all if strip.name != exclude}
    channel = 1
    while channel in used:
        channel += 1
    return channel


MAX_CHANNEL = 128


def _channel_block(editor, obj, count):
    """First of ``count`` consecutive channels for the composition: its 'Canale'
    when set (as for the mix strip), otherwise the first block with no strips."""
    if obj.gp2m.channel > 0:
        return obj.gp2m.channel
    used = {strip.channel for strip in editor.strips_all
            if not (strip.name.startswith(STRIP_PREFIX) and _owned(strip, obj))}
    count = max(1, count)
    base = 1
    while base + count - 1 < MAX_CHANNEL and any(
            channel in used for channel in range(base, base + count)):
        base += 1
    return base


def _remove_strip(editor, strip):
    sound = strip.sound
    editor.strips.remove(strip)
    if sound is not None and sound.users == 0:
        bpy.data.sounds.remove(sound)


def _new_strip(scene, name, path, channel, old=None, tags=None):
    """A new sound strip; the volume, pan and mute of ``old`` (removed) are kept."""
    editor = scene.sequence_editor or scene.sequence_editor_create()
    keep = {}
    if old is not None:
        for attr in ("volume", "pan", "mute", "color_tag"):
            if hasattr(old, attr):
                keep[attr] = getattr(old, attr)
        _remove_strip(editor, old)
    strip = editor.strips.new_sound(name, path, channel, scene.frame_start)
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
    old = find_strip(scene, obj)
    if old is not None and old.get(LAYER_KEY) is not None:
        old = None
    if (old is not None and old.sound is not None and old.sound.users == 1
            and old.duration == frames):
        old.sound.filepath = path  # reloads the audio
        return old
    if obj.gp2m.channel > 0:
        channel = obj.gp2m.channel
    elif old is not None:
        channel = old.channel
    else:
        channel = _free_channel(editor, strip_name(obj))
    if old is not None:
        _remove_strip(editor, old)
    return _new_strip(scene, strip_name(obj), path, channel, tags={OWNER_KEY: obj.name})


def _remove_layer_strips(scene, obj, keep=()):
    editor = scene.sequence_editor
    for strip in composition_strips(scene, obj):
        if strip.get(LAYER_KEY) is not None and strip[LAYER_KEY] not in keep:
            _remove_strip(editor, strip)


def _same_audio(previous, audio):
    """True when a layer sounds exactly as before (cheaper than hashing the samples)."""
    if previous is None:
        return False
    return previous is audio or (previous.shape == audio.shape
                                 and bool(np.array_equal(previous, audio)))


def _forget_file(path):
    if path:
        try:
            os.remove(path)
        except OSError:
            pass  # still in use (Windows) or already gone


def _place_layer_strips(scene, obj, result):
    """One strip per layer on consecutive channels: a file is written only for the
    layers whose sound changed, a strip is recreated only when its length or
    channel changed (volume, pan and mute set in the Sequencer are kept)."""
    editor = scene.sequence_editor or scene.sequence_editor_create()
    st = state(obj)
    names = [name for name, _audio in result.stems]
    for strip in composition_strips(scene, obj):  # the mix strip, layers gone
        if strip.get(LAYER_KEY) is None or strip[LAYER_KEY] not in names:
            _remove_strip(editor, strip)
    strips = layer_strips(scene, obj)
    # The audio of each layer file (read-only arrays, shared with the mixer's cache).
    paths, sounds = st.setdefault("layer_paths", {}), st.setdefault("layer_audio", {})
    base = _channel_block(editor, obj, len(names))
    fps = scene.render.fps / scene.render.fps_base
    for index, (name, audio) in enumerate(result.stems):
        strip, channel = strips.get(name), base + index
        frames = max(1, int(round(len(audio) / result.sample_rate * fps)))
        # The strip must still play the file written for that audio: undo can give
        # it back an older file (kept on disk when Windows could not delete it).
        same_sound = (_same_audio(sounds.get(name), audio) and _strip_file_ok(strip)
                      and _same_file(strip, paths.get(name)))
        if same_sound and strip.channel == channel and strip.duration == frames:
            _color_strip(obj, strip, name)
            continue
        path = paths.get(name)
        if not same_sound:
            path = os.path.join(cache_dir(),
                                f"{_safe(obj.name)}_{_safe(name)}_{time.time_ns()}.wav")
            write_audio(path, audio, result.sample_rate, "WAV")
        if (strip is not None and strip.sound is not None and strip.sound.users == 1
                and strip.duration == frames and strip.channel == channel):
            strip.sound.filepath = path  # reloads the audio, playback goes on
        else:
            strip = _new_strip(scene, strip_name(obj, name), path, channel, old=strip,
                               tags={OWNER_KEY: obj.name, LAYER_KEY: name})
            strip.mute = strip.mute or bool(st.get("muted"))
        _color_strip(obj, strip, name)
        if paths.get(name) != path:
            _forget_file(paths.get(name))
        paths[name], sounds[name] = path, audio
    for name in [name for name in paths if name not in names]:
        _forget_file(paths.pop(name))
        sounds.pop(name, None)
    if obj.gp2m.channel != base:
        obj.gp2m.channel = base


def _color_strip(obj, strip, layer_name):
    """The strip of a layer has the layer's color."""
    item = props.find_layer_settings(obj.data, layer_name)
    color = item.color if item is not None else "NONE"
    if strip.color_tag != color:
        strip.color_tag = color


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
    """How many channels the composition uses (one per layer, or its mix)."""
    return max(1, len(layer_strips(scene, obj)))


def resolve_channels(scene):
    """Duplicated compositions copy the channel: give the copies free ones (with
    'Un canale per livello' a composition takes one channel per layer)."""
    taken = set()
    editor = scene.sequence_editor
    for obj in sorted(scene_compositions(scene), key=lambda o: o.name):
        count = _channel_count(scene, obj)
        span = set(range(obj.gp2m.channel, obj.gp2m.channel + count))
        if obj.gp2m.channel and span & taken:
            channel = _free_channel(editor, strip_name(obj)) if editor else 0
            channel = max(channel, 1)
            while set(range(channel, channel + count)) & taken:
                channel += 1
            obj.gp2m.channel = channel
            span = set(range(channel, channel + count))
        if obj.gp2m.channel:
            taken |= span


def arrange(scene):
    """Guarded: properties written while arranging call back into arrange_safe()."""
    if _arranging[0]:
        return
    _arranging[0] = True
    try:
        _arrange(scene)
    finally:
        _arranging[0] = False


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
    for obj in comps:
        st = state(obj)
        start_offset = offset if play.mode == "SEQUENCE" else 0
        if play.mode == "SEQUENCE":
            offset += lengths[obj.name]
        st["offset_frames"] = start_offset
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
        if obj.gp2m.channel == 0:
            obj.gp2m.channel = strip.channel  # show the automatic choice
        elif strip.channel != obj.gp2m.channel:
            strip.channel = obj.gp2m.channel
        if strip.mute != mute:
            strip.mute = mute

    if play.fit_range and not linked:  # following the scene, the scene leads
        if play.mode == "SEQUENCE":
            total = offset
        elif solo is not None:
            total = lengths[solo.name]
        else:
            total = max(lengths.values())
        end = scene.frame_start + total - 1
        if scene.frame_end != end:
            scene.frame_end = end


def _arrange_layers(scene, obj, strips, target, mute):
    """Layer strips: same start, consecutive channels from 'Canale' (in the order
    of the layers), muted with the composition. A layer muted in the Sequencer
    stays muted until the composition itself is muted or unmuted."""
    st = state(obj)
    if obj.gp2m.channel == 0:
        obj.gp2m.channel = min(strip.channel for strip in strips)  # the automatic choice
    order = [layer.name for layer in obj.data.layers]
    strips = sorted(strips, key=lambda strip: order.index(strip[LAYER_KEY])
                    if strip[LAYER_KEY] in order else len(order))
    wrong = [(strip, obj.gp2m.channel + index) for index, strip in enumerate(strips)
             if strip.channel != obj.gp2m.channel + index]
    for strip, channel in wrong:
        # Setting .channel shuffles a strip that would overlap another one: the
        # strip is created again on its channel (temporary overlaps are allowed).
        if strip.sound is not None:
            _new_strip(scene, strip.name, strip.sound.filepath, channel, old=strip,
                       tags={OWNER_KEY: obj.name, LAYER_KEY: strip[LAYER_KEY]})
    if wrong:
        strips = [strip for strip in composition_strips(scene, obj)
                  if strip.get(LAYER_KEY) is not None]
    for strip in strips:
        if strip.content_start != target:
            strip.content_start = target
    previous = st.get("muted")
    st["muted"] = mute
    if previous != mute and (previous is not None or mute):
        for strip in strips:
            if strip.mute != mute:
                strip.mute = mute


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
            "low": settings.low_note,
            "high": settings.low_note + settings.octaves * 12,
            "length": result.duration or settings.length}


def regenerate(obj, scene=None, force=False, only_active=False):
    """Render the composition and update its sound strip(s).

    Writes nothing when the sound did not change, so it is safe to call from
    depsgraph handlers without creating update loops. ``only_active``: render
    only the active layer when the others can keep their sound (with
    'Un canale per livello'; otherwise, or when not possible, everything).
    """
    scene = scene or scene_of(obj)
    s = obj.gp2m
    if not s.is_composition:
        return None
    props.ensure_layer_settings(obj.data)
    began = time.perf_counter()
    per_layer = s.layer_channels
    result = reads = None
    partial = False
    if only_active and per_layer and not force:
        result, reads = render_active_layer(obj, scene)
        partial = result is not None
    if result is None:
        result, reads = render_composition(obj, scene, stems=per_layer)
    st = state(obj)
    key = (result.key, per_layer)
    if per_layer:
        strips = layer_strips(scene, obj)
        paths = st.get("layer_paths") or {}
        files_ok = (set(strips) == {name for name, _audio in result.stems}
                    and all(_strip_file_ok(strip) and _same_file(strip, paths.get(name))
                            for name, strip in strips.items())
                    and len(composition_strips(scene, obj)) == len(strips))
    else:
        strip = find_strip(scene, obj)
        files_ok = (_strip_file_ok(strip) and strip.get(LAYER_KEY) is None
                    and _same_file(strip, st.get("path"))
                    and len(composition_strips(scene, obj)) == 1)
    if force or st.get("key") != key or not files_ok:
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
        _keep_layers(obj, scene, result)
    else:
        st["layers"] = None
    arrange(scene)
    st["stats"] = {
        "notes": len(result.notes),
        "voices": result.voice_count,
        "seconds": time.perf_counter() - began,
        "multi_keyframes": [] if s.use_sections else [
            layer.name for layer in reader.audible_layers(obj.data) if len(layer.frames) > 1],
        "sections": len(result.sections),
        "skipped": result.errors,
        "layers": len(result.stems),
        "only_active": partial,
    }
    st["error"] = None
    return result


def regenerate_safe(obj, scene=None, force=False, only_active=False):
    try:
        return regenerate(obj, scene, force, only_active)
    except Exception as error:
        traceback.print_exc()
        state(obj)["error"] = f"{type(error).__name__}: {error}"
        return None
