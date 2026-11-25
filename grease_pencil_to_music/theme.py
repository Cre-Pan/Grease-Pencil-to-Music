# SPDX-License-Identifier: GPL-3.0-or-later
"""Colors of the board, the playhead and the rig, taken from the Blender theme.

The board reads like Blender's own timing editors: background, grid and text of the
Dope Sheet, the playhead and the out-of-range shade of the animation theme
(*Preferences → Themes → Common → Animation*), the C lines in the selected keyframe
color. The rig handles follow Frame by Plane: light handles with a dark rim that turn
to the Active Object color under the mouse and while dragged.

Grease Pencil materials are in scene linear color while the theme is sRGB, so theme
colors are converted (they match exactly with the *Standard* view transform).
A slow timer notices a theme change and recolors the board materials in place.
"""

import bpy

# Fallbacks: Blender 5.3's default theme.
DEFAULTS = {
    "back": (0.188, 0.188, 0.188),
    "grid": (0.086, 0.086, 0.086),
    "text": (0.651, 0.651, 0.651),
    "text_hi": (1.0, 1.0, 1.0),
    "playhead": (0.278, 0.447, 0.702),
    "scene_range": (0.0, 0.0, 0.0, 0.502),
    "keyframe_selected": (1.0, 0.745, 0.2),
    "object_active": (1.0, 0.627, 0.157),
}

HANDLE_COLOR = (0.96, 0.96, 0.96)  # Frame by Plane's handle white
HANDLE_RIM = (0.0, 0.0, 0.0, 0.45)
GLYPH_COLOR = (0.13, 0.13, 0.14)


def _get(owner, attr, default):
    try:
        value = tuple(getattr(owner, attr))
    except (AttributeError, TypeError, ReferenceError):
        return default
    return value if len(value) >= 3 else default


def colors(context=None):
    """The theme colors used by the add-on, sRGB, with Blender's defaults as fallback."""
    out = dict(DEFAULTS)
    try:
        theme = (context or bpy.context).preferences.themes[0]
    except (AttributeError, IndexError, TypeError):
        return out
    dope = getattr(theme, "dopesheet_editor", None)
    space = getattr(dope, "space", None)
    anim = getattr(getattr(theme, "common", None), "anim", None)
    out["back"] = _get(space, "back", out["back"])
    out["grid"] = _get(dope, "grid", out["grid"])
    out["text"] = _get(space, "text", out["text"])
    out["text_hi"] = _get(space, "text_hi", out["text_hi"])
    out["playhead"] = _get(anim, "playhead", out["playhead"])
    out["scene_range"] = _get(anim, "scene_strip_range", out["scene_range"])
    out["keyframe_selected"] = _get(anim, "keyframe_selected", out["keyframe_selected"])
    out["object_active"] = _get(getattr(theme, "view_3d", None), "object_active",
                                out["object_active"])
    return out


def to_linear(c):
    def one(v):
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return tuple(one(float(v)) for v in c[:3])


def mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a[:3], b[:3]))


def rgba(c, alpha=1.0):
    """Linear RGBA of an sRGB theme color."""
    return (*to_linear(c), alpha)


def board_palette(context=None):
    """name: (stroke RGBA or None, fill RGBA or None) of the board materials, linear."""
    t = colors(context)
    back, grid, text = t["back"], t["grid"], t["text"]
    shade = t["scene_range"]
    return {
        "GP2M Sfondo": (None, rgba(back)),
        "GP2M Banda tasti neri": (None, rgba(mix(back, grid, 0.55))),
        "GP2M Linea Do": (rgba(t["keyframe_selected"], 0.9), None),
        "GP2M Linea nota": (rgba(mix(back, grid, 0.8)), None),
        "GP2M Linea secondo": (rgba(mix(back, text, 0.42)), None),
        "GP2M Linea battito": (rgba(mix(back, text, 0.16)), None),
        "GP2M Tasto bianco": (rgba(mix(text, back, 0.35)), rgba(mix(text, t["text_hi"], 0.7))),
        "GP2M Tasto nero": (None, rgba(mix(grid, (0.0, 0.0, 0.0), 0.4))),
        "GP2M Etichetta tasti": (rgba(mix(back, text, 0.55)), None),
        "GP2M Etichetta tempo": (rgba(text), None),
        "GP2M Testina": (rgba(t["playhead"]), None),
        "GP2M Fuori anteprima": (None, rgba(shade, max(0.35, min(0.8, shade[3] + 0.12))
                                            if len(shade) > 3 else 0.62)),
    }


def handle_colors(context=None):
    """sRGB colors of the rig gizmos (gizmos draw in display space)."""
    t = colors(context)
    accent = t["object_active"][:3]
    return {
        # "Off" until the mouse comes: a muted grey, half way to the theme background.
        "idle": mix(HANDLE_COLOR, t["back"], 0.45),
        "rim_idle": (0.0, 0.0, 0.0, 0.3),
        "glyph_idle": mix(GLYPH_COLOR, t["back"], 0.35),
        "hover": mix(HANDLE_COLOR, accent, 0.7),
        "active": accent,
        "rim": HANDLE_RIM,
        "glyph": GLYPH_COLOR,
        "playhead": t["playhead"][:3],
        "text": t["text_hi"][:3],
    }


# --- Following the theme ----------------------------------------------------------------

_signature = [None]
POLL = 1.0  # seconds


def signature(context=None):
    return tuple(round(v, 4) for c in colors(context).values() for v in c)


def apply_to_materials(force=False):
    """Recolor the board materials if the theme changed. True when something changed."""
    sig = signature()
    if sig == _signature[0] and not force:
        return False
    _signature[0] = sig
    from . import board
    changed = False
    for name, (stroke, fill) in board_palette().items():
        material = bpy.data.materials.get(name)
        if material is None or material.grease_pencil is None:
            continue
        style = material.grease_pencil
        for attr, value in (("color", stroke), ("fill_color", fill)):
            if value is None:
                continue
            if any(abs(a - b) > 1e-5 for a, b in zip(getattr(style, attr), value)):
                setattr(style, attr, value)
                changed = True
    if changed:
        board.tag_redraw_views()
    return changed


def _tick():
    try:
        apply_to_materials()
    except Exception as error:  # never stop the timer
        print(f"[Doodle Music] theme colors failed: {error!r}")
    return POLL


def register():
    _signature[0] = None
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=POLL, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
