# SPDX-License-Identifier: GPL-3.0-or-later
"""Sound drawn in the Timeline / Dope Sheet, with a header button (music note,
next to Overlays) that chooses what to show.

Sources: everything (every sound of the Sequencer, on any channel, the
Speakers and the compositions with their notes), the active composition, all
compositions, one composition, the mix of the Video Sequencer, one Sequencer
channel, Speaker objects. Plain audio and compositions get their own colors. Layers:
waveform (peaks, filled, outline, RMS), note blocks (MIDI) and pitch curves
of optical strokes.

Approach inspired by "Timeline Audio Visualizer" (OwOpq, GPL-3.0): a
``POST_PIXEL`` draw handler on the Dope Sheet window region that converts
frames to pixels through ``region.view2d``.
"""

import os

import bpy
import numpy as np

_handles = []
_reported = [False]
_file_cache = {}  # (path, mtime, size) -> (peaks, rate), or None if unreadable
PEAK_RATE = 100  # peaks per second for sound files


# --- Pure geometry (unit tested) ---------------------------------------------------

def build_wave(segments, frame_min, frame_max, fps, bins_per_frame=4):
    """Sum the amplitude of several sounds on a common frame grid.

    ``segments``: dicts with ``start`` (timeline frame of the sound start),
    ``peaks`` (amplitudes 0..1), ``rate`` (peaks per second), ``frame_from``,
    ``frame_to`` (visible part) and ``gain``. Returns ``(frames, amplitude)``.
    """
    if frame_max <= frame_min or not segments:
        return np.zeros(0), np.zeros(0)
    count = int(min(max((frame_max - frame_min) * bins_per_frame, 2), 20000))
    frames = np.linspace(frame_min, frame_max, count)
    total = np.zeros(count)
    for seg in segments:
        peaks = seg["peaks"]
        if not len(peaks):
            continue
        t = (frames - seg["start"]) / fps * seg["rate"]
        inside = (frames >= seg["frame_from"]) & (frames <= seg["frame_to"]) & (t >= 0) & (
            t <= len(peaks) - 1)
        if np.any(inside):
            total[inside] += np.interp(t[inside], np.arange(len(peaks)), peaks) * seg.get(
                "gain", 1.0)
    return frames, np.clip(total, 0.0, 1.0)


def wave_geometry(x, amplitude, y0, y1, style):
    """Return ``(primitive, vertices)`` lists to draw the waveform."""
    if len(x) < 2 or style == "NONE":
        return []
    center = (y0 + y1) / 2.0
    if style == "RMS":
        window = 9
        squared = np.convolve(amplitude ** 2, np.ones(window) / window, mode="same")
        amplitude = np.sqrt(squared)
    half = (y1 - y0) / 2.0 * amplitude
    top = np.stack((x, center + half), axis=1)
    bottom = np.stack((x, center - half), axis=1)
    if style == "PEAKS":
        lines = np.empty((len(x) * 2, 2))
        lines[0::2], lines[1::2] = bottom, top
        return [("LINES", lines.astype(np.float32), 1.0)]
    quads = []
    if style in ("FILLED", "RMS"):
        a, b, c, d = bottom[:-1], top[:-1], top[1:], bottom[1:]
        tris = np.stack((a, b, c, a, c, d), axis=1).reshape(-1, 2)
        quads.append(("TRIS", tris.astype(np.float32), 0.45 if style == "RMS" else 1.0))
    if style in ("OUTLINE", "RMS"):
        def segments(poly):
            out = np.empty(((len(poly) - 1) * 2, 2))
            out[0::2], out[1::2] = poly[:-1], poly[1:]
            return out
        lines = np.concatenate((segments(top), segments(bottom)))
        quads.append(("LINES", lines.astype(np.float32), 1.0))
    return quads


def note_geometry(data, start_frame, fps, to_x, width, y0, y1, show_notes=True,
                  show_curves=True):
    """Note rectangles and pitch curves of one composition, grouped by color."""
    tris, lines = {}, {}
    span = max(data["high"] - data["low"] + 1, 1)
    row = (y1 - y0) / span
    thickness = max(row, 2.0)

    def x_of(seconds):
        return to_x(start_frame + np.asarray(seconds) * fps)

    if show_notes:
        for start, end, pitch, color in data["notes"]:
            xa, xb = float(x_of(start)), float(x_of(end))
            if xb < 0 or xa > width:
                continue
            xb = max(xb, xa + 2.0)
            ya = y0 + (pitch - data["low"]) * row
            yb = ya + thickness
            key = tuple(round(c, 3) for c in color[:3])
            tris.setdefault(key, []).extend(
                [(xa, ya), (xb, ya), (xb, yb), (xa, ya), (xb, yb), (xa, yb)])
    if show_curves:
        rate = data.get("curve_rate", 50.0)
        for start, pitch, color in data.get("curves", ()):
            if len(pitch) < 2:
                continue
            xs = x_of(start + np.arange(len(pitch)) / rate)
            ys = y0 + (np.asarray(pitch) - data["low"] + 0.5) * row
            poly = np.stack((xs, ys), axis=1)
            seg = np.empty(((len(poly) - 1) * 2, 2))
            seg[0::2], seg[1::2] = poly[:-1], poly[1:]
            key = tuple(round(c, 3) for c in color[:3])
            lines.setdefault(key, []).append(seg)
    tris = {k: np.asarray(v, dtype=np.float32) for k, v in tris.items()}
    lines = {k: np.concatenate(v).astype(np.float32) for k, v in lines.items()}
    return tris, lines


# --- Sources -----------------------------------------------------------------------

def _peaks_of(sound):
    """``(peaks, rate)`` of an ``aud.Sound`` (loudest channel)."""
    rate = int(sound.specs[0])
    data = np.abs(sound.data())
    mono = data.max(axis=1) if data.ndim == 2 else data
    hop = max(1, rate // PEAK_RATE)
    usable = len(mono) // hop * hop
    peaks = mono[:usable].reshape(-1, hop).max(axis=1) if usable else np.zeros(0)
    return peaks.astype(np.float32), PEAK_RATE


def _remember(key, value):
    if len(_file_cache) > 64:
        _file_cache.clear()
    _file_cache[key] = value
    return value


def file_peaks(path):
    """Peaks (0..1, PEAK_RATE per second) of a sound file, cached.

    Unreadable files are cached too, so a broken path is not decoded again
    at every redraw."""
    try:
        stat = os.stat(path)
    except OSError:
        return None
    key = (path, stat.st_mtime, stat.st_size)
    if key in _file_cache:
        return _file_cache[key]
    import aud
    try:
        found = _peaks_of(aud.Sound(path))
    except Exception:
        found = None
    return _remember(key, found)


def sound_peaks(sound):
    """Peaks of a Blender sound datablock: from its file, or from memory when
    it is packed in the .blend (or the file is missing)."""
    if sound is None:
        return None
    if sound.packed_file is None:
        path = bpy.path.abspath(sound.filepath, library=sound.library)
        found = file_peaks(path)
        if found is not None:
            return found
        if os.path.exists(path):
            return None  # the file exists but cannot be decoded
    key = ("packed", sound.name_full,
           sound.packed_file.size if sound.packed_file is not None else 0)
    if key in _file_cache:
        return _file_cache[key]
    found = None
    try:
        if sound.packed_file is not None:
            found = _packed_peaks(sound)
        elif sound.factory is not None:
            found = _peaks_of(sound.factory)
    except Exception:
        found = None
    return _remember(key, found)


def _packed_peaks(sound):
    """aud reads files only: decode the packed bytes from a temporary copy."""
    import tempfile
    import aud
    ext = os.path.splitext(sound.filepath)[1] or ".wav"
    handle, path = tempfile.mkstemp(suffix=ext, prefix="gp2m_peaks_")
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(sound.packed_file.data)
        return _peaks_of(aud.Sound(path))
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _is_composition_strip(strip):
    from .engine import STRIP_PREFIX
    return strip.name.startswith(STRIP_PREFIX)


def _strip_segments(scene, channel=None, skip_compositions=False):
    """Every audible sound strip of the Sequencer (on any channel, or one)."""
    editor = scene.sequence_editor
    if editor is None:
        return []
    segments = []
    for strip in editor.strips_all:
        if strip.type != "SOUND" or strip.mute or strip.sound is None:
            continue
        if channel is not None and strip.channel != channel:
            continue
        if skip_compositions and _is_composition_strip(strip):
            continue
        channel_data = editor.channels[strip.channel] if strip.channel < len(
            editor.channels) else None
        if channel_data is not None and channel_data.mute:
            continue
        found = sound_peaks(strip.sound)
        if found is None:
            continue
        peaks, rate = found
        segments.append({"start": strip.content_start, "peaks": peaks, "rate": rate,
                         "frame_from": strip.left_handle, "frame_to": strip.right_handle,
                         "gain": float(strip.volume)})
    return segments


def _speaker_segments(scene):
    segments = []
    for obj in scene.objects:
        if obj.type != "SPEAKER" or obj.data.muted or obj.animation_data is None:
            continue
        for track in obj.animation_data.nla_tracks:
            if track.mute:
                continue
            for strip in track.strips:
                if strip.type != "SOUND" or strip.mute:
                    continue
                found = sound_peaks(obj.data.sound)
                if found is None:
                    continue
                peaks, rate = found
                segments.append({"start": strip.frame_start, "peaks": peaks, "rate": rate,
                                 "frame_from": strip.frame_start, "frame_to": strip.frame_end,
                                 "gain": float(obj.data.volume)})
    return segments


def _composition_items(context, settings):
    from . import engine
    from .operators import active_composition
    scene = context.scene
    if settings.source == "PICK":
        candidates = [settings.composition] if settings.composition else []
    elif settings.source == "ACTIVE" and active_composition(context) is not None:
        candidates = [active_composition(context)]
    else:
        candidates = engine.scene_compositions(scene)
    items = []
    fps = scene.render.fps / scene.render.fps_base
    for obj in candidates:
        st = engine.state(obj)
        data = st.get("timeline")
        if not data or obj.gp2m.mute:
            continue
        start = scene.frame_start + st.get("offset_frames", 0)
        items.append((data, start, start + data["length"] * fps))
    return items


def _composition_segments(items):
    return [{"start": start, "peaks": data["peaks"], "rate": data["rate"],
             "frame_from": start, "frame_to": end} for data, start, end in items]


def collect(context, settings):
    """``(audio segments, composition segments, composition items)`` for the
    chosen source. Audio is every other sound (Sequencer, Speakers)."""
    scene = context.scene
    source = settings.source
    if source == "EVERYTHING":
        items = _composition_items(context, settings)
        audio = _strip_segments(scene, skip_compositions=True) + _speaker_segments(scene)
        return audio, _composition_segments(items), items
    if source == "VSE_MIX":
        return _strip_segments(scene), [], []
    if source == "VSE_CHANNEL":
        return _strip_segments(scene, settings.channel), [], []
    if source == "SPEAKERS":
        return _speaker_segments(scene), [], []
    items = _composition_items(context, settings)
    return [], _composition_segments(items), items


# --- Drawing -----------------------------------------------------------------------

def _draw():
    context = bpy.context
    try:
        scene = context.scene
        if scene is None:
            return
        settings = scene.gp2m_timeline
        if not settings.enabled:
            return
        region = context.region
        if region is None or region.type != "WINDOW" or region.view2d is None:
            return
        audio, composed, items = collect(context, settings)
        if not audio and not composed and not items:
            return
        import gpu
        from gpu_extras.batch import batch_for_shader

        fps = scene.render.fps / scene.render.fps_base
        view2d = region.view2d
        x0 = view2d.view_to_region(0.0, 0.0, clip=False)[0]
        x100 = view2d.view_to_region(100.0, 0.0, clip=False)[0]
        ppf = (x100 - x0) / 100.0
        if ppf <= 0:
            return
        frame_min = view2d.region_to_view(0, 0)[0]
        frame_max = view2d.region_to_view(region.width, 0)[0]

        def to_x(frames):
            return x0 + np.asarray(frames) * ppf

        y0 = 6.0
        y1 = y0 + max((region.height - 32.0) * settings.height, 8.0)
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        gpu.state.blend_set("ALPHA")
        alpha = settings.opacity

        bins = max(1.0, min(4.0, ppf))
        for segments, color in ((audio, settings.audio_color),
                                (composed, settings.wave_color)):
            if not segments:
                continue
            frames, amplitude = build_wave(segments, frame_min, frame_max, fps,
                                           bins_per_frame=bins)
            for primitive, vertices, weight in wave_geometry(
                    to_x(frames), amplitude, y0, y1, settings.wave_style):
                batch = batch_for_shader(shader, primitive, {"pos": vertices})
                shader.uniform_float("color", (*color, 0.35 * alpha * weight))
                batch.draw(shader)

        for data, start, _end in items:
            tris, lines = note_geometry(data, start, fps, to_x, region.width, y0, y1,
                                        settings.show_notes, settings.show_optical)
            for color, vertices in tris.items():
                batch = batch_for_shader(shader, "TRIS", {"pos": vertices})
                shader.uniform_float("color", (*color, alpha))
                batch.draw(shader)
            if lines:
                gpu.state.line_width_set(2.0)
                for color, vertices in lines.items():
                    batch = batch_for_shader(shader, "LINES", {"pos": vertices})
                    shader.uniform_float("color", (*color, alpha))
                    batch.draw(shader)
                gpu.state.line_width_set(1.0)
        gpu.state.blend_set("NONE")
    except Exception as error:  # never break Blender's drawing
        if not _reported[0]:
            _reported[0] = True
            print(f"[Doodle Music] timeline draw failed: {error!r}")


def tag_redraw():
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None:
        return
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == "DOPESHEET_EDITOR":
                area.tag_redraw()


# --- Header button and popover ----------------------------------------------------------

class GP2M_PT_timeline(bpy.types.Panel):
    bl_space_type = "DOPESHEET_EDITOR"
    bl_region_type = "HEADER"
    bl_label = "Suono nella Timeline"
    bl_ui_units_x = 12

    def draw(self, context):
        settings = context.scene.gp2m_timeline
        layout = self.layout
        layout.label(text="Suono nella Timeline", icon="FILE_SOUND")
        layout.use_property_split = True
        layout.use_property_decorate = False
        col = layout.column()
        col.active = settings.enabled
        col.prop(settings, "source")
        if settings.source == "PICK":
            col.prop(settings, "composition")
        elif settings.source == "VSE_CHANNEL":
            col.prop(settings, "channel")
        col.separator()
        col.prop(settings, "wave_style")
        if settings.source in ("EVERYTHING", "VSE_MIX", "VSE_CHANNEL", "SPEAKERS"):
            col.prop(settings, "audio_color")
        if settings.source not in ("VSE_MIX", "VSE_CHANNEL", "SPEAKERS"):
            col.prop(settings, "wave_color")
        sub = col.column(heading="Mostra")
        sub.active = settings.source in ("EVERYTHING", "ACTIVE", "ALL", "PICK")
        sub.prop(settings, "show_notes")
        sub.prop(settings, "show_optical")
        col.separator()
        col.prop(settings, "height", slider=True)
        col.prop(settings, "opacity", slider=True)


def draw_header_button(self, context):
    scene = context.scene
    if scene is None or not hasattr(scene, "gp2m_timeline"):
        return
    row = self.layout.row(align=True)
    row.prop(scene.gp2m_timeline, "enabled", text="", icon="FILE_SOUND")
    row.popover(panel="GP2M_PT_timeline", text="")


classes = (GP2M_PT_timeline,)


def register():
    if not _handles:
        _handles.append(bpy.types.SpaceDopeSheetEditor.draw_handler_add(
            _draw, (), "WINDOW", "POST_PIXEL"))
    bpy.types.DOPESHEET_HT_header.append(draw_header_button)


def unregister():
    bpy.types.DOPESHEET_HT_header.remove(draw_header_button)
    while _handles:
        bpy.types.SpaceDopeSheetEditor.draw_handler_remove(_handles.pop(), "WINDOW")
