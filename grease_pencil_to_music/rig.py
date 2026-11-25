# SPDX-License-Identifier: GPL-3.0-or-later
"""The rig of a composition: handles you drag in Object Mode, in the style of the
Frame by Plane rigs.

* Four handles, drawn as gizmos at a fixed size on screen (they never get tiny when
  you zoom out, nor huge when you zoom in): light, with a dark rim; under the mouse
  and while dragged they take the theme's Active Object color, like a selected object.
  - on the right edge: the length of the timeline (snaps to beats, Ctrl: free);
  - on top of the playhead, a box in the theme's playhead color: moves the scene's
    current frame, like the playhead of the Timeline;
  - above and below the keyboard: show or hide octaves on top / at the bottom
    (the drawing never moves, see :func:`board.shift_octaves`).
  They show only in Object Mode (and with the viewport's Gizmos overlay on).
* Gizmos are clicked before objects, so dragging a handle never selects the board;
  it runs ``gp2m.rig_drag``, a modal operator: while dragging only the handle moves
  (cheap), the board and the sound change once, on release (one Undo step).

Version 0.0.22 drew the handles as a third Grease Pencil object, "<composition> ·
Rig": it is removed when found (:func:`remove_legacy`, :func:`remove_orphans`).
"""

import math

import blf
import bpy
import gpu
from bpy.props import EnumProperty, StringProperty
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector
from mathutils.geometry import intersect_line_plane

from . import board, theme

RIG_ROLE = "gp2m_rig"  # custom property on the rig object of 0.0.22
RIG_SUFFIX = " · Rig"
RIG_DEPTH = -0.004  # just in front of the drawing

LENGTH, HEAD, OCT_TOP, OCT_BOTTOM = "LENGTH", "HEAD", "OCT_TOP", "OCT_BOTTOM"
HANDLE_NAMES = {
    LENGTH: "Maniglia durata",
    HEAD: "Maniglia testina",
    OCT_TOP: "Maniglia ottave sopra",
    OCT_BOTTOM: "Maniglia ottave sotto",
}
HANDLE_ITEMS = tuple((key, name, "") for key, name in HANDLE_NAMES.items())

HEAD_LIFT = 0.24  # the playhead box sits this high above the grid (over the time labels)
PAD = 6.0  # pixels between the board edge and a handle


# --- Where the handles are (board coordinates: x time, z pitch) ---------------------

def handle_room(settings):
    """Room (board units) kept above and below a board for the handles."""
    return 0.4


def handle_point(comp, handle, playhead_x=0.0):
    """Anchor of a handle on the board; the handle is drawn beside it, outside the
    board, at a fixed distance in pixels."""
    s = comp.gp2m
    rows, width, top = board.dimensions(s)
    if handle == LENGTH:
        return width, top / 2.0
    if handle == HEAD:
        return playhead_x, top + HEAD_LIFT
    keys = -board.key_width(s) / 2.0
    if handle == OCT_TOP:
        return keys, top
    return keys, 0.0


def playhead_x(comp, depsgraph=None):
    """Current x of the playhead (the driven translation of its layer)."""
    obj = comp
    if depsgraph is not None:
        obj = comp.evaluated_get(depsgraph)
    layer = obj.data.layers.get(board.HEAD_LAYER)
    return float(layer.translation[0]) if layer is not None else 0.0


# --- Shapes (pixels, in the board plane: x right, z up) ------------------------------

def _tris_fan(points, centre):
    cx, cz = centre
    out = []
    n = len(points)
    for i in range(n):
        (x0, z0), (x1, z1) = points[i], points[(i + 1) % n]
        out.extend(((cx, 0.0, cz), (x0, 0.0, z0), (x1, 0.0, z1)))
    return out


def pill(cx, cz, hw, hh, steps=10):
    """A rounded rectangle (a stadium when one side is the diameter) as triangles."""
    r = min(hw, hh)
    points = []
    for corner, (ox, oz) in enumerate(((hw - r, hh - r), (-(hw - r), hh - r),
                                       (-(hw - r), -(hh - r)), (hw - r, -(hh - r)))):
        for i in range(steps + 1):
            a = math.pi / 2.0 * (corner + i / steps)
            points.append((cx + ox + r * math.cos(a), cz + oz + r * math.sin(a)))
    return _tris_fan(points, (cx, cz))


def rounded_box(cx, cz, hw, hh, radius, steps=5):
    radius = min(radius, hw, hh)
    points = []
    for corner, (ox, oz) in enumerate(((hw - radius, hh - radius), (-(hw - radius), hh - radius),
                                       (-(hw - radius), -(hh - radius)),
                                       (hw - radius, -(hh - radius)))):
        for i in range(steps + 1):
            a = math.pi / 2.0 * (corner + i / steps)
            points.append((cx + ox + radius * math.cos(a), cz + oz + radius * math.sin(a)))
    return _tris_fan(points, (cx, cz))


def triangle(cx, cz, dx, dz, size):
    """A filled arrow head pointing to (dx, dz), centred on (cx, cz)."""
    sx, sz = -dz, dx
    tip = (cx + dx * size, 0.0, cz + dz * size)
    back = (cx - dx * size * 0.7, cz - dz * size * 0.7)
    left = (back[0] + sx * size, 0.0, back[1] + sz * size)
    right = (back[0] - sx * size, 0.0, back[1] - sz * size)
    return [tip, left, right]


HEAD_BOX_HH = 8.0  # half height of the playhead box (pixels); its centre is this high + 3


def head_half_width(digits):
    """The playhead box widens with the frame number, like Blender's."""
    return max(11.0, 3.6 * digits + 5.0)


def handle_geometry(handle, digits=2):
    """(body, rim, glyphs) triangles of a handle around its anchor, in pixels."""
    if handle == LENGTH:
        cx, cz, hw, hh = PAD + 7.0, 0.0, 7.0, 19.0
        body = pill(cx, cz, hw, hh)
        rim = pill(cx, cz, hw + 1.5, hh + 1.5)
        glyphs = triangle(cx, cz + 6.5, 1.0, 0.0, 3.6) + triangle(cx, cz - 6.5, -1.0, 0.0, 3.6)
        return body, rim, glyphs
    if handle == HEAD:  # Blender's playhead: a box on the line, with a tip
        cx, cz, hw, hh = 0.0, HEAD_BOX_HH + 3.0, head_half_width(digits), HEAD_BOX_HH
        body = rounded_box(cx, cz, hw, hh, 3.0) + [(-4.0, 0.0, 3.5), (4.0, 0.0, 3.5),
                                                   (0.0, 0.0, -1.0)]
        rim = rounded_box(cx, cz, hw + 1.5, hh + 1.5, 4.5) + [(-6.0, 0.0, 3.0),
                                                              (6.0, 0.0, 3.0),
                                                              (0.0, 0.0, -3.0)]
        glyphs = []
        return body, rim, glyphs
    up = 1.0 if handle == OCT_TOP else -1.0
    cx, cz, hw, hh = 0.0, up * (PAD + 7.0), 17.0, 7.0
    body = pill(cx, cz, hw, hh)
    rim = pill(cx, cz, hw + 1.5, hh + 1.5)
    glyphs = triangle(cx - 6.0, cz, 0.0, up, 3.6) + triangle(cx + 6.0, cz, 0.0, -up, 3.6)
    return body, rim, glyphs


# --- The drawn rig of 0.0.22 (removed) --------------------------------------------------

def is_rig(obj):
    return obj is not None and bool(obj.get(RIG_ROLE))


def rig_object(comp):
    for child in comp.children:
        if is_rig(child):
            return child
    return None


def _remove(obj):
    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if data is not None and data.users == 0 and isinstance(data, bpy.types.GreasePencil):
        bpy.data.grease_pencils.remove(data)


def remove_legacy(comp):
    """Remove the Grease Pencil rig of 0.0.22 under ``comp``; True if there was one."""
    found = False
    for child in list(comp.children):
        if is_rig(child):
            _remove(child)
            found = True
    return found


def remove_orphans():
    """Rig objects of 0.0.22 (the handles are gizmos now)."""
    for obj in list(bpy.data.objects):
        if is_rig(obj):
            _remove(obj)
    for name in ("GP2M Rig durata", "GP2M Rig testina", "GP2M Rig ottave"):
        material = bpy.data.materials.get(name)
        if material is not None and material.users == 0:
            bpy.data.materials.remove(material)


# --- While dragging ------------------------------------------------------------------------

_drag = {}  # (composition name, handle) -> preview offset (dx, dz) in board units


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
        _drag[(self.name, self.handle)] = (0.0, 0.0)
        context.window_manager.modal_handler_add(self)
        self._update(context, event)
        return {"RUNNING_MODAL"}

    def _update(self, context, event):
        comp = self._comp()
        point = board_point(context, comp, (event.mouse_region_x, event.mouse_region_y))
        if comp is None or point is None:
            return
        s = comp.gp2m
        key = (self.name, self.handle)
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
            _drag[key] = ((seconds - s.length) * s.seconds_width, 0.0)
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
            _drag[key] = (0.0, steps * octave * (1.0 if edge == "TOP" else -1.0))
            sign = "+" if steps > 0 else ""
            context.area.header_text_set(
                f"Ottave {'sopra' if edge == 'TOP' else 'sotto'}: {sign}{steps}")
        context.area.tag_redraw()

    def _reset_preview(self, comp=None):
        _drag.pop((self.name, self.handle), None)
        board.tag_redraw_views()

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

def _gizmo_size(context):
    try:
        return max(float(context.preferences.view.gizmo_size), 1.0)
    except (AttributeError, TypeError):
        return 75.0


class GP2M_GT_handle(bpy.types.Gizmo):
    """A rig handle: light body, dark rim, theme accent under the mouse and while dragged."""

    bl_idname = "GP2M_GT_handle"
    __slots__ = ("gp2m_body", "gp2m_rim", "gp2m_glyphs", "gp2m_handle", "gp2m_comp",
                 "gp2m_digits")

    def setup(self):
        self.gp2m_body = self.gp2m_rim = self.gp2m_glyphs = None
        self.gp2m_handle = ""
        self.gp2m_comp = ""
        self.gp2m_digits = 0
        # A fixed size on screen (see draw_prepare), drawn also during the drag.
        self.use_draw_scale = True
        self.use_draw_modal = True

    def set_handle(self, handle, digits=2):
        if self.gp2m_handle == handle and self.gp2m_body is not None \
                and (handle != HEAD or digits == self.gp2m_digits):
            return
        self.gp2m_handle = handle
        self.gp2m_digits = digits
        body, rim, glyphs = handle_geometry(handle, digits)
        self.gp2m_body = self.new_custom_shape("TRIS", body)
        self.gp2m_rim = self.new_custom_shape("TRIS", rim)
        self.gp2m_glyphs = self.new_custom_shape("TRIS", glyphs) if glyphs else None

    def _part(self, shape, color, alpha=1.0):
        self.color = color[:3]
        self.color_highlight = color[:3]
        self.alpha = alpha
        self.alpha_highlight = alpha
        self.draw_custom_shape(shape)

    def draw(self, context):
        if self.gp2m_body is None:
            return
        colors = theme.handle_colors(context)
        dragged = (self.gp2m_comp, self.gp2m_handle) in _drag
        if self.gp2m_handle == HEAD:
            body = colors["playhead_hover"] if (self.is_highlight or dragged) \
                else colors["playhead"]
        elif dragged:
            body = colors["active"]
        elif self.is_highlight:
            body = colors["hover"]
        else:
            body = colors["idle"]
        rim = colors["rim"]
        self._part(self.gp2m_rim, rim[:3], rim[3])
        self._part(self.gp2m_body, body)
        if self.gp2m_glyphs is not None:
            self._part(self.gp2m_glyphs, colors["glyph"])
        if self.gp2m_handle == HEAD:
            self._draw_frame(context, colors["text"])

    def _draw_frame(self, context, color):
        """The current frame inside the playhead box, like in the Timeline."""
        region, rv3d = context.region, context.region_data
        if region is None or rv3d is None:
            return
        anchor = view3d_utils.location_3d_to_region_2d(region, rv3d,
                                                       self.matrix_basis.translation)
        if anchor is None:
            return
        ui = context.preferences.system.ui_scale
        text = str(context.scene.frame_current)
        font = 0
        blf.size(font, 10.0 * ui)
        width, height = blf.dimensions(font, text)
        ortho = Matrix.Identity(4)
        ortho[0][0], ortho[1][1] = 2.0 / region.width, 2.0 / region.height
        ortho[0][3] = ortho[1][3] = -1.0
        with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
            gpu.matrix.load_identity()
            gpu.matrix.load_projection_matrix(ortho)
            blf.color(font, *color[:3], 1.0)
            blf.position(font, round(anchor.x - width / 2.0),
                         round(anchor.y + (HEAD_BOX_HH + 3.0) * ui - height / 2.0), 0.0)
            blf.draw(font, text)

    def draw_select(self, context, select_id):
        if self.gp2m_rim is not None:
            self.draw_custom_shape(self.gp2m_rim, select_id=select_id)


def _compositions(context):
    for obj in context.visible_objects:
        if obj.type == "GREASEPENCIL" and obj.gp2m.is_composition:
            yield obj


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
        return any(True for _ in _compositions(context))

    def setup(self, context):
        self.handles = {}
        self._sync(context)

    def _sync(self, context):
        wanted = {}
        for comp in _compositions(context):
            for handle in HANDLE_NAMES:
                wanted[(comp.name, handle)] = comp
        for key in [key for key in self.handles if key not in wanted]:
            self.gizmos.remove(self.handles.pop(key))
        for key in wanted:
            if key in self.handles:
                continue
            gz = self.gizmos.new(GP2M_GT_handle.bl_idname)
            gz.set_handle(key[1])
            gz.gp2m_comp = key[0]
            op = gz.target_set_operator(GP2M_OT_rig_drag.bl_idname)
            op.name, op.handle = key[0], key[1]
            self.handles[key] = gz

    def refresh(self, context):
        self._sync(context)

    def draw_prepare(self, context):
        depsgraph = context.evaluated_depsgraph_get()
        # Blender scales a draw-scaled gizmo by the Gizmo Size preference and the UI
        # scale: with this, one unit of the shapes is one pixel.
        scale = 1.0 / _gizmo_size(context)
        for (name, handle), gz in self.handles.items():
            comp = bpy.data.objects.get(name)
            if comp is None or not comp.gp2m.is_composition:
                gz.hide = True
                continue
            gz.hide = False
            x, z = handle_point(comp, handle, playhead_x(comp, depsgraph)
                                if handle == HEAD else 0.0)
            dx, dz = _drag.get((name, handle), (0.0, 0.0))
            world = comp.matrix_world
            location = world @ Vector((x + dx, RIG_DEPTH, z + dz))
            rotation = world.to_quaternion().to_matrix().to_4x4()
            gz.matrix_basis = Matrix.Translation(location) @ rotation
            gz.scale_basis = scale
            if handle == HEAD:
                gz.set_handle(HEAD, len(str(context.scene.frame_current)))


classes = (GP2M_OT_rig_drag, GP2M_GT_handle, GP2M_GGT_rig)
