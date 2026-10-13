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
    if settings is None:
        return mixer.LayerFx()
    return mixer.LayerFx(
        delay_mix=settings.delay_mix,
        delay_beats=settings.delay_beats,
        delay_feedback=settings.delay_feedback,
        reverb_mix=settings.reverb_mix,
        reverb_size=settings.reverb_size,
        lofi=settings.lofi,
    )


MAX_SECTIONS = 24


def section_frames(obj, scene):
    """Scene frames where a keyframe section starts (the first is the scene start)."""
    start = scene.frame_start
    frames = {start}
    for layer in board.user_layers(obj.data):
        for frame in layer.frames:
            frames.add(max(int(frame.frame_number), start))
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
            gain=read.opacity,
            fx=_layer_fx(settings),
            canon_voices=settings.canon_voices if settings else 1,
            canon_delay=settings.canon_delay * beat if settings else 0.0,
            canon_transpose=settings.canon_transpose if settings else 0,
        ))
    return layers


def render_composition(obj, scene):
    """Render the loop drawn at the scene start, or every keyframe section."""
    s = obj.gp2m
    spec, mapping, rate = board_spec(s), prefs.get_mapping(), int(s.sample_rate)
    frames = section_frames(obj, scene) if s.use_sections else [scene.frame_start]
    if len(frames) == 1:
        reads = reader.read_composition(obj, frames[0], use_modifiers=s.use_modifiers)
        result = mixer.render(_layer_inputs(obj, reads), spec, mapping, rate, loop=s.loop,
                              master_volume=s.master_volume)
        result.duration = s.length
        return result, reads
    times = [(frame - scene.frame_start) / _fps(scene) for frame in frames]
    parts, first_reads = [], None
    for i, frame in enumerate(frames):
        reads = reader.read_composition(obj, frame, use_modifiers=s.use_modifiers)
        first_reads = reads if first_reads is None else first_reads
        end = times[i + 1] if i + 1 < len(times) else times[i] + s.length
        parts.append((times[i], end, mixer.render(
            _layer_inputs(obj, reads), spec, mapping, rate, loop=False,
            master_volume=s.master_volume)))
    return mixer.sequence(parts, s.length, rate, loop=s.loop), first_reads


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
    current = bpy.context.scene
    users = obj.users_scene
    if current is not None and (not users or current in users):
        return current
    return users[0]


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
            owner = bpy.data.objects.get(strip.name[len(STRIP_PREFIX):])
            if owner is None or not owner.gp2m.is_composition or scene not in owner.users_scene:
                sound = strip.sound
                editor.strips.remove(strip)
                if sound is not None and sound.users == 0:
                    bpy.data.sounds.remove(sound)
    for obj in list(bpy.data.objects):
        if obj.get(ROLE) in ("board", "label", "playhead") and obj.parent is None:
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data is not None and data.users == 0:
                if isinstance(data, bpy.types.GreasePencil):
                    bpy.data.grease_pencils.remove(data)
                elif isinstance(data, bpy.types.Curve):
                    bpy.data.curves.remove(data)


def strip_name(obj):
    return STRIP_PREFIX + obj.name


def find_strip(scene, obj):
    editor = scene.sequence_editor
    if editor is None:
        return None
    return editor.strips.get(strip_name(obj))


def _free_channel(editor, exclude=None):
    """Lowest channel without strips (the composition's own strip excluded)."""
    used = {strip.channel for strip in editor.strips_all if strip.name != exclude}
    channel = 1
    while channel in used:
        channel += 1
    return channel


def _place_strip(scene, obj, path, frames):
    """Point the composition's strip to a new sound file.

    When the length is unchanged only the file of the sound datablock is
    swapped (no strip is removed, so playback is not disturbed); otherwise the
    strip is recreated with the new length.
    """
    editor = scene.sequence_editor or scene.sequence_editor_create()
    old = editor.strips.get(strip_name(obj))
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
    old_sound = old.sound if old is not None else None
    if old is not None:
        editor.strips.remove(old)
    if old_sound is not None and old_sound.users == 0:
        bpy.data.sounds.remove(old_sound)
    strip = editor.strips.new_sound(strip_name(obj), path, channel, scene.frame_start)
    strip.sound.name = strip_name(obj)
    strip.sound.use_memory_cache = True  # play from RAM: smoother playback
    return strip


def _strip_file_ok(strip):
    if strip is None or strip.sound is None:
        return False
    return os.path.exists(bpy.path.abspath(strip.sound.filepath))


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


def resolve_channels(scene):
    """Duplicated compositions copy the channel: give the copies a free one."""
    seen = set()
    for obj in sorted(scene_compositions(scene), key=lambda o: o.name):
        if obj.gp2m.channel and obj.gp2m.channel in seen:
            editor = scene.sequence_editor
            obj.gp2m.channel = _free_channel(editor, strip_name(obj)) if editor else 0
            while obj.gp2m.channel in seen:
                obj.gp2m.channel += 1
        seen.add(obj.gp2m.channel)


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

    TOGETHER: all start at the scene start. SOLO: only the active composition
    is heard. SEQUENCE: one after another, by "order" then name. The scene
    range follows (so playback loops on what you hear). Writes only changes.
    """
    comps = scene_compositions(scene)
    if not comps:
        return
    play = scene.gp2m_play
    fps = _fps(scene)
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
        strip = find_strip(scene, obj)
        if strip is None:
            continue
        target = scene.frame_start + start_offset
        if strip.content_start != target:
            strip.content_start = target
        if obj.gp2m.channel == 0:
            obj.gp2m.channel = strip.channel  # show the automatic choice
        elif strip.channel != obj.gp2m.channel:
            strip.channel = obj.gp2m.channel
        mute = obj.gp2m.mute or (solo is not None and obj != solo)
        if strip.mute != mute:
            strip.mute = mute

    if play.fit_range:
        if play.mode == "SEQUENCE":
            total = offset
        elif solo is not None:
            total = lengths[solo.name]
        else:
            total = max(lengths.values())
        end = scene.frame_start + total - 1
        if scene.frame_end != end:
            scene.frame_end = end


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
    mono = np.abs(audio[:usable]).max(axis=1) if usable else np.zeros(0)
    peaks = mono.reshape(-1, hop).max(axis=1) if usable else np.zeros(0)
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


def regenerate(obj, scene=None, force=False):
    """Render the composition and update its sound strip.

    Writes nothing when the sound did not change, so it is safe to call from
    depsgraph handlers without creating update loops.
    """
    scene = scene or scene_of(obj)
    s = obj.gp2m
    if not s.is_composition:
        return None
    props.ensure_layer_settings(obj.data)
    began = time.perf_counter()
    result, reads = render_composition(obj, scene)
    st = state(obj)
    strip = find_strip(scene, obj)
    if force or st.get("key") != result.key or not _strip_file_ok(strip):
        path = os.path.join(cache_dir(), f"{_safe(obj.name)}_{time.time_ns()}.wav")
        write_audio(path, result.audio, result.sample_rate, "WAV")
        fps = scene.render.fps / scene.render.fps_base
        frames = max(1, int(round(len(result.audio) / result.sample_rate * fps)))
        strip = _place_strip(scene, obj, path, frames)
        old_path = st.get("path")
        if old_path and old_path != path:
            try:
                os.remove(old_path)
            except OSError:
                pass  # still in use (Windows) or already gone
        st["key"] = result.key
        st["path"] = path
        st["sections"] = result.sections
        st["duration"] = result.duration or s.length
        st["timeline"] = timeline_data(result, s)
        from . import timeline
        timeline.tag_redraw()
    arrange(scene)
    st["stats"] = {
        "notes": len(result.notes),
        "voices": result.voice_count,
        "seconds": time.perf_counter() - began,
        "multi_keyframes": [] if s.use_sections else [r.name for r in reads
                                                       if r.keyframes > 1],
        "sections": len(result.sections),
    }
    st["error"] = None
    return result


def regenerate_safe(obj, scene=None, force=False):
    try:
        return regenerate(obj, scene, force)
    except Exception as error:
        traceback.print_exc()
        state(obj)["error"] = f"{type(error).__name__}: {error}"
        return None
