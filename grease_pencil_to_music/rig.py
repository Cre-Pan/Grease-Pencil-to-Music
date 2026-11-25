# SPDX-License-Identifier: GPL-3.0-or-later
"""The rig of a composition: drawn handles you drag in Object Mode.

* "<composition> · Rig", a third Grease Pencil object (child of the composition,
  locked, not selectable, never rendered), holds the handles drawn as strokes:
  - on the right edge: the length of the timeline (snaps to beats, Ctrl: free);
  - above the grid, on the playhead: moves the scene's current frame;
  - above and below the keyboard: show or hide octaves on top / at the bottom
    (the drawing never moves, see :func:`board.shift_octaves`).
  It is visible only in Object Mode.
* A gizmo group puts an invisible gizmo on each handle. Gizmos are clicked before
  objects, so dragging a handle never selects the board; it runs
  ``gp2m.rig_drag``, a modal operator: while dragging only the drawn handle moves
  (cheap), the board and the sound change once, on release (one Undo step).
"""

import math

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector
from mathutils.geometry import intersect_line_plane

from . import board

RIG_ROLE = "gp2m_rig"  # custom property on the rig object
RIG_SUFFIX = " · Rig"
RIG_DEPTH = -0.004  # just in front of the drawing

LENGTH, HEAD, OCT_TOP, OCT_BOTTOM = "LENGTH", "HEAD", "OCT_TOP", "OCT_BOTTOM"
HANDLE_LAYERS = {
    LENGTH: "Maniglia durata",
    HEAD: "Maniglia testina",
    OCT_TOP: "Maniglia ottave sopra",
    OCT_BOTTOM: "Maniglia ottave sotto",
}
RIG_MATERIALS = {
    "GP2M Rig durata": ((1.0, 0.82, 0.25, 1.0), (1.0, 0.82, 0.25, 0.35)),
    "GP2M Rig testina": ((1.0, 0.25, 0.2, 1.0), (1.0, 0.25, 0.2, 0.45)),
    "GP2M Rig ottave": ((0.45, 0.85, 1.0, 1.0), (0.45, 0.85, 1.0, 0.3)),
}
HANDLE_MATERIAL = {LENGTH: "GP2M Rig durata", HEAD: "GP2M Rig testina",
                   OCT_TOP: "GP2M Rig ottave", OCT_BOTTOM: "GP2M Rig ottave"}
HANDLE_ITEMS = tuple((key, name, "") for key, name in HANDLE_LAYERS.items())


# --- Where the handles are (board coordinates: x time, z pitch) ---------------------

def handle_size(settings):
    """Half width and half height of a handle, from the board's scale."""
    unit = max(0.12, min(0.5, 2.2 * settings.row_height))
    return unit, unit * 1.3


def handle_point(comp, handle, playhead_x=0.0):
    s = comp.gp2m
    rows, width, top = board.dimensions(s)
    hw, hh = handle_size(s)
    if handle == LENGTH:
        return width + hw + 0.04, top / 2.0
    if handle == HEAD:
        return playhead_x, top + 0.3 + hh
    keys = -board.key_width(s) / 2.0
    if handle == OCT_TOP:
        return keys, top + 0.08 + hh
    return keys, -0.08 - hh


def playhead_x(comp, depsgraph=None):
    """Current x of the playhead (the driven translation of its layer)."""
    obj = comp
    if depsgraph is not None:
        obj = comp.evaluated_get(depsgraph)
    layer = obj.data.layers.get(board.HEAD_LAYER)
    return float(layer.translation[0]) if layer is not None else 0.0


# --- Hand-drawn strokes ---------------------------------------------------------------

def _wobble(points, seed, amount):
    """A slightly shaky line, the same every time (it looks drawn, it never flickers)."""
    out = []
    for i, (x, z) in enumerate(points):
        k = seed * 12.9898 + i * 78.233
        out.append((x + amount * math.sin(k), z + amount * math.cos(k * 1.3)))
    return out


def _pill(cx, cz, hw, hh, steps=28):
    """Rounded rectangle (a stadium) around (cx, cz)."""
    r = min(hw, hh)
    points = []
    for corner, (ox, oz) in enumerate(((hw - r, hh - r), (-(hw - r), hh - r),
                                       (-(hw - r), -(hh - r)), (hw - r, -(hh - r)))):
        for i in range(steps // 4 + 1):
            a = math.pi / 2.0 * (corner + i / (steps // 4))
            points.append((cx + ox + r * math.cos(a), cz + oz + r * math.sin(a)))
    return points


def _arrow(cx, cz, dx, dz, size):
    """Shaft and head of an arrow pointing to (dx, dz) (unit), centred on (cx, cz)."""
    tip = (cx + dx * size, cz + dz * size)
    tail = (cx - dx * size, cz - dz * size)
    side = (-dz, dx)
    head = size * 0.55
    left = (tip[0] - dx * head + side[0] * head * 0.8, tip[1] - dz * head + side[1] * head * 0.8)
    right = (tip[0] - dx * head - side[0] * head * 0.8, tip[1] - dz * head - side[1] * head * 0.8)
    return [[tail, tip], [left, tip, right]]


def handle_specs(comp, handle, index):
    """Strokes of one handle, drawn around its point (playhead handle around x=0: its
    layer is moved by the same driver as the playhead)."""
    s = comp.gp2m
    hw, hh = handle_size(s)
    cx, cz = handle_point(comp, handle, 0.0)
    line = 0.007 * hw / 0.26
    wobble = 0.004 * hw / 0.26
    specs = []
    seed = sum(ord(c) for c in handle)
    if handle == HEAD:  # a drop hanging on the playhead line, tip down
        radius = hw * 0.75
        centre = cz + hh - radius
        points = []
        for i in range(21):
            a = -math.pi / 6.0 + (math.pi * 4.0 / 3.0) * i / 20.0
            points.append((cx + radius * math.cos(a), centre + radius * math.sin(a)))
        drop = _wobble(points + [(cx, cz - hh)], seed, wobble)
        specs.append((drop, line, index, "fill"))
        specs.append((drop + drop[:1], line, index, "line"))
        return specs
    if handle == LENGTH:
        outline = _pill(cx, cz, hw * 0.75, hh * 1.6)
        arrows = _arrow(cx, cz + hh * 0.45, 1.0, 0.0, hw * 0.45) + \
            _arrow(cx, cz - hh * 0.45, -1.0, 0.0, hw * 0.45)
    else:
        outline = _pill(cx, cz, hw * 1.2, hh * 0.75)
        up = 1.0 if handle == OCT_TOP else -1.0
        arrows = _arrow(cx - hw * 0.4, cz, 0.0, up, hh * 0.45) + \
            _arrow(cx + hw * 0.4, cz, 0.0, -up, hh * 0.3)
    outline = _wobble(outline, seed, wobble)
    specs.append((outline, line, index, "fill"))  # fill first, lines on top
    specs.append((outline + outline[:1], line, index, "line"))
    for k, stroke in enumerate(arrows):
        specs.append((_wobble(stroke, seed + k + 1, wobble * 0.5), line, index, "line"))
    return specs


# --- The rig object -----------------------------------------------------------------

def is_rig(obj):
    return obj is not None and bool(obj.get(RIG_ROLE))


def rig_object(comp):
    for child in comp.children:
        if is_rig(child) and child.type == "GREASEPENCIL":
            return child
    return None


def rig_owner(rig):
    owner = rig.parent
    if owner is not None and owner.type == "GREASEPENCIL" and owner.gp2m.is_composition:
        return owner
    return None


def ensure_rig(comp):
    rig = rig_object(comp)
    name = comp.name + RIG_SUFFIX
    if rig is None:
        data = bpy.data.grease_pencils.new(name)
        rig = bpy.data.objects.new(name, data)
        rig[RIG_ROLE] = True
        for collection in comp.users_collection or (bpy.context.scene.collection,):
            collection.objects.link(rig)
        rig.parent = comp
        rig.matrix_parent_inverse.identity()
        rig.lock_location = rig.lock_rotation = rig.lock_scale = (True, True, True)
        rig.hide_select = True  # clicks go to the gizmos or to the composition
        rig.hide_render = True
        rig.show_in_front = True
    elif rig.data is None or rig.data.users > 1:
        rig.data = bpy.data.grease_pencils.new(name)
    if rig.name != name:
        rig.name = name
    if rig.data.name != rig.name:
        rig.data.name = rig.name
    rig.location = (0.0, RIG_DEPTH, 0.0)
    rig.rotation_euler = (0.0, 0.0, 0.0)
    rig.scale = (1.0, 1.0, 1.0)
    return rig


def _ensure_materials(gp):
    index = {}
    names = [m.name if m else "" for m in gp.materials]
    for name, (stroke, fill) in RIG_MATERIALS.items():
        material = board.gp_material(name, stroke, fill)
        material[board.BOARD_FLAG] = True
        if name not in names:
            gp.materials.append(material)
            names.append(name)
        index[name] = names.index(name)
    return index


def rebuild(comp, scene=None):
    """(Re)draw the handles; called with the board's rebuild."""
    scene = scene or bpy.context.scene
    rig = ensure_rig(comp)
    gp = rig.data
    index = _ensure_materials(gp)
    for layer in list(gp.layers):
        gp.layers.remove(layer)
    frame = board._first_frame(scene)
    for handle, layer_name in HANDLE_LAYERS.items():
        layer = gp.layers.new(layer_name, set_active=False)
        layer.use_lights = False
        board._add_strokes(layer.frames.new(frame).drawing,
                           handle_specs(comp, handle, index[HANDLE_MATERIAL[handle]]))
        layer.lock = True
    _drive_head(comp, gp, scene)
    sync_visibility()
    return rig


def _drive_head(comp, gp, scene):
    """The playhead handle moves with the playhead: same driver expression."""
    path = f'layers["{HANDLE_LAYERS[HEAD]}"].translation'
    try:
        gp.driver_remove(path, 0)
    except TypeError:
        pass
    source = comp.data.animation_data
    curve = source.drivers.find(f'layers["{board.HEAD_LAYER}"].translation', index=0) \
        if source is not None else None
    if curve is None:
        return
    driver = gp.driver_add(path, 0).driver
    driver.type = "SCRIPTED"
    for var_in in curve.driver.variables:
        var = driver.variables.new()
        var.name = var_in.name
        var.targets[0].id_type = var_in.targets[0].id_type
        var.targets[0].id = var_in.targets[0].id
        var.targets[0].data_path = var_in.targets[0].data_path
    driver.expression = curve.driver.expression


def sync_head_driver(comp):
    """Keep the handle's driver on the playhead's (sequence offset, sections)."""
    rig = rig_object(comp)
    if rig is None or rig.data is None or rig.data.animation_data is None:
        return
    source = comp.data.animation_data
    curve = source.drivers.find(f'layers["{board.HEAD_LAYER}"].translation', index=0) \
        if source is not None else None
    mine = rig.data.animation_data.drivers.find(
        f'layers["{HANDLE_LAYERS[HEAD]}"].translation', index=0)
    if curve is not None and mine is not None \
            and mine.driver.expression != curve.driver.expression:
        mine.driver.expression = curve.driver.expression


def remove_orphans():
    """Rigs of deleted compositions (or copies of a rig made with Shift+D)."""
    for obj in list(bpy.data.objects):
        if not is_rig(obj):
            continue
        owner = rig_owner(obj)
        if owner is None or rig_object(owner) != obj:
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data is not None and data.users == 0:
                bpy.data.grease_pencils.remove(data)


def _object_mode():
    context = bpy.context
    mode = getattr(context, "mode", "OBJECT")
    return mode == "OBJECT"


def sync_visibility():
    """The handles show only in Object Mode."""
    hide = not _object_mode()
    for obj in bpy.data.objects:
        if is_rig(obj) and obj.hide_viewport != hide:
            obj.hide_viewport = hide


# --- Dragging --------------------------------------------------------------------------

def board_point(context, comp, mouse):
    """Board coordinates (x, z) under the mouse, on the plane of the composition."""
    region, rv3d = context.region, context.region_data
    if region is None or rv3d is None:
        return None
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse)
    world = comp.matrix_world
    normal = (world.to_3x3() @ Vector((0.0, 1.0, 0.0))).normalized()
    hit = intersect_line_plane(origin, origin + direction, world.translation, normal)
    if hit is None:
        return None
    local = world.inverted_safe() @ hit
    return local.x, local.z


def snap_length(settings, seconds, free=False):
    seconds = min(max(seconds, 1.0), 300.0)
    if free:
        return round(seconds, 3)
    step = 60.0 / settings.bpm if settings.show_beats and settings.bpm > 0 else 0.5
    return min(max(round(seconds / step) * step, 1.0), 300.0)


def frame_at(scene, comp, x):
    from . import engine
    s = comp.gp2m
    fps = scene.render.fps / scene.render.fps_base
    offset = engine.state(comp).get("offset_frames", 0)
    seconds = min(max(x / max(s.seconds_width, 1e-9), 0.0), s.length)
    return int(round(scene.frame_start + offset + seconds * fps))


class GP2M_OT_rig_drag(bpy.types.Operator):
    """Trascina la maniglia: durata, testina o ottave della tavola"""

    bl_idname = "gp2m.rig_drag"
    bl_label = "Trascina maniglia"
    bl_options = {"REGISTER", "UNDO", "BLOCKING", "INTERNAL"}

    name: StringProperty()
    handle: EnumProperty(items=HANDLE_ITEMS)

    def _comp(self):
        obj = bpy.data.objects.get(self.name)
        return obj if obj is not None and obj.gp2m.is_composition else None

    def _layer(self, comp):
        rig = rig_object(comp)
        if rig is None:
            return None
        return rig.data.layers.get(HANDLE_LAYERS[self.handle])

    def invoke(self, context, event):
        comp = self._comp()
        if comp is None or context.area is None or context.area.type != "VIEW_3D":
            return {"CANCELLED"}
        point = board_point(context, comp, (event.mouse_region_x, event.mouse_region_y))
        if point is None:
            return {"CANCELLED"}
        self.start = point
        self.frame = context.scene.frame_current
        self.value = None
        context.window_manager.modal_handler_add(self)
        self._update(context, event)
        return {"RUNNING_MODAL"}

    def _update(self, context, event):
        comp = self._comp()
        point = board_point(context, comp, (event.mouse_region_x, event.mouse_region_y))
        if comp is None or point is None:
            return
        s = comp.gp2m
        layer = self._layer(comp)
        x, z = point
        if self.handle == HEAD:
            frame = frame_at(context.scene, comp, x)
            if context.scene.frame_current != frame:
                context.scene.frame_current = frame
            self.value = frame
            context.area.header_text_set(f"Testina: fotogramma {frame}")
        elif self.handle == LENGTH:
            seconds = snap_length(s, x / max(s.seconds_width, 1e-9), event.ctrl)
            self.value = seconds
            if layer is not None:
                layer.translation = ((seconds - s.length) * s.seconds_width, 0.0, 0.0)
            context.area.header_text_set(
                f"Durata: {seconds:g} s   (Ctrl: senza aggancio ai battiti)")
        else:
            octave = 12 * s.row_height
            steps = round((z - self.start[1]) / octave)
            if self.handle == OCT_BOTTOM:
                steps = -steps  # dragging down shows more octaves below
            edge = "TOP" if self.handle == OCT_TOP else "BOTTOM"
            steps = board.octave_steps(s, edge, steps)
            self.value = steps
            if layer is not None:
                shift = steps * octave * (1.0 if edge == "TOP" else -1.0)
                layer.translation = (0.0, 0.0, shift)
            sign = "+" if steps > 0 else ""
            context.area.header_text_set(
                f"Ottave {'sopra' if edge == 'TOP' else 'sotto'}: {sign}{steps}")
        context.area.tag_redraw()

    def _reset_preview(self, comp):
        layer = self._layer(comp) if comp is not None else None
        if layer is not None and self.handle != HEAD:
            layer.translation = (0.0, 0.0, 0.0)

    def modal(self, context, event):
        if event.type == "MOUSEMOVE":
            self._update(context, event)
            return {"RUNNING_MODAL"}
        if event.type in {"LEFTMOUSE", "RET", "NUMPAD_ENTER"} and event.value == "RELEASE":
            return self._finish(context)
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            comp = self._comp()
            self._reset_preview(comp)
            context.scene.frame_current = self.frame
            context.area.header_text_set(None)
            return {"CANCELLED"}
        if event.type in {"LEFT_CTRL", "RIGHT_CTRL"}:
            self._update(context, event)
        return {"RUNNING_MODAL"}

    def _finish(self, context):
        context.area.header_text_set(None)
        comp = self._comp()
        if comp is None:
            return {"CANCELLED"}
        self._reset_preview(comp)
        return {"FINISHED"} if apply(comp, self.handle, self.value) else {"CANCELLED"}


def apply(comp, handle, value):
    """Apply the value of a drag; True when something changed."""
    s = comp.gp2m
    if value is None:
        return False
    if handle == HEAD:
        return True
    if handle == LENGTH:
        if abs(value - s.length) < 1e-6:
            return False
        s.length = value
        return True
    edge = "TOP" if handle == OCT_TOP else "BOTTOM"
    return bool(value) and bool(board.shift_octaves(comp, edge, value))


# --- Gizmos --------------------------------------------------------------------------------

class GP2M_GT_handle(bpy.types.Gizmo):
    """An invisible hit area over a drawn handle; it glows under the mouse."""

    bl_idname = "GP2M_GT_handle"

    def setup(self):
        self.shape = None
        self.size = (0.0, 0.0)

    def set_size(self, hw, hh):
        if self.shape is None or self.size != (hw, hh):
            self.size = (hw, hh)
            a, b, c, d = (-hw, 0, -hh), (hw, 0, -hh), (hw, 0, hh), (-hw, 0, hh)
            self.shape = self.new_custom_shape("TRIS", (a, b, c, a, c, d))

    def draw(self, context):
        if self.shape is not None and self.is_highlight:
            self.draw_custom_shape(self.shape)

    def draw_select(self, context, select_id):
        if self.shape is not None:
            self.draw_custom_shape(self.shape, select_id=select_id)


class GP2M_GGT_rig(bpy.types.GizmoGroup):
    bl_idname = "GP2M_GGT_rig"
    bl_label = "Maniglie della composizione"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D", "PERSISTENT", "SHOW_MODAL_ALL"}

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT":
            return False
        return any(is_rig(obj) for obj in context.visible_objects)

    def setup(self, context):
        self.handles = {}
        self._sync(context)

    def _sync(self, context):
        wanted = {}
        for rig in context.visible_objects:
            if not is_rig(rig):
                continue
            comp = rig_owner(rig)
            if comp is None or comp.hide_get():
                continue
            for handle in HANDLE_LAYERS:
                wanted[(comp.name, handle)] = comp
        for key in [key for key in self.handles if key not in wanted]:
            self.gizmos.remove(self.handles.pop(key))
        for key, comp in wanted.items():
            if key in self.handles:
                continue
            gz = self.gizmos.new(GP2M_GT_handle.bl_idname)
            gz.use_draw_scale = False
            gz.use_draw_modal = False
            gz.color = (1.0, 1.0, 1.0)
            gz.alpha = 0.0
            gz.color_highlight = (1.0, 1.0, 1.0)
            gz.alpha_highlight = 0.18
            op = gz.target_set_operator(GP2M_OT_rig_drag.bl_idname)
            op.name, op.handle = key[0], key[1]
            self.handles[key] = gz

    def refresh(self, context):
        self._sync(context)

    def draw_prepare(self, context):
        depsgraph = context.evaluated_depsgraph_get()
        for (name, handle), gz in self.handles.items():
            comp = bpy.data.objects.get(name)
            if comp is None or not comp.gp2m.is_composition:
                gz.hide = True
                continue
            gz.hide = False
            s = comp.gp2m
            hw, hh = handle_size(s)
            if handle == LENGTH:
                hw, hh = hw * 0.75, hh * 1.6
            elif handle != HEAD:
                hw, hh = hw * 1.2, hh * 0.75
            gz.set_size(hw, hh)
            x, z = handle_point(comp, handle, playhead_x(comp, depsgraph)
                                if handle == HEAD else 0.0)
            gz.matrix_basis = comp.matrix_world @ Matrix.Translation((x, RIG_DEPTH, z))


classes = (GP2M_OT_rig_drag, GP2M_GT_handle, GP2M_GGT_rig)
