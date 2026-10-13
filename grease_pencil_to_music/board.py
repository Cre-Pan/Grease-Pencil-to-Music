# SPDX-License-Identifier: GPL-3.0-or-later
"""The drawing board, built *inside* the composition object.

Everything lives in the composition's own Grease Pencil data, so a
composition is one single object (no parent lines, Shift+D duplicates a whole
work plane):

* layer group "GP2M Tavola" (bottom, locked): background, grid, note rows,
  piano keys and labels;
* layer group "GP2M Testina" (top, locked): the playhead, moved by a driver
  on the layer translation;
* the user's layers in between.

Board coordinates are the object's local X-Z plane ("the wall"):
x = 0 is the loop start, one second is ``seconds_width`` wide; z = 0 is the
bottom of the lowest note row, one semitone is ``row_height``.
"""

import math
import warnings

import bpy

from . import glyphs, music, synth

BOARD_GROUP = "GP2M Tavola"
HEAD_GROUP = "GP2M Testina"
BOARD_GROUPS = (BOARD_GROUP, HEAD_GROUP)
HEAD_LAYER = "GP2M Linea testina"
BOARD_FLAG = "gp2m_board"  # custom property on board materials
LEGACY_ROLE = "gp2m_role"  # 0.0.1 used separate child objects

# name: (stroke RGBA or None, fill RGBA or None)
BOARD_MATERIALS = {
    "GP2M Sfondo": (None, (0.06, 0.06, 0.07, 1.0)),
    "GP2M Banda tasti neri": (None, (0.032, 0.032, 0.04, 1.0)),
    "GP2M Linea Do": ((1.0, 0.68, 0.2, 1.0), None),
    "GP2M Linea nota": ((0.2, 0.2, 0.23, 1.0), None),
    "GP2M Linea secondo": ((0.45, 0.62, 0.95, 1.0), None),
    "GP2M Linea battito": ((0.12, 0.13, 0.18, 1.0), None),
    "GP2M Tasto bianco": ((0.55, 0.55, 0.55, 1.0), (0.93, 0.93, 0.9, 1.0)),
    "GP2M Tasto nero": (None, (0.04, 0.04, 0.05, 1.0)),
    "GP2M Etichetta tasti": ((0.42, 0.42, 0.45, 1.0), None),
    "GP2M Etichetta tempo": ((0.45, 0.62, 0.95, 1.0), None),
    "GP2M Testina": ((1.0, 0.18, 0.15, 1.0), None),
}

KEY_LABEL_ITEMS = (
    ("C", "Solo Do", "Etichetta solo sui Do (C)"),
    ("WHITE", "Tasti bianchi", "Etichette su tutti i tasti bianchi"),
    ("ALL", "Tutte le note", "Etichette su tutti i tasti"),
    ("NONE", "Nessuna", "Nessuna etichetta sulla tastiera"),
)


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


def _fill_color(color):
    return (color[0], color[1], color[2], 0.45)


LABEL_KEY = "gp2m_label"  # instrument name shown in the UI (without .001 suffixes)


def instrument_material(inst):
    """A new Grease Pencil material for an instrument.

    Every composition gets its own materials, so mute, volume and instrument
    of one composition never change another one. Filled shapes (clusters) get
    the instrument color, half transparent.
    """
    material = bpy.data.materials.new(inst.label)
    bpy.data.materials.create_gpencil_data(material)
    _set_gp_style(material, inst.color, None)
    material.grease_pencil.fill_color = _fill_color(inst.color)
    material.gp2m_instrument = inst.ident
    material.diffuse_color = inst.color
    material[LABEL_KEY] = inst.label
    return material


def instrument_materials(idents=None):
    return [instrument_material(inst) for inst in synth.INSTRUMENTS
            if idents is None or inst.ident in idents]


def material_label(material):
    if material is None:
        return ""
    return material.get(LABEL_KEY) or material.name


def make_independent(compositions):
    """Give every composition its own data and instrument materials.

    Shift+D (or Alt+D) may share Grease Pencil data or materials between
    compositions; the first one (by name) keeps them, the others get copies.
    """
    changed = []
    owners = {}
    for obj in sorted(compositions, key=lambda o: o.name):
        if obj.data.name in owners:
            obj.data = obj.data.copy()
            changed.append(obj)
        owners[obj.data.name] = obj
    used = {}
    for obj in sorted(compositions, key=lambda o: o.name):
        gp = obj.data
        for index, material in enumerate(gp.materials):
            if material is None or is_board_material(material):
                continue
            if material.name in used and used[material.name] != obj.name:
                copy = material.copy()
                copy[LABEL_KEY] = material_label(material)
                gp.materials[index] = copy
                if obj not in changed:
                    changed.append(obj)
            else:
                used[material.name] = obj.name
    return changed


def is_board_material(material):
    return material is not None and bool(material.get(BOARD_FLAG))


def is_board_layer(layer):
    group = layer.parent_group
    while group is not None:
        if group.name in BOARD_GROUPS:
            return True
        group = group.parent_group
    return False


def user_layers(gp):
    return [layer for layer in gp.layers if not is_board_layer(layer)]


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


def dimensions(settings):
    rows = settings.octaves * 12 + 1
    return rows, settings.length * settings.seconds_width, rows * settings.row_height


def key_width(settings):
    return max(0.6, 6.0 * settings.row_height)


def _first_frame(scene):
    return min(1, scene.frame_start)


def _note_style():
    from . import prefs
    return prefs.get_prefs().note_naming


# --- Pieces of the board -------------------------------------------------------

def _background(s, index, rows, width):
    h = s.row_height
    specs = [(_rect(0.0, 0.0, width, rows * h), 0.01, index["GP2M Sfondo"], "fill")]
    for r in range(rows):
        if music.is_black(s.low_note + r):
            specs.append((_rect(0.0, r * h, width, (r + 1) * h), 0.001,
                          index["GP2M Banda tasti neri"], "fill"))
    return specs


def _grid(s, index, width, top):
    specs = []
    if s.show_beats and s.bpm > 0:
        beat = 60.0 / s.bpm
        k = 1
        while k * beat < s.length - 1e-6:
            t = k * beat
            if abs(t - round(t)) > 1e-3:
                x = t * s.seconds_width
                specs.append(([(x, 0.0), (x, top)], 0.0025, index["GP2M Linea battito"], "line"))
            k += 1
    for sec in range(int(math.floor(s.length + 1e-6)) + 1):
        x = sec * s.seconds_width
        specs.append(([(x, 0.0), (x, top)], 0.008 if sec == 0 else 0.005,
                      index["GP2M Linea secondo"], "line"))
    if abs(s.length - round(s.length)) > 1e-6:
        specs.append(([(width, 0.0), (width, top)], 0.008, index["GP2M Linea secondo"], "line"))
    return specs


def _rows(s, index, rows, width):
    h = s.row_height
    kw = key_width(s)
    specs = []
    for r in range(rows + 1):
        is_c = (s.low_note + r) % 12 == 0
        name = "GP2M Linea Do" if is_c else "GP2M Linea nota"
        # C lines also cross the keyboard, so octaves read at a glance.
        x0 = -kw if is_c else 0.0
        specs.append(([(x0, r * h), (width, r * h)], 0.007 if is_c else 0.0025,
                      index[name], "line"))
    return specs


def _keys(s, index, rows):
    """One key per row: white and black keys are as tall as the note rows."""
    h = s.row_height
    kw = key_width(s)
    inset = 0.08 * h
    specs = []
    for r in range(rows):
        specs.append((_rect(-kw, r * h, 0.0, (r + 1) * h), 0.0015,
                       index["GP2M Tasto bianco"], "both"))
    for r in range(rows):
        if music.is_black(s.low_note + r):
            # Black keys sit on the grid side, like a piano roll.
            specs.append((_rect(-kw * 0.58, r * h + inset, 0.0, (r + 1) * h - inset), 0.001,
                          index["GP2M Tasto nero"], "fill"))
    return specs


def _labels(s, index, rows, top):
    h = s.row_height
    style = _note_style()
    specs = []
    mode = s.key_labels
    height = 0.55 * h
    for r in range(rows):
        midi = s.low_note + r
        black = music.is_black(midi)
        show = (mode == "ALL" or (mode == "WHITE" and not black)
                or (mode == "C" and midi % 12 == 0))
        if not show:
            continue
        text = music.note_name(midi, style)
        baseline = r * h + (h - height) / 2.0
        # Labels on the free (left) side of the keys.
        for line in glyphs.text_polylines(text, -key_width(s) + 0.03, baseline, height, "LEFT"):
            specs.append((line, height * 0.06, index["GP2M Etichetta tasti"], "line"))
    height = 0.12
    for sec in range(int(math.floor(s.length + 1e-6)) + 1):
        for line in glyphs.text_polylines(f"{sec}s", sec * s.seconds_width, top + 0.05,
                                          height, "CENTER"):
            specs.append((line, 0.006, index["GP2M Etichetta tempo"], "line"))
    return specs


# --- Assembly ------------------------------------------------------------------

def _ensure_materials(gp):
    """Append the board materials to the composition (after the instruments)."""
    index = {}
    names = [m.name if m else "" for m in gp.materials]
    for name, (stroke, fill) in BOARD_MATERIALS.items():
        material = gp_material(name, stroke, fill)
        material[BOARD_FLAG] = True
        if name not in names:
            gp.materials.append(material)
            names.append(name)
        index[name] = names.index(name)
    return index


def _ensure_group(gp, name, bottom):
    group = gp.layer_groups.get(name)
    if group is None:
        group = gp.layer_groups.new(name)
        group.is_expanded = False
    if bottom:
        gp.layer_groups.move_bottom(group)
    else:
        gp.layer_groups.move_top(group)
    return group


def _remove_legacy_children(comp):
    for child in list(comp.children):
        if child.get(LEGACY_ROLE) not in ("board", "label", "playhead"):
            continue
        data = child.data
        bpy.data.objects.remove(child, do_unlink=True)
        if data is not None and data.users == 0:
            if isinstance(data, bpy.types.GreasePencil):
                bpy.data.grease_pencils.remove(data)
            elif isinstance(data, bpy.types.Curve):
                bpy.data.curves.remove(data)


def _playhead_expression(seconds_width, offset_frames):
    return (f"(frame - start - {int(offset_frames)}) * base / fps * {seconds_width:.6f}")


def set_playhead_offset(comp, offset_frames):
    """Shift the playhead when the composition starts later (sequence mode)."""
    data = comp.data.animation_data
    if data is None:
        return
    curve = data.drivers.find(f'layers["{HEAD_LAYER}"].translation', index=0)
    if curve is None:
        return
    expression = _playhead_expression(comp.gp2m.seconds_width, offset_frames)
    if curve.driver.expression != expression:
        curve.driver.expression = expression


def _set_playhead_driver(gp, scene, seconds_width, offset_frames=0):
    path = f'layers["{HEAD_LAYER}"].translation'
    try:
        gp.driver_remove(path, 0)
    except TypeError:
        pass
    driver = gp.driver_add(path, 0).driver
    driver.type = "SCRIPTED"
    for name, prop in (("start", "frame_start"), ("fps", "render.fps"),
                       ("base", "render.fps_base")):
        var = driver.variables.new()
        var.name = name
        var.targets[0].id_type = "SCENE"
        var.targets[0].id = scene
        var.targets[0].data_path = prop
    # x = seconds since the composition start * seconds_width, every frame.
    driver.expression = _playhead_expression(seconds_width, offset_frames)


def ensure_order(gp):
    """Board group at the bottom, playhead group on top (writes only if needed)."""
    layers = list(gp.layers)
    if not layers:
        return
    head = gp.layer_groups.get(HEAD_GROUP)
    if head is not None and layers[-1].parent_group is None:
        gp.layer_groups.move_top(head)
    tavola = gp.layer_groups.get(BOARD_GROUP)
    if tavola is not None and layers[0].parent_group is None:
        gp.layer_groups.move_bottom(tavola)


def has_board(comp):
    return comp.data.layer_groups.get(BOARD_GROUP) is not None


def rebuild(comp, scene=None):
    """(Re)create board, labels and playhead inside the composition."""
    scene = scene or bpy.context.scene
    _remove_legacy_children(comp)
    s = comp.gp2m
    gp = comp.data
    active_name = gp.layers.active.name if gp.layers.active is not None else None
    index = _ensure_materials(gp)
    rows, width, top = dimensions(s)
    frame = _first_frame(scene)

    for layer in [layer for layer in gp.layers if is_board_layer(layer)]:
        gp.layers.remove(layer)
    board_group = _ensure_group(gp, BOARD_GROUP, bottom=True)
    head_group = _ensure_group(gp, HEAD_GROUP, bottom=False)

    for name, specs in (
            ("GP2M Sfondo", _background(s, index, rows, width)),
            ("GP2M Griglia", _grid(s, index, width, top)),
            ("GP2M Righe", _rows(s, index, rows, width)),
            ("GP2M Tasti", _keys(s, index, rows)),
            ("GP2M Etichette", _labels(s, index, rows, top))):
        layer = gp.layers.new(name, set_active=False, layer_group=board_group)
        layer.use_lights = False
        _add_strokes(layer.frames.new(frame).drawing, specs)
        layer.lock = True

    head = gp.layers.new(HEAD_LAYER, set_active=False, layer_group=head_group)
    head.use_lights = False
    _add_strokes(head.frames.new(frame).drawing,
                 [([(0.0, -0.12), (0.0, top + 0.04)], 0.012, index["GP2M Testina"], "line")])
    head.lock = True
    from . import engine
    offset = engine.state(comp).get("offset_frames", 0)
    _set_playhead_driver(gp, scene, s.seconds_width, offset)

    layer = gp.layers.get(active_name) if active_name else None
    if layer is None or is_board_layer(layer):
        layers = user_layers(gp)
        layer = layers[-1] if layers else None
    if layer is not None:
        gp.layers.active = layer


# --- Deferred rebuild (sliders call update callbacks continuously) -------------

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
