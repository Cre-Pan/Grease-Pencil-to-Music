# SPDX-License-Identifier: GPL-3.0-or-later
"""Show the modifiers of a layer on its strokes (visual only).

The modifiers of a layer (Array, Simmetria, Trasponi, Fade, Noise, see
``layer_mods.py``) change the sound. Here a Geometry Nodes modifier per layer
("GP2M Modificatori <layer>") does the same to the drawn strokes, with the same
formulas and in the same order: the copies of Array appear, Fade makes the
ends of every stroke thin, Trasponi moves the strokes by degrees of the scale...
The strokes themselves are never changed: switch a modifier off and they are
as drawn.

Only Noise differs in its details: the wobble has the same size and
frequency as the one heard, not the very same shape.

The node group is built once (and again when its version changes); the
modifier of each layer only carries the settings of that layer.
"""

from . import layer_mods as lm
from . import music

MODIFIER_PREFIX = "GP2M Modificatori "
GROUP_NAME = "GP2M Modificatori"
GROUP_VERSION = 4  # 2: board coordinates (the origin is on the C4 dot); 4: copies made
# before moving to the board (Edit Mode selection)
VERSION_KEY = "gp2m_version"


def is_stroke_modifier(modifier):
    return modifier.name.startswith(MODIFIER_PREFIX)


# --- Pure part (no bpy) ---------------------------------------------------------------------

def degree_tables(scale, root):
    """``(degrees, intervals, n)`` for the diatonic shift of the nodes.

    ``degrees[c]``: the scale degree (0..n, n = the root an octave up) nearest to the
    pitch class ``c`` semitones above the root, ties going down, as
    :func:`music.diatonic_shift` does. ``intervals``: the scale (padded to 12)."""
    if scale == "CHROMATIC":
        scale = "MAJOR"  # as music._scale_notes
    intervals = list(music.SCALE_INTERVALS.get(scale, music.SCALE_INTERVALS["MAJOR"]))
    n = len(intervals)
    notes = intervals + [12]
    degrees = []
    for c in range(12):
        above = next(i for i, note in enumerate(notes) if note >= c)
        if notes[above] == c or above == 0:
            degrees.append(above)
            continue
        below = above - 1
        degrees.append(below if c - notes[below] <= notes[above] - c else above)
    return degrees, intervals + [0] * (12 - n), n


def node_inputs(stack, board, origin=(0.0, 0.0)):
    """{input name: value} of the node group for a :class:`layer_mods.Stack`.

    ``origin``: board coordinates of the object's origin (the strokes are moved to
    the board, changed, and moved back)."""
    beat, rh = board.beat, board.row_height
    degrees, intervals, n = degree_tables(board.scale, board.root)
    diatonic_scale = board.scale != "CHROMATIC"
    values = {
        "Beat": float(beat), "Row": float(rh), "Low": int(board.low_note),
        "Loop": float(board.loop), "Root": int(board.root), "Degrees": int(n),
        "Origin X": float(origin[0]), "Origin Z": float(origin[1]),
    }
    for c in range(12):
        values[f"Deg {c}"] = int(degrees[c])
        values[f"Iv {c}"] = int(intervals[c])

    a = stack.array
    count = 1 if a is None else int(min(max(round(a.count), 1), lm.MAX_COPIES))
    step = 0.0 if a is None else float(min(max(a.beats, -64.0), 64.0)) * beat
    values.update({
        "Array Count": count,
        "Array Fill": bool(a is not None and a.fill and step > 0),
        "Array Step": step,
        "Array Pitch": 0 if a is None else int(a.pitch),
        "Array Diatonic": bool(a is not None and a.unit != "SEMITONES" and diatonic_scale),
        "Array Decay": 1.0 if a is None else 1.0 - float(min(max(a.decay, 0.0), 0.95)),
    })

    m = stack.mirror
    variants = [0]
    if m is not None:
        variants = ([0] if m.keep else []) + ([1] if m.time else []) \
            + ([2] if m.pitch else []) + ([3] if m.time and m.pitch else [])
        variants = variants or [0]
    values["Mirror Count"] = len(variants)
    for i in range(4):
        values[f"Mirror {i}"] = variants[i] if i < len(variants) else 0
    values["Mirror Time"] = 0.0 if m is None else \
        float(min(max(m.time_center, 0.0), 1.0)) * board.loop
    values["Mirror Pitch"] = 0.0 if m is None else \
        float(min(max(m.pitch_center, 0.0), 1.0)) * board.rows * rh

    t = stack.transpose
    values["Transpose"] = 0 if t is None else int(round(t.steps))
    values["Transpose Diatonic"] = bool(t is not None and t.unit != "SEMITONES"
                                        and diatonic_scale)

    f = stack.fade
    values.update({
        "Fade": f is not None,
        "Fade In": bool(f is not None and f.direction in ("IN", "BOTH")),
        "Fade Out": bool(f is not None and f.direction in ("OUT", "BOTH")),
        "Fade Song": bool(f is not None and f.scope == "SONG"),
        "Fade Length": 0.5 if f is None else float(min(max(f.length, 0.02), 1.0)),
        "Fade Minimum": 0.05 if f is None else float(min(max(f.minimum, 0.0), 1.0)),
    })

    z = stack.noise
    values.update({
        "Noise": z is not None,
        "Noise Pitch": 0.0 if z is None else float(z.pitch) * rh,
        "Noise Width": 0.0 if z is None else float(z.width),
        "Noise Time": 0.0 if z is None else float(z.time) * beat,
        "Noise Scale": 0.0 if z is None else max(float(z.scale), 0.0),
        "Noise Seed": 0 if z is None else int(z.seed),
    })
    return values


# (name, socket type) of the inputs, after Geometry and Layer.
INPUTS = (
    [("Beat", "FLOAT"), ("Row", "FLOAT"), ("Low", "INT"), ("Loop", "FLOAT"),
     ("Root", "INT"), ("Degrees", "INT"), ("Origin X", "FLOAT"), ("Origin Z", "FLOAT")]
    + [(f"Deg {c}", "INT") for c in range(12)]
    + [(f"Iv {c}", "INT") for c in range(12)]
    + [("Array Count", "INT"), ("Array Fill", "BOOLEAN"), ("Array Step", "FLOAT"),
       ("Array Pitch", "INT"), ("Array Diatonic", "BOOLEAN"), ("Array Decay", "FLOAT"),
       ("Mirror Count", "INT")]
    + [(f"Mirror {i}", "INT") for i in range(4)]
    + [("Mirror Time", "FLOAT"), ("Mirror Pitch", "FLOAT"),
       ("Transpose", "INT"), ("Transpose Diatonic", "BOOLEAN"),
       ("Fade", "BOOLEAN"), ("Fade In", "BOOLEAN"), ("Fade Out", "BOOLEAN"),
       ("Fade Song", "BOOLEAN"), ("Fade Length", "FLOAT"), ("Fade Minimum", "FLOAT"),
       ("Noise", "BOOLEAN"), ("Noise Pitch", "FLOAT"), ("Noise Width", "FLOAT"),
       ("Noise Time", "FLOAT"), ("Noise Scale", "FLOAT"), ("Noise Seed", "INT")]
)


# --- The node group -------------------------------------------------------------------------

_SOCKETS = {"FLOAT": "NodeSocketFloat", "INT": "NodeSocketInt", "BOOLEAN": "NodeSocketBool",
            "STRING": "NodeSocketString", "GEOMETRY": "NodeSocketGeometry"}


class _Builder:
    """Small helper to write a node tree as expressions."""

    def __init__(self, tree):
        self.tree = tree
        self.x = 0

    def node(self, kind, **props):
        node = self.tree.nodes.new(kind)
        for key, value in props.items():
            setattr(node, key, value)
        node.location = (self.x, 0)
        self.x += 30
        return node

    @staticmethod
    def socket(sockets, name):
        for socket in sockets:
            if (socket.name == name or socket.identifier == name) and socket.enabled:
                return socket
        raise KeyError(name)

    def put(self, node, name, value):
        socket = self.socket(node.inputs, name) if isinstance(name, str) else node.inputs[name]
        if hasattr(value, "is_output"):
            self.tree.links.new(value, socket)
        else:
            socket.default_value = value

    def math(self, op, a, b=0.0, c=0.0):
        node = self.node("ShaderNodeMath", operation=op)
        for i, value in enumerate((a, b, c)):
            self.put(node, i, value)
        return node.outputs[0]

    def add(self, a, b):
        return self.math("ADD", a, b)

    def sub(self, a, b):
        return self.math("SUBTRACT", a, b)

    def mul(self, a, b):
        return self.math("MULTIPLY", a, b)

    def div(self, a, b):
        return self.math("DIVIDE", a, b)

    def to_int(self, value, mode="ROUND"):
        node = self.node("FunctionNodeFloatToInt", rounding_mode=mode)
        self.put(node, 0, value)
        return node.outputs[0]

    def compare(self, op, a, b, data_type="FLOAT"):
        node = self.node("FunctionNodeCompare", data_type=data_type, operation=op)
        self.put(node, "A", a)
        self.put(node, "B", b)
        return self.socket(node.outputs, "Result")

    def boolean(self, op, a, b=False):
        node = self.node("FunctionNodeBooleanMath", operation=op)
        self.put(node, 0, a)
        self.put(node, 1, b)
        return node.outputs[0]

    def switch(self, kind, condition, false, true):
        node = self.node("GeometryNodeSwitch", input_type=kind)
        self.put(node, "Switch", condition)
        self.put(node, "False", false)
        self.put(node, "True", true)
        return node.outputs[0]

    def index_switch(self, index, values):
        node = self.node("GeometryNodeIndexSwitch", data_type="INT")
        while len(node.index_switch_items) < len(values):
            node.index_switch_items.new()
        self.put(node, "Index", index)
        for i, value in enumerate(values):
            self.put(node, i + 1, value)
        return node.outputs[0]

    def xyz(self, vector):
        node = self.node("ShaderNodeSeparateXYZ")
        self.put(node, 0, vector)
        return node.outputs[0], node.outputs[1], node.outputs[2]

    def vector(self, x, y, z):
        node = self.node("ShaderNodeCombineXYZ")
        for i, value in enumerate((x, y, z)):
            self.put(node, i, value)
        return node.outputs[0]

    def smooth(self, value):
        """``u*u*(3-2u)`` of ``value`` clamped to 0..1 (layer_mods._ease)."""
        u = self.math("MINIMUM", self.math("MAXIMUM", value, 0.0), 1.0)
        return self.mul(self.mul(u, u), self.sub(3.0, self.mul(u, 2.0)))


def _build(tree):
    tree.nodes.clear()
    tree.interface.clear()
    face = tree.interface
    face.new_socket("Geometry", in_out="INPUT", socket_type=_SOCKETS["GEOMETRY"])
    face.new_socket("Layer", in_out="INPUT", socket_type=_SOCKETS["STRING"])
    for name, kind in INPUTS:
        face.new_socket(name, in_out="INPUT", socket_type=_SOCKETS[kind])
    face.new_socket("Geometry", in_out="OUTPUT", socket_type=_SOCKETS["GEOMETRY"])

    b = _Builder(tree)
    group_in = b.node("NodeGroupInput")
    group_out = b.node("NodeGroupOutput")

    def gi(name):
        return b.socket(group_in.outputs, name)

    row = gi("Row")

    def position():
        return b.node("GeometryNodeInputPosition").outputs[0]

    def radius():
        return b.node("GeometryNodeInputRadius").outputs[0]

    def curve_index():
        node = b.node("GeometryNodeCurveOfPoint")
        b.put(node, "Point Index", b.node("GeometryNodeInputIndex").outputs[0])
        return b.socket(node.outputs, "Curve Index")

    def set_position(geometry, selection, new_position):
        node = b.node("GeometryNodeSetPosition")
        b.put(node, "Geometry", geometry)
        b.put(node, "Selection", selection)
        b.put(node, "Position", new_position)
        return node.outputs[0]

    def set_radius(geometry, selection, value):
        node = b.node("GeometryNodeSetCurveRadius")
        b.put(node, "Curve", geometry)
        b.put(node, "Selection", selection)
        b.put(node, "Radius", value)
        return node.outputs[0]

    def shift(z, steps, diatonic):
        """z moved by ``steps`` (float field) semitones or degrees (layer_mods._shift_z)."""
        pitch = b.sub(b.add(gi("Low"), b.div(z, row)), 0.5)
        base = b.math("ROUND", pitch)
        rel = b.sub(base, gi("Root"))
        pc = b.math("FLOORED_MODULO", rel, 12.0)
        octave = b.div(b.sub(rel, pc), 12.0)
        degree = b.index_switch(b.to_int(pc), [gi(f"Deg {c}") for c in range(12)])
        d = b.add(degree, steps)
        q = b.math("FLOOR", b.div(d, gi("Degrees")))
        r = b.sub(d, b.mul(q, gi("Degrees")))
        interval = b.index_switch(b.to_int(r), [gi(f"Iv {c}") for c in range(12)])
        note = b.add(b.add(gi("Root"), b.mul(b.add(octave, q), 12.0)), interval)
        semis = b.switch("FLOAT", diatonic, steps, b.sub(note, base))
        semis = b.switch("FLOAT", b.compare("EQUAL", steps, 0.0), semis, 0.0)
        return b.add(z, b.mul(semis, row))

    layer = b.node("GeometryNodeInputNamedLayerSelection")
    b.put(layer, "Name", gi("Layer"))
    selected = layer.outputs[0]

    # Array: copies every Step, each moved up by Pitch and softer by Decay.
    # Edit Mode: Blender selects (box, lasso, click) the points where they were when the
    # first node that adds or removes points ran ("edit hints"). The copies are made on
    # the strokes as drawn, before moving anything: moved to the board first, the
    # selection looked for the strokes off by the origin (box select found nothing).
    first_x = b.node("GeometryNodeFieldMinAndMax", domain="POINT", data_type="FLOAT")
    b.put(first_x, "Value", b.add(b.xyz(position())[0], gi("Origin X")))  # board x
    b.put(first_x, "Group Index", curve_index())
    fill = b.math("FLOOR", b.div(b.sub(b.sub(gi("Loop"), 1e-6), b.socket(first_x.outputs, "Min")),
                                 b.math("MAXIMUM", gi("Array Step"), 1e-9)))
    fill = b.math("MINIMUM", b.math("MAXIMUM", b.add(fill, 1.0), 1.0), float(lm.MAX_COPIES))
    count = b.switch("FLOAT", gi("Array Fill"), gi("Array Count"), fill)
    count = b.switch("FLOAT", selected, 1.0, count)
    array = b.node("GeometryNodeDuplicateElements", domain="SPLINE")
    b.put(array, "Geometry", gi("Geometry"))
    b.put(array, "Amount", b.to_int(count))
    k = b.socket(array.outputs, "Duplicate Index")
    # Object -> board coordinates (x = 0 where the loop starts, z = 0 the lowest row).
    ox, oy, oz = b.xyz(position())
    on_board = set_position(b.socket(array.outputs, "Geometry"), True,
                            b.vector(b.add(ox, gi("Origin X")), oy, b.add(oz, gi("Origin Z"))))
    x, y, z = b.xyz(position())
    moved = b.vector(b.add(x, b.mul(k, gi("Array Step"))), y,
                     shift(z, b.mul(k, gi("Array Pitch")), gi("Array Diatonic")))
    has_copy = b.compare("GREATER_THAN", k, 0.5)
    geometry = set_position(on_board, has_copy, moved)
    geometry = set_radius(geometry, has_copy,
                          b.mul(radius(), b.math("POWER", gi("Array Decay"), k)))

    # Simmetria: one copy per variant (0 original, 1 in time, 2 in pitch, 3 both).
    count = b.switch("FLOAT", selected, 1.0, gi("Mirror Count"))
    mirror = b.node("GeometryNodeDuplicateElements", domain="SPLINE")
    b.put(mirror, "Geometry", geometry)
    b.put(mirror, "Amount", b.to_int(count))
    j = b.socket(mirror.outputs, "Duplicate Index")
    code = b.index_switch(j, [gi(f"Mirror {i}") for i in range(4)])
    code = b.switch("INT", selected, 0, code)
    in_time = b.compare("EQUAL", b.math("FLOORED_MODULO", code, 2.0), 1.0)
    in_pitch = b.compare("GREATER_THAN", code, 1.5)
    reverse = b.node("GeometryNodeReverseCurve")
    b.put(reverse, "Curve", b.socket(mirror.outputs, "Geometry"))
    b.put(reverse, "Selection", in_time)
    x, y, z = b.xyz(position())
    flipped = b.vector(
        b.switch("FLOAT", in_time, x, b.sub(b.mul(gi("Mirror Time"), 2.0), x)), y,
        b.switch("FLOAT", in_pitch, z, b.sub(b.mul(gi("Mirror Pitch"), 2.0), z)))
    geometry = set_position(reverse.outputs[0], b.boolean("OR", in_time, in_pitch), flipped)

    # Trasponi.
    x, y, z = b.xyz(position())
    geometry = set_position(geometry, selected,
                            b.vector(x, y, shift(z, gi("Transpose"),
                                                 gi("Transpose Diatonic"))))

    # Distance along each stroke, in beats (a semitone counts 1/4): layer_mods._arc.
    previous = b.node("GeometryNodeOffsetPointInCurve")
    b.put(previous, "Point Index", b.node("GeometryNodeInputIndex").outputs[0])
    b.put(previous, "Offset", -1)
    at = b.node("GeometryNodeFieldAtIndex", domain="POINT", data_type="FLOAT_VECTOR")
    b.put(at, "Value", position())
    b.put(at, "Index", b.socket(previous.outputs, "Point Index"))
    vector_sub = b.node("ShaderNodeVectorMath", operation="SUBTRACT")
    b.put(vector_sub, 0, position())
    b.put(vector_sub, 1, at.outputs[0])
    dx, _dy, dz = b.xyz(vector_sub.outputs[0])
    segment = b.math("SQRT", b.add(b.math("POWER", b.div(dx, gi("Beat")), 2.0),
                                   b.math("POWER", b.mul(b.div(dz, row), 0.25), 2.0)))
    segment = b.switch("FLOAT", b.socket(previous.outputs, "Is Valid Offset"), 0.0, segment)
    accumulate = b.node("GeometryNodeAccumulateField", data_type="FLOAT", domain="POINT")
    b.put(accumulate, "Value", segment)
    b.put(accumulate, "Group Index", curve_index())
    arc = b.socket(accumulate.outputs, "Leading")
    total = b.socket(accumulate.outputs, "Total")

    # Fade: the volume, so the thickness, grows at the start and/or falls at the end.
    has_length = b.compare("GREATER_THAN", total, 0.0)
    u_stroke = b.div(arc, b.math("MAXIMUM", total, 1e-9))
    u_song = b.math("MINIMUM", b.math("MAXIMUM", b.div(b.xyz(position())[0],
                                                       b.math("MAXIMUM", gi("Loop"), 1e-9)),
                                      0.0), 1.0)
    u = b.switch("FLOAT", gi("Fade Song"), u_stroke, u_song)
    gain_in = b.switch("FLOAT", gi("Fade In"), 1.0, b.smooth(b.div(u, gi("Fade Length"))))
    gain_out = b.switch("FLOAT", gi("Fade Out"), 1.0,
                        b.smooth(b.div(b.sub(1.0, u), gi("Fade Length"))))
    low = gi("Fade Minimum")
    gain = b.add(low, b.mul(b.sub(1.0, low), b.mul(gain_in, gain_out)))
    fade_on = b.boolean("AND", selected, gi("Fade"))
    fade_on = b.boolean("AND", fade_on, b.boolean("OR", gi("Fade Song"), has_length))
    geometry = set_radius(geometry, fade_on, b.mul(radius(), gain))

    # Noise: every stroke a little early or late, its pitch and thickness wobbling.
    noise_on = b.boolean("AND", selected, gi("Noise"))
    curve = curve_index()
    early = b.node("FunctionNodeRandomValue", data_type="FLOAT")
    b.put(early, "Min", -1.0)
    b.put(early, "Max", 1.0)
    b.put(early, "ID", curve)
    b.put(early, "Seed", gi("Noise Seed"))
    stroke_seed = b.add(b.mul(curve, 17.13), b.mul(gi("Noise Seed"), 57.13))
    t = b.mul(arc, gi("Noise Scale"))

    def wobble(t, offset):
        """Smooth 1-D value noise in [-1, 1] (layer_mods._noise1, another hash)."""
        i = b.math("FLOOR", t)
        f = b.sub(t, i)
        w = b.mul(b.mul(f, f), b.sub(3.0, b.mul(f, 2.0)))
        seed = b.add(stroke_seed, offset)
        values = []
        for step in (0.0, 1.0):
            hashed = b.node("ShaderNodeTexWhiteNoise", noise_dimensions="1D")
            b.put(hashed, "W", b.add(b.add(i, step), b.mul(seed, 0.618)))
            values.append(b.socket(hashed.outputs, "Value"))
        mixed = b.add(b.mul(values[0], b.sub(1.0, w)), b.mul(values[1], w))
        return b.sub(b.mul(mixed, 2.0), 1.0)

    x, y, z = b.xyz(position())
    wobbled = b.vector(b.add(x, b.mul(early.outputs[0], gi("Noise Time"))), y,
                       b.add(z, b.mul(gi("Noise Pitch"), wobble(t, 1.0))))
    thick = b.mul(radius(), b.add(1.0, b.mul(gi("Noise Width"), wobble(b.mul(t, 1.3), 2.0))))
    thick = b.math("MAXIMUM", thick, b.mul(row, 0.01))
    # Radius first: the arc above is read on the strokes before they move.
    geometry = set_radius(geometry, noise_on, thick)
    geometry = set_position(geometry, noise_on, wobbled)
    # ... and back to the object's coordinates.
    bx, by, bz = b.xyz(position())
    geometry = set_position(geometry, True, b.vector(b.sub(bx, gi("Origin X")), by,
                                                     b.sub(bz, gi("Origin Z"))))

    b.put(group_out, 0, geometry)
    tree[VERSION_KEY] = GROUP_VERSION


def node_group():
    """The shared node group, built (again) when missing or of another version."""
    import bpy
    tree = bpy.data.node_groups.get(GROUP_NAME)
    if tree is not None and tree.bl_idname != "GeometryNodeTree":
        tree = None
    if tree is None:
        tree = bpy.data.node_groups.new(GROUP_NAME, "GeometryNodeTree")
    if tree.get(VERSION_KEY) != GROUP_VERSION or not len(tree.nodes):
        _build(tree)
    return tree


# --- Keeping the modifiers in line with the layers -----------------------------------------

def _set_input(modifier, identifiers, name, value):
    """Write one input of the modifier if it differs. Returns True if written."""
    # Blender 5: modifier.properties.inputs.<identifier>.value (no ID properties).
    socket = getattr(modifier.properties.inputs, identifiers[name])
    current = socket.value
    if isinstance(value, float):
        if abs(float(current) - value) < 1e-7:
            return False
    elif current == value:
        return False
    socket.value = value
    return True


def wanted(obj):
    """{layer name: Stack} of the layers whose modifiers are shown on the strokes."""
    from . import board, engine, props
    if not getattr(obj.gp2m, "show_layer_mods", True):
        return {}
    result = {}
    for layer in board.user_layers(obj.data):
        stack = engine.layer_mods(props.find_layer_settings(obj.data, layer.name))
        if stack:
            result[layer.name] = stack
    return result


def sync(obj):
    """Add, update or remove the modifiers of the layers (writes only changes).
    Returns True if something changed."""
    from . import board, engine, mixer
    stacks = wanted(obj)
    changed = False
    for modifier in [m for m in obj.modifiers if is_stroke_modifier(m)]:
        if modifier.name[len(MODIFIER_PREFIX):] not in stacks:
            obj.modifiers.remove(modifier)
            changed = True
    if not stacks:
        return changed
    tree = node_group()
    identifiers = {item.name: item.identifier for item in tree.interface.items_tree
                   if item.item_type == "SOCKET" and item.in_out == "INPUT"}
    spec = engine.board_spec(obj.gp2m)
    mods_board = mixer.mods_board(spec, board.dimensions(obj.gp2m)[0])
    for index, (name, stack) in enumerate(stacks.items()):
        modifier = obj.modifiers.get(MODIFIER_PREFIX + name)
        if modifier is None:
            modifier = obj.modifiers.new(MODIFIER_PREFIX + name, "NODES")
            modifier.show_expanded = False
            changed = True
        if modifier.node_group != tree:
            modifier.node_group = tree
            changed = True
        # First in the stack, in the order of the layers (before the user's own).
        position = list(obj.modifiers).index(modifier)
        if position != index:
            obj.modifiers.move(position, index)
            changed = True
        values = {"Layer": name, **node_inputs(stack, mods_board, board.origin(obj.gp2m))}
        for key, value in values.items():
            changed |= _set_input(modifier, identifiers, key, value)
    if changed:
        obj.update_tag()  # inputs written as ID properties: evaluate again
    return changed

