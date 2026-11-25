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
from bpy.app.handlers import persistent

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

# The overlay is redrawn at every frame of the playback, by every Timeline and
# Dope Sheet. Collecting the sounds (one ``os.stat`` per strip) and rebuilding
# the GPU batches each time is wasted work: the sounds are collected again only
# when something changed (``_version``), and the batches only when the view or
# the settings changed too.
_version = [0]
_collected = {}  # (version, scene, settings) -> collect() result
_batches = {}  # region pointer -> (key, [(primitive, batch, rgba, line width)])
_shaders = {}
MIN_WIDTH = 16  # pixels: narrower regions (a Timeline squeezed sideways) draw nothing
MIN_HEIGHT = 12  # pixels: a Timeline collapsed to its header has no room for a wave
_CACHE_SIZE = 16


def invalidate(*_args):
    """Something that the overlay shows may have changed: collect it again."""
    _version[0] += 1
    _collected.clear()


def wave_band(height, fraction):
    """``(y0, y1)`` of the overlay in a region ``height`` pixels tall, or None
    when the region is too short to show anything (collapsed Timeline).

    The band leaves room for the frame numbers at the top of tall regions and
    always stays inside the region, also when the Timeline is only a few rows
    high."""
    if height < MIN_HEIGHT:
        return None
    margin = 32.0 if height >= 80 else height * 0.25
    y0 = min(6.0, height * 0.1)
    usable = max(height - margin - y0, 2.0)
    return y0, y0 + max(usable * fraction, min(8.0, usable))


def _settings_key(settings):
    composition = settings.composition.name_full if settings.composition else ""
    return (settings.source, composition, settings.channel, settings.wave_style,
            tuple(settings.audio_color), tuple(settings.wave_color), settings.show_notes,
            settings.show_optical, round(settings.height, 4), round(settings.opacity, 4))


def _collect_cached(context, scene, settings, skey):
    active = getattr(context, "active_object", None)
    key = (_version[0], scene.as_pointer(), skey,
           active.name_full if active is not None and settings.source == "ACTIVE" else "")
    found = _collected.get(key)
    if found is None:
        if len(_collected) > _CACHE_SIZE:
            _collected.clear()
        found = _collected[key] = collect(context, settings)
    return found


def _shader(name):
    import gpu
    shader = _shaders.get(name)
    if shader is None:
        shader = _shaders[name] = gpu.shader.from_builtin(name)
    return shader


def _build(context, scene, settings, skey, region, view):
    """Batches to draw: ``[(primitive, batch, rgba, line width)]``, primitive
    "TRIS" or "LINES"."""
    from gpu_extras.batch import batch_for_shader
    audio, composed, items = _collect_cached(context, scene, settings, skey)
    if not audio and not composed and not items:
        return []
    fps, x0, ppf, frame_min, frame_max, y0, y1 = view
    alpha = settings.opacity
    fill = _shader("UNIFORM_COLOR")
    poly = _shader("POLYLINE_UNIFORM_COLOR")
    out = []

    def to_x(frames):
        return x0 + np.asarray(frames) * ppf

    def add(primitive, vertices, rgba, width=1.0):
        if not len(vertices):
            return
        shader = fill if primitive == "TRIS" else poly
        out.append((primitive, batch_for_shader(shader, primitive, {"pos": vertices}),
                    rgba, width))

    bins = max(1.0, min(4.0, ppf))
    for segments, color in ((audio, settings.audio_color), (composed, settings.wave_color)):
        if not segments:
            continue
        frames, amplitude = build_wave(segments, frame_min, frame_max, fps, bins_per_frame=bins)
        for primitive, vertices, weight in wave_geometry(
                to_x(frames), amplitude, y0, y1, settings.wave_style):
            add(primitive, vertices, (*color, 0.35 * alpha * weight))

    for data, start, _end in items:
        tris, lines = note_geometry(data, start, fps, to_x, region.width, y0, y1,
                                    settings.show_notes, settings.show_optical)
        for color, vertices in tris.items():
            add("TRIS", vertices, (*color, alpha))
        for color, vertices in lines.items():
            add("LINES", vertices, (*color, alpha), 2.0)
    return out


def _draw():
    draw_overlay(bpy.context)


def draw_overlay(context):
    """Draw handler body. Returns what was done, for the tests: None (nothing
    to draw: no region, a region squeezed to a thin bar, overlay off...) or the
    number of batches drawn."""
    try:
        scene = context.scene
        if scene is None:
            return
        settings = getattr(scene, "gp2m_timeline", None)
        if settings is None or not settings.enabled:
            return
        region = context.region
        if region is None or region.type != "WINDOW" or region.view2d is None:
            return
        width, height = region.width, region.height
        if width < MIN_WIDTH:
            return
        band = wave_band(height, settings.height)
        if band is None:
            return  # collapsed to a thin bar: nothing would be visible
        y0, y1 = band

        fps = scene.render.fps / scene.render.fps_base
        view2d = region.view2d
        x0 = view2d.view_to_region(0.0, 0.0, clip=False)[0]
        x100 = view2d.view_to_region(100.0, 0.0, clip=False)[0]
        ppf = (x100 - x0) / 100.0
        if ppf <= 0 or fps <= 0:
            return
        frame_min = view2d.region_to_view(0, 0)[0]
        frame_max = view2d.region_to_view(width, 0)[0]
        if frame_max <= frame_min:
            return

        skey = _settings_key(settings)
        view = (fps, x0, ppf, frame_min, frame_max, y0, y1)
        key = (_version[0], scene.as_pointer(), skey, width, height,
               round(x0, 2), round(ppf, 6))
        pointer = region.as_pointer()
        cached = _batches.get(pointer)
        if cached is None or cached[0] != key:
            if len(_batches) > _CACHE_SIZE:
                _batches.clear()
            cached = _batches[pointer] = (key, _build(context, scene, settings, skey,
                                                      region, view))
        draws = cached[1]
        if not draws:
            return 0

        import gpu
        gpu.state.blend_set("ALPHA")
        try:
            viewport = (float(width), float(height))
            for primitive, batch, rgba, line_width in draws:
                if primitive == "TRIS":
                    shader = _shader("UNIFORM_COLOR")
                else:  # wide lines also on Vulkan and Metal, where line_width_set is ignored
                    shader = _shader("POLYLINE_UNIFORM_COLOR")
                    shader.uniform_float("viewportSize", viewport)
                    shader.uniform_float("lineWidth", line_width)
                shader.uniform_float("color", rgba)
                batch.draw(shader)
        finally:
            gpu.state.blend_set("NONE")
        return len(draws)
    except Exception as error:  # never break Blender's drawing
        if not _reported[0]:
            _reported[0] = True
            print(f"[Doodle Music] timeline draw failed: {error!r}")


def tag_redraw():
    """Collect the sounds again and redraw every Timeline / Dope Sheet (if any)."""
    invalidate()
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None:
        return
    for window in wm.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
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


@persistent
def _on_change(*_args):
    invalidate()


_HANDLERS = (
    bpy.app.handlers.depsgraph_update_post,  # strips moved, muted, sounds loaded...
    bpy.app.handlers.load_post,
    bpy.app.handlers.undo_post,
    bpy.app.handlers.redo_post,
)


def _clear_caches():
    invalidate()
    _batches.clear()
    _shaders.clear()


def register():
    if not _handles:
        _handles.append(bpy.types.SpaceDopeSheetEditor.draw_handler_add(
            _draw, (), "WINDOW", "POST_PIXEL"))
    for handler_list in _HANDLERS:
        if _on_change not in handler_list:
            handler_list.append(_on_change)
    bpy.types.DOPESHEET_HT_header.append(draw_header_button)


def unregister():
    bpy.types.DOPESHEET_HT_header.remove(draw_header_button)
    for handler_list in _HANDLERS:
        if _on_change in handler_list:
            handler_list.remove(_on_change)
    while _handles:
        bpy.types.SpaceDopeSheetEditor.draw_handler_remove(_handles.pop(), "WINDOW")
    _clear_caches()
