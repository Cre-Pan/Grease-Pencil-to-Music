# SPDX-License-Identifier: GPL-3.0-or-later
"""The drawing board of a composition: a small rig of two Grease Pencil objects.

* the composition (the object you draw on): only your layers and instruments,
  plus the layer group "GP2M Testina" on top (locked) with the playhead, moved by
  a driver on the layer translation;
* its grid, "<composition> · Tavola", a child of the composition (since 0.0.21):
  layer group "Tavola Composizione" with the window, grid rows, lines, piano keys,
  the dots on C (or note names) and the dark boxes outside the scene Preview Range,
  drawn after the Figma design of the board (see the "window" section below). Its transform is
  locked and clicking it selects the composition, so Draw Mode always opens on the
  drawing, never on the grid. The composition is drawn in front of it.

Files up to 0.0.20 kept the grid inside the composition: it moves out on load.

Board coordinates are the object's local X-Z plane ("the wall"):
x = 0 is the loop start, one second is ``seconds_width`` wide; z = 0 is the
bottom of the lowest note row, one semitone is ``row_height``.
"""

import math
import warnings

import bpy

from . import beat, glyphs, music, synth, theme

BOARD_GROUP = "Tavola Composizione"
LEGACY_BOARD_GROUP = "GP2M Tavola"  # name up to 0.0.12, renamed when found
HEAD_GROUP = "GP2M Testina"
BOARD_GROUPS = (BOARD_GROUP, HEAD_GROUP, LEGACY_BOARD_GROUP)
HEAD_LAYER = "GP2M Linea testina"
BOARD_FLAG = "gp2m_board"  # custom property on board materials
LEGACY_ROLE = "gp2m_role"  # 0.0.1 used separate child objects
BOARD_PASS = 77  # layer pass index of board layers, excluded from modifiers
GRID_ROLE = "gp2m_grid"  # custom property on the grid object
GRID_SUFFIX = " · Tavola"
GRID_DEPTH = 0.005  # the grid sits just behind the drawing (+Y, away from the front view)
HEAD_MATERIALS = ("GP2M Testina",)  # the only board material left in the composition

# The board materials take their colors from the Blender theme: see theme.board_palette.
SHADE_LAYER = "GP2M Fuori anteprima"
SHADE_KEY = "gp2m_shade"  # ID property on the GP data: spans last drawn

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


def change_instrument(material, inst):
    """Give an instrument material another instrument, keeping its strokes.

    Color and name follow the new instrument unless they were changed by hand.
    """
    old = synth.INSTRUMENT_BY_ID.get(material.gp2m_instrument)
    style = material.grease_pencil
    if old is None or all(abs(a - b) < 2e-3 for a, b in zip(style.color[:3], old.color[:3])):
        style.color = (*inst.color[:3], style.color[3])
        fill = _fill_color(inst.color)
        style.fill_color = (*fill[:3], style.fill_color[3])
        material.diffuse_color = inst.color
    label = material.get(LABEL_KEY)
    if old is None or label is None or label == old.label:
        material[LABEL_KEY] = inst.label
        if old is None or material.name.split(".")[0] == old.label:
            material.name = inst.label
    if material.gp2m_instrument != inst.ident:
        material.gp2m_instrument = inst.ident


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


def layer_instruments(comp, layer_name):
    """``[(slot index, material)]`` of the instruments that belong to a layer."""
    return [(index, slot.material) for index, slot in enumerate(comp.material_slots)
            if slot.material is not None and not is_board_material(slot.material)
            and slot.material.grease_pencil is not None
            and slot.material.gp2m_layer == layer_name]


def loose_instruments(comp):
    """Instruments not attached to any existing layer."""
    names = {layer.name for layer in user_layers(comp.data)}
    return [(index, slot.material) for index, slot in enumerate(comp.material_slots)
            if slot.material is not None and not is_board_material(slot.material)
            and slot.material.grease_pencil is not None
            and slot.material.gp2m_layer not in names]


def is_board_layer(layer):
    group = layer.parent_group
    while group is not None:
        if group.name in BOARD_GROUPS:
            return True
        group = group.parent_group
    return False


def user_layers(gp):
    return [layer for layer in gp.layers if not is_board_layer(layer)]


def is_group(node):
    return isinstance(node, bpy.types.GreasePencilLayerGroup)


def is_board_group(group):
    while group is not None:
        if group.name in BOARD_GROUPS:
            return True
        group = group.parent_group
    return False


def user_groups(gp):
    """The layer groups made by the user (the board's own groups excluded)."""
    return [group for group in gp.layer_groups if not is_board_group(group)]


def ancestors(node):
    """The groups that contain ``node``, innermost first."""
    groups = []
    group = node.parent_group
    while group is not None:
        groups.append(group)
        group = group.parent_group
    return groups


def is_hidden(layer):
    """Hidden itself or inside a hidden group (Blender does not draw it either)."""
    return layer.hide or any(group.hide for group in ancestors(layer))


def user_tree(gp):
    """``[(node, depth)]`` of the user's layers and groups, top first, as Blender's
    layer tree shows them (a group comes before its children)."""
    rows = []

    def walk(nodes, depth):
        for node in reversed(list(nodes)):  # Blender lists nodes bottom to top
            if is_group(node):
                if node.name in BOARD_GROUPS:
                    continue
                rows.append((node, depth))
                walk(node.children, depth + 1)
            else:
                rows.append((node, depth))

    walk(gp.root_nodes, 0)
    return rows


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


def add_strokes_bulk(drawing, strokes):
    """Add many strokes at once (MIDI import, keyboard recording).

    ``strokes``: list of (x array, z array, radius array, material_index).
    """
    if not strokes:
        return
    import numpy as np
    existing = drawing.attributes.get("position")
    first_point = len(existing.data) if existing is not None and len(drawing.strokes) else 0
    first_curve = len(drawing.strokes)
    drawing.add_strokes([len(x) for x, _z, _r, _m in strokes])
    attrs = drawing.attributes
    positions = np.zeros((sum(len(x) for x, _z, _r, _m in strokes), 3), dtype=np.float32)
    radii = np.empty(len(positions), dtype=np.float32)
    cursor = 0
    for x, z, r, _m in strokes:
        positions[cursor:cursor + len(x), 0] = x
        positions[cursor:cursor + len(x), 2] = z
        radii[cursor:cursor + len(x)] = r
        cursor += len(x)
    all_pos = np.empty(len(attrs["position"].data) * 3, dtype=np.float32)
    attrs["position"].data.foreach_get("vector", all_pos)
    all_pos = all_pos.reshape(-1, 3)
    all_pos[first_point:] = positions
    attrs["position"].data.foreach_set("vector", all_pos.ravel())
    for name, values, domain, default in (("radius", radii, "POINT", 0.01),
                                          ("opacity", np.ones(len(radii), np.float32),
                                           "POINT", 1.0)):
        attr = attrs.get(name) or attrs.new(name, "FLOAT", domain)
        current = np.full(len(attr.data), default, dtype=np.float32)
        attr.data.foreach_get("value", current)
        current[first_point:] = values
        attr.data.foreach_set("value", current)
    attr = attrs.get("material_index") or attrs.new("material_index", "INT", "CURVE")
    current = np.zeros(len(attr.data), dtype=np.int32)
    attr.data.foreach_get("value", current)
    current[first_curve:] = [m for _x, _z, _r, m in strokes]
    attr.data.foreach_set("value", current)
    drawing.tag_positions_changed()


def span(settings):
    """Semitones from the lowest to the highest row (whole octaves plus extra keys)."""
    return settings.octaves * 12 + settings.extra_keys


def _set_span(settings, semitones):
    semitones = max(12, min(MAX_OCTAVES * 12, semitones))
    octaves, extra = divmod(semitones, 12)
    if settings.octaves != octaves:
        settings.octaves = octaves
    if settings.extra_keys != extra:
        settings.extra_keys = extra


def dimensions(settings):
    """(rows, width, height) of the grid. The rows of a Bit composition are its lanes."""
    if beat.is_beat(settings):
        lanes = beat.lane_count(settings)
        return lanes, settings.length * settings.seconds_width, \
            lanes * beat.lane_height(settings)
    rows = span(settings) + 1
    return rows, settings.length * settings.seconds_width, rows * settings.row_height


def vertical_extent(settings):
    """(bottom, top) of the board in local z: the window, the tab with the name below
    it and the playhead box above it."""
    from . import rig
    _x0, z0, _x1, z1 = window_box(settings)
    u = unit(settings)
    return z0 - NAME_TAB_OUT * u - rig.handle_room(settings), \
        z1 + HEAD_BOX_UP * u + rig.handle_room(settings)


MIN_LOW_NOTE, MAX_LOW_NOTE, MAX_OCTAVES = 12, 96, 7


def key_steps(settings, edge, delta):
    """How many keys (semitones, signed) can really be added (+) or hidden (-) at
    ``edge``: the board shows from 1 to 7 octaves. A Bit composition counts lanes
    (from 1 to 16)."""
    if beat.is_beat(settings):
        now = beat.lane_count(settings)
        return max(beat.MIN_LANES, min(beat.MAX_LANES, now + delta)) - now
    now = span(settings)
    if edge == "TOP":
        return max(12, min(MAX_OCTAVES * 12, now + delta)) - now
    if delta > 0:  # show more below: the lowest note goes down, the board grows
        room = min(settings.low_note - MIN_LOW_NOTE, MAX_OCTAVES * 12 - now)
        return max(0, min(delta, room))
    room = min(MAX_LOW_NOTE - settings.low_note, now - 12)
    return -max(0, min(-delta, room))


def octave_steps(settings, edge, delta):
    """How many whole octaves (signed) can really be added (+) or hidden (-)."""
    keys = key_steps(settings, edge, 12 * delta)
    return int(keys / 12)


def shift_octaves(comp, edge, delta):
    """Show (delta > 0) or hide (delta < 0) octaves at the top or bottom of the board
    without moving the drawing: every stroke stays where it is in the world and
    plays the same notes.

    The top only changes "Ottave". At the bottom the lowest note changes, so the
    board origin (z = 0, the lowest row) moves down or up by whole octaves and the
    strokes move the opposite way inside the object. Returns the octaves changed."""
    if beat.is_beat(comp.gp2m):  # Bit: one lane for each octave of a note board
        return shift_keys(comp, edge, delta)
    steps = octave_steps(comp.gp2m, edge, delta)
    return shift_keys(comp, edge, 12 * steps) // 12 if steps else 0


def shift_keys(comp, edge, delta):
    """Like :func:`shift_octaves`, one key (semitone) at a time. Returns the keys
    changed (signed)."""
    s = comp.gp2m
    steps = key_steps(s, edge, delta)
    if not steps:
        return 0
    if beat.is_beat(s):
        return _shift_lanes(comp, edge, steps)
    if edge == "TOP":
        _set_span(s, span(s) + steps)
        return steps  # the top edge: the origin stays, the deferred rebuild is enough
    _move_drawing(comp, steps * s.row_height)
    _set_span(s, span(s) + steps)
    s.low_note -= steps
    # The board at once, with the object that just moved: a board drawn for a moment
    # with the old rows on the new origin jumped up or down. The sound is deferred.
    scene = bpy.context.scene
    build_grid(comp, scene)
    _build_playhead(comp, scene)
    return steps


def _move_drawing(comp, dz):
    """Move the strokes up by ``dz`` inside the object and the object down by as much:
    in the world nothing moves, the board origin (z = 0) goes down."""
    import numpy as np
    for layer in user_layers(comp.data):
        for frame in layer.frames:
            attr = frame.drawing.attributes.get("position")
            if attr is None or not len(attr.data):
                continue
            positions = np.empty(len(attr.data) * 3, dtype=np.float32)
            attr.data.foreach_get("vector", positions)
            positions[2::3] += dz
            attr.data.foreach_set("vector", positions)
            frame.drawing.tag_positions_changed()
    from mathutils import Vector
    world = comp.matrix_world.copy()
    world.translation = world @ Vector((0.0, 0.0, -dz))
    comp.matrix_world = world


LANE_STASH_KEY = "gp2m_lane_stash"


def _shift_lanes(comp, edge, steps):
    """Lanes of a Bit composition added (+) or taken away (-) at the top or at the
    bottom; the drawing stays where it is and every lane keeps its percussion."""
    from . import props
    s = comp.gp2m
    props.ensure_lanes(s)
    items = s.lane_drums
    if edge == "TOP":
        # The items above the last lane stay: a lane shown again keeps its drum.
        s.lanes = s.lanes + steps
        return steps
    stash = list(comp.get(LANE_STASH_KEY, []))  # drums of the lanes hidden below
    if steps > 0:  # new lanes below: their items go first
        for _ in range(steps):
            used = {item.drum for item in items}
            drum = stash.pop() if stash else beat.default_drum(len(items), used)
            items.add().drum = drum
            items.move(len(items) - 1, 0)
    else:
        for _ in range(-steps):
            stash.append(items[0].drum)
            items.remove(0)
    comp[LANE_STASH_KEY] = stash[-beat.MAX_LANES:]
    _move_drawing(comp, steps * beat.lane_height(s))
    s.lanes = s.lanes + steps
    scene = bpy.context.scene
    build_grid(comp, scene)
    _build_playhead(comp, scene)
    return steps


# --- The window (Figma "Tavola": FINESTRA, KEYBOARD, GRIGLIA...) -------------------
# Measures in design pixels: one octave of the keyboard is 210 px (12 rows), so one
# design pixel is row_height / 17.5 board units.

DESIGN_ROW = 17.5  # design pixels in a row (a semitone)
KEYBOARD_W = 173.0  # keyboard width
KEY_GAP = 16.0  # between keyboard and grid
MARGIN_LEFT, MARGIN_RIGHT = 23.0, 21.0  # window edge to keyboard / grid
MARGIN_TOP, MARGIN_BOTTOM = 20.0, 22.0
WINDOW_RADIUS, KEYBOARD_RADIUS, GRID_RADIUS = 47.0, 25.0, 25.0
BLACK_KEY_W = 85.0  # from the grid side
BLACK_KEY_RADIUS = 4.0
DOT_X, DOT_R = 14.0, 7.0  # the dot on C, from the keyboard's left edge
TAB_OUT = 40.0  # how far the grips stick out of the window
NAME_TAB_OUT = 50.0  # the tab with the composition's name, at the bottom
HEAD_BOX_UP = 52.0  # the top of the playhead box above the window (it is 32 tall)
# White keys of a realistic piano over the semitones of an octave (from C):
# C D E share 5 semitones, F G A B share 7.
WHITE_KEYS = ((0.0, 5 / 3), (5 / 3, 10 / 3), (10 / 3, 5.0), (5.0, 6.75), (6.75, 8.5),
              (8.5, 10.25), (10.25, 12.0))


def unit(settings):
    """Board units in one design pixel."""
    return settings.row_height / DESIGN_ROW


def key_width(settings):
    """Keyboard plus the gap before the grid: the keyboard ends at x = -KEY_GAP."""
    return (KEYBOARD_W + KEY_GAP) * unit(settings)


def keyboard_box(settings):
    u = unit(settings)
    top = dimensions(settings)[2]
    return (-(KEYBOARD_W + KEY_GAP) * u, 0.0, -KEY_GAP * u, top)


def window_box(settings):
    """(x0, z0, x1, z1) of the window around keyboard and grid."""
    u = unit(settings)
    _rows, width, top = dimensions(settings)
    x0 = -(KEYBOARD_W + KEY_GAP + MARGIN_LEFT) * u
    return (x0, -MARGIN_BOTTOM * u, width + MARGIN_RIGHT * u, top + MARGIN_TOP * u)


def _first_frame(scene):
    return min(1, scene.frame_start)


def _note_style():
    from . import prefs
    return prefs.get_prefs().note_naming


# --- Rounded shapes ------------------------------------------------------------------

def _arc_steps(radius, u):
    return max(3, min(10, int(radius / max(u, 1e-9) / 5.0)))


def _rounded_rect(x0, z0, x1, z1, radius, steps=8, corners=(True, True, True, True)):
    """Corners: bottom-left, bottom-right, top-right, top-left."""
    radius = max(0.0, min(radius, (x1 - x0) / 2.0, (z1 - z0) / 2.0))
    centres = ((x0 + radius, z0 + radius, math.pi), (x1 - radius, z0 + radius, 1.5 * math.pi),
               (x1 - radius, z1 - radius, 0.0), (x0 + radius, z1 - radius, 0.5 * math.pi))
    plain = ((x0, z0), (x1, z0), (x1, z1), (x0, z1))
    points = []
    for (cx, cz, a0), corner, round_it in zip(centres, plain, corners):
        if not round_it or radius <= 0.0:
            points.append(corner)
            continue
        for i in range(steps + 1):
            a = a0 + 0.5 * math.pi * i / steps
            points.append((cx + radius * math.cos(a), cz + radius * math.sin(a)))
    return points


def _inset(box, radius, z):
    """Horizontal inset of a rounded box at height z (0 away from the corners)."""
    _x0, z0, _x1, z1 = box
    d = max(z0 + radius - z, z - (z1 - radius), 0.0)
    return radius - math.sqrt(max(radius * radius - d * d, 0.0))


def _clip_rect(rx0, rz0, rx1, rz1, box, radius, steps=6):
    """The rectangle cut by a box with rounded corners, as a polygon (or None)."""
    x0, z0, x1, z1 = box
    za, zb = max(rz0, z0), min(rz1, z1)
    if zb - za <= 1e-9 or min(rx1, x1) - max(rx0, x0) <= 1e-9:
        return None
    zs = {za, zb}
    for lo, hi in ((z0, z0 + radius), (z1 - radius, z1)):
        for i in range(steps + 1):
            z = lo + (hi - lo) * i / steps
            if za < z < zb:
                zs.add(z)
    zs = sorted(zs)
    left, right = [], []
    for z in zs:
        inset = _inset(box, radius, z)
        a, b = max(rx0, x0 + inset), min(rx1, x1 - inset)
        if b - a <= 1e-9:
            continue
        left.append((a, z))
        right.append((b, z))
    if len(left) < 2:
        return None
    return left + right[::-1]


def _vline(x, box, radius):
    """A vertical line across a rounded box, cut at its corners."""
    x0, z0, x1, z1 = box
    if not x0 < x < x1:
        return None
    d = max(x0 + radius - x, x - (x1 - radius), 0.0)
    inset = radius - math.sqrt(max(radius * radius - d * d, 0.0))
    return [(x, z0 + inset), (x, z1 - inset)]


# --- Pieces of the board -------------------------------------------------------

def grid_box(settings):
    _rows, width, top = dimensions(settings)
    return (0.0, 0.0, width, top)


def _background(s, index, rows, width):
    """Window, grid area and the darker rows of the black keys (FINESTRA, GRIGLIA)."""
    u = unit(s)
    h = s.row_height
    window = window_box(s)
    box = grid_box(s)
    gr = GRID_RADIUS * u
    specs = [(_rounded_rect(*window, WINDOW_RADIUS * u, _arc_steps(WINDOW_RADIUS, 1.0)),
              u, index["GP2M Finestra"], "both"),
             (_rounded_rect(*box, gr, _arc_steps(GRID_RADIUS, 1.0)), 0.001,
              index["GP2M Riga bianca"], "fill")]
    for r in range(rows):
        if music.is_black(s.low_note + r):
            band = _clip_rect(0.0, r * h, width, (r + 1) * h, box, gr)
            if band:
                specs.append((band, 0.001, index["GP2M Banda tasti neri"], "fill"))
    return specs


def _grid(s, index, width, top):
    """Vertical lines: beats and seconds (LINEE VERTICALI)."""
    u = unit(s)
    box = grid_box(s)
    gr = GRID_RADIUS * u
    specs = []
    if s.show_beats and s.bpm > 0:
        beat = 60.0 / s.bpm
        k = 1
        while k * beat < s.length - 1e-6:
            t = k * beat
            if abs(t - round(t)) > 1e-3:
                line = _vline(t * s.seconds_width, box, gr)
                if line:
                    specs.append((line, u, index["GP2M Linea battito"], "line"))
            k += 1
    for sec in range(1, int(math.floor(s.length - 1e-6)) + 1):
        line = _vline(sec * s.seconds_width, box, gr)
        if line:
            specs.append((line, u, index["GP2M Linea secondo"], "line"))
    return specs


def _rows(s, index, rows, width):
    """Lines between two white rows (E-F, B-C), the frames of grid and keyboard."""
    u = unit(s)
    h = s.row_height
    box = grid_box(s)
    gr = GRID_RADIUS * u
    specs = []
    for r in range(1, rows):
        if (s.low_note + r) % 12 in (0, 5):  # C or F: under it a white key too
            inset = _inset(box, gr, r * h)
            specs.append(([(inset, r * h), (width - inset, r * h)], u,
                          index["GP2M Linea ottava"], "line"))
    for frame, radius in ((box, GRID_RADIUS), (keyboard_box(s), KEYBOARD_RADIUS)):
        outline = _rounded_rect(*frame, radius * u, _arc_steps(radius, 1.0))
        specs.append((outline + outline[:1], u, index["GP2M Bordo"], "line"))
    return specs


def white_keys(settings):
    """(z0, z1, midi) of the white keys drawn on the keyboard, bottom up."""
    h = settings.row_height
    rows = span(settings) + 1
    top = rows * h
    low = settings.low_note
    keys = []
    first_c = low - (low % 12)
    c = first_c
    while (c - low) * h < top:
        base = (c - low) * h
        for k, (a, b) in enumerate(WHITE_KEYS):
            z0, z1 = max(base + a * h, 0.0), min(base + b * h, top)
            if z1 - z0 > 1e-9:
                keys.append((z0, z1, c + (0, 2, 4, 5, 7, 9, 11)[k]))
        c += 12
    return keys


def _keys(s, index, rows):
    """The keyboard (KEYBOARD / OTTAVE): white keys of a real piano, black keys on
    their rows, rounded at the free end."""
    u = unit(s)
    h = s.row_height
    kb = keyboard_box(s)
    x0, _z0, x1, top = kb
    kr = KEYBOARD_RADIUS * u
    specs = [(_rounded_rect(*kb, kr, _arc_steps(KEYBOARD_RADIUS, 1.0)), 0.001,
              index["GP2M Tasto bianco"], "fill")]
    for z0, _z1, _midi in white_keys(s):
        if z0 <= 1e-9:
            continue
        inset = _inset(kb, kr, z0)
        specs.append(([(x0 + inset, z0), (x1 - inset, z0)], u, index["GP2M Tasto bianco"],
                      "line"))
    bx = x1 - BLACK_KEY_W * u
    for r in range(rows):
        if not music.is_black(s.low_note + r):
            continue
        z0, z1 = r * h - 0.07 * h, (r + 1) * h + 0.07 * h  # 20 px of 17.5
        key = _clip_rect(bx, max(z0, 0.0), x1, min(z1, top), kb, kr)
        if key is None:
            continue
        if z0 >= 0.0 and z1 <= top:
            key = _rounded_rect(bx, z0, x1, z1, BLACK_KEY_RADIUS * u, 3,
                                corners=(True, False, False, True))
        specs.append((key, u, index["GP2M Tasto nero"], "both"))
    return specs


def _dot(cx, cz, radius, steps=16):
    return [(cx + radius * math.cos(2 * math.pi * i / steps),
             cz + radius * math.sin(2 * math.pi * i / steps)) for i in range(steps)]


def _labels(s, index, rows, top):
    """A dot on every C ("Solo Do", DO in the design), or the note names."""
    u = unit(s)
    h = s.row_height
    style = _note_style()
    x0, _z0, x1, _top = keyboard_box(s)
    specs = []
    mode = s.key_labels
    if mode == "C":
        for z0, z1, midi in white_keys(s):
            if midi % 12 == 0 and z1 - z0 > (5 / 3) * h - 1e-6:  # a whole key
                points = _dot(x0 + DOT_X * u, (z0 + z1) / 2.0, DOT_R * u)
                specs.append((points, u, index["GP2M Pallino Do"], "both"))
        return specs
    height = 0.5 * h
    for r in range(rows):
        midi = s.low_note + r
        black = music.is_black(midi)
        if mode not in ("ALL", "WHITE") or (mode == "WHITE" and black):
            continue
        text = music.note_name(midi, style)
        baseline = r * h + (h - height) / 2.0
        # White notes at the free end, black notes on their black key.
        x = x1 - BLACK_KEY_W * u + 6 * u if black else x0 + 8 * u
        name = "GP2M Etichetta tasti neri" if black else "GP2M Etichetta tasti"
        for line in glyphs.text_polylines(text, x, baseline, height, "LEFT"):
            specs.append((line, height * 0.06, index[name], "line"))
    return specs


# --- Composizione Bit (Figma "Composizione Bit": lanes instead of keys) -------------

LANE_LABEL = 14.0  # design px, height of the drum names
LANE_LABEL_X = 16.0


def _lane_band(z0, z1, x0, x1, box, radius):
    return _clip_rect(x0, z0, x1, z1, box, radius)


def _lane_material(s, lane):
    """The top lane is the lighter one (#272727), then they alternate."""
    return "GP2M Corsia" if (beat.lane_count(s) - 1 - lane) % 2 == 0 else "GP2M Corsia alterna"


def _beat_background(s, index, lanes, width):
    """Window, the two panels (KEYBOARD and MASCHERA GRIGLIA, #1B1B1B) and the lanes
    on both, cut by the rounded corners of their panel (Group 79)."""
    u = unit(s)
    h = beat.lane_height(s)
    window = window_box(s)
    specs = [(_rounded_rect(*window, WINDOW_RADIUS * u, _arc_steps(WINDOW_RADIUS, 1.0)),
              u, index["GP2M Finestra"], "both")]
    for box, radius in ((keyboard_box(s), KEYBOARD_RADIUS), (grid_box(s), GRID_RADIUS)):
        r = radius * u
        specs.append((_rounded_rect(*box, r, _arc_steps(radius, 1.0)), 0.001,
                      index["GP2M Fondo corsie"], "fill"))
        x0, _z0, x1, _z1 = box
        for lane in range(lanes):
            band = _lane_band(lane * h, (lane + 1) * h, x0, x1, box, r)
            if band:
                specs.append((band, 0.001, index[_lane_material(s, lane)], "fill"))
    return specs


def _beat_rows(s, index, lanes, width):
    """The 2 px borders between the lanes (#1C1C1C), then the outlines of the two
    panels (OUTLINE TASTIERA, OUTLINE GRIGLIA: 2 px #323232, radius 25)."""
    u = unit(s)
    h = beat.lane_height(s)
    specs = []
    for box, radius in ((keyboard_box(s), KEYBOARD_RADIUS), (grid_box(s), GRID_RADIUS)):
        r = radius * u
        x0, _z0, x1, _z1 = box
        for lane in range(1, lanes):
            z = lane * h
            inset = _inset(box, r, z)
            specs.append(([(x0 + inset, z), (x1 - inset, z)], u,
                          index["GP2M Bordo corsia"], "line"))
    for frame, radius in ((grid_box(s), GRID_RADIUS), (keyboard_box(s), KEYBOARD_RADIUS)):
        outline = _rounded_rect(*frame, radius * u, _arc_steps(radius, 1.0))
        specs.append((outline + outline[:1], u, index["GP2M Bordo"], "line"))
    return specs


def _plain_upper(text):
    """Capitals without accents (the single-stroke font of the board)."""
    import unicodedata
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).upper()


def _beat_labels(s, index, lanes):
    """The name of each lane's percussion, on the left panel ("Nessuna": none)."""
    if s.key_labels == "NONE":
        return []
    u = unit(s)
    h = beat.lane_height(s)
    x0, _z0, x1, _z1 = keyboard_box(s)
    height = LANE_LABEL * u
    room = (x1 - x0) - 2 * LANE_LABEL_X * u
    specs = []
    for lane, ident in enumerate(beat.lane_drums(s)):
        text = _plain_upper(synth.get_instrument(ident).label)
        size = height
        width = glyphs.text_width(text, size)
        if width > room > 0:
            size *= room / width
        baseline = lane * h + (h - size) / 2.0
        for line in glyphs.text_polylines(text, x0 + LANE_LABEL_X * u, baseline, size, "LEFT"):
            specs.append((line, size * 0.07, index["GP2M Etichetta corsia"], "line"))
    return specs


def _span_union(spans):
    merged = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1] + 1e-9:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def preview_lit(comp, scene):
    """Seconds of the board inside the scene Preview Range, as ``[(start, end)]``.

    ``None`` when there is nothing to darken (no Preview Range, or the range covers
    the whole loop). Times follow the playhead: the composition starts at the scene
    start (plus its offset in "one after another"), a time past the loop lands on
    the loop like the notes of the Timeline.
    """
    if scene is None or not scene.use_preview_range:
        return None
    from . import engine
    s = comp.gp2m
    length = s.length
    if length <= 0:
        return None
    fps = scene.render.fps / scene.render.fps_base
    offset = engine.state(comp).get("offset_frames", 0)
    t_in = (scene.frame_preview_start - scene.frame_start - offset) / fps
    t_out = (scene.frame_preview_end + 1 - scene.frame_start - offset) / fps
    t_out = min(t_out, engine.duration(comp))
    if t_out <= max(t_in, 0.0):
        return []  # the range is outside the composition: all dark
    t_in = max(t_in, 0.0)
    if t_out - t_in >= length - 1e-6:
        return None
    sections = engine.state(comp).get("sections") or (0.0,)
    if any(t_in < b < t_out for b in sections):
        return None  # two keyframe sections on the same board
    _start, a = engine.locate(comp, t_in)
    b = a + (t_out - t_in)
    if b <= length + 1e-9:
        return [(a, min(b, length))]
    return [(0.0, b - length), (a, length)]


def _shade(s, index, lit, top):
    """Dark boxes over the parts of the board outside the Preview Range."""
    if lit is None:
        return []
    dark, cursor = [], 0.0
    for a, b in _span_union(lit):
        if a > cursor + 1e-6:
            dark.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < s.length - 1e-6:
        dark.append((cursor, s.length))
    sw = s.seconds_width
    box = grid_box(s)
    gr = GRID_RADIUS * unit(s)
    shapes = [_clip_rect(a * sw, 0.0, b * sw, top, box, gr) for a, b in dark]
    return [(shape, 0.001, index["GP2M Fuori anteprima"], "fill") for shape in shapes if shape]


def _shade_signature(s, lit):
    if lit is None:
        return "none"
    return ";".join(f"{a:.4f}-{b:.4f}" for a, b in _span_union(lit)) + \
        f"|{s.length:.4f}|{s.seconds_width:.4f}|{dimensions(s)[2]:.4f}"


def update_preview_shade(comp, scene=None):
    """Redraw the Preview Range shading (only the shade layer, only when it changed).

    Returns True if the board was touched.
    """
    grid = grid_object(comp)
    gp = grid.data if grid is not None else None
    layer = gp.layers.get(SHADE_LAYER) if gp is not None else None
    if layer is None or not is_board_layer(layer):
        request_rebuild(comp)  # board of an older version: add the layer
        return False
    scene = scene or bpy.context.scene
    s = comp.gp2m
    lit = preview_lit(comp, scene)
    signature = _shade_signature(s, lit)
    if gp.get(SHADE_KEY) == signature:
        return False
    index = {m.name: i for i, m in enumerate(gp.materials) if m is not None}
    if "GP2M Fuori anteprima" not in index:
        request_rebuild(comp)
        return False
    frame = layer.frames[0] if len(layer.frames) else layer.frames.new(_first_frame(scene))
    drawing = frame.drawing
    layer.lock = False
    if len(drawing.strokes):
        drawing.remove_strokes()
    _add_strokes(drawing, _shade(s, index, lit, dimensions(s)[2]))
    layer.lock = True
    gp[SHADE_KEY] = signature
    return True


# --- Assembly ------------------------------------------------------------------

def _ensure_materials(gp, wanted=None):
    """Append the board materials (or only ``wanted``) after the instruments."""
    index = {}
    names = [m.name if m else "" for m in gp.materials]
    for name, (stroke, fill) in theme.board_palette().items():
        if wanted is not None and name not in wanted:
            continue
        material = gp_material(name, stroke, fill)
        _set_gp_style(material, stroke, fill)  # the theme may have changed
        material[BOARD_FLAG] = True
        if name not in names:
            gp.materials.append(material)
            names.append(name)
        index[name] = names.index(name)
    return index


def is_grid(obj):
    return obj is not None and bool(obj.get(GRID_ROLE))


def grid_object(comp):
    """The grid object of the composition, or None (missing, or the one of the
    composition this one was duplicated from)."""
    grid = comp.gp2m.grid
    if grid is None or grid.parent != comp or grid.type != "GREASEPENCIL":
        return None
    return grid


def grid_owner(grid):
    owner = grid.parent
    if owner is not None and owner.type == "GREASEPENCIL" and owner.gp2m.is_composition:
        return owner
    return None


def ensure_grid(comp):
    """The grid object of the composition, created when missing."""
    grid = grid_object(comp)
    name = comp.name + GRID_SUFFIX
    if grid is None:
        data = bpy.data.grease_pencils.new(name)
        grid = bpy.data.objects.new(name, data)
        grid[GRID_ROLE] = True
        for collection in comp.users_collection or (bpy.context.scene.collection,):
            collection.objects.link(grid)
        grid.parent = comp
        grid.matrix_parent_inverse.identity()
        grid.lock_location = grid.lock_rotation = grid.lock_scale = (True, True, True)
        grid.show_in_front = False  # the drawing (in front) stays above the grid
        comp.show_in_front = True
        comp.gp2m.grid = grid
    elif grid.data is None or grid.data.users > 1:
        grid.data = bpy.data.grease_pencils.new(name)
    if grid.name != name:
        grid.name = name
    if grid.data.name != grid.name:
        grid.data.name = grid.name
    place = (*grid.location, *grid.rotation_euler, *grid.scale)
    if any(abs(a - b) > 1e-6 for a, b in zip(place, (0.0, GRID_DEPTH, 0.0, 0.0, 0.0, 0.0,
                                                      1.0, 1.0, 1.0))):
        grid.location = (0.0, GRID_DEPTH, 0.0)
        grid.rotation_euler = (0.0, 0.0, 0.0)
        grid.scale = (1.0, 1.0, 1.0)
    return grid


def _strip_inner_board(comp):
    """Up to 0.0.20 the grid lived inside the composition: take it out (its layers,
    group and materials; the playhead stays). Returns True if something changed."""
    gp = comp.data
    changed = False
    for name in (BOARD_GROUP, LEGACY_BOARD_GROUP):
        group = gp.layer_groups.get(name)
        if group is None:
            continue
        for layer in [layer for layer in gp.layers if group in ancestors(layer)]:
            gp.layers.remove(layer)
        group = gp.layer_groups.get(name)
        if group is not None:
            gp.layer_groups.remove(group, keep_children=False)
        changed = True
    for index in reversed(range(len(gp.materials))):
        material = gp.materials[index]
        if is_board_material(material) and material.name not in HEAD_MATERIALS:
            gp.materials.pop(index=index)  # no stroke uses it any more
            changed = True
    return changed


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


def _playhead_expression(seconds_width, offset_frames, sections=None, length=0.0):
    """x of the playhead: seconds since the composition start * seconds_width.

    With keyframe sections the playhead restarts at every section and loops
    inside it (only simple-expression functions: fmod and conditionals, so the
    driver works even with Python auto-run disabled).
    """
    t = f"(frame - start - {int(offset_frames)}) * base / fps"
    if not sections or len(sections) < 2 or length <= 0:
        return f"{t} * {seconds_width:.6f}"
    expression = f"fmod({t}, {length:.6f})"
    for begin in sections[1:]:
        expression = (f"(fmod({t} - {begin:.6f}, {length:.6f}) if {t} >= {begin:.6f} "
                      f"else {expression})")
    return f"{expression} * {seconds_width:.6f}"


def set_playhead_offset(comp, offset_frames, sections=None):
    """Shift the playhead when the composition starts later (sequence mode)."""
    data = comp.data.animation_data
    if data is None:
        return
    curve = data.drivers.find(f'layers["{HEAD_LAYER}"].translation', index=0)
    if curve is None:
        return
    expression = _playhead_expression(comp.gp2m.seconds_width, offset_frames, sections,
                                      comp.gp2m.length)
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
    head = gp.layer_groups.get(HEAD_GROUP)
    if head is not None and head.parent_group is None:
        roots = list(gp.root_nodes)
        if roots and roots[-1].name != HEAD_GROUP:
            gp.layer_groups.move_top(head)
    rename_legacy_board(gp)
    tavola = gp.layer_groups.get(BOARD_GROUP)
    if tavola is not None and tavola.parent_group is None:
        roots = list(gp.root_nodes)
        if roots and roots[0].name != BOARD_GROUP:
            gp.layer_groups.move_bottom(tavola)


def protect_board(obj):
    """Keep modifiers (Array, Noise...) off the board: every modifier without a
    layer pass filter skips the board layers. Returns True if something changed."""
    changed = False
    for layer in obj.data.layers:
        if is_board_layer(layer) and layer.pass_index != BOARD_PASS:
            layer.pass_index = BOARD_PASS
            changed = True
    for modifier in obj.modifiers:
        if not hasattr(modifier, "use_layer_pass_filter") or modifier.use_layer_pass_filter:
            continue
        modifier.use_layer_pass_filter = True
        modifier.layer_pass_filter = BOARD_PASS
        modifier.invert_layer_pass_filter = True
        changed = True
    return changed


def has_board(comp):
    """True when the composition has its grid object and its playhead (and no grid of
    0.0.20 or earlier still inside)."""
    groups = comp.data.layer_groups
    if groups.get(BOARD_GROUP) is not None or groups.get(LEGACY_BOARD_GROUP) is not None:
        return False
    grid = grid_object(comp)
    from . import rig
    if rig.rig_object(comp) is not None:
        return False  # the drawn rig of 0.0.22: rebuild removes it
    return (grid is not None and grid.data is not None
            and grid.data.layer_groups.get(BOARD_GROUP) is not None
            and groups.get(HEAD_GROUP) is not None)


def rename_legacy_board(gp):
    """Files up to 0.0.12 call the board group "GP2M Tavola". Returns True if renamed."""
    legacy = gp.layer_groups.get(LEGACY_BOARD_GROUP)
    if legacy is None or gp.layer_groups.get(BOARD_GROUP) is not None:
        return False
    legacy.name = BOARD_GROUP
    return legacy.name == BOARD_GROUP


# Board layer -> materials its strokes may use.
_LAYER_MATERIALS = {
    "GP2M Sfondo": {"GP2M Finestra", "GP2M Riga bianca", "GP2M Banda tasti neri",
                    "GP2M Fondo corsie", "GP2M Corsia", "GP2M Corsia alterna"},
    "GP2M Griglia": {"GP2M Linea battito", "GP2M Linea secondo"},
    "GP2M Righe": {"GP2M Linea ottava", "GP2M Bordo", "GP2M Bordo corsia"},
    "GP2M Tasti": {"GP2M Tasto bianco", "GP2M Tasto nero"},
    "GP2M Etichette": {"GP2M Pallino Do", "GP2M Etichetta tasti",
                       "GP2M Etichetta tasti neri", "GP2M Etichetta corsia"},
    SHADE_LAYER: {"GP2M Fuori anteprima"},
    HEAD_LAYER: {"GP2M Testina"},
}


def board_materials_ok(comp):
    """False when board strokes point at the wrong material slots.

    Undo in Draw/Edit/Sculpt Mode restores the drawings but not the material
    slots: after adding (or removing) an instrument, which shifts the board
    slots, Ctrl+Z leaves the board strokes on the neighbouring materials and
    keyboard and grid turn black.
    """
    grid = grid_object(comp)
    datas = [comp.data] + ([grid.data] if grid is not None and grid.data else [])
    return all(_materials_ok(gp) for gp in datas)


def _materials_ok(gp):
    import numpy as np
    names = [m.name if m is not None else "" for m in gp.materials]
    for layer in gp.layers:
        allowed = _LAYER_MATERIALS.get(layer.name)
        if allowed is None or not is_board_layer(layer):
            continue
        for frame in layer.frames:
            drawing = frame.drawing
            count = len(drawing.strokes)
            if not count:
                continue
            attr = drawing.attributes.get("material_index")
            indices = np.zeros(count, dtype=np.int32)
            if attr is not None:
                attr.data.foreach_get("value", indices)
            for index in np.unique(indices):
                if not 0 <= index < len(names) or names[index] not in allowed:
                    return False
    return True


BOARD_KEY = "gp2m_board"  # on the grid data: the settings it was built for


def board_signature(settings):
    """The settings the grid and the playhead are drawn from."""
    s = settings
    lanes = f"|{s.kind}|{','.join(beat.lane_drums(s))}" if beat.is_beat(s) else ""
    return (f"{s.bpm:.4f}|{s.length:.4f}|{s.low_note}|{s.octaves}|{s.extra_keys}|"
            f"{s.row_height:.5f}|{s.seconds_width:.5f}|{int(s.show_beats)}|{s.key_labels}"
            + lanes)


def board_current(comp):
    """False when the grid was built for other settings. The rebuild after a change
    waits a moment (sliders), so the Undo step of the change can keep the grid of
    before: Ctrl+Shift+Z then gives back the new settings with the old grid."""
    grid = grid_object(comp)
    return grid is not None and grid.data is not None \
        and grid.data.get(BOARD_KEY) == board_signature(comp.gp2m)


def rebuild(comp, scene=None):
    """(Re)create the grid object (board and labels) and the playhead."""
    scene = scene or bpy.context.scene
    _remove_legacy_children(comp)
    _strip_inner_board(comp)
    build_grid(comp, scene)
    _build_playhead(comp, scene)


def build_grid(comp, scene=None):
    """(Re)create the grid object (board and labels) of the composition.

    It does not touch the composition's own drawing, so it is also safe while the
    composition is being moved: the copy made by Shift+D gets its board at once and
    carries it along while it follows the mouse."""
    scene = scene or bpy.context.scene
    s = comp.gp2m
    grid = ensure_grid(comp)
    grid_gp = grid.data
    palette = theme.board_palette()
    if any(m is None or m.name not in palette for m in grid_gp.materials):
        # A board of an older version (other materials): its strokes go anyway.
        for layer in [layer for layer in grid_gp.layers if is_board_layer(layer)]:
            grid_gp.layers.remove(layer)
        grid_gp.materials.clear()
    index = _ensure_materials(grid_gp)
    rows, width, top = dimensions(s)
    frame = _first_frame(scene)
    lit = preview_lit(comp, scene)
    grid_gp[SHADE_KEY] = _shade_signature(s, lit)
    grid_gp[BOARD_KEY] = board_signature(s)

    for layer in [layer for layer in grid_gp.layers if is_board_layer(layer)]:
        grid_gp.layers.remove(layer)
    board_group = _ensure_group(grid_gp, BOARD_GROUP, bottom=True)

    if beat.is_beat(s):
        pieces = (("GP2M Sfondo", _beat_background(s, index, rows, width)),
                  ("GP2M Griglia", _grid(s, index, width, top)),
                  ("GP2M Righe", _beat_rows(s, index, rows, width)),
                  ("GP2M Tasti", []),
                  ("GP2M Etichette", _beat_labels(s, index, rows)))
    else:
        pieces = (("GP2M Sfondo", _background(s, index, rows, width)),
                  ("GP2M Griglia", _grid(s, index, width, top)),
                  ("GP2M Righe", _rows(s, index, rows, width)),
                  ("GP2M Tasti", _keys(s, index, rows)),
                  ("GP2M Etichette", _labels(s, index, rows, top)))
    for name, specs in pieces + ((SHADE_LAYER, _shade(s, index, lit, top)),):
        layer = grid_gp.layers.new(name, set_active=False, layer_group=board_group)
        layer.use_lights = False
        layer.pass_index = BOARD_PASS
        _add_strokes(layer.frames.new(frame).drawing, specs)
        layer.lock = True

    apply_grid_opacity(comp)


def _build_playhead(comp, scene):
    s = comp.gp2m
    gp = comp.data
    active_name = gp.layers.active.name if gp.layers.active is not None else None
    _rows, _width, top = dimensions(s)
    frame = _first_frame(scene)
    for layer in [layer for layer in gp.layers if is_board_layer(layer)]:
        gp.layers.remove(layer)  # the playhead
    head_group = _ensure_group(gp, HEAD_GROUP, bottom=False)
    head = gp.layers.new(HEAD_LAYER, set_active=False, layer_group=head_group)
    head.use_lights = False
    head.pass_index = BOARD_PASS
    head_index = _ensure_materials(gp, HEAD_MATERIALS)
    u = unit(s)
    # CURSORE BLU: 5 px, across the grid and up to the box above the window.
    _add_strokes(head.frames.new(frame).drawing,
                 [([(0.0, 0.0), (0.0, top + rig_lift(s))], 2.5 * u,
                   head_index["GP2M Testina"], "line")])
    head.lock = True
    from . import engine
    offset = engine.state(comp).get("offset_frames", 0)
    _set_playhead_driver(gp, scene, s.seconds_width, offset)

    from . import rig
    rig.remove_legacy(comp)

    layer = gp.layers.get(active_name) if active_name else None
    if layer is None or is_board_layer(layer):
        layers = user_layers(gp)
        layer = layers[-1] if layers else None
    if layer is not None:
        gp.layers.active = layer


# --- Deferred rebuild (sliders call update callbacks continuously) -------------

_pending = set()


def _rebuild_pending():
    from .handlers import TRANSFORM_POLL, board_transform_running
    if board_transform_running():
        # Never rebuild under a running G/R/S (it crashes Blender); a clip dragged in
        # the Sequencer is fine: the board follows its end while dragging.
        return TRANSFORM_POLL
    names = list(_pending)
    _pending.clear()
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is not None and obj.gp2m.is_composition:
            try:
                rebuild(obj)
            except Exception as error:  # keep Blender responsive
                print(f"[Doodle Music] rebuild failed: {error!r}")
    if names:
        tag_redraw_views()  # also while a handle is dragged (no other redraw comes)
    return None


def apply_grid_opacity(comp):
    """Opacity of every layer of the grid (the drawing stays opaque)."""
    grid = grid_object(comp)
    if grid is None or grid.data is None:
        return
    value = comp.gp2m.grid_opacity
    for layer in grid.data.layers:
        if abs(layer.opacity - value) > 1e-6:
            layer.opacity = value


def rig_lift(settings):
    """Height of the playhead box's foot above the grid: the line reaches it."""
    from . import rig
    return rig.head_lift(settings)


def tag_redraw_views():
    for window in getattr(bpy.context.window_manager, "windows", ()):
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def request_rebuild(comp):
    _pending.add(comp.name)
    if not bpy.app.timers.is_registered(_rebuild_pending):
        bpy.app.timers.register(_rebuild_pending, first_interval=0.15)
