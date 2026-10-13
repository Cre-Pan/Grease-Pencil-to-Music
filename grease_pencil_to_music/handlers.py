# SPDX-License-Identifier: GPL-3.0-or-later
"""Automatic updates: any change to the strokes (Draw, Edit, Sculpt mode,
materials, layers, undo) regenerates the sound after a short pause.

Playback friendly: while playing, only real stroke edits are processed and the
sound file is swapped without touching the strip; Ctrl+Z during playback
resumes the playback if Blender stopped it.
"""

import time

import bpy
from bpy.app.handlers import persistent

from . import board, engine, prefs

_dirty = set()
_last_change = [0.0]
_stack_counts = {}  # composition name -> number of modifiers + shader effects
_popup_queue = []
_cleanup_needed = [False]
_object_signature = [None]
_was_playing = [False]


def compositions():
    return [obj for obj in bpy.data.objects
            if obj.type == "GREASEPENCIL" and obj.gp2m.is_composition and obj.users_scene]


def is_playing():
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None:
        return False
    return any(window.screen is not None and window.screen.is_animation_playing
               for window in wm.windows)


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
            if not board.has_board(obj):  # file from 0.0.1, or board removed
                board.rebuild(obj, engine.scene_of(obj))
            board.ensure_order(obj.data)  # layers added with Blender's own "+"
            engine.regenerate_safe(obj)


def _signature():
    """Changes when objects are added, deleted, renamed or duplicated."""
    return hash(tuple(sorted(bpy.data.objects.keys())))


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
        # Duplicated (Shift+D) or renamed compositions need their own strip.
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
    if count > previous and not obj.gp2m.use_modifiers:
        _popup_queue.append(obj.name)
        _ensure_timer()


def _draw_stack_popup(menu, _context):
    layout = menu.layout
    layout.label(text="Modificatori ed effetti non cambiano il suono:")
    layout.label(text="attiva 'Usa modificatori' nel pannello N → Musica per sentirli.")


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
            # Cheap check first: only look for leftovers when objects changed.
            signature = _signature()
            if signature != _object_signature[0]:
                _object_signature[0] = signature
                _cleanup_needed[0] = True
                _ensure_timer()


@persistent
def on_load_post(*_args):
    _dirty.clear()
    _stack_counts.clear()
    _object_signature[0] = _signature()
    for obj in compositions():
        _stack_counts[obj.name] = len(obj.modifiers) + len(getattr(obj, "shader_effects", ()))
        # Sound files live in a temporary folder: recreate them for this session,
        # even when automatic updates are off.
        _dirty.add(obj.name)
    if _dirty:
        _ensure_timer()


@persistent
def on_undo_pre(*_args):
    _was_playing[0] = is_playing()


def _resume_playback():
    if is_playing():
        return None
    wm = bpy.context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type in ("VIEW_3D", "DOPESHEET_EDITOR", "SEQUENCE_EDITOR"):
                try:
                    with bpy.context.temp_override(window=window, area=area):
                        bpy.ops.screen.animation_play()
                except Exception:
                    continue
                return None
    return None


@persistent
def on_undo_redo(*_args):
    mark_all_dirty()
    if _was_playing[0] and prefs.get_prefs().resume_after_undo and not bpy.app.background:
        _was_playing[0] = False
        bpy.app.timers.register(_resume_playback, first_interval=0.05)


_HANDLERS = (
    (bpy.app.handlers.depsgraph_update_post, on_depsgraph_update),
    (bpy.app.handlers.load_post, on_load_post),
    (bpy.app.handlers.undo_pre, on_undo_pre),
    (bpy.app.handlers.redo_pre, on_undo_pre),
    (bpy.app.handlers.undo_post, on_undo_redo),
    (bpy.app.handlers.redo_post, on_undo_redo),
)


def register():
    for handler_list, func in _HANDLERS:
        if func not in handler_list:
            handler_list.append(func)
    _object_signature[0] = None


def unregister():
    for handler_list, func in _HANDLERS:
        if func in handler_list:
            handler_list.remove(func)
    for timer in (_tick, _resume_playback):
        if bpy.app.timers.is_registered(timer):
            bpy.app.timers.unregister(timer)
