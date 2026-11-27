# SPDX-License-Identifier: GPL-3.0-or-later
"""Edit Mode: a box, lasso or click on a copy of Array (or Simmetria) selects the stroke
it was copied from.

The copies are made by the layer's node modifier (stroke_mods): they are not strokes of
the drawing, so Blender's own selection never finds them. Every evaluated point keeps
the index it had in the drawing (``stroke_mods.SOURCE_ATTRIBUTE``): after Blender's
select operator has run (it is the last registered operator), the evaluated points in
the same box / lasso / around the same click select their source points. The copies
follow the original, so moving it moves them all, as in Blender.
"""

import bpy
from bpy_extras import view3d_utils
from mathutils import Vector

from . import board
from .stroke_mods import SOURCE_ATTRIBUTE

SELECT_OPERATORS = {"VIEW3D_OT_select_box", "VIEW3D_OT_select_lasso",
                    "VIEW3D_OT_select_circle", "VIEW3D_OT_select"}
CLICK_RADIUS = 12.0  # pixels around a click (Blender's own is about this)
_last = [None]  # the operator already handled (its pointer)


# --- Geometry on screen (pure) ---------------------------------------------------------------

def in_box(point, xmin, xmax, ymin, ymax):
    return xmin <= point[0] <= xmax and ymin <= point[1] <= ymax


def in_polygon(point, polygon):
    """Even-odd rule: is ``point`` inside the closed ``polygon`` [(x, y), ...]?"""
    x, y = point
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def hits(points, kind, props):
    """Indices of ``points`` (screen (x, y) or None) the selection covers. ``kind``:
    BOX (xmin, xmax, ymin, ymax), LASSO (path), CIRCLE (x, y, radius) or CLICK (location):
    the nearest point within CLICK_RADIUS."""
    if kind == "BOX":
        box = (props["xmin"], props["xmax"], props["ymin"], props["ymax"])
        return [i for i, p in enumerate(points) if p is not None and in_box(p, *box)]
    if kind == "LASSO":
        polygon = props["path"]
        if len(polygon) < 3:
            return []
        return [i for i, p in enumerate(points) if p is not None and in_polygon(p, polygon)]
    if kind == "CIRCLE":
        cx, cy, r = props["x"], props["y"], props["radius"]
        return [i for i, p in enumerate(points)
                if p is not None and (p[0] - cx) ** 2 + (p[1] - cy) ** 2 <= r * r]
    if kind == "CLICK":
        cx, cy = props["location"]
        best, best_d = None, CLICK_RADIUS ** 2
        for i, p in enumerate(points):
            if p is None:
                continue
            d = (p[0] - cx) ** 2 + (p[1] - cy) ** 2
            if d <= best_d:
                best, best_d = i, d
        return [] if best is None else [best]
    return []


def stroke_points(offsets, point_indices):
    """All the points of the strokes that hold ``point_indices`` (``offsets``: the
    drawing's curve offsets, one more than the strokes)."""
    import bisect
    out = set()
    for index in point_indices:
        curve = bisect.bisect_right(offsets, index) - 1
        if 0 <= curve < len(offsets) - 1:
            out.update(range(offsets[curve], offsets[curve + 1]))
    return out


# --- Reading the operator ---------------------------------------------------------------------

def _request(op):
    """(kind, props, action) of a select operator, or None when there is nothing to add.
    action: True selects, False deselects."""
    props = op.properties
    idname = op.bl_idname
    mode = getattr(props, "mode", "SET")
    if idname == "VIEW3D_OT_select":
        if getattr(props, "deselect", False) or getattr(props, "toggle", False):
            return None
        return "CLICK", {"location": tuple(props.location)}, True
    if mode not in {"SET", "ADD", "SUB"}:
        return None  # XOR / AND: left to Blender (originals only)
    action = mode != "SUB"
    if idname == "VIEW3D_OT_select_box":
        return "BOX", {k: getattr(props, k) for k in ("xmin", "xmax", "ymin", "ymax")}, action
    if idname == "VIEW3D_OT_select_lasso":
        return "LASSO", {"path": [tuple(item.loc) for item in props.path]}, action
    if idname == "VIEW3D_OT_select_circle":
        return "CIRCLE", {"x": props.x, "y": props.y, "radius": props.radius}, action
    return None


def _view_region(context):
    """The 3D View the selection happened in: the biggest one of the window (the
    operator does not say which; with one 3D View there is no doubt)."""
    best = None
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            for region in area.regions:
                if region.type == "WINDOW":
                    size = region.width * region.height
                    if best is None or size > best[0]:
                        best = (size, region, area.spaces.active.region_3d)
    return (best[1], best[2]) if best else (None, None)


def _selection(drawing):
    attribute = drawing.attributes.get(".selection")
    if attribute is None:
        attribute = drawing.attributes.new(".selection", "BOOLEAN", "POINT")
    return attribute


def _any_selected(obj):
    for layer in obj.data.layers:
        frame = layer.current_frame()
        attribute = frame.drawing.attributes.get(".selection") if frame else None
        if attribute is not None and any(item.value for item in attribute.data):
            return True
    return False


def _editable(layer):
    """Unlocked and shown, its groups too (Blender selects only there)."""
    node = layer
    while node is not None:
        if node.lock or node.hide:
            return False
        node = node.parent_group
    return True


def apply(context, request, region=None, rv3d=None):
    """Add the copies to what Blender's select operator selected. ``request``: (kind,
    props, action) as :func:`_request` gives. Returns the number of points it changed."""
    if request is None:
        return 0
    kind, props, action = request
    if region is None or rv3d is None:
        region, rv3d = _view_region(context)
    if region is None or rv3d is None:
        return 0
    objects = [obj for obj in context.objects_in_mode
               if obj.type == "GREASEPENCIL" and obj.gp2m.is_composition]
    if kind == "CLICK" and any(_any_selected(obj) for obj in objects):
        return 0  # Blender found a stroke under the mouse: that one wins
    stroke_mode = context.scene.tool_settings.gpencil_selectmode_edit != "POINT"
    depsgraph = context.evaluated_depsgraph_get()
    changed = 0
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        layers = {layer.name: layer for layer in board.user_layers(obj.data)
                  if _editable(layer)}
        for ev_layer in evaluated.data.layers:
            layer = layers.get(ev_layer.name)
            if layer is None:
                continue
            frame, ev_frame = layer.current_frame(), ev_layer.current_frame()
            if frame is None or ev_frame is None:
                continue
            source = ev_frame.drawing.attributes.get(SOURCE_ATTRIBUTE)
            if source is None:
                continue
            world = obj.matrix_world @ layer.matrix_local
            positions = ev_frame.drawing.attributes["position"].data
            screen = []
            for item in positions:
                p = view3d_utils.location_3d_to_region_2d(region, rv3d,
                                                          world @ Vector(item.vector))
                screen.append(None if p is None else (p.x, p.y))
            found = hits(screen, kind, props)
            if not found:
                continue
            sources = {source.data[i].value for i in found}
            drawing = frame.drawing
            count = len(drawing.attributes["position"].data)
            sources = {i for i in sources if 0 <= i < count}
            if stroke_mode:
                offsets = [item.value for item in drawing.curve_offsets]
                sources = stroke_points(offsets, sources)
            selection = _selection(drawing).data
            for i in sources:
                if selection[i].value != action:
                    selection[i].value = action
                    changed += 1
            if kind == "CLICK":
                break
        if changed:
            obj.data.update_tag()
        if kind == "CLICK" and changed:
            break
    if changed:
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
    return changed


def check(context=None):
    """After a depsgraph update: a new select operator in Edit Mode adds the copies."""
    context = context or bpy.context
    if context.mode != "EDIT_GREASE_PENCIL":
        return
    operators = context.window_manager.operators
    if not len(operators):
        return
    op = operators[-1]
    pointer = op.as_pointer()
    if pointer == _last[0]:
        return
    _last[0] = pointer
    if op.bl_idname in SELECT_OPERATORS:
        apply(context, _request(op))


# --- Gestures that select nothing in the drawing ----------------------------------------------
# Blender's box / lasso end "cancelled" when they change nothing (a box only around copies,
# with B or Shift): they are not registered, so check() never sees them. The keys and the
# select tools run them through this operator, which starts Blender's own and watches the
# mouse (it only passes the events on).

GESTURES = {"BOX": "select_box", "LASSO": "select_lasso"}


def _wanted(context):
    obj = context.active_object
    if context.mode != "EDIT_GREASE_PENCIL" or obj is None or obj.type != "GREASEPENCIL":
        return False
    return obj.gp2m.is_composition and any(
        m.name.startswith("GP2M Modificatori ") for m in obj.modifiers)


class GP2M_OT_select_copies(bpy.types.Operator):
    """Box / lasso select that also takes the copies of Array and Simmetria"""

    bl_idname = "gp2m.select_copies"
    bl_label = "Seleziona anche le copie"
    bl_options = {"INTERNAL"}

    kind: bpy.props.EnumProperty(items=(("BOX", "Box", ""), ("LASSO", "Lasso", "")))
    mode: bpy.props.EnumProperty(items=(("SET", "Set", ""), ("ADD", "Add", ""),
                                        ("SUB", "Sub", ""), ("XOR", "Xor", ""),
                                        ("AND", "And", "")), default="SET")
    wait_for_input: bpy.props.BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D" \
            and _wanted(context)

    def _local(self, x, y):
        return (x - self.region.x, y - self.region.y)

    def invoke(self, context, event):
        operator = getattr(bpy.ops.view3d, GESTURES[self.kind])
        arguments = {"mode": self.mode}
        if self.kind == "BOX":
            arguments["wait_for_input"] = self.wait_for_input
        result = operator("INVOKE_DEFAULT", **arguments)
        if "RUNNING_MODAL" not in result or self.mode in {"XOR", "AND"}:
            return {"FINISHED"}
        self.region = context.region
        self.rv3d = context.region_data
        self.action = self.mode != "SUB"
        if self.wait_for_input:  # B: the box starts at the next click
            self.start = None
            self.path = []
        else:  # dragged with a tool: from where the mouse was pressed
            self.start = self._local(event.mouse_prev_press_x, event.mouse_prev_press_y)
            self.path = [self.start, self._local(event.mouse_x, event.mouse_y)]
        self.button = None if self.wait_for_input else "LEFTMOUSE"
        self.target = "VIEW3D_OT_" + GESTURES[self.kind]
        self.window = context.window
        self.timer = context.window_manager.event_timer_add(0.02, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _running(self):
        """Blender's gesture is still going (it may eat the release of the mouse)."""
        return any(op.bl_idname == self.target for op in self.window.modal_operators)

    def _end(self, context, result):
        context.window_manager.event_timer_remove(self.timer)
        return result

    def modal(self, context, event):
        here = self._local(event.mouse_x, event.mouse_y)
        if event.type in {"ESC", "RIGHTMOUSE"} and self.button != "RIGHTMOUSE":
            return self._end(context, {"CANCELLED", "PASS_THROUGH"})
        if not self._running():  # it ended (and took the release with it)
            if self.start is not None and len(self.path) > 1:
                self._finish(context)
            return self._end(context, {"FINISHED", "PASS_THROUGH"})
        if event.type == "TIMER":
            return {"PASS_THROUGH"}
        if event.type == "MOUSEMOVE":
            if self.start is not None:
                self.path.append(here)
        elif self.button is None and event.value == "PRESS" \
                and event.type in {"LEFTMOUSE", "MIDDLEMOUSE"}:
            self.button = event.type
            self.action = event.type == "LEFTMOUSE" and not event.shift
            self.start = here
            self.path = [here]
        elif event.type == self.button and event.value == "RELEASE":
            self.path.append(here)
            self._finish(context)
            return self._end(context, {"FINISHED", "PASS_THROUGH"})
        return {"PASS_THROUGH"}

    def _finish(self, context):
        if self.kind == "BOX":
            (x0, y0), (x1, y1) = self.start, self.path[-1]
            props = {"xmin": min(x0, x1), "xmax": max(x0, x1),
                     "ymin": min(y0, y1), "ymax": max(y0, y1)}
        else:
            props = {"path": list(self.path)}
        request = (self.kind, props, self.action)
        region, rv3d = self.region, self.rv3d

        def later():  # after Blender's own operator has used the release
            try:
                apply(bpy.context, request, region, rv3d)
            except Exception as error:
                print(f"[Doodle Music] selecting the copies failed: {error!r}")
            return None
        bpy.app.timers.register(later, first_interval=0.01)


# (keymap, key, value, shift, ctrl, operator settings)
KEYS = (
    ("Grease Pencil Edit Mode", "B", "PRESS", False, False,
     {"kind": "BOX", "mode": "SET", "wait_for_input": True}),
    ("Grease Pencil Edit Mode", "RIGHTMOUSE", "CLICK_DRAG", False, True,
     {"kind": "LASSO", "mode": "ADD"}),
    ("Grease Pencil Edit Mode", "RIGHTMOUSE", "CLICK_DRAG", True, True,
     {"kind": "LASSO", "mode": "SUB"}),
)
for _tool, _kind in (("3D View Tool: Select Box", "BOX"), ("3D View Tool: Select Lasso", "LASSO")):
    for _shift, _ctrl, _mode in ((False, False, "SET"), (True, False, "ADD"),
                                 (False, True, "SUB")):
        KEYS += ((_tool, "LEFTMOUSE", "CLICK_DRAG", _shift, _ctrl,
                  {"kind": _kind, "mode": _mode}),)
        KEYS += ((_tool + " (fallback)", "LEFTMOUSE", "CLICK_DRAG", _shift, _ctrl,
                  {"kind": _kind, "mode": _mode}),)

_keymaps = []


def register():
    bpy.utils.register_class(GP2M_OT_select_copies)
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:
        return
    for name, key, value, shift, ctrl, settings in KEYS:
        km = kc.keymaps.new(name=name, space_type="VIEW_3D" if "Tool" in name else "EMPTY")
        item = km.keymap_items.new(GP2M_OT_select_copies.bl_idname, key, value,
                                   shift=shift, ctrl=ctrl)
        for prop, setting in settings.items():
            setattr(item.properties, prop, setting)
        _keymaps.append((km, item))


def unregister():
    for km, item in _keymaps:
        try:
            km.keymap_items.remove(item)
        except (ReferenceError, RuntimeError):
            pass
    _keymaps.clear()
    bpy.utils.unregister_class(GP2M_OT_select_copies)
