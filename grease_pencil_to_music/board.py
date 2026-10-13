# SPDX-License-Identifier: GPL-3.0-or-later
"""The drawing board: piano, note rows, second lines, labels and playhead.

Everything is parented to the composition object and drawn in its local X-Z
plane ("the wall", like the 2D Animation template):

* x = 0 is the loop start, one second is ``seconds_width`` wide;
* z = 0 is the bottom of the lowest note row, one semitone is ``row_height``.
"""

import math
import warnings

import bpy

from . import music, synth

ROLE = "gp2m_role"
BOARD_Y = 0.02  # behind the drawing (front view looks towards +Y)
PLAYHEAD_Y = -0.03  # in front of the drawing

# name: (stroke RGBA or None, fill RGBA or None)
BOARD_MATERIALS = {
    "GP2M Sfondo": (None, (0.06, 0.06, 0.07, 1.0)),
    "GP2M Banda tasti neri": (None, (0.032, 0.032, 0.04, 1.0)),
    "GP2M Linea Do": ((1.0, 0.68, 0.2, 1.0), None),
    "GP2M Linea nota": ((0.2, 0.2, 0.23, 1.0), None),
    "GP2M Linea secondo": ((0.45, 0.62, 0.95, 1.0), None),
    "GP2M Linea battito": ((0.12, 0.13, 0.18, 1.0), None),
    "GP2M Tasto bianco": ((0.25, 0.25, 0.25, 1.0), (0.93, 0.93, 0.9, 1.0)),
    "GP2M Tasto nero": (None, (0.04, 0.04, 0.05, 1.0)),
    "GP2M Testina": ((1.0, 0.18, 0.15, 1.0), None),
}


def _set_gp_style(material, stroke, fill):
    style = material.grease_pencil
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        style.show_stroke = stroke is not None
        style.show_fill = fill is not None
    if stroke is not None:
        style.color = stroke
    if fill is not None:
        style.fill_color = fill


def gp_material(name, stroke=None, fill=None):
    material = bpy.data.materials.get(name)
    if material is None or material.grease_pencil is None:
        material = bpy.data.materials.new(name)
        bpy.data.materials.create_gpencil_data(material)
        _set_gp_style(material, stroke, fill)
    return material


def instrument_materials():
    """One Grease Pencil material per instrument, reused if already present."""
    result = []
    for inst in synth.INSTRUMENTS:
        material = bpy.data.materials.get(inst.label)
        if material is None or material.grease_pencil is None:
            material = bpy.data.materials.new(inst.label)
            bpy.data.materials.create_gpencil_data(material)
            _set_gp_style(material, inst.color, None)
            material.gp2m_instrument = inst.ident
            material.diffuse_color = inst.color
        result.append(material)
    return result


def _label_material():
    material = bpy.data.materials.get("GP2M Etichette")
    if material is None:
        material = bpy.data.materials.new("GP2M Etichette")
        material.diffuse_color = (0.85, 0.85, 0.85, 1.0)  # Solid shading
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            material.use_nodes = True
        tree = material.node_tree
        if tree is not None:  # emissive, so labels read well in any lighting
            tree.nodes.clear()
            emission = tree.nodes.new("ShaderNodeEmission")
            emission.inputs["Color"].default_value = (0.85, 0.85, 0.85, 1.0)
            output = tree.nodes.new("ShaderNodeOutputMaterial")
            tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def _rect(x0, z0, x1, z1):
    return [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]


def _add_strokes(drawing, specs):
    """``specs``: list of (points [(x, z), ...], radius, material_index, kind) where
    kind is "line", "fill" (closed, filled, no outline) or "both"."""
    if not specs:
        return
    first = len(drawing.strokes)
    drawing.add_strokes([len(points) for points, _r, _m, _k in specs])
    for k, (points, radius, material_index, kind) in enumerate(specs):
        stroke = drawing.strokes[first + k]
        stroke.material_index = material_index
        if kind in ("fill", "both"):
            # Blender 5.x fills strokes per stroke (fill_id), not per material.
            stroke.cyclic = True
            stroke.fill_id = first + k + 1
            stroke.hide_stroke = kind == "fill"
        for point, (x, z) in zip(stroke.points, points):
            point.position = (x, 0.0, z)
            point.radius = radius
            point.opacity = 1.0
    # Without this the cached bounds stay empty and the drawing is culled.
    drawing.tag_positions_changed()


def _new_layer(gp, name, frame_number):
    layer = gp.layers.new(name)
    layer.use_lights = False  # flat colors, whatever the scene lighting
    return layer.frames.new(frame_number).drawing


def _link_child(comp, obj, role, y=0.0):
    for collection in comp.users_collection[:1] or [bpy.context.scene.collection]:
        collection.objects.link(obj)
    obj.parent = comp
    obj.location = (0.0, y, 0.0)
    obj[ROLE] = role
    obj.hide_select = True
    return obj


def dimensions(settings):
    rows = settings.octaves * 12 + 1
    return rows, settings.length * settings.seconds_width, rows * settings.row_height


def key_width(settings):
    return max(0.6, 6.0 * settings.row_height)


def _remove_children(comp):
    for child in list(comp.children):
        if child.get(ROLE) not in ("board", "label", "playhead"):
            continue
        data = child.data
        bpy.data.objects.remove(child, do_unlink=True)
        if data is not None and data.users == 0:
            if isinstance(data, bpy.types.GreasePencil):
                bpy.data.grease_pencils.remove(data)
            elif isinstance(data, bpy.types.Curve):
                bpy.data.curves.remove(data)


def _first_frame(scene):
    return min(1, scene.frame_start)


def _build_board_object(comp, scene):
    s = comp.gp2m
    rows, width, top = dimensions(s)
    h = s.row_height
    kw = key_width(s)

    gp = bpy.data.grease_pencils.new(f"{comp.name} · Tavola")
    board = _link_child(comp, bpy.data.objects.new(gp.name, gp), "board", BOARD_Y)
    materials = list(BOARD_MATERIALS)
    for name in materials:
        stroke, fill = BOARD_MATERIALS[name]
        gp.materials.append(gp_material(name, stroke, fill))
    index = {name: i for i, name in enumerate(materials)}

    def layer(name):
        return _new_layer(gp, name, _first_frame(scene))

    # Background and darker bands on the black-key rows.
    background = [(_rect(0.0, 0.0, width, top), 0.01, index["GP2M Sfondo"], "fill")]
    for r in range(rows):
        if music.is_black(s.low_note + r):
            background.append((_rect(0.0, r * h, width, (r + 1) * h), 0.001,
                               index["GP2M Banda tasti neri"], "fill"))
    _add_strokes(layer("Sfondo"), background)

    # Vertical lines: faint beats, stronger seconds.
    vertical = []
    if s.show_beats and s.bpm > 0:
        beat = 60.0 / s.bpm
        k = 1
        while k * beat < s.length - 1e-6:
            t = k * beat
            if abs(t - round(t)) > 1e-3:
                x = t * s.seconds_width
                vertical.append(([(x, 0.0), (x, top)], 0.0025,
                                 index["GP2M Linea battito"], "line"))
            k += 1
    for sec in range(int(math.floor(s.length + 1e-6)) + 1):
        x = sec * s.seconds_width
        radius = 0.008 if sec == 0 else 0.005
        vertical.append(([(x, 0.0), (x, top)], radius, index["GP2M Linea secondo"], "line"))
    if abs(s.length - round(s.length)) > 1e-6:
        vertical.append(([(width, 0.0), (width, top)], 0.008,
                         index["GP2M Linea secondo"], "line"))
    _add_strokes(layer("Griglia"), vertical)

    # Horizontal lines between rows: every C is highlighted.
    horizontal = []
    for r in range(rows + 1):
        z = r * h
        is_c = (s.low_note + r) % 12 == 0
        name = "GP2M Linea Do" if is_c else "GP2M Linea nota"
        horizontal.append(([(0.0, z), (width, z)], 0.007 if is_c else 0.0025,
                           index[name], "line"))
    _add_strokes(layer("Righe"), horizontal)

    # Vertical piano on the left: white keys with real proportions,
    # black keys aligned with their rows.
    keys = []
    white_h = 12.0 * h / 7.0
    for r in range(rows):
        midi = s.low_note + r
        if music.is_black(midi):
            continue
        octave_c = midi - midi % 12
        white_index = (0, 2, 4, 5, 7, 9, 11).index(midi % 12)
        z0 = (octave_c - s.low_note) * h + white_index * white_h
        z0, z1 = max(z0, 0.0), min(z0 + white_h, top)
        if z1 > z0:
            keys.append((_rect(-kw, z0, 0.0, z1), 0.003, index["GP2M Tasto bianco"], "both"))
    for r in range(rows):
        if music.is_black(s.low_note + r):
            keys.append((_rect(-kw, r * h, -kw * 0.38, (r + 1) * h), 0.001,
                         index["GP2M Tasto nero"], "fill"))
    _add_strokes(layer("Tasti"), keys)
    return board


def _add_label(comp, text, x, z, size, align_x, align_y):
    curve = bpy.data.curves.new(f"{comp.name} · {text}", "FONT")
    curve.body = text
    curve.size = size
    curve.align_x = align_x
    curve.align_y = align_y
    curve.materials.append(_label_material())
    obj = _link_child(comp, bpy.data.objects.new(curve.name, curve), "label", BOARD_Y)
    obj.location = (x, BOARD_Y, z)
    obj.rotation_euler = (math.pi / 2.0, 0.0, 0.0)
    return obj


def _build_labels(comp):
    s = comp.gp2m
    rows, _width, top = dimensions(s)
    h = s.row_height
    kw = key_width(s)
    size = max(1.3 * h, 0.12)
    for r in range(rows):
        midi = s.low_note + r
        if midi % 12 == 0:
            _add_label(comp, music.note_name(midi), -kw - 0.06, (r + 0.5) * h, size,
                       "RIGHT", "CENTER")
    for sec in range(int(math.floor(s.length + 1e-6)) + 1):
        _add_label(comp, f"{sec}s", sec * s.seconds_width, top + 0.06, 0.14, "CENTER",
                   "BOTTOM")


def _build_playhead(comp, scene):
    s = comp.gp2m
    _rows, _width, top = dimensions(s)
    gp = bpy.data.grease_pencils.new(f"{comp.name} · Testina")
    playhead = _link_child(comp, bpy.data.objects.new(gp.name, gp), "playhead", PLAYHEAD_Y)
    gp.materials.append(gp_material("GP2M Testina", *BOARD_MATERIALS["GP2M Testina"]))
    drawing = _new_layer(gp, "Testina", _first_frame(scene))
    _add_strokes(drawing, [([(0.0, -0.12), (0.0, top + 0.04)], 0.012, 0, "line")])
    playhead.show_in_front = True

    # x = seconds since the loop start * seconds_width, evaluated every frame.
    curve = playhead.driver_add("location", 0)
    driver = curve.driver
    driver.type = "SCRIPTED"
    for name, id_type, target, path in (
            ("start", "SCENE", scene, "frame_start"),
            ("fps", "SCENE", scene, "render.fps"),
            ("base", "SCENE", scene, "render.fps_base"),
            ("sw", "OBJECT", comp, "gp2m.seconds_width")):
        var = driver.variables.new()
        var.name = name
        var.targets[0].id_type = id_type
        var.targets[0].id = target
        var.targets[0].data_path = path
    driver.expression = "(frame - start) * base / fps * sw"
    s.playhead = playhead
    return playhead


def rebuild(comp, scene=None):
    """(Re)create board, labels and playhead of a composition."""
    scene = scene or bpy.context.scene
    _remove_children(comp)
    comp.gp2m.board = _build_board_object(comp, scene)
    _build_labels(comp)
    _build_playhead(comp, scene)


# --- Deferred rebuild (sliders call update callbacks continuously) -----------

_pending = set()


def _rebuild_pending():
    names = list(_pending)
    _pending.clear()
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is not None and obj.gp2m.is_composition:
            try:
                rebuild(obj)
            except Exception as error:  # keep Blender responsive
                print(f"[Grease Pencil to Music] rebuild failed: {error!r}")
    return None


def request_rebuild(comp):
    _pending.add(comp.name)
    if not bpy.app.timers.is_registered(_rebuild_pending):
        bpy.app.timers.register(_rebuild_pending, first_interval=0.15)
