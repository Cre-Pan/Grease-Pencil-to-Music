# SPDX-License-Identifier: GPL-3.0-or-later
"""Read Grease Pencil v3 strokes into NumPy arrays.

Hidden layers and hidden materials are muted: they are not read at all.
Modifiers and shader effects are ignored (the original data is read).
"""

from dataclasses import dataclass, field

import bpy
import numpy as np

from .board import is_board_layer
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
    ident = getattr(material, "gp2m_instrument", synth.DEFAULT_INSTRUMENT)
    if ident == "SAMPLE":
        from . import samples
        return samples.instrument_key(material)
    if ident == "LIBRARY":
        from . import samples
        return samples.library_key(material)
    return ident


def material_gain(material):
    return float(getattr(material, "gp2m_volume", 1.0)) if material is not None else 1.0


FX_FIELDS = ("delay_mix", "delay_beats", "delay_feedback", "reverb_mix", "reverb_size", "lofi")


def material_fx(material):
    """Instrument effects as a tuple, or None when they are all off."""
    fx = getattr(material, "gp2m_fx", None) if material is not None else None
    if fx is None or (fx.delay_mix <= 0 and fx.reverb_mix <= 0 and fx.lofi <= 0):
        return None
    return tuple(round(float(getattr(fx, name)), 4) for name in FX_FIELDS)


def material_muted(material):
    return bool(material is not None and material.grease_pencil is not None
                and material.grease_pencil.hide)


def read_drawing(drawing, materials, layer_name, matrix=None, radius_divisors=None):
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
    if radius_divisors:  # undo the "volume visible" Thickness modifiers
        index_of_point = np.repeat(
            _attribute(drawing, "material_index", curves, default=0).astype(np.int64),
            np.diff(offsets))
        for slot, factor in radius_divisors.items():
            radius = np.where(index_of_point == slot, radius / factor, radius)
    opacity = _attribute(drawing, "opacity", points, default=1.0)
    has_color = drawing.attributes.get("vertex_color") is not None
    color = _attribute(drawing, "vertex_color", points, 4) if has_color else None
    material_index = _attribute(drawing, "material_index", curves, default=0).astype(np.int64)
    softness = _attribute(drawing, "softness", curves, default=0.0)
    fill_id = _attribute(drawing, "fill_id", curves, default=0).astype(np.int64)
    cyclic = _attribute(drawing, "cyclic", curves, default=0).astype(bool)
    has_time = drawing.attributes.get("delta_time") is not None  # drawing speed
    times = _attribute(drawing, "delta_time", points) if has_time else None

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
            gain=material_gain(material),
            fx=material_fx(material),
            filled=bool(fill_id[i] != 0) and b - a >= 3,
            cyclic=bool(cyclic[i]),
            times=None if times is None else times[a:b].astype(np.float64),
        ))
    return strokes


def read_composition(obj, frame_number, use_modifiers=False, depsgraph=None):
    """Read every visible user layer of a composition object.

    With ``use_modifiers`` the evaluated strokes (after modifiers such as
    Noise or Array) of the current frame are read instead of the originals.
    """
    materials = [slot.material for slot in obj.material_slots]
    gp = obj.data
    divisors = None
    if use_modifiers:
        depsgraph = depsgraph or bpy.context.evaluated_depsgraph_get()
        gp = obj.evaluated_get(depsgraph).data
        from .feedback import radius_divisors
        divisors = radius_divisors(obj)
    result = []
    for layer in gp.layers:
        if layer.hide or is_board_layer(layer):
            continue
        read = LayerRead(name=layer.name, opacity=float(layer.opacity),
                         keyframes=len(layer.frames))
        if use_modifiers:
            frame = layer.current_frame()
            drawing = frame.drawing if frame is not None else None
        else:
            drawing = drawing_at(layer, frame_number)
        if drawing is not None:
            read.strokes = read_drawing(drawing, materials, layer.name,
                                        layer.matrix_local, divisors)
        result.append(read)
    return result


def has_unsupported_stack(obj):
    """True when user modifiers or shader effects are present (not heard by default)."""
    from .feedback import user_modifiers
    return bool(user_modifiers(obj) or len(getattr(obj, "shader_effects", ())))
