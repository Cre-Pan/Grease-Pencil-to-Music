# SPDX-License-Identifier: GPL-3.0-or-later
"""The Video Sequencer as a view of the layers: what you change there comes back.

* Muting a layer's clip (inside the composition's meta-clip) mutes the layer, and
  unmuting it unmutes it; muting a layer in its list mutes the clip at once.
* Moving a layer's clip to another channel inside the meta-clip reorders the
  Grease Pencil layers (channel 1 = bottom layer). Layers inside a group are
  reordered only among themselves.
* Moving the meta-clip to another channel changes the composition's "Canale", so
  the Composizioni list follows; moving it in time makes the composition start
  later ("Parte dopo"): playhead and sound follow.
* Volume, pan and color of a layer's clip are the layer's "Volume clip", "Pan" and
  color, both ways (animated values are left to their keyframes); exports use them.

Runs after every depsgraph update of a scene, never while a transform (G in the
Sequencer) is running: then once it ends.
"""

import bpy

from . import board, engine, props

_busy = [False]


def _settings(gp, name):
    return props.find_layer_settings(gp, name)


MESSAGES = []  # the last notices (also for the tests)


def notify(text):
    """A short notice in the Sequencer's status bar (and the console)."""
    MESSAGES.append(text)
    del MESSAGES[:-10]
    print(f"[Doodle Music] {text}")
    if bpy.app.background:
        return
    wm = getattr(bpy.context, "window_manager", None)
    for window in (wm.windows if wm else ()):
        try:
            window.workspace.status_text_set(text)
        except Exception:
            pass

    def clear():
        for window in (wm.windows if wm else ()):
            try:
                window.workspace.status_text_set(None)
            except Exception:
                pass
    bpy.app.timers.register(clear, first_interval=4.0)


def _owned_metas(scene, obj):
    return [strip for strip in engine._top_strips(scene.sequence_editor, obj)
            if strip.type == "META"]


def rebuild_clips(scene, obj):
    """Throw away the composition's clips and make them again (everything they carry,
    volume, pan, color, mute, is stored on the layers)."""
    editor = scene.sequence_editor
    for strip in engine._top_strips(editor, obj):
        engine._remove_strip(editor, strip)
    engine.state(obj).pop("key", None)
    engine.regenerate_safe(obj, scene, force=True)


def _check_clips(scene, obj):
    """Cut (K), duplicated (Shift+D), sped up (retiming) or deleted clips of a
    composition. Returns True when it acted."""
    st = engine.state(obj)
    metas = _owned_metas(scene, obj)
    if not metas:
        if st.pop("had_meta", None) and not obj.gp2m.mute:
            obj.gp2m.mute = True  # the meta-clip was deleted: the composition is muted
            notify(f"Clip eliminata: {obj.name} ora è muta (togli il muto per riaverla)")
            return True
        return False
    main = next((m for m in metas if m.name == engine.strip_name(obj)), metas[0])
    others = [m for m in metas if m != main]
    if others:
        span = st.get("meta_span")
        cut = span is not None and int(main.right_handle) < span[1] and any(
            int(m.left_handle) == int(main.right_handle) for m in others)
        if cut:
            rebuild_clips(scene, obj)
            notify("Le clip di una composizione non si tagliano: la composizione è intera")
            return True
        from . import table
        fps = scene.render.fps / scene.render.fps_base
        for copy_strip in others:
            inner = [s for s in copy_strip.strips if s.type == "SOUND"]
            start = min((s.content_start for s in inner), default=copy_strip.content_start)
            base = st.get("offset_frames", 0) - st.get("delay_frames", 0)
            delay = max(0.0, (start - scene.frame_start - base) / fps)
            channel = copy_strip.channel
            engine._remove_strip(scene.sequence_editor, copy_strip)
            table.duplicate(scene, obj, channel=channel, delay=round(delay, 4))
        notify("Clip duplicata: è una nuova composizione")
        return True
    inner = [s for s in main.strips if s.type == "SOUND" and engine._owned(s, obj)]
    names = [s.get(engine.LAYER_KEY) for s in inner]
    sped = any(len(s.retiming_keys) for s in inner if hasattr(s, "retiming_keys"))
    if len(names) != len(set(names)) or sped:
        rebuild_clips(scene, obj)
        notify("Le clip di una composizione non si scalano: la durata si cambia "
               "dalla fine della clip" if sped else
               "Le clip di una composizione non si tagliano: la composizione è intera")
        return True
    return False


def _sync_name(scene, obj):
    """The meta-clip renamed in the Sequencer: the composition takes the name."""
    meta = engine.meta_strip(scene, obj) or engine.top_strip(scene, obj)
    if meta is None or meta.name == engine.strip_name(obj):
        return False
    name = meta.name
    if name.startswith(engine.STRIP_PREFIX):
        name = name[len(engine.STRIP_PREFIX):]
    name = name.strip()
    import re
    if not name or re.sub(r"\.\d{3}$", "", name) == obj.name:  # e.g. "… 1.001"
        meta.name = engine.strip_name(obj)
        return False
    engine.rename_composition(obj, name)
    return True


def _sync_layer_times(scene, obj):
    """The clip of a layer moved in time inside the meta-clip: the layer's strokes move
    on the board by as much (what you see is what you hear)."""
    st = engine.state(obj)
    if "offset_frames" not in st:
        return False
    target = scene.frame_start + st["offset_frames"]
    strips = engine.layer_strips(scene, obj)
    shifts = {name: int(round(strip.content_start - target))
              for name, strip in strips.items() if strip.parent_meta() is not None}
    moved = {name: shift for name, shift in shifts.items() if shift}
    if not moved or (len(set(shifts.values())) == 1 and len(shifts) > 1):
        return False  # nothing, or the whole meta-clip moved (see _sync_time)
    fps = scene.render.fps / scene.render.fps_base
    s = obj.gp2m
    import numpy as np
    for name, shift in moved.items():
        layer = obj.data.layers.get(name)
        if layer is None:
            continue
        dx = shift / fps * s.seconds_width
        for frame in layer.frames:
            attr = frame.drawing.attributes.get("position")
            if attr is None or not len(attr.data):
                continue
            data = np.empty(len(attr.data) * 3, dtype=np.float32)
            attr.data.foreach_get("vector", data)
            data[0::3] += dx
            attr.data.foreach_set("vector", data)
            frame.drawing.tag_positions_changed()
        strips[name].content_start = target
    from . import handlers
    handlers.mark_dirty(obj)
    return True


def _sync_foreign_layers(scene, obj):
    """The clip of another composition's layer pasted or dragged into this meta-clip:
    the layer moves here (with its instruments and settings)."""
    meta = engine.meta_strip(scene, obj)
    if meta is None:
        return False
    moved = False
    for strip in list(meta.strips):
        owner_name = strip.get(engine.OWNER_KEY)
        layer = strip.get(engine.LAYER_KEY)
        if owner_name in (None, obj.name) or layer is None:
            continue
        owner = bpy.data.objects.get(owner_name)
        engine._remove_strip(scene.sequence_editor, strip)
        if owner is None or not owner.gp2m.is_composition or owner.data.layers.get(layer) is None:
            continue
        from . import layer_transfer
        new = layer_transfer.move_layer(owner, obj, layer)
        if new:
            notify(f"Livello {layer} spostato da {owner.name} a {obj.name}")
            moved = True
    return moved


def _sync_mutes(scene, obj):
    """A clip muted or unmuted by hand in the Sequencer: the layer follows. Returns
    True when a layer changed."""
    changed = False
    for name, strip in engine.layer_strips(scene, obj).items():
        if not engine.clip_mute_changed_by_hand(strip):
            continue
        item = _settings(obj.data, name)
        mute = strip.mute
        engine.set_clip_mute(strip, mute)
        if item is not None and item.mute != mute:
            item.mute = mute  # its update mutes the clips again as they must be
            changed = True
    if changed:
        engine.sync_layer_mutes(scene, obj)  # e.g. hidden or silenced by a Solo
    return changed


def _sync_mix(scene, obj):
    """Volume, pan and color changed on a layer's clip: the layer takes them (the
    add-on keeps them equal, so a difference was made in the Sequencer). Animated
    values belong to their keyframes and are left alone."""
    changed = False
    for name, strip in engine.layer_strips(scene, obj).items():
        item = _settings(obj.data, name)
        if item is None:
            continue
        if strip.color_tag != item.color:
            item.color = strip.color_tag
            changed = True
        mixed = False
        for attr, prop, low, high in (("volume", "clip_volume", 0.0, 10.0),
                                      ("pan", "clip_pan", -1.0, 1.0)):
            if engine.is_animated(scene, strip, attr):
                continue
            value = min(max(getattr(strip, attr), low), high)
            if abs(value - getattr(item, prop)) > 1e-5:
                item[prop] = value  # both read before writing back (no update in between)
                mixed = True
        if mixed:
            engine.dress_strip(obj, strip, name)  # back in range, if it was outside
            changed = True
    return changed


def _sync_time(scene, obj):
    """The composition's clip moved in time: it now starts later (or earlier, never
    before the scene start; "Parte dopo")."""
    strip = engine.top_strip(scene, obj)
    if strip is None:
        return False
    st = engine.state(obj)
    if "offset_frames" not in st:
        return False  # never arranged yet
    if strip.type == "META":
        inner = [s for s in strip.strips if s.type == "SOUND"]
        if not inner:
            return False
        start = min(s.content_start for s in inner)
    else:
        start = strip.content_start
    expected = scene.frame_start + st["offset_frames"]
    if int(round(start)) == int(expected):
        return False
    base = st["offset_frames"] - st.get("delay_frames", 0)
    fps = scene.render.fps / scene.render.fps_base
    delay = max(0.0, (start - scene.frame_start - base) / fps)
    if abs(delay - obj.gp2m.start_delay) < 0.5 / fps:
        return False
    obj.gp2m.start_delay = round(delay, 4)
    return True


def _sync_length(scene, obj):
    """The meta-clip's end dragged in the Sequencer: the composition gets longer or
    shorter by as much (the board and its rig follow)."""
    meta = engine.meta_strip(scene, obj)
    st = engine.state(obj)
    span = st.get("meta_span")
    if meta is None or span is None:
        return False
    left, right = int(meta.left_handle), int(meta.right_handle)
    if (left, right) == tuple(span):
        return False
    st["meta_span"] = (left, right)
    s = obj.gp2m
    moved = (left - span[0]) == (right - span[1])
    if moved:
        return False  # moved in time: see _sync_time
    if left != span[0]:
        notify("L'inizio della clip di una composizione non si taglia")
        return True  # the arrangement puts the start back
    if engine.follows_scene(obj, scene):
        scene.frame_end = max(scene.frame_start + 1, scene.frame_end + right - span[1])
        return True  # the composition follows the scene's End
    if s.use_sections:
        return True  # the length of a song with sections is not free: back as it was
    fps = scene.render.fps / scene.render.fps_base
    length = round(min(max(s.length + (right - span[1]) / fps, 1.0), 300.0), 4)
    if abs(length - s.length) < 0.5 / fps:
        return False
    s.length = length
    return True


def _reorder(gp, wanted):
    """Put the layers ``wanted`` (bottom first) in that order, the other layers and
    groups keep their places. Only layers with the same parent group."""
    layers = [gp.layers.get(name) for name in wanted]
    if any(layer is None for layer in layers):
        return False
    parents = {layer.parent_group.name if layer.parent_group else "" for layer in layers}
    if len(parents) != 1:
        return False  # across groups: the clips go back to their channels
    parent = layers[0].parent_group
    nodes = list(parent.children if parent is not None else gp.root_nodes)
    names = [node.name for node in nodes]
    slots = [i for i, node in enumerate(nodes) if node.name in wanted
             and not board.is_group(node)]
    if [names[i] for i in slots] == list(wanted):
        return False
    order = list(nodes)
    for slot, name in zip(slots, wanted):
        order[slot] = gp.layers[name]
    for node in order:  # moving each to the top, in order, gives exactly that order
        if board.is_group(node):
            gp.layer_groups.move_top(node)
        else:
            gp.layers.move_top(node)
    board.ensure_order(gp)
    return True


def _sync_order(scene, obj):
    strips = engine.layer_strips(scene, obj)
    if len(strips) < 2:
        return False
    by_channel = [name for name, _strip in
                  sorted(strips.items(), key=lambda item: (item[1].channel, item[0]))]
    if by_channel == engine.layer_channel_order(obj, list(strips)):
        return False
    return _reorder(obj.data, by_channel)


def _sync_channel(scene, obj):
    meta = engine.top_strip(scene, obj)
    if meta is None or not obj.gp2m.channel or meta.channel == obj.gp2m.channel:
        return False
    obj.gp2m.channel = meta.channel  # the list of compositions follows
    return True


def sync_scene(scene):
    """Read back what was changed in the Sequencer. Returns True if anything changed."""
    if _busy[0] or engine._arranging[0] or scene.sequence_editor is None:
        return False
    from . import rig
    if rig.dragging():  # the rig moves the meta-clip itself while dragging
        return False
    _busy[0] = True
    changed = False
    try:
        for obj in engine.scene_compositions(scene):
            top = engine.top_strip(scene, obj)
            if top is not None and top.lock:
                continue  # locked in the Sequencer: left as it is
            if obj.gp2m.layer_channels and _check_clips(scene, obj):
                changed = True
                continue
            changed |= _sync_name(scene, obj)
            if obj.gp2m.layer_channels and _sync_foreign_layers(scene, obj):
                changed = True
            if not obj.gp2m.layer_channels or engine.meta_strip(scene, obj) is None:
                if engine.top_strip(scene, obj) is not None:
                    changed |= _sync_channel(scene, obj)
                    changed |= _sync_time(scene, obj)
                continue
            changed |= _sync_mutes(scene, obj)
            changed |= _sync_mix(scene, obj)
            changed |= _sync_order(scene, obj)
            changed |= _sync_channel(scene, obj)
            changed |= _sync_length(scene, obj)
            changed |= _sync_layer_times(scene, obj)
            changed |= _sync_time(scene, obj)
    finally:
        _busy[0] = False
    if changed:
        engine.arrange_safe(scene)
    return changed


def _later():
    from .handlers import TRANSFORM_POLL, transform_running
    if transform_running():
        return TRANSFORM_POLL
    for scene in bpy.data.scenes:
        try:
            sync_scene(scene)
        except Exception as error:  # keep Blender responsive
            print(f"[Doodle Music] Sequencer sync failed: {error!r}")
    return None


def request(scene):
    """From the depsgraph handler: now, or when the running transform ends."""
    from .handlers import transform_running
    if transform_running():
        if not bpy.app.timers.is_registered(_later):
            bpy.app.timers.register(_later, first_interval=0.1)
        return
    sync_scene(scene)


def unregister():
    if bpy.app.timers.is_registered(_later):
        bpy.app.timers.unregister(_later)
