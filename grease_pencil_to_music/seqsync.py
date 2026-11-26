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
_undoing = [False]  # between undo_pre and undo_post: nothing is read back


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
        loose = [strip for strip in engine._top_strips(scene.sequence_editor, obj)
                 if strip.get(engine.LAYER_KEY) is not None]
        if loose and st.get("had_meta"):  # Alt+G on the composition's meta-clip
            rebuild_clips(scene, obj)
            notify("La clip di una composizione non si separa: per raggruppare dei "
                   "livelli usa Ctrl+G dentro la clip")
            return True
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
            inner = engine.meta_sounds(copy_strip)
            start = min((s.content_start for s in inner), default=copy_strip.content_start)
            base = st.get("offset_frames", 0) - st.get("delay_frames", 0)
            delay = max(0.0, (start - scene.frame_start - base) / fps)
            channel = copy_strip.channel
            parent = copy_strip.parent_meta()
            group = parent.get(engine.GROUP_KEY) if parent is not None else None
            engine._remove_strip(scene.sequence_editor, copy_strip)
            table.duplicate(scene, obj, channel=channel, delay=round(delay, 4), group=group)
        notify("Clip duplicata: è una nuova composizione")
        return True
    inner = [s for s in engine.meta_sounds(main) if engine._owned(s, obj)]
    names = [s.get(engine.LAYER_KEY) for s in inner]
    sped = any(len(s.retiming_keys) for s in inner if hasattr(s, "retiming_keys"))
    if len(names) != len(set(names)) or sped:
        rebuild_clips(scene, obj)
        notify("Le clip di una composizione non si scalano: la durata si cambia "
               "dalla fine della clip" if sped else
               "Le clip di una composizione non si tagliano: la composizione è intera")
        return True
    return False


def _new_group_name(editor):
    names = {meta.name for meta in engine.group_metas(editor)}
    index = 1
    while f"Gruppo {index}" in names:
        index += 1
    return f"Gruppo {index}"


def _new_group_key(editor):
    keys = {meta[engine.GROUP_KEY] for meta in engine.group_metas(editor)}
    index = 1
    while f"g{index}" in keys:
        index += 1
    return f"g{index}"


def make_group(meta):
    """``meta`` becomes a group of compositions, with its volume and pan."""
    editor = meta.id_data.sequence_editor
    meta[engine.GROUP_KEY] = _new_group_key(editor)
    meta.name = _new_group_name(editor)
    meta[engine.BUS_VOLUME] = 1.0
    meta[engine.BUS_PAN] = 0.0
    meta.id_properties_ui(engine.BUS_VOLUME).update(
        min=0.0, max=10.0, soft_max=2.0, description="Volume di tutte le composizioni del gruppo")
    meta.id_properties_ui(engine.BUS_PAN).update(
        min=-1.0, max=1.0, description="Pan di tutte le composizioni del gruppo")


def _sync_groups(scene):
    """Groups of compositions: Ctrl+G on composition clips makes one (they stay apart
    on the table, together in the Sequencer), Alt+G on it takes them out again; a
    composition belongs to the group its clip is in. Returns True when it acted."""
    editor = scene.sequence_editor
    changed = False
    for strips in engine._containers(editor):
        for meta in list(strips):
            if meta.type != "META" or meta.get(engine.OWNER_KEY) is not None \
                    or engine.is_group_meta(meta):
                continue
            if any(engine._is_composition_strip(inner) or engine.is_group_meta(inner)
                   for inner in meta.strips):
                make_group(meta)  # Ctrl+G
                notify(f"{meta.name}: le composizioni restano separate sul tavolo e "
                       "si muovono insieme nel Sequencer")
                changed = True
    seen = set()
    for meta in engine.group_metas(editor):
        if meta[engine.GROUP_KEY] in seen:  # a copy of a group (Shift+D)
            meta[engine.GROUP_KEY] = _new_group_key(editor)
            changed = True
        seen.add(meta[engine.GROUP_KEY])
        if abs(meta.volume - 1.0) > 1e-4:
            # The volume set on the meta-clip itself reaches only the strips right
            # inside: it becomes the group's volume, for every composition in it.
            meta[engine.BUS_VOLUME] = float(meta.get(engine.BUS_VOLUME, 1.0)) * meta.volume
            meta.volume = 1.0
            changed = True
    for obj in engine.scene_compositions(scene):
        top = engine.top_strip(scene, obj)
        if top is None:
            continue
        parent = top.parent_meta()
        key = parent.get(engine.GROUP_KEY) if parent is not None else None
        if obj.get(engine.GROUP_KEY) != key:
            if key is None:
                del obj[engine.GROUP_KEY]
            else:
                obj[engine.GROUP_KEY] = key
            if obj.gp2m.channel != top.channel:
                obj.gp2m.channel = top.channel
            changed = True
    return changed


def _sync_bus(scene, obj):
    """The volume or pan of a group changed: every clip of the composition takes it.
    Returns True when it did (the clips are then not read back this time)."""
    st = engine.state(obj)
    volume, pan, muted = engine.group_bus(scene, obj)
    bus = (round(volume, 5), round(pan, 5))
    if st.get("bus", (1.0, 0.0)) == bus:
        return False
    st["bus"] = bus
    for name, strip in engine.layer_strips(scene, obj).items():
        engine.dress_strip(obj, strip, name)
    return True


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
    for strip in engine.meta_sounds(meta):
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
        bus_volume, bus_pan = engine.strip_bus(scene, obj, name)
        for attr, prop, low, high in (("volume", "clip_volume", 0.0, 10.0),
                                      ("pan", "clip_pan", -1.0, 1.0)):
            if engine.is_animated(scene, strip, attr):
                continue
            current = getattr(strip, attr)
            if attr == "volume":
                expected = item.clip_volume * bus_volume
                value = current / bus_volume if bus_volume > 1e-6 else item.clip_volume
            else:
                expected = min(max(item.clip_pan + bus_pan, -1.0), 1.0)
                value = current - bus_pan
            if abs(current - expected) <= 1e-5:
                continue
            value = min(max(value, low), high)
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
        inner = engine.meta_sounds(strip)
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


def _node(gp, name):
    layer = gp.layers.get(name)
    return layer if layer is not None else gp.layer_groups.get(name)


def _reorder(gp, wanted):
    """Put the layers and groups ``wanted`` (bottom first) in that order, the other
    layers and groups keep their places. Only nodes with the same parent group."""
    layers = [_node(gp, name) for name in wanted]
    if any(layer is None for layer in layers):
        return False
    parents = {layer.parent_group.name if layer.parent_group else "" for layer in layers}
    if len(parents) != 1:
        return False  # across groups: the clips go back to their channels
    parent = layers[0].parent_group
    nodes = list(parent.children if parent is not None else gp.root_nodes)
    names = [node.name for node in nodes]
    slots = [i for i, node in enumerate(nodes) if node.name in wanted]
    if [names[i] for i in slots] == list(wanted):
        return False
    order = list(nodes)
    for slot, name in zip(slots, wanted):
        order[slot] = _node(gp, name)
    for node in order:  # moving each to the top, in order, gives exactly that order
        if board.is_group(node):
            gp.layer_groups.move_top(node)
        else:
            gp.layers.move_top(node)
    board.ensure_order(gp)
    return True


def _node_name(strip):
    return strip.get(engine.LAYER_KEY) or strip.get(engine.LAYER_GROUP_KEY)


def _sync_order(scene, obj):
    """Clips of layers (or of groups of layers) moved to other channels inside their
    meta-clip: the layers and groups take that order."""
    meta = engine.meta_strip(scene, obj)
    if meta is None or engine.state(obj).get("tree") != engine.tree_signature(obj):
        return False  # the layers changed on the board: the Sequencer follows them
    gp = obj.data
    changed = False
    undo_order = engine.state(obj).get("undo_order") or {}
    for key, container in [("", meta)] + list(engine.layer_group_metas(meta).items()):
        inside = [strip for strip in container.strips if _node_name(strip)]
        if len(inside) < 2:
            continue
        by_channel = [_node_name(strip) for strip in
                      sorted(inside, key=lambda strip: (strip.channel, _node_name(strip)))]
        if undo_order.get(key) == by_channel:
            continue  # after Ctrl+Z: the clips as the step has them, not moved by hand
        group = gp.layer_groups.get(container.get(engine.LAYER_GROUP_KEY) or "") \
            if container != meta else None
        siblings = list(group.children if group is not None else gp.root_nodes)
        current = [node.name for node in siblings if node.name in by_channel]
        if current != by_channel and len(current) == len(by_channel):
            changed |= _reorder(gp, by_channel)
    return changed


def _move_node(gp, node, group):
    if board.is_group(node):
        gp.layer_groups.move_to_layer_group(node, group)
    else:
        gp.layers.move_to_layer_group(node, group)
    if group is not None:
        group.is_expanded = True


def _sync_layer_groups(scene, obj):
    """Groups of layers inside the composition's meta-clip: Ctrl+G on clips of layers
    makes a group of those layers (in the same composition), Alt+G on a group's clip
    breaks the group up, a clip pasted in a group's clip moves the layer into the
    group; deleting a group's clip mutes the group. Returns True when it acted."""
    meta = engine.meta_strip(scene, obj)
    if meta is None:
        return False
    gp = obj.data
    st = engine.state(obj)
    from . import operators
    changed = False
    for container in [meta] + list(engine.layer_group_metas(meta).values()):
        parent = gp.layer_groups.get(container.get(engine.LAYER_GROUP_KEY) or "") \
            if container != meta else None
        for strip in list(container.strips):
            if strip.type != "META" or strip.get(engine.OWNER_KEY) is not None:
                continue
            members = sorted((inner for inner in strip.strips if _node_name(inner)
                              and _node(gp, _node_name(inner)) is not None),
                             key=lambda inner: inner.channel)
            if not members:
                continue
            name = operators._unique_node_name(gp, "Gruppo")
            group = gp.layer_groups.new(name, parent_group=parent)
            group.is_expanded = True
            first = _node(gp, _node_name(members[0]))
            if (first.parent_group.name if first.parent_group else None) == \
                    (parent.name if parent else None):
                operators._place_next_to(gp, group, first, above=True)
            for inner in members:  # bottom first: each on top gives the same order
                node = _node(gp, _node_name(inner))
                _move_node(gp, node, group)
                if board.is_group(node):
                    gp.layer_groups.move_top(node)
                else:
                    gp.layers.move_top(node)
            strip[engine.OWNER_KEY] = obj.name
            strip[engine.LAYER_GROUP_KEY] = name
            strip.name = engine.strip_name(obj, name)
            props.ensure_layer_settings(gp)
            board.ensure_order(gp)
            notify(f"Nuovo gruppo di livelli in {obj.name}: {name}")
            changed = True
    if changed or st.get("tree") != engine.tree_signature(obj):
        return changed  # the layers changed on the board: the Sequencer follows them
    metas = engine.layer_group_metas(meta)

    def group_of(strip):
        holder = strip.parent_meta()
        if holder is None or holder.name == meta.name:
            return None
        return gp.layer_groups.get(holder.get(engine.LAYER_GROUP_KEY) or "")

    clips = list(engine.layer_strips(scene, obj).items()) + list(metas.items())
    for name, strip in clips:
        node = _node(gp, name)
        if node is None:
            continue
        target = group_of(strip)
        if target is not None and target.name == name:
            continue
        current = node.parent_group
        if (current.name if current else None) != (target.name if target else None):
            _move_node(gp, node, target)  # pasted in another group, or Alt+G
            changed = True
    for name in st.get("layer_groups", ()):
        group = gp.layer_groups.get(name)
        if name in metas or group is None:
            continue
        if not len(group.children):  # Alt+G: the group is broken up
            gp.layer_groups.remove(group)
            notify(f"Gruppo di livelli sciolto: {name}")
            changed = True
            continue
        strips = engine.layer_strips(scene, obj)
        inside = [layer.name for layer in gp.layers if group in board.ancestors(layer)]
        item = props.find_layer_settings(gp, name)
        if item is not None and not item.mute and not any(n in strips for n in inside):
            item.mute = True  # its clip was deleted
            notify(f"Clip eliminata: il gruppo {name} ora è muto")
            changed = True
    if changed:
        props.ensure_layer_settings(gp)
        board.ensure_order(gp)
    return changed


def _sync_layer_group_clips(scene, obj):
    """Mute and volume set on the clip of a group of layers: the group takes them
    (the volume set on a meta-clip reaches only the strips right inside it, so it
    becomes the group's "Volume clip", for every layer in it)."""
    meta = engine.meta_strip(scene, obj)
    if meta is None:
        return False
    changed = False
    for name, group_meta in engine.layer_group_metas(meta).items():
        item = props.find_layer_settings(obj.data, name)
        if item is None:
            continue
        if engine.clip_mute_changed_by_hand(group_meta):
            engine.set_clip_mute(group_meta, group_meta.mute)
            if item.mute != group_meta.mute:
                item.mute = group_meta.mute
                changed = True
        if abs(group_meta.volume - 1.0) > 1e-4:
            volume = min(max(item.clip_volume * group_meta.volume, 0.0), 10.0)
            group_meta.volume = 1.0
            item.clip_volume = volume  # its update dresses the clips of the layers
            changed = True
    return changed


def _sync_composition_mute(scene, obj):
    """H / Alt+H on the composition's clip in the Sequencer: the composition is muted
    or heard again ("Muto"; before, the clip was simply unmuted again)."""
    top = engine.top_strip(scene, obj)
    if top is None or not engine.clip_mute_changed_by_hand(top):
        return False
    mute = top.mute
    engine.set_clip_mute(top, mute)
    if obj.gp2m.mute == mute:
        return False  # e.g. Alt+H on a composition silenced by Solo: it stays silent
    obj.gp2m.mute = mute
    return True


def _sync_channel(scene, obj):
    meta = engine.top_strip(scene, obj)
    if meta is None or not obj.gp2m.channel or meta.channel == obj.gp2m.channel:
        return False
    obj.gp2m.channel = meta.channel  # the list of compositions follows
    return True


def sync_scene(scene):
    """Read back what was changed in the Sequencer. Returns True if anything changed."""
    if _busy[0] or _undoing[0] or engine._arranging[0] or scene.sequence_editor is None:
        return False
    from . import rig
    if rig.dragging():  # the rig moves the meta-clip itself while dragging
        return False
    _busy[0] = True
    changed = False
    try:
        changed |= _sync_groups(scene)
        for obj in engine.scene_compositions(scene):
            top = engine.top_strip(scene, obj)
            if top is not None and top.lock:
                continue  # locked in the Sequencer: left as it is
            if obj.gp2m.layer_channels and _check_clips(scene, obj):
                changed = True
                continue
            changed |= _sync_composition_mute(scene, obj)
            st = engine.state(obj)
            if st.get("muted_stale") and not obj.gp2m.mute \
                    and not engine.muted_by_group(scene, obj):
                engine.regenerate_safe(obj, scene)  # its group is heard again
                changed = True
            changed |= _sync_name(scene, obj)
            if obj.gp2m.layer_channels and _sync_foreign_layers(scene, obj):
                changed = True
            if not obj.gp2m.layer_channels or engine.meta_strip(scene, obj) is None:
                if engine.top_strip(scene, obj) is not None:
                    changed |= _sync_channel(scene, obj)
                    changed |= _sync_time(scene, obj)
                continue
            if _sync_layer_groups(scene, obj):
                changed = True
                continue  # the clips follow the layers at the next arrangement
            changed |= _sync_layer_group_clips(scene, obj)
            changed |= _sync_mutes(scene, obj)
            if _sync_bus(scene, obj):
                changed = True
            else:
                changed |= _sync_mix(scene, obj)
            changed |= _sync_order(scene, obj)
            changed |= _sync_channel(scene, obj)
            changed |= _sync_length(scene, obj)
            changed |= _sync_layer_times(scene, obj)
            changed |= _sync_time(scene, obj)
        for obj in engine.scene_compositions(scene):
            engine.save_sync_state(obj)
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


def before_undo():
    """Ctrl+Z / Ctrl+Shift+Z is starting: the clips about to come back are not edits
    made in the Sequencer."""
    _undoing[0] = True


def after_undo():
    """Ctrl+Z / Ctrl+Shift+Z gave back the layers, the settings and the clips of an
    Undo step. The step was saved right after the action, before the add-on followed
    it (the sound, the clips placed again, a clip moved in the Sequencer read back):
    what the read-back remembers is taken from the step too (see
    :func:`engine.save_sync_state`), the clips are read back against it (a clip moved
    or trimmed in the Sequencer is a new start or length again, Ctrl+Shift+Z included)
    and then placed from the settings. With what Python remembered of the moment left
    instead, the clips given back looked like clips dragged or trimmed in the
    Sequencer: the Durata undone by Ctrl+Z came back shortened by the same amount."""
    _undoing[0] = True
    try:
        scenes = []
        for scene in bpy.data.scenes:
            comps = engine.scene_compositions(scene)
            if not comps or scene.sequence_editor is None:
                continue
            for obj in comps:
                engine.load_sync_state(obj)
                if not obj.gp2m.use_sections:
                    engine.state(obj).pop("duration", None)  # the length given back
            scenes.append(scene)
    finally:
        _undoing[0] = False
    for scene in scenes:
        try:
            if not sync_scene(scene):
                engine.arrange_safe(scene)
        except Exception as error:  # keep Blender responsive
            print(f"[Doodle Music] Sequencer sync after undo failed: {error!r}")
        finally:
            for obj in engine.scene_compositions(scene):
                engine.state(obj).pop("undo_order", None)


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
