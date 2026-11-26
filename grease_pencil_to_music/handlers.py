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

from . import board, engine, feedback, prefs, props, stroke_mods

_dirty = set()
_full = set()  # dirty compositions that need every layer rendered again
_last_change = [0.0]
_stack_counts = {}  # composition name -> number of modifiers + shader effects
_popup_queue = []
_cleanup_needed = [False]
_object_signature = [None]
_was_playing = [False]
_scaled = set()  # compositions whose object scale changed
_scene_timing = {}  # scene name -> (frame_start, fps, fps_base, frame_end)
_msgbus_owner = object()


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


def mark_dirty(obj, strokes_only=False):
    """Regenerate ``obj`` after the pause. ``strokes_only``: only strokes changed
    (drawing, Edit or Sculpt Mode), so 'Solo livello attivo' may render only the
    active layer; any other change renders every layer."""
    if obj is None or not obj.gp2m.is_composition or not obj.gp2m.auto_update:
        return
    if not strokes_only:
        _full.add(obj.name)
    _dirty.add(obj.name)
    engine.invalidate(obj.name)  # a render still running is for strokes now old
    _last_change[0] = time.monotonic()
    _ensure_timer()


def _mark_full(name):
    _dirty.add(name)
    _full.add(name)


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


def flush(background=False):
    """Regenerate every pending composition now. ``background``: compute the sound in
    the worker thread (automatic updates with Blender's interface)."""
    background = (background and not bpy.app.background
                  and getattr(prefs.get_prefs(), "background_render", True))
    names = list(_dirty)
    full = set(_full)
    _dirty.clear()
    _full.clear()
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None or not obj.gp2m.is_composition:
            continue
        try:  # one broken composition must not stop the others (nor the timer)
            if not board.has_board(obj):  # file from 0.0.1, or board removed
                board.rebuild(obj, engine.scene_of(obj))
            board.ensure_order(obj.data)  # layers added with Blender's own "+"
            feedback.sync(obj)  # also keeps every modifier off the board
        except Exception as error:
            print(f"[Doodle Music] board update failed: {error!r}")
        try:
            stroke_mods.sync(obj)  # the layer modifiers shown on the strokes
        except Exception as error:
            print(f"[Doodle Music] stroke modifiers update failed: {error!r}")
        only_active = name not in full and obj.gp2m.auto_active_layer
        if background:
            engine.regenerate_background(obj, only_active=only_active)
        else:
            engine.regenerate_safe(obj, only_active=only_active)


def _signature():
    """Changes when objects are added, deleted, renamed or duplicated."""
    return hash(tuple(sorted(bpy.data.objects.keys())))


def _modal_running(test):
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None:
        return False
    for window in wm.windows:
        for operator in getattr(window, "modal_operators", ()):
            if test(operator.bl_idname):
                return True
    return False


def transform_running():
    """True while an interactive transform (G, R, S) is in progress."""
    return _modal_running(lambda name: name.startswith("TRANSFORM_OT"))


BRUSH_OPERATORS = frozenset((
    "GREASE_PENCIL_OT_brush_stroke",  # Draw and Erase
    "GREASE_PENCIL_OT_sculpt_paint",
    "GREASE_PENCIL_OT_vertex_brush_stroke",
    "GREASE_PENCIL_OT_weight_brush_stroke",
))


def brush_running():
    """True while the pen is down in Draw or Sculpt Mode (a brush stroke is going on)."""
    return _modal_running(lambda name: name in BRUSH_OPERATORS)


_scale_base = {}  # composition -> (length, octaves) when its scale left 1
_scale_seen = {}  # composition -> (scale tuple, time) to know when it stops moving
SCALE_SETTLE = 0.5  # seconds the scale must stay still before it is applied
TRANSFORM_POLL = 0.1  # seconds between checks while a transform is running


def _scale_of(obj):
    return tuple(round(abs(v), 5) for v in obj.scale)


def apply_scale(obj):
    """Object scale X = loop length, Z = octaves; the strokes are not stretched.

    The new values are computed from the ones the composition had when the
    scale left 1 (never compounded), then the scale goes back to 1 and the
    board is rebuilt bigger or smaller.
    """
    sx, sy, sz = _scale_of(obj)
    base = _scale_base.pop(obj.name, None)
    _scale_seen.pop(obj.name, None)
    if abs(sx - 1.0) < 1e-4 and abs(sy - 1.0) < 1e-4 and abs(sz - 1.0) < 1e-4:
        return False
    s = obj.gp2m
    base_length, base_octaves = base if base is not None else (s.length, s.octaves)
    length = round(min(max(base_length * sx, 1.0), 300.0), 3)
    octaves = int(min(max(round(base_octaves * sz), 1), 7))
    obj.scale = (1.0, 1.0, 1.0)
    if abs(length - s.length) > 1e-6:
        s.length = length
    if octaves != s.octaves:
        s.octaves = octaves
    board.rebuild(obj, engine.scene_of(obj))
    return True


def _scale_pending():
    """Apply finished scale gestures; returns seconds to wait, or None when done."""
    now = time.monotonic()
    waiting = False
    for name in list(_scaled):
        obj = bpy.data.objects.get(name)
        if obj is None or not obj.gp2m.is_composition:
            _scaled.discard(name)
            continue
        current = _scale_of(obj)
        seen = _scale_seen.get(name)
        if seen is None or seen[0] != current:
            _scale_seen[name] = (current, now)
            waiting = True
            continue
        if transform_running() or now - seen[1] < SCALE_SETTLE:
            waiting = True
            continue
        _scaled.discard(name)
        if apply_scale(obj):
            _mark_full(name)
    return SCALE_SETTLE / 2 if waiting else None


def _tick():
    wait = prefs.get_prefs().debounce - (time.monotonic() - _last_change[0])
    if wait > 0.0:
        return wait
    if transform_running():
        # Never rebuild while G/R/S, Alt+S... is still dragging: the transform
        # holds pointers into the Grease Pencil drawings, and regenerating
        # (board, layers, modifiers, strips) under it crashes Blender.
        # The edits stay pending and run as soon as the transform ends.
        return TRANSFORM_POLL
    if brush_running():
        # The pen is still down (it may just be resting): rendering now would stall
        # the stroke. The sound follows when it is lifted.
        return TRANSFORM_POLL
    if _scaled:
        wait = _scale_pending()
        if wait is not None:
            return wait  # the S drag is still going on
    if _cleanup_needed[0]:
        _cleanup_needed[0] = False
        try:
            engine.cleanup_orphans()
            # Shift+D / Alt+D: every composition keeps its own rules.
            for obj in board.make_independent(compositions()):
                _mark_full(obj.name)
        except Exception as error:
            print(f"[Doodle Music] cleanup failed: {error!r}")
        # Duplicated (Shift+D) or renamed compositions need their own strip.
        for obj in compositions():
            if engine.find_strip(engine.scene_of(obj), obj) is None:
                _mark_full(obj.name)
        for scene in bpy.data.scenes:
            engine.resolve_channels(scene)
            engine.arrange_safe(scene)
    flush(background=True)
    _show_popups()
    return None


_layer_syncs = set()  # Grease Pencil data whose layer settings must be checked
_layer_names = {}  # Grease Pencil data name -> names of its layers and groups last seen


def _layer_tree(gp_data):
    def parent(node):
        group = getattr(node, "parent_group", None)
        return group.name if group is not None else ""
    return (tuple((layer.name, parent(layer)) for layer in gp_data.layers),
            tuple((group.name, parent(group)) for group in gp_data.layer_groups))


def layers_changed(gp_data):
    """True when layers or groups were added, removed, renamed or reordered since the
    last call (cheap: strokes drawn or sculpted change nothing here)."""
    tree = _layer_tree(gp_data)
    if _layer_names.get(gp_data.name) == tree:
        return False
    _layer_names[gp_data.name] = tree
    return True


def request_layer_sync(gp_data):
    """Layers or groups added, duplicated or renamed (also with Blender's own layer
    list): give them their settings right away, even with Auto off."""
    _layer_syncs.add(gp_data.name)
    if not bpy.app.timers.is_registered(_layer_sync_tick):
        bpy.app.timers.register(_layer_sync_tick, first_interval=0.0)


def _layer_sync_tick():
    if transform_running():
        return TRANSFORM_POLL
    names = set(_layer_syncs)
    _layer_syncs.clear()
    for obj in compositions():
        if obj.data is None or obj.data.name not in names:
            continue
        try:
            props.ensure_layer_settings(obj.data)
            board.ensure_order(obj.data)
        except Exception as error:
            print(f"[Doodle Music] layer settings update failed: {error!r}")
    return None


def _stack_count(obj):
    return len(feedback.user_modifiers(obj)) + len(getattr(obj, "shader_effects", ()))


def _check_stack(obj):
    count = _stack_count(obj)
    previous = _stack_counts.get(obj.name, 0)
    _stack_counts[obj.name] = count
    if count > previous:
        _mark_full(obj.name)  # the timer keeps new modifiers off the board
        _ensure_timer()
    if count > previous and not obj.gp2m.use_modifiers:
        _popup_queue.append(obj.name)
        _ensure_timer()


def _draw_stack_popup(menu, _context):
    layout = menu.layout
    layout.label(text="Modificatori ed effetti non cambiano il suono:")
    layout.label(text="attiva 'Usa modificatori' (Proprietà → Dati oggetto → Musica → Lettura).")


def _show_popups():
    if not _popup_queue:
        return
    _popup_queue.clear()
    if bpy.app.background:  # no UI: a popup would crash Blender
        return
    wm = getattr(bpy.context, "window_manager", None)
    window = next((w for w in wm.windows if w.screen is not None), None) if wm else None
    if window is None:
        return
    try:
        with bpy.context.temp_override(window=window):
            wm.popup_menu(_draw_stack_popup, title="Doodle Music", icon="INFO")
    except Exception:
        pass  # the warning is also shown in the N panel


UNDO_TICK = "gp2m_undo_tick"  # custom property: changes all the time (see tick_undo)
UNDO_TICK_INTERVAL = 0.1  # seconds
_tick_names = [0.0, ()]  # when the compositions were last listed, their names


def tick_undo(only_scenes=False):
    """Keep every Undo step different from the one before, for the data the add-on
    changes by itself after a step was saved (the sound computed in the background,
    the clips placed again, a clip edited in the Sequencer read back, the grid rebuilt
    a moment later...).

    Blender's Ctrl+Z reads again only the data that differs between two steps and
    keeps the rest as it is in memory. Data equal in both steps but changed by the
    add-on after the last one was then kept as it was changed: after H on a layer's
    clip and Ctrl+Z the layer stayed muted, and a scene kept with clips made after
    the last step pointed to sounds Blender had just thrown away, so Blender crashed
    (Nuovo livello, Ctrl+Z, Ctrl+Shift+Z, Ctrl+Z). A counter on the scenes, the
    compositions, their drawings, grids and collections changes after every update
    and ten times a second: two steps are never equal there, Ctrl+Z reads them again.
    ``only_scenes``: while a brush or a transform is running (their data is left
    alone)."""
    now = time.monotonic()
    if now - _tick_names[0] > 2.0:
        _tick_names[0] = now
        _tick_names[1] = tuple(obj.name for obj in compositions())
    if not _tick_names[1]:
        return
    ids = set()
    for name in _tick_names[1]:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "GREASEPENCIL" or not obj.gp2m.is_composition:
            continue
        ids.update(obj.users_scene)
        if only_scenes:
            continue
        for owner in (obj, board.grid_object(obj)):
            if owner is None:
                continue
            ids.add(owner)
            if owner.data is not None:
                ids.add(owner.data)
            ids.update(owner.users_collection)
    for id_block in ids:
        try:
            id_block[UNDO_TICK] = (id_block.get(UNDO_TICK, 0) + 1) % 1000000
        except (TypeError, AttributeError, ReferenceError):
            pass  # linked (read-only) data


def _undo_tick_timer():
    try:
        tick_undo(only_scenes=transform_running() or brush_running())
    except Exception as error:
        print(f"[Doodle Music] undo tick failed: {error!r}")
    return UNDO_TICK_INTERVAL


@persistent
def on_depsgraph_update(_scene, depsgraph):
    try:
        tick_undo(only_scenes=transform_running() or brush_running())
    except Exception as error:
        print(f"[Doodle Music] undo tick failed: {error!r}")
    comps = None
    for update in depsgraph.updates:
        original = getattr(update.id, "original", update.id)
        if isinstance(original, bpy.types.GreasePencil):
            comps = comps if comps is not None else compositions()
            for obj in comps:
                if obj.data == original:
                    mark_dirty(obj, strokes_only=True)
                    if layers_changed(original):
                        request_layer_sync(original)
        elif isinstance(original, bpy.types.Object):
            if original.type == "GREASEPENCIL" and original.gp2m.is_composition:
                _check_stack(original)
                if update.is_updated_geometry or update.is_updated_shading:
                    mark_dirty(original, strokes_only=True)
                if update.is_updated_transform and _scale_of(original) != (1.0, 1.0, 1.0):
                    if original.name not in _scale_base:
                        _scale_base[original.name] = (original.gp2m.length,
                                                      original.gp2m.octaves)
                    _scaled.add(original.name)
                    _ensure_timer()
        elif isinstance(original, bpy.types.Material):
            mark_material_dirty(original)
        elif isinstance(original, (bpy.types.Scene, bpy.types.Collection)):
            if isinstance(original, bpy.types.Scene):
                _check_scene_timing(original)
                _check_preview(original)
                try:  # clips muted or moved in the Sequencer: the layers follow
                    from . import seqsync
                    seqsync.request(original)
                except Exception as error:
                    print(f"[Doodle Music] Sequencer sync failed: {error!r}")
            # Cheap check first: only look for leftovers when objects changed.
            signature = _signature()
            if signature != _object_signature[0]:
                _object_signature[0] = signature
                _tick_names[0] = 0.0  # list the compositions again
                _cleanup_needed[0] = True
                _ensure_timer()


def _timing(scene):
    return (scene.frame_start, scene.render.fps, round(scene.render.fps_base, 6),
            scene.frame_end)


def _preview(scene):
    return (scene.use_preview_range, scene.frame_preview_start, scene.frame_preview_end)


_scene_preview = {}  # scene name -> Preview Range last seen
_shade_scenes = set()


def _shade_tick():
    """Darken the board outside the Preview Range (grid only: the sound is unchanged)."""
    names = list(_shade_scenes)
    _shade_scenes.clear()
    for name in names:
        scene = bpy.data.scenes.get(name)
        if scene is None:
            continue
        for obj in compositions():
            if engine.scene_of(obj) == scene and board.has_board(obj):
                try:
                    board.update_preview_shade(obj, scene)
                except Exception as error:
                    print(f"[Doodle Music] preview range shading failed: {error!r}")
    return None


def request_shade(scene):
    _shade_scenes.add(scene.name)
    if not bpy.app.timers.is_registered(_shade_tick):
        bpy.app.timers.register(_shade_tick, first_interval=0.01)


def _check_preview(scene):
    preview = _preview(scene)
    if _scene_preview.get(scene.name) != preview:
        _scene_preview[scene.name] = preview
        request_shade(scene)


def _check_scene_timing(scene):
    """A new scene start or frame rate moves strips, playheads and keyframe sections;
    a new Start or End changes the compositions that follow the scene's In/Out."""
    timing = _timing(scene)
    previous = _scene_timing.get(scene.name)
    _scene_timing[scene.name] = timing
    if previous is None or previous == timing:
        return
    only_end = previous[:3] == timing[:3]
    following = False
    for obj in compositions():
        if engine.scene_of(obj) != scene:
            continue
        follows = engine.follows_scene(obj, scene)
        following = following or follows
        if only_end:
            if follows and obj.gp2m.use_sections:
                mark_dirty(obj)  # the last section ends at the new End
        elif previous[0] != timing[0] or obj.gp2m.use_sections:
            mark_dirty(obj)
    if only_end and not following:
        return  # e.g. the End written by 'Adatta l'intervallo della scena'
    _cleanup_needed[0] = True  # arranges every scene
    _ensure_timer()


@persistent
def on_load_post(*_args):
    _dirty.clear()
    _tick_names[0] = 0.0
    _full.clear()
    _stack_counts.clear()
    _scaled.clear()
    _scale_base.clear()
    _scale_seen.clear()
    engine.new_file()  # renders still running belong to the previous file
    engine._state.clear()  # runtime state of the previous file (keyed by object name)
    _scene_timing.clear()
    _scene_preview.clear()
    _layer_syncs.clear()  # names of the previous file
    _layer_names.clear()
    _shade_scenes.clear()
    board._pending.clear()
    for scene in bpy.data.scenes:
        _scene_timing[scene.name] = _timing(scene)
        _scene_preview[scene.name] = _preview(scene)
    _object_signature[0] = _signature()
    for obj in compositions():
        for item in obj.data.gp2m_layers:  # files saved before 0.0.15
            if item.settings_version < props.SETTINGS_VERSION:
                props.migrate_layer_settings(item)
        _stack_counts[obj.name] = _stack_count(obj)
        # Sound files live in a temporary folder: recreate them for this session,
        # even when automatic updates are off.
        _mark_full(obj.name)
    _cleanup_needed[0] = True  # also makes shared data independent
    subscribe()
    _ensure_timer()


def select_composition_of_grid(view_layer=None):
    """Clicking the grid selects its composition: Draw Mode (and G/R/S, the panels...)
    always work on the drawing, never on the grid. Returns the composition."""
    view_layer = view_layer or getattr(bpy.context, "view_layer", None)
    if view_layer is None:
        return None
    active = view_layer.objects.active
    if not board.is_grid(active):
        return None
    owner = board.grid_owner(active)
    if owner is None:
        return None
    try:
        active.select_set(False, view_layer=view_layer)
        owner.select_set(True, view_layer=view_layer)
    except RuntimeError:
        pass  # not in this view layer
    view_layer.objects.active = owner
    return owner


def _on_active_object():
    """The grid hands the selection to its composition; Solo mode follows the
    active composition."""
    try:
        select_composition_of_grid()
    except Exception as error:
        print(f"[Doodle Music] grid selection failed: {error!r}")
    for scene in bpy.data.scenes:
        if scene.gp2m_play.mode == "SOLO":
            engine.arrange_safe(scene)


def subscribe():
    bpy.msgbus.clear_by_owner(_msgbus_owner)
    bpy.msgbus.subscribe_rna(key=(bpy.types.LayerObjects, "active"), owner=_msgbus_owner,
                             args=(), notify=_on_active_object)


@persistent
def on_undo_pre(*_args):
    _was_playing[0] = is_playing()
    from . import seqsync
    seqsync.before_undo()


def _resume_playback():
    """Restart the playback stopped by Ctrl+Z.

    ``screen.animation_play`` only needs a window with a screen: it works
    without a Timeline, with a Timeline collapsed to its header, or with only
    a Properties editor open. An editor of the screen is preferred when there
    is one, as Blender itself would do."""
    if is_playing():
        return None
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None:
        return None
    for window in wm.windows:
        screen = window.screen
        if screen is None:
            continue
        areas = [area for area in screen.areas
                 if area.type in ("VIEW_3D", "DOPESHEET_EDITOR", "SEQUENCE_EDITOR")]
        for override in [{"area": area} for area in areas] + [{}]:
            try:
                with bpy.context.temp_override(window=window, **override):
                    if bpy.ops.screen.animation_play() == {"FINISHED"}:
                        return None
            except Exception:
                continue
    return None


@persistent
def on_undo_redo(*_args):
    from . import seqsync
    seqsync.after_undo()
    for obj in compositions():
        # Paint-mode undo does not restore material slots: fix the board colours.
        # The grid may also be the one of other settings (its rebuild came after the
        # Undo step of the change, e.g. Ctrl+Shift+Z of a rig handle or of "Ottave").
        if board.has_board(obj) and (not board.board_materials_ok(obj)
                                     or not board.board_current(obj)):
            board.request_rebuild(obj)
    mark_all_dirty()
    for obj in compositions():
        # With automatic updates off the strips may now point to deleted files.
        if not obj.gp2m.auto_update and not engine.sound_files_ok(obj, engine.scene_of(obj)):
            _mark_full(obj.name)
            _ensure_timer()
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
    subscribe()
    if not bpy.app.background and not bpy.app.timers.is_registered(_undo_tick_timer):
        bpy.app.timers.register(_undo_tick_timer, first_interval=UNDO_TICK_INTERVAL,
                                persistent=True)


def unregister():
    for handler_list, func in _HANDLERS:
        if func in handler_list:
            handler_list.remove(func)
    bpy.msgbus.clear_by_owner(_msgbus_owner)
    for timer in (_tick, _resume_playback, _shade_tick, _layer_sync_tick,
                  board._rebuild_pending, _undo_tick_timer):
        if bpy.app.timers.is_registered(timer):
            bpy.app.timers.unregister(timer)
    engine.stop_background()
    _layer_syncs.clear()
    _shade_scenes.clear()
    board._pending.clear()
