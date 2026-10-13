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

import aud
import bpy
import numpy as np

from . import interpret, midi, mixer, music, prefs, props, reader, synth

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


def render_composition(obj, scene):
    s = obj.gp2m
    reads = reader.read_composition(obj, scene.frame_start, use_modifiers=s.use_modifiers)
    layers = []
    for read in reads:
        settings = props.find_layer_settings(obj.data, read.name)
        layers.append(mixer.LayerInput(
            name=read.name,
            strokes=read.strokes,
            mode=settings.mode if settings else "QUANTIZED",
            fill_mode=settings.fill_mode if settings else "TONAL",
            gain=read.opacity,
            fx=_layer_fx(settings),
        ))
    result = mixer.render(layers, board_spec(s), prefs.get_mapping(), int(s.sample_rate),
                          loop=s.loop, master_volume=s.master_volume)
    return result, reads


# --- Files -------------------------------------------------------------------

AUDIO_FORMATS = {
    "WAV": (aud.CONTAINER_WAV, aud.CODEC_PCM, ".wav"),
    "MP3": (aud.CONTAINER_MP3, aud.CODEC_MP3, ".mp3"),
}


def write_audio(path, audio, sample_rate, fmt="WAV", bitrate_kbps=192):
    container, codec, _ext = AUDIO_FORMATS[fmt]
    data = np.ascontiguousarray(audio, dtype=np.float32)
    if data.ndim != 2 or len(data) == 0:
        data = np.zeros((max(1, len(data)), 2), dtype=np.float32)
    sound = aud.Sound.buffer(data, float(sample_rate))
    sound.write(path, rate=int(sample_rate), channels=aud.CHANNELS_STEREO,
                format=aud.FORMAT_S16, container=container, codec=codec,
                bitrate=int(bitrate_kbps) * 1000)


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


def _free_channel(editor):
    used = [strip.channel for strip in editor.strips_all]
    return (max(used) + 1) if used else 1


def _place_strip(scene, obj, path, frames):
    """Point the composition's strip to a new sound file.

    When the length is unchanged only the file of the sound datablock is
    swapped (no strip is removed, so playback is not disturbed); otherwise the
    strip is recreated with the new length.
    """
    editor = scene.sequence_editor or scene.sequence_editor_create()
    old = editor.strips.get(strip_name(obj))
    if (old is not None and old.sound is not None and old.sound.users == 1
            and old.duration == frames and old.left_handle == scene.frame_start):
        old.sound.filepath = path  # reloads the audio
        return old
    channel = old.channel if old is not None else _free_channel(editor)
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


def _sync_scene_range(scene, settings):
    if not settings.loop:
        return
    fps = scene.render.fps / scene.render.fps_base
    end = scene.frame_start + max(1, int(round(settings.length * fps))) - 1
    if scene.frame_end != end:
        scene.frame_end = end


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
    return {"peaks": (peaks / top).astype(np.float32), "rate": PEAKS_PER_SECOND,
            "notes": notes, "low": settings.low_note,
            "high": settings.low_note + settings.octaves * 12, "length": settings.length}


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
        st["timeline"] = timeline_data(result, s)
        from . import timeline
        timeline.tag_redraw()
    if strip is not None and strip.mute != s.mute:
        strip.mute = s.mute
    _sync_scene_range(scene, s)
    st["stats"] = {
        "notes": len(result.notes),
        "voices": result.voice_count,
        "seconds": time.perf_counter() - began,
        "multi_keyframes": [r.name for r in reads if r.keyframes > 1],
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
