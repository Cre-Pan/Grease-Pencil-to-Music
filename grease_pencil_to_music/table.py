# SPDX-License-Identifier: GPL-3.0-or-later
"""The 3D viewport as a table of compositions, managed like layers.

* "Composizioni" in the sidebar lists the compositions of the scene like a
  layer list: the top row is the highest channel in the Video Sequencer, so the
  list and the timeline read the same way. Each row has its channel, mute, eye
  and lock; next to the list: add, duplicate, delete, move up / down (swaps the
  Sequencer channels), frame and "Riordina".
* A new composition is placed on the table above the highest one (aligned with
  it, same rotation) instead of on top of the others at the 3D cursor.
* "Riordina" stacks every composition, lowest channel at the bottom.
"""

import bpy
from bpy.props import EnumProperty, IntProperty
from mathutils import Vector

from . import board, engine

GAP = 0.4  # space between two boards stacked on the table


# --- Compositions in channel order --------------------------------------------

def compositions(scene):
    return [obj for obj in scene.objects
            if obj.type == "GREASEPENCIL" and obj.gp2m.is_composition]


def channel_span(scene, obj):
    """(first, last) Sequencer channel of the composition (0, 0 when unknown)."""
    first = obj.gp2m.channel
    if not first:
        strip = engine.find_strip(scene, obj)
        first = strip.channel if strip is not None else 0
    count = engine._channel_count(scene, obj)
    return first, first + count - 1 if first else 0


def by_channel(scene):
    """Compositions from the lowest channel up (unknown channels last, by name)."""
    def key(obj):
        first = channel_span(scene, obj)[0]
        return (first if first else 10 ** 6, obj.name)
    return sorted(compositions(scene), key=key)


# --- Placement on the table -------------------------------------------------------

def _top_point(obj):
    """World point just above the board of ``obj`` (its left edge)."""
    _z0, z1 = board.vertical_extent(obj.gp2m)
    return obj.matrix_world @ Vector((0.0, 0.0, z1 + GAP))


def place_new(obj, scene):
    """Put a new composition above the highest one on the table (or at the 3D cursor
    when it is the first)."""
    others = [o for o in compositions(scene) if o != obj and o.visible_get()]
    if not others:
        obj.location = scene.cursor.location
        return
    top = max(others, key=lambda o: _top_point(o).z)
    z0, _z1 = board.vertical_extent(obj.gp2m)
    obj.rotation_euler = top.matrix_world.to_euler()
    point = _top_point(top)
    # The bottom of the new board (z0, below its origin) sits on the point.
    up = top.matrix_world.to_3x3().normalized() @ Vector((0.0, 0.0, 1.0))
    obj.location = point - up * z0


def stack(scene, comps=None):
    """Stack the compositions from the lowest channel up, starting where the lowest
    one is now, all with its rotation."""
    comps = comps or by_channel(scene)
    if len(comps) < 2:
        return
    base = comps[0]
    rotation = base.matrix_world.to_3x3().normalized()
    up = rotation @ Vector((0.0, 0.0, 1.0))
    origin = base.matrix_world.translation.copy()
    _z0, z1 = board.vertical_extent(base.gp2m)
    level = z1 + GAP
    for obj in comps[1:]:
        z0, z1 = board.vertical_extent(obj.gp2m)
        world = rotation.to_4x4()
        world.translation = origin + up * (level - z0)
        obj.matrix_world = world
        level += (z1 - z0) + GAP


# --- Active row <-> active object ---------------------------------------------------

def _get_index(scene):
    layer = bpy.context.view_layer
    active = layer.objects.active if layer is not None else None
    if active is None:
        return -1
    for index, obj in enumerate(scene.objects):
        if obj == active:
            return index
    return -1


def _set_index(scene, value):
    if not 0 <= value < len(scene.objects):
        return
    obj = scene.objects[value]
    if not obj.gp2m.is_composition:
        return
    select_only(bpy.context, obj)


def select_only(context, obj):
    view_layer = context.view_layer
    if view_layer is None:
        return
    active = view_layer.objects.active
    if active is not None and active != obj and active.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            return  # Blender refuses here: leave the selection alone
    for other in context.selected_objects:
        if other != obj:
            other.select_set(False)
    try:
        obj.select_set(True)
    except RuntimeError:
        return  # hidden or not in this view layer
    view_layer.objects.active = obj


def _parts(obj, with_rig=True):
    """The composition and its grid (the rig handles are gizmos, not objects)."""
    grid = board.grid_object(obj)
    return [obj] + ([grid] if grid is not None else [])


# --- List ------------------------------------------------------------------------

class GP2M_UL_compositions(bpy.types.UIList):
    """The compositions of the scene, highest Sequencer channel on top."""

    bl_idname = "GP2M_UL_compositions"

    def draw_item(self, context, layout, _data, item, _icon, _active_data, _active_prop,
                  _index=0, _flt_flag=0):
        obj = item
        row = layout.row(align=True)
        hidden = obj.hide_get()
        locked = obj.hide_select
        op = row.operator("gp2m.composition_toggle", text="", emboss=False,
                          icon="LOCKED" if locked else "UNLOCKED")
        op.name, op.what = obj.name, "LOCK"
        op = row.operator("gp2m.composition_toggle", text="", emboss=False,
                          icon="HIDE_ON" if hidden else "HIDE_OFF")
        op.name, op.what = obj.name, "HIDE"
        name = row.row(align=True)
        name.active = not hidden and not obj.gp2m.mute
        name.prop(obj, "name", text="", emboss=False, icon="OUTLINER_OB_GREASEPENCIL")
        first, last = channel_span(context.scene, obj)
        right = row.row(align=True)
        right.alignment = "RIGHT"
        if first:
            right.label(text=f"{first}" if first == last else f"{first}–{last}")
        right.prop(obj.gp2m, "mute", text="", emboss=False,
                   icon="MUTE_IPO_ON" if obj.gp2m.mute else "MUTE_IPO_OFF")

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        scene = context.scene
        ordered = by_channel(scene)
        rank = {obj.name: len(ordered) - 1 - i for i, obj in enumerate(ordered)}  # top first
        needle = getattr(self, "filter_name", "").lower().strip("*")
        flags, keys = [], []
        for index, obj in enumerate(items):
            visible = obj.name in rank and (not needle or needle in obj.name.lower())
            flags.append(self.bitflag_filter_item if visible else 0)
            keys.append((rank.get(obj.name, len(rank)), index))
        order = [0] * len(keys)
        for position, (_key, index) in enumerate(sorted(keys)):
            order[index] = position
        return flags, order


def draw_list(layout, context):
    scene = context.scene
    row = layout.row()
    row.template_list("GP2M_UL_compositions", "", scene, "objects", scene,
                      "gp2m_composition_index", rows=4)
    col = row.column(align=True)
    col.operator("gp2m.add_composition", text="", icon="ADD")
    col.operator("gp2m.composition_duplicate", text="", icon="DUPLICATE")
    col.operator("gp2m.composition_remove", text="", icon="REMOVE")
    col.separator()
    col.operator("gp2m.composition_move", text="", icon="TRIA_UP").direction = "UP"
    col.operator("gp2m.composition_move", text="", icon="TRIA_DOWN").direction = "DOWN"
    col.separator()
    col.operator("gp2m.composition_frame", text="", icon="ZOOM_SELECTED")
    col.operator("gp2m.table_stack", text="", icon="ALIGN_BOTTOM")


class GP2M_PT_compositions(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Musica"
    bl_label = "Composizioni"

    def draw_header_preset(self, _context):
        from . import help
        help.button(self.layout, "TABLE")

    def draw(self, context):
        draw_list(self.layout, context)


# --- Operators ---------------------------------------------------------------------

def _active(context):
    obj = context.view_layer.objects.active if context.view_layer else None
    if obj is not None and obj.type == "GREASEPENCIL" and obj.gp2m.is_composition:
        return obj
    return None


class GP2M_OT_composition_toggle(bpy.types.Operator):
    """Mostra o nascondi, blocca o sblocca la composizione (con la sua tavola)"""

    bl_idname = "gp2m.composition_toggle"
    bl_label = "Mostra / blocca composizione"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    name: bpy.props.StringProperty()
    what: EnumProperty(items=(("HIDE", "Mostra", ""), ("LOCK", "Blocca", "")))

    def execute(self, context):
        obj = bpy.data.objects.get(self.name)
        if obj is None or not obj.gp2m.is_composition:
            return {"CANCELLED"}
        if self.what == "HIDE":
            hide = not obj.hide_get()
            if hide and obj.mode != "OBJECT" and obj == _active(context):
                bpy.ops.object.mode_set(mode="OBJECT")
            for part in _parts(obj):
                try:
                    part.hide_set(hide)
                except RuntimeError:
                    pass
        else:
            lock = not obj.hide_select
            for part in _parts(obj, with_rig=False):  # the handles are never selectable
                part.hide_select = lock
            if lock:
                obj.select_set(False)
        return {"FINISHED"}


class GP2M_OT_composition_move(bpy.types.Operator):
    """Sposta la composizione su (o giù) nella lista: scambia i canali del Sequencer con
    la vicina"""

    bl_idname = "gp2m.composition_move"
    bl_label = "Sposta composizione"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(items=(("UP", "Su", ""), ("DOWN", "Giù", "")))

    @classmethod
    def poll(cls, context):
        return _active(context) is not None

    def execute(self, context):
        scene = context.scene
        obj = _active(context)
        ordered = by_channel(scene)
        index = ordered.index(obj)
        other_index = index + (1 if self.direction == "UP" else -1)
        if not 0 <= other_index < len(ordered):
            return {"CANCELLED"}
        lower, upper = sorted((obj, ordered[other_index]), key=ordered.index)
        swap_channels(scene, lower, upper)
        return {"FINISHED"}


def swap_channels(scene, lower, upper):
    """``upper`` takes the bottom of the two channel blocks, ``lower`` the top."""
    low_first, _low_last = channel_span(scene, lower)
    up_first, up_last = channel_span(scene, upper)
    if not low_first or not up_first:
        return
    low_count = engine._channel_count(scene, lower)
    # Both move at once (no arranging in between, or one would push the other away).
    engine._arranging[0] = True
    try:
        upper.gp2m.channel = low_first
        lower.gp2m.channel = up_last - low_count + 1
        # Blender pushes a strip away from an occupied channel: park one strip on a
        # free channel first, then put both in place.
        lower_strip, upper_strip = engine.top_strip(scene, lower), engine.top_strip(scene, upper)
        if lower_strip is not None and upper_strip is not None:
            used = {strip.channel for strip in scene.sequence_editor.strips}
            lower_strip.channel = engine._block_from(engine.MAX_CHANNEL, 1, used)
            upper_strip.channel = upper.gp2m.channel
            lower_strip.channel = lower.gp2m.channel
    finally:
        engine._arranging[0] = False
    engine.arrange_safe(scene)


class GP2M_OT_composition_duplicate(bpy.types.Operator):
    """Duplica la composizione: la copia va sopra le altre, sul tavolo e nel Sequencer"""

    bl_idname = "gp2m.composition_duplicate"
    bl_label = "Duplica composizione"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active(context) is not None

    def execute(self, context):
        scene = context.scene
        source = _active(context)
        select_only(context, source)
        copy = source.copy()
        copy.data = source.data.copy()
        copy.gp2m.grid = None  # its own grid is built for it
        for collection in source.users_collection or (scene.collection,):
            collection.objects.link(copy)
        copy.gp2m.channel = engine.new_composition_channel(
            scene, engine._channel_count(scene, source))
        place_new(copy, scene)
        board.make_independent([source, copy])
        board.rebuild(copy, scene)
        engine.regenerate_safe(copy, scene, force=True)
        select_only(context, copy)
        return {"FINISHED"}


class GP2M_OT_composition_remove(bpy.types.Operator):
    """Elimina la composizione, la sua tavola e il suo suono"""

    bl_idname = "gp2m.composition_remove"
    bl_label = "Elimina composizione"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active(context) is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        obj = _active(context)
        if obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        scene = context.scene
        ordered = [o.name for o in by_channel(scene)]
        index = ordered.index(obj.name)
        name = obj.name
        for part in reversed(_parts(obj)):
            data = part.data
            bpy.data.objects.remove(part, do_unlink=True)
            if data is not None and data.users == 0:
                bpy.data.grease_pencils.remove(data)
        engine.cleanup_orphans()
        rest = [bpy.data.objects[n] for n in ordered if n != name and n in bpy.data.objects]
        if rest:
            select_only(context, rest[min(index, len(rest) - 1)])
        engine.arrange_safe(scene)
        return {"FINISHED"}


class GP2M_OT_composition_frame(bpy.types.Operator):
    """Inquadra la composizione attiva (vista frontale)"""

    bl_idname = "gp2m.composition_frame"
    bl_label = "Inquadra composizione"

    @classmethod
    def poll(cls, context):
        return _active(context) is not None

    def execute(self, context):
        from .operators import frame_view
        frame_view(context, _active(context))
        return {"FINISHED"}


class GP2M_OT_table_stack(bpy.types.Operator):
    """Riordina il tavolo: impila le composizioni nell'ordine dei canali, la più bassa
    resta dov'è"""

    bl_idname = "gp2m.table_stack"
    bl_label = "Riordina il tavolo"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return len(compositions(context.scene)) > 1

    def execute(self, context):
        stack(context.scene)
        return {"FINISHED"}


classes = (
    GP2M_UL_compositions,
    GP2M_PT_compositions,
    GP2M_OT_composition_toggle,
    GP2M_OT_composition_move,
    GP2M_OT_composition_duplicate,
    GP2M_OT_composition_remove,
    GP2M_OT_composition_frame,
    GP2M_OT_table_stack,
)


def register():
    bpy.types.Scene.gp2m_composition_index = IntProperty(
        name="Composizione attiva", get=_get_index, set=_set_index, options={"SKIP_SAVE"})


def unregister():
    del bpy.types.Scene.gp2m_composition_index
