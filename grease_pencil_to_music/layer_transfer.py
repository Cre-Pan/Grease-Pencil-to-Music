# SPDX-License-Identifier: GPL-3.0-or-later
"""Move a layer from one composition to another, keeping what it plays.

Used when the clip of a layer is pasted or dragged into the meta-clip of another
composition in the Video Sequencer. The strokes keep their time and their notes:
x is converted through seconds, z through MIDI notes (the two boards may have a
different scale, lowest note or row height); thickness follows the row height,
so the volume stays the same. The layer's instruments and settings go with it.
"""

import numpy as np

from . import board, props

_VALUE_KEYS = {
    "FLOAT": "value", "INT": "value", "BOOLEAN": "value", "INT8": "value",
    "FLOAT_VECTOR": "vector", "FLOAT2": "vector", "FLOAT_COLOR": "color",
    "BYTE_COLOR": "color", "INT32_2D": "value", "QUATERNION": "value",
}
_WIDTH = {"FLOAT_VECTOR": 3, "FLOAT2": 2, "FLOAT_COLOR": 4, "BYTE_COLOR": 4,
          "INT32_2D": 2, "QUATERNION": 4}
_DTYPE = {"INT": np.int32, "INT8": np.int32, "BOOLEAN": bool, "INT32_2D": np.int32}


def _read(attr):
    key = _VALUE_KEYS[attr.data_type]
    data = np.empty(len(attr.data) * _WIDTH.get(attr.data_type, 1),
                    dtype=_DTYPE.get(attr.data_type, np.float32))
    attr.data.foreach_get(key, data)
    return key, data


def _copy_drawing(src, dst, remap, transform):
    """Copy every stroke of ``src`` into the empty drawing ``dst``."""
    count = len(src.strokes)
    if not count:
        return
    dst.add_strokes([len(stroke.points) for stroke in src.strokes])
    for attr in src.attributes:
        if attr.data_type not in _VALUE_KEYS or attr.name.startswith("."):
            continue
        key, data = _read(attr)
        if attr.name == "position":
            data = transform["position"](data)
        elif attr.name == "radius":
            data = data * transform["radius"]
        elif attr.name == "material_index":
            data = np.array([remap.get(int(i), int(i)) for i in data], dtype=np.int32)
        target = dst.attributes.get(attr.name)
        if target is None:
            target = dst.attributes.new(attr.name, attr.data_type, attr.domain)
        if len(target.data) * _WIDTH.get(attr.data_type, 1) != len(data):
            continue
        target.data.foreach_set(key, data)
    dst.tag_positions_changed()


def _transform(src_comp, dst_comp):
    a, b = src_comp.gp2m, dst_comp.gp2m

    def position(data):
        xyz = data.reshape(-1, 3).astype(np.float64)
        seconds = xyz[:, 0] / max(a.seconds_width, 1e-9)
        notes = xyz[:, 2] / max(a.row_height, 1e-9) + a.low_note
        xyz[:, 0] = seconds * b.seconds_width
        xyz[:, 2] = (notes - b.low_note) * b.row_height
        return xyz.astype(np.float32).ravel()

    return {"position": position, "radius": b.row_height / max(a.row_height, 1e-9)}


def _unique_layer_name(gp, name):
    if gp.layers.get(name) is None and gp.layer_groups.get(name) is None:
        return name
    index = 1
    while gp.layers.get(f"{name}.{index:03d}") is not None:
        index += 1
    return f"{name}.{index:03d}"


def move_layer(src_comp, dst_comp, layer_name):
    """Move ``layer_name`` from ``src_comp`` to the top of ``dst_comp``. Returns the
    name it has there, or None."""
    src_gp, dst_gp = src_comp.data, dst_comp.data
    layer = src_gp.layers.get(layer_name)
    if layer is None or board.is_board_layer(layer) or src_comp == dst_comp:
        return None
    name = _unique_layer_name(dst_gp, layer_name)
    # Instruments: the layer's own go with it; any other material used is shared.
    remap = {}
    used = set()
    for frame in layer.frames:
        attr = frame.drawing.attributes.get("material_index")
        if attr is not None and len(attr.data):
            _key, data = _read(attr)
            used.update(int(i) for i in np.unique(data))
        elif len(frame.drawing.strokes):
            used.add(0)
    own = {index for index, _m in board.layer_instruments(src_comp, layer_name)}
    for index in sorted(used | own):
        if not 0 <= index < len(src_gp.materials):
            continue
        material = src_gp.materials[index]
        if material is None:
            continue
        names = [m.name if m else "" for m in dst_gp.materials]
        if material.name in names:
            remap[index] = names.index(material.name)
            continue
        from .operators import append_instrument
        remap[index] = append_instrument(dst_comp, material)
        if index in own:
            material.gp2m_layer = name
    new = dst_gp.layers.new(name, set_active=False)
    new.use_lights = False
    new.opacity = layer.opacity
    new.hide = layer.hide
    transform = _transform(src_comp, dst_comp)
    for frame in layer.frames:
        target = new.frames.new(frame.frame_number)
        _copy_drawing(frame.drawing, target.drawing, remap, transform)
    board.ensure_order(dst_gp)
    props.ensure_layer_settings(dst_gp)
    _copy_settings(src_gp, layer_name, dst_gp, name)
    # Remove it from the source, with the instruments that only it used.
    src_gp.layers.remove(layer)
    for index in sorted(own, reverse=True):
        if index < len(src_gp.materials):
            src_gp.materials.pop(index=index)
    _shift_material_indices(src_gp, sorted(own))
    props.ensure_layer_settings(src_gp)
    from . import handlers
    handlers.mark_dirty(src_comp)
    handlers.mark_dirty(dst_comp)
    return name


def _shift_material_indices(gp, removed):
    """After popping material slots, the strokes above them point one slot lower."""
    if not removed:
        return
    removed = np.array(removed)
    for layer in gp.layers:
        for frame in layer.frames:
            attr = frame.drawing.attributes.get("material_index")
            if attr is None or not len(attr.data):
                continue
            _key, data = _read(attr)
            shift = np.searchsorted(removed, data, side="left")
            data = (data - shift).astype(np.int32)
            attr.data.foreach_set("value", data)


def _copy_settings(src_gp, src_name, dst_gp, dst_name):
    source = props.find_layer_settings(src_gp, src_name)
    target = props.find_layer_settings(dst_gp, dst_name)
    if source is None or target is None:
        return
    for prop in source.bl_rna.properties:
        ident = prop.identifier
        if ident in ("rna_type", "name") or prop.is_readonly:
            continue
        try:
            setattr(target, ident, getattr(source, ident))
        except (AttributeError, TypeError, ValueError):
            pass
