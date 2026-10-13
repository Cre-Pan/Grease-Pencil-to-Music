# SPDX-License-Identifier: GPL-3.0-or-later
"""Automatic updates: any change to the strokes (Draw, Edit, Sculpt mode,
materials, layers, undo) regenerates the sound after a short pause."""

import time

import bpy
from bpy.app.handlers import persistent

from . import engine, prefs

_dirty = set()
_last_change = [0.0]
_stack_counts = {}  # composition name -> number of modifiers + shader effects
_popup_queue = []
_cleanup_needed = [False]


def compositions():
    return [obj for obj in bpy.data.objects
            if obj.type == "GREASEPENCIL" and obj.gp2m.is_composition and obj.users_scene]


def _ensure_timer():
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=prefs.get_prefs().debounce)


def mark_dirty(obj):
    if obj is None or not obj.gp2m.is_composition or not obj.gp2m.auto_update:
        return
    _dirty.add(obj.name)
    _last_change[0] = time.monotonic()
    _ensure_timer()


def mark_data_dirty(gp_data):
    for obj in compositions():
        if obj.data == gp_data:
            mark_dirty(obj)


def mark_material_dirty(material):
    for obj in compositions():
        if any(slot.material == material for slot in obj.material_slots):
            mark_dirty(obj)


def mark_all_dirty():
    for obj in compositions():
        mark_dirty(obj)


def flush():
    """Regenerate every pending composition now."""
    names = list(_dirty)
    _dirty.clear()
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is not None and obj.gp2m.is_composition:
            engine.regenerate_safe(obj)


def _tick():
    wait = prefs.get_prefs().debounce - (time.monotonic() - _last_change[0])
    if wait > 0.0:
        return wait
    if _cleanup_needed[0]:
        _cleanup_needed[0] = False
        try:
            engine.cleanup_orphans()
        except Exception as error:
            print(f"[Grease Pencil to Music] cleanup failed: {error!r}")
        # A renamed composition needs a strip under its new name.
        for obj in compositions():
            if engine.find_strip(engine.scene_of(obj), obj) is None:
                _dirty.add(obj.name)
    flush()
    _show_popups()
    return None


def _check_stack(obj):
    count = len(obj.modifiers) + len(getattr(obj, "shader_effects", ()))
    previous = _stack_counts.get(obj.name, 0)
    _stack_counts[obj.name] = count
    if count > previous:
        _popup_queue.append(obj.name)
        _ensure_timer()


def _draw_stack_popup(menu, _context):
    layout = menu.layout
    layout.label(text="Modificatori ed effetti non cambiano ancora il suono:")
    layout.label(text="il suono viene generato dai tratti originali.")


def _show_popups():
    if not _popup_queue:
        return
    _popup_queue.clear()
    wm = bpy.context.window_manager
    if wm is None or not wm.windows:
        return
    try:
        with bpy.context.temp_override(window=wm.windows[0]):
            wm.popup_menu(_draw_stack_popup, title="Grease Pencil to Music", icon="INFO")
    except Exception:
        pass  # the warning is also shown in the N panel


@persistent
def on_depsgraph_update(_scene, depsgraph):
    comps = None
    for update in depsgraph.updates:
        original = getattr(update.id, "original", update.id)
        if isinstance(original, bpy.types.GreasePencil):
            comps = comps if comps is not None else compositions()
            for obj in comps:
                if obj.data == original:
                    mark_dirty(obj)
        elif isinstance(original, bpy.types.Object):
            if original.type == "GREASEPENCIL" and original.gp2m.is_composition:
                _check_stack(original)
                if update.is_updated_geometry or update.is_updated_shading:
                    mark_dirty(original)
        elif isinstance(original, bpy.types.Material):
            mark_material_dirty(original)
        elif isinstance(original, (bpy.types.Scene, bpy.types.Collection)):
            # Objects added, deleted or renamed: check for leftovers.
            if not _cleanup_needed[0]:
                _cleanup_needed[0] = True
                _ensure_timer()


@persistent
def on_load_post(*_args):
    _dirty.clear()
    _stack_counts.clear()
    for obj in compositions():
        _stack_counts[obj.name] = len(obj.modifiers) + len(getattr(obj, "shader_effects", ()))
    # Sound files live in a temporary folder: recreate them for this session,
    # even when automatic updates are off.
    for obj in compositions():
        _dirty.add(obj.name)
    if _dirty:
        _ensure_timer()


@persistent
def on_undo_redo(*_args):
    mark_all_dirty()


_HANDLERS = (
    (bpy.app.handlers.depsgraph_update_post, on_depsgraph_update),
    (bpy.app.handlers.load_post, on_load_post),
    (bpy.app.handlers.undo_post, on_undo_redo),
    (bpy.app.handlers.redo_post, on_undo_redo),
)


def register():
    for handler_list, func in _HANDLERS:
        if func not in handler_list:
            handler_list.append(func)


def unregister():
    for handler_list, func in _HANDLERS:
        if func in handler_list:
            handler_list.remove(func)
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
