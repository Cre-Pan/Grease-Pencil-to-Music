# SPDX-License-Identifier: GPL-3.0-or-later
"""Read Grease Pencil v3 strokes into NumPy arrays.

Hidden layers and hidden materials are muted: they are not read at all.
Modifiers and shader effects are ignored (the original data is read).
"""

from dataclasses import dataclass, field

import numpy as np

from .interpret import StrokeData
from . import synth

_DTYPES = {"INT": np.int32, "BOOLEAN": bool, "INT8": np.int8}


@dataclass
class LayerRead:
    name: str
    opacity: float
    strokes: list = field(default_factory=list)
    keyframes: int = 0


def _attribute(drawing, name, count, width=1, default=0.0):
    attr = drawing.attributes.get(name)
    shape = (count, width) if width > 1 else (count,)
    if attr is None or count == 0:
        return np.full(shape, default, dtype=np.float32)
    dtype = _DTYPES.get(attr.data_type, np.float32)
    data_field = {"FLOAT_VECTOR": "vector", "FLOAT_COLOR": "color"}.get(attr.data_type, "value")
    out = np.empty(count * width, dtype=dtype)
    attr.data.foreach_get(data_field, out)
    return out.reshape(shape)


def drawing_at(layer, frame_number):
    """The drawing shown at ``frame_number`` (or the first one before any key)."""
    frames = list(layer.frames)
    if not frames:
        return None
    before = [f for f in frames if f.frame_number <= frame_number]
    frame = (max(before, key=lambda f: f.frame_number) if before
             else min(frames, key=lambda f: f.frame_number))
    return frame.drawing


def material_instrument(material):
    if material is None:
        return synth.DEFAULT_INSTRUMENT
    return getattr(material, "gp2m_instrument", synth.DEFAULT_INSTRUMENT)


def material_muted(material):
    return bool(material is not None and material.grease_pencil is not None
                and material.grease_pencil.hide)


def read_drawing(drawing, materials, layer_name, matrix=None):
    """Return the audible strokes of one drawing as :class:`StrokeData`."""
    curves = len(drawing.strokes)
    if curves == 0:
        return []  # an empty drawing reports one offset but cannot read it
    offsets = np.empty(curves + 1, dtype=np.int32)
    drawing.curve_offsets.foreach_get("value", offsets)
    points = int(offsets[-1])
    if points == 0:
        return []

    position = _attribute(drawing, "position", points, 3)
    if matrix is not None:
        m = np.asarray(matrix, dtype=np.float64)
        if not np.allclose(m, np.eye(4)):
            position = position @ m[:3, :3].T + m[:3, 3]
    radius = _attribute(drawing, "radius", points, default=0.01)
    opacity = _attribute(drawing, "opacity", points, default=1.0)
    has_color = drawing.attributes.get("vertex_color") is not None
    color = _attribute(drawing, "vertex_color", points, 4) if has_color else None
    material_index = _attribute(drawing, "material_index", curves, default=0).astype(np.int64)
    softness = _attribute(drawing, "softness", curves, default=0.0)

    strokes = []
    for i in range(curves):
        a, b = int(offsets[i]), int(offsets[i + 1])
        if b <= a:
            continue
        idx = int(material_index[i])
        material = materials[idx] if 0 <= idx < len(materials) else None
        if material_muted(material):
            continue
        strokes.append(StrokeData(
            x=position[a:b, 0].astype(np.float64),
            z=position[a:b, 2].astype(np.float64),
            radius=radius[a:b].astype(np.float64),
            opacity=opacity[a:b].astype(np.float64),
            color=None if color is None else color[a:b].astype(np.float64),
            softness=float(softness[i]),
            instrument=material_instrument(material),
            layer=layer_name,
        ))
    return strokes


def read_composition(obj, frame_number):
    """Read every visible layer of a composition object."""
    gp = obj.data
    materials = [slot.material for slot in obj.material_slots]
    result = []
    for layer in gp.layers:
        if layer.hide:
            continue
        read = LayerRead(name=layer.name, opacity=float(layer.opacity),
                         keyframes=len(layer.frames))
        drawing = drawing_at(layer, frame_number)
        if drawing is not None:
            read.strokes = read_drawing(drawing, materials, layer.name,
                                        layer.matrix_local)
        result.append(read)
    return result


def has_unsupported_stack(obj):
    """True when modifiers or shader effects are present (they are not heard)."""
    return bool(len(obj.modifiers) or len(getattr(obj, "shader_effects", ())))
