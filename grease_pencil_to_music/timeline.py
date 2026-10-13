# SPDX-License-Identifier: GPL-3.0-or-later
"""Waveform and note blocks drawn in the Timeline / Dope Sheet.

Approach inspired by "Timeline Audio Visualizer" (OwOpq, GPL-3.0): a
``POST_PIXEL`` draw handler on the Dope Sheet window region that converts
frames to pixels through ``region.view2d``.
"""

import bpy
import numpy as np

_handles = []
_reported = [False]


def build_geometry(data, frame_start, fps, x_of_frame0, pixels_per_frame, width, y0, y1,
                   show_wave=True, show_notes=True):
    """Vertices to draw, in region pixels.

    Returns ``(wave_lines, note_tris)`` where ``wave_lines`` is an (N, 2)
    array of line endpoints and ``note_tris`` maps an RGB color to an (M, 2)
    array of triangle vertices.
    """
    wave = np.zeros((0, 2), dtype=np.float32)
    notes = {}
    if y1 <= y0 or pixels_per_frame <= 0:
        return wave, notes

    def to_x(seconds):
        return x_of_frame0 + (frame_start + np.asarray(seconds) * fps) * pixels_per_frame

    if show_wave and len(data["peaks"]):
        peaks = data["peaks"]
        x = to_x(np.arange(len(peaks)) / data["rate"])
        visible = (x >= -2) & (x <= width + 2)
        x, peaks = x[visible], peaks[visible]
        if len(x):
            # At most ~2 lines per pixel: keep the loudest peak of each bucket.
            bucket = np.floor(x * 2).astype(np.int64)
            order = np.lexsort((-peaks, bucket))
            first = np.ones(len(order), dtype=bool)
            first[1:] = bucket[order][1:] != bucket[order][:-1]
            keep = order[first]
            x, peaks = x[keep], peaks[keep]
            center = (y0 + y1) / 2.0
            half = (y1 - y0) / 2.0 * peaks
            wave = np.empty((len(x) * 2, 2), dtype=np.float32)
            wave[0::2, 0] = x
            wave[1::2, 0] = x
            wave[0::2, 1] = center - half
            wave[1::2, 1] = center + half

    if show_notes and data["notes"]:
        span = max(data["high"] - data["low"] + 1, 1)
        row = (y1 - y0) / span
        thickness = max(row, 2.0)
        for start, end, pitch, color in data["notes"]:
            xa, xb = float(to_x(start)), float(to_x(end))
            if xb < 0 or xa > width:
                continue
            xb = max(xb, xa + 2.0)
            ya = y0 + (pitch - data["low"]) * row
            yb = ya + thickness
            key = tuple(round(c, 3) for c in color[:3])
            notes.setdefault(key, []).extend(
                [(xa, ya), (xb, ya), (xb, yb), (xa, ya), (xb, yb), (xa, yb)])
        notes = {k: np.asarray(v, dtype=np.float32) for k, v in notes.items()}
    return wave, notes


def _compositions(context):
    from . import engine
    from .operators import active_composition
    active = active_composition(context)
    if active is not None:
        candidates = [active]
    else:
        candidates = [obj for obj in context.scene.objects
                      if obj.type == "GREASEPENCIL" and obj.gp2m.is_composition]
    return [(obj, engine.state(obj).get("timeline")) for obj in candidates
            if engine.state(obj).get("timeline") and not obj.gp2m.mute]


def _draw():
    context = bpy.context
    try:
        from . import prefs
        mode = prefs.get_prefs().timeline_display
        if mode == "NONE" or context.scene is None:
            return
        region = context.region
        if region is None or region.type != "WINDOW" or region.view2d is None:
            return
        items = _compositions(context)
        if not items:
            return
        import gpu
        from gpu_extras.batch import batch_for_shader

        scene = context.scene
        fps = scene.render.fps / scene.render.fps_base
        x0 = region.view2d.view_to_region(0.0, 0.0, clip=False)[0]
        x100 = region.view2d.view_to_region(100.0, 0.0, clip=False)[0]
        ppf = (x100 - x0) / 100.0
        y0, y1 = 6.0, max(region.height - 26.0, 12.0)
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        gpu.state.blend_set("ALPHA")
        for _obj, data in items:
            wave, notes = build_geometry(data, scene.frame_start, fps, x0, ppf, region.width,
                                         y0, y1, mode in ("BOTH", "WAVE"),
                                         mode in ("BOTH", "NOTES"))
            if len(wave):
                batch = batch_for_shader(shader, "LINES", {"pos": wave})
                shader.uniform_float("color", (0.85, 0.9, 1.0, 0.28))
                batch.draw(shader)
            for color, tris in notes.items():
                batch = batch_for_shader(shader, "TRIS", {"pos": tris})
                shader.uniform_float("color", (*color, 0.8))
                batch.draw(shader)
        gpu.state.blend_set("NONE")
    except Exception as error:  # never break Blender's drawing
        if not _reported[0]:
            _reported[0] = True
            print(f"[Grease Pencil to Music] timeline draw failed: {error!r}")


def tag_redraw():
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None:
        return
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == "DOPESHEET_EDITOR":
                area.tag_redraw()


def register():
    if not _handles:
        _handles.append(bpy.types.SpaceDopeSheetEditor.draw_handler_add(
            _draw, (), "WINDOW", "POST_PIXEL"))


def unregister():
    while _handles:
        bpy.types.SpaceDopeSheetEditor.draw_handler_remove(_handles.pop(), "WINDOW")
