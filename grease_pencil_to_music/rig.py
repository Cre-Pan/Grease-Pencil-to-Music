# SPDX-License-Identifier: GPL-3.0-or-later
"""The rig of a composition: handles you drag in Object Mode, in the style of the
Frame by Plane rigs.

* Four handles, drawn as gizmos at a fixed size on screen (they never get tiny when
  you zoom out, nor huge when you zoom in): light, with a dark rim; under the mouse
  and while dragged they take the theme's Active Object color, like a selected object.
  - on the right edge: the length of the timeline (free, Ctrl: whole bars); board,
    sound and the meta-clip in the Sequencer follow while dragging;
  - on top of the playhead, a box in the theme's playhead color: moves the scene's
    current frame, like the playhead of the Timeline;
  - above and below the keyboard: show or hide keys on top / at the bottom, one key
    at a time (Ctrl: whole octaves; the drawing never moves, see :func:`board.shift_keys`);
    the rows come or go at that edge while dragging, the other edge stays still.
  They show only in Object Mode (and with the viewport's Gizmos overlay on).
* Gizmos are clicked before objects, so dragging a handle never selects the board;
  it runs ``gp2m.rig_drag``, a modal operator: the board follows while dragging, the
  sound once the handle is let go (one Undo step; Esc or right click put it back).

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


LABEL_OFFSET = {LENGTH: (PAD + 20.0, 0.0), OCT_TOP: (PAD + 22.0, PAD + 7.0),
                OCT_BOTTOM: (PAD + 22.0, -(PAD + 7.0))}  # value shown while dragging
TEXT_LIFT = -0.5  # the text a hair in front of the handle (handle units, -y)
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

def board_point(context, comp, mouse, world=None):
    """Board coordinates (x, z) under the mouse, on the plane of the composition
    (measured with ``world``, its matrix when the drag started, if given)."""
    region, rv3d = context.region, context.region_data
    if region is None or rv3d is None:
        return None
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse)
    world = comp.matrix_world if world is None else world
    normal = (world.to_3x3() @ Vector((0.0, 1.0, 0.0))).normalized()
    hit = intersect_line_plane(origin, origin + direction, world.translation, normal)
    if hit is None:
        return None
    local = world.inverted_safe() @ hit
    return local.x, local.z


BEATS_PER_BAR = 4  # the board has no meter: bars of 4/4


def bar_seconds(settings):
    return BEATS_PER_BAR * 60.0 / settings.bpm if settings.bpm > 0 else 2.0


def snap_to_bars(settings, seconds):
    bar = bar_seconds(settings)
    return round(seconds / bar) * bar


def length_value(settings, seconds, fps, bars=False):
    """Length for a drag: free (to the frame); with Ctrl on whole bars."""
    if bars:
        bar = bar_seconds(settings)
        seconds = max(bar, snap_to_bars(settings, seconds))
    else:
        seconds = round(seconds * fps) / fps
    return round(min(max(seconds, 1.0), 300.0), 4)


def _fps(scene):
    return scene.render.fps / scene.render.fps_base


def _preview_meta(scene, comp, seconds):
    """While the length is dragged the composition's meta-clip in the Sequencer follows
    at once (the sound follows after the pause, then the clip fits it again)."""
    from . import engine
    if comp.gp2m.use_sections:
        return
    meta = engine.meta_strip(scene, comp)
    if meta is None:
        return
    end = int(meta.left_handle + max(1, round(seconds * _fps(scene))))
    try:
        if meta.right_handle != end:
            meta.right_handle = end
    except (AttributeError, RuntimeError, ValueError):
        pass


def dragging():
    """True while a handle is dragged (the Sequencer sync waits)."""
    return bool(_drag)


def frame_at(scene, comp, x):
    from . import engine
    s = comp.gp2m
    fps = scene.render.fps / scene.render.fps_base
    offset = engine.state(comp).get("offset_frames", 0)
    seconds = min(max(x / max(s.seconds_width, 1e-9), 0.0), s.length)
    return int(round(scene.frame_start + offset + seconds * fps))


class _HandleMove:
    """Shared by the drag of a handle and G on the selected one."""

    grab = False  # G: follow the mouse until a click (Enter) confirms

    def _comp(self):
        obj = bpy.data.objects.get(self.name)
        return obj if obj is not None and obj.gp2m.is_composition else None

    def invoke(self, context, event):
        comp = self._comp()
        if comp is None or context.area is None or context.area.type != "VIEW_3D":
            return {"CANCELLED"}
        mouse = (event.mouse_region_x, event.mouse_region_y)
        # The keys below move the board origin while dragging: measure on the board
        # as it was when the drag started.
        self.world = comp.matrix_world.copy()
        point = board_point(context, comp, mouse, self.world)
        if point is None:
            return {"CANCELLED"}
        self.start = point
        self.applied = 0  # keys already shown (+) or hidden (-) while dragging
        self.mouse = mouse
        self.moved = False
        self.frame = context.scene.frame_current
        self.length = comp.gp2m.length
        self.head_x = playhead_x(comp, context.evaluated_depsgraph_get())
        self.value = None
        _drag[(self.name, self.handle)] = (0.0, 0.0, "")
        context.window_manager.modal_handler_add(self)
        if self.grab:
            self.moved = True
        return {"RUNNING_MODAL"}

    def _update(self, context, event):
        comp = self._comp()
        mouse = (event.mouse_region_x, event.mouse_region_y)
        if not self.moved:
            if abs(mouse[0] - self.mouse[0]) + abs(mouse[1] - self.mouse[1]) < 4:
                return  # a click selects the handle, it does not move it
            self.moved = True
        point = board_point(context, comp, mouse, self.world) if comp is not None else None
        if point is None:
            return
        s = comp.gp2m
        key = (self.name, self.handle)
        dx, dz = point[0] - self.start[0], point[1] - self.start[1]
        if self.handle == HEAD:
            x = self.head_x + dx
            if event.ctrl:  # on the bars
                width = max(s.seconds_width, 1e-9)
                x = snap_to_bars(s, x / width) * width
            frame = frame_at(context.scene, comp, x)
            if context.scene.frame_current != frame:
                context.scene.frame_current = frame
            self.value = frame
            _drag[key] = (0.0, 0.0, "")
        elif self.handle == LENGTH:
            # No snap (Ctrl: whole bars); the board, the sound and the meta-clip follow
            # while dragging, so the handle sits on the real edge.
            seconds = length_value(s, self.length + dx / max(s.seconds_width, 1e-9),
                                   _fps(context.scene), event.ctrl)
            self.value = seconds
            if abs(s.length - seconds) > 1e-6:
                s.length = seconds
            _preview_meta(context.scene, comp, seconds)
            _drag[key] = (0.0, 0.0, f"{seconds:.2f} s".replace(".", ","))
        else:
            # One key at a time; Ctrl: whole octaves.
            # The board follows while dragging (rows added or taken away at that
            # edge, the drawing and the other edge stay where they are).
            raw = dz / max(s.row_height, 1e-9)
            wanted = 12 * round(raw / 12.0) if event.ctrl else round(raw)
            if self.handle == OCT_BOTTOM:
                wanted = -wanted  # dragging down shows more keys below
            edge = "TOP" if self.handle == OCT_TOP else "BOTTOM"
            delta = board.key_steps(s, edge, wanted - self.applied)
            if event.ctrl:  # whole octaves from where the drag started
                delta = int((self.applied + delta) / 12) * 12 - self.applied
            if delta:
                self.applied += board.shift_keys(comp, edge, delta)
            steps = self.applied
            self.value = steps
            sign = "+" if steps > 0 else ""
            if not steps:
                label = ""
            elif steps % 12 == 0:
                label = f"{sign}{steps // 12} ott."
            else:
                label = f"{sign}{steps} tast{'o' if abs(steps) == 1 else 'i'}"
            _drag[key] = (0.0, 0.0, label)  # the handle sits on the real edge
        context.area.tag_redraw()

    def _reset_preview(self):
        _drag.pop((self.name, self.handle), None)
        board.tag_redraw_views()

    def _cancel(self, context):
        self._reset_preview()
        context.scene.frame_current = self.frame
        comp = self._comp()
        if comp is not None and self.handle == LENGTH and comp.gp2m.length != self.length:
            comp.gp2m.length = self.length
        if comp is not None and self.handle in (OCT_TOP, OCT_BOTTOM) and self.applied:
            edge = "TOP" if self.handle == OCT_TOP else "BOTTOM"
            board.shift_keys(comp, edge, -self.applied)  # back as it was
            self.applied = 0
        return {"CANCELLED"}

    def modal(self, context, event):
        if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            self._update(context, event)
            return {"RUNNING_MODAL"}
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            return self._cancel(context)
        confirm = {"RET", "NUMPAD_ENTER"}
        if event.type in confirm and event.value == "PRESS":
            return self._finish(context)
        if event.type == "LEFTMOUSE" and event.value == ("PRESS" if self.grab else "RELEASE"):
            return self._finish(context)
        if event.type in {"LEFT_CTRL", "RIGHT_CTRL"}:
            self._update(context, event)
        return {"RUNNING_MODAL"}

    def _finish(self, context):
        comp = self._comp()
        self._reset_preview()
        if comp is None:
            return {"CANCELLED"}
        if not self.moved:  # a click: select the handle (G then moves it)
            select(self.name, self.handle)
            return {"CANCELLED"}
        select(self.name, self.handle)
        if self.handle == LENGTH:  # already applied while dragging
            from . import engine
            engine.arrange_safe(context.scene)  # the meta-clip fits its sound again
            return {"FINISHED"} if abs(comp.gp2m.length - self.length) > 1e-6 \
                else {"CANCELLED"}
        if self.handle in (OCT_TOP, OCT_BOTTOM):  # already applied while dragging
            return {"FINISHED"} if self.applied else {"CANCELLED"}
        return {"FINISHED"} if apply(comp, self.handle, self.value) else {"CANCELLED"}


# --- Selection (a clicked handle; G moves it) ------------------------------------------------

_selected = [None]  # (composition name, handle) or None


def select(name, handle):
    _selected[0] = (name, handle) if name else None
    board.tag_redraw_views()


def selected():
    key = _selected[0]
    if key is None:
        return None
    obj = bpy.data.objects.get(key[0])
    if obj is None or obj.type != "GREASEPENCIL" or not obj.gp2m.is_composition:
        _selected[0] = None
        return None
    return key


class GP2M_OT_rig_drag(_HandleMove, bpy.types.Operator):
    """Trascina la maniglia (clic: la selezioni, poi G per spostarla)"""

    bl_idname = "gp2m.rig_drag"
    bl_label = "Trascina maniglia"
    bl_options = {"REGISTER", "UNDO", "BLOCKING", "INTERNAL"}

    name: StringProperty()
    handle: EnumProperty(items=HANDLE_ITEMS)


class GP2M_OT_rig_grab(_HandleMove, bpy.types.Operator):
    """Sposta la maniglia selezionata con il mouse, come G"""

    bl_idname = "gp2m.rig_grab"
    bl_label = "Sposta maniglia"
    bl_options = {"REGISTER", "UNDO", "BLOCKING", "INTERNAL"}
    grab = True

    name: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    handle: EnumProperty(items=HANDLE_ITEMS, options={"HIDDEN", "SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return (context.mode == "OBJECT" and context.area is not None
                and context.area.type == "VIEW_3D" and selected() is not None)

    def invoke(self, context, event):
        self.name, self.handle = selected()
        return _HandleMove.invoke(self, context, event)


class GP2M_OT_rig_deselect(bpy.types.Operator):
    """Deseleziona la maniglia (clic altrove o Esc); il clic prosegue verso la scena"""

    bl_idname = "gp2m.rig_deselect"
    bl_label = "Deseleziona maniglia"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return selected() is not None

    def invoke(self, context, event):
        select(None, None)
        return {"PASS_THROUGH"}


_keymaps = []


def register_keymap():
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:
        return
    # "Object Mode" comes before "3D View", where G is Blender's Move: with no handle
    # selected the poll fails and G goes on to move objects as usual.
    km = kc.keymaps.new(name="Object Mode")
    _keymaps.append((km, km.keymap_items.new(GP2M_OT_rig_grab.bl_idname, "G", "PRESS")))
    for key in ("LEFTMOUSE", "ESC"):
        _keymaps.append((km, km.keymap_items.new(GP2M_OT_rig_deselect.bl_idname, key, "PRESS")))


def unregister_keymap():
    for km, item in _keymaps:
        try:
            km.keymap_items.remove(item)
        except (ReferenceError, RuntimeError):
            pass
    _keymaps.clear()


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
    edge = "TOP" if handle == OCT_TOP else "BOTTOM"  # value: keys (semitones)
    return bool(value) and bool(board.shift_keys(comp, edge, value))


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
        key = (self.gp2m_comp, self.gp2m_handle)
        dragged = key in _drag
        chosen = dragged or _selected[0] == key
        glyph = colors["glyph"]
        if self.gp2m_handle == HEAD:
            # Exactly the Timeline's playhead; hover / selection show on the rim.
            body = colors["playhead"]
            rim = (*colors["active"], 1.0) if chosen else \
                (*colors["hover"], 0.9) if self.is_highlight else colors["rim"]
        elif chosen:
            body, rim = colors["active"], colors["rim"]
        elif self.is_highlight:
            body, rim = colors["hover"], colors["rim"]
        else:  # "off": quiet until the mouse comes
            body, rim, glyph = colors["idle"], colors["rim_idle"], colors["glyph_idle"]
        self._part(self.gp2m_rim, rim[:3], rim[3])
        self._part(self.gp2m_body, body)
        if self.gp2m_glyphs is not None:
            self._part(self.gp2m_glyphs, glyph)
        if self.gp2m_handle == HEAD:
            self._draw_text(context, str(context.scene.frame_current), colors["text"],
                            (0.0, HEAD_BOX_HH + 3.0), "CENTER")
        elif dragged and _drag[key][2]:
            self._draw_text(context, _drag[key][2], colors["text"], LABEL_OFFSET[self.gp2m_handle],
                            "LEFT")

    def _draw_text(self, context, text, color, offset, align):
        """Text beside the handle (pixels from its anchor): the frame in the playhead
        box, like in the Timeline, or the value while dragging. It lies flat on the
        plane of the composition, like the handle: seen from the side it is
        foreshortened with the box, it never turns to face the view."""
        ui = context.preferences.system.ui_scale
        font = 0
        blf.size(font, 10.0 * ui)  # crisp glyphs, scaled back to handle units below
        width, height = blf.dimensions(font, text)
        width, height = width / ui, height / ui
        x = offset[0] - (width / 2.0 if align == "CENTER" else 0.0)
        z = offset[1] - height / 2.0
        # The shapes lie in the x/z plane of the gizmo (one unit: one pixel at UI
        # scale 1); blf writes in x/y: y goes to z, a hair in front of the body.
        place = Matrix(((1.0, 0.0, 0.0, x),
                        (0.0, 0.0, -1.0, TEXT_LIFT),
                        (0.0, 1.0, 0.0, z),
                        (0.0, 0.0, 0.0, 1.0)))
        with gpu.matrix.push_pop():
            gpu.matrix.multiply_matrix(self.matrix_world @ place
                                       @ Matrix.Scale(1.0 / ui, 4))
            blf.color(font, *color[:3], 1.0)
            blf.position(font, 0.0, 0.0, 0.0)
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
            gz.use_tooltip = False  # no message over the viewport
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
            dx, dz, _label = _drag.get((name, handle), (0.0, 0.0, ""))
            world = comp.matrix_world
            location = world @ Vector((x + dx, RIG_DEPTH, z + dz))
            rotation = world.to_quaternion().to_matrix().to_4x4()
            gz.matrix_basis = Matrix.Translation(location) @ rotation
            gz.scale_basis = scale
            if handle == HEAD:
                gz.set_handle(HEAD, len(str(context.scene.frame_current)))


classes = (GP2M_OT_rig_drag, GP2M_OT_rig_grab, GP2M_OT_rig_deselect, GP2M_GT_handle,
           GP2M_GGT_rig)
