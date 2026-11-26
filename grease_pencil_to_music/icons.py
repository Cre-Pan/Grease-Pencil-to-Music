# SPDX-License-Identifier: GPL-3.0-or-later
"""The add-on's own icons (``icons/*.png``, drawn by tools/build_icons.py), loaded with
``bpy.utils.previews``: Solo, the two kinds of composition and the instruments.

Loaded first when the add-on is enabled, so the instrument list (an EnumProperty) can
show them too.
"""

import os

from . import families

_previews = None


def icon(name):
    """``icon_value`` of an add-on icon (``icons/<name>.png``), 0 if missing."""
    if _previews is None or name not in _previews:
        return 0
    return _previews[name].icon_id


def instrument_icon(ident):
    """``(icon, icon_value)`` for an instrument: one of the two is set, the other is
    empty (Blender's own icon for Campione / Libreria, ours for the rest)."""
    builtin = families.BUILTIN_ICONS.get(ident)
    if builtin:
        return builtin, 0
    value = icon("inst_" + families.icon_name(ident))
    return ("", value) if value else ("DOT", 0)


def family_icon(family):
    """Like ``instrument_icon``, for a family's menu entry."""
    if not family.icon:
        return "FILE_SOUND", 0
    value = icon("inst_" + family.icon)
    return ("", value) if value else ("SOUND", 0)


def composition_icon(obj=None, beat=False):
    """``icon=`` / ``icon_value=`` of a composition: our piano roll (Musicale) or step
    grid (Ritmica); Blender's Grease Pencil icon if they are missing."""
    if obj is not None:
        beat = getattr(obj.gp2m, "kind", "NOTES") == "BEAT"
    return icon_kwargs("OUTLINER_OB_GREASEPENCIL", icon("comp_beat" if beat else "comp_notes"))


def icon_kwargs(icon_name, value):
    """``icon=`` or ``icon_value=`` for a layout call."""
    return {"icon_value": value} if value else {"icon": icon_name or "NONE"}


def load():
    global _previews
    import bpy.utils.previews
    if _previews is not None:
        return
    _previews = bpy.utils.previews.new()
    folder = os.path.join(os.path.dirname(__file__), "icons")
    names = ["solo_on", "solo_off", "comp_notes", "comp_beat"]
    names += ["inst_" + n for n in families.icon_names()]
    for name in names:
        path = os.path.join(folder, f"{name}.png")
        if os.path.isfile(path):
            _previews.load(name, path, "IMAGE")


def free():
    global _previews
    if _previews is not None:
        import bpy.utils.previews
        bpy.utils.previews.remove(_previews)
        _previews = None
