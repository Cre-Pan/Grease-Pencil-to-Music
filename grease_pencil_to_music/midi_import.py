# SPDX-License-Identifier: GPL-3.0-or-later
"""File > Import > MIDI: notes become Grease Pencil strokes on the board.

Every MIDI track (and channel) becomes a layer; the General MIDI program
chooses the instrument (drums: one instrument per drum sound); velocity
becomes thickness.
"""

import math
import os

import bpy
import numpy as np
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ImportHelper

from . import board, engine, midi, props, synth
from .operators import active_composition


def _material_slot(comp, ident):
    """Slot index of the composition's material for ``ident`` (added if missing)."""
    gp = comp.data
    for index, material in enumerate(gp.materials):
        if material is not None and not board.is_board_material(material) \
                and material.gp2m_instrument == ident:
            return index
    material = board.instrument_material(synth.get_instrument(ident))
    gp.materials.append(material)
    index = len(gp.materials) - 1
    first_board = next((i for i, m in enumerate(gp.materials) if board.is_board_material(m)),
                       None)
    if first_board is not None and first_board < index:
        from .operators import _move_material_slot
        _move_material_slot(comp, index, first_board)
        index = first_board
    return index


def _unique_layer(gp, name):
    base, index = name[:56] or "MIDI", 2
    name = base
    while gp.layers.get(name) is not None:
        name = f"{base} {index}"
        index += 1
    return name


def fit_board(comp, tracks, bpm):
    s = comp.gp2m
    pitches = [n[2] for t in tracks if t["program"] >= 0 for n in t["notes"]]
    ends = [n[1] for t in tracks for n in t["notes"]]
    if bpm > 0:
        s.bpm = min(max(bpm, 20.0), 300.0)
    if ends:
        s.length = min(max(math.ceil(max(ends)), 1.0), 300.0)
    if pitches:
        low = max(12, (min(pitches) // 12) * 12)
        s.low_note = min(low, 96)
        s.octaves = int(min(max(math.ceil((max(pitches) + 1 - s.low_note) / 12), 1), 7))


def import_midi(context, path, comp=None, fit=True):
    """Import ``path`` into ``comp`` (a new composition when None)."""
    tracks, bpm = midi.read_midi(path)
    empty_defaults = []
    if comp is None:
        bpy.ops.gp2m.add_composition()
        comp = active_composition(context)
        empty_defaults = [layer.name for layer in board.user_layers(comp.data)]
    if fit:
        fit_board(comp, tracks, bpm)
    s = comp.gp2m
    h, sw = s.row_height, s.seconds_width
    top = s.low_note + s.octaves * 12
    gp = comp.data
    frame = min(1, context.scene.frame_start)
    base_radius = h * 0.22
    for track in tracks:
        layer = gp.layers.new(_unique_layer(gp, track["name"]))
        layer.use_lights = False
        drawing = layer.frames.new(frame).drawing
        strokes = []
        for start, end, pitch, velocity in track["notes"]:
            ident = synth.instrument_for_program(track["program"], pitch)
            row_pitch = pitch
            if track["program"] < 0:  # drums: keep them inside the board
                row_pitch = min(max(pitch, s.low_note), top)
            if not s.low_note <= row_pitch <= top or start >= s.length:
                continue
            end = min(end, s.length)
            count = max(2, int((end - start) * 20) + 1)
            x = np.linspace(start * sw, max(end, start + 0.02) * sw, count)
            z = np.full(count, (row_pitch - s.low_note + 0.5) * h)
            radius = np.full(count, base_radius * (0.35 + 0.65 * velocity / 127.0))
            strokes.append((x, z, radius, _material_slot(comp, ident)))
        board.add_strokes_bulk(drawing, strokes)
    if tracks:  # the empty "Livello 1..3" of a new composition are not needed
        for name in empty_defaults:
            layer = gp.layers.get(name)
            if layer is not None and not layer.frames[0].drawing.strokes:
                gp.layers.remove(layer)
    layers = board.user_layers(gp)
    if layers:
        gp.layers.active = layers[-1]
    board.ensure_order(gp)
    props.ensure_layer_settings(gp)
    board.rebuild(comp, context.scene)
    engine.regenerate_safe(comp, context.scene, force=True)
    return comp, sum(len(t["notes"]) for t in tracks)


class GP2M_OT_import_midi(bpy.types.Operator, ImportHelper):
    """Importa un file MIDI come tratti Grease Pencil su una composizione"""

    bl_idname = "gp2m.import_midi"
    bl_label = "Importa MIDI"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".mid"
    filter_glob: StringProperty(default="*.mid;*.midi", options={"HIDDEN"})
    new_composition: BoolProperty(name="Nuova composizione", default=True,
                                  description="Crea una nuova composizione invece di usare "
                                  "quella attiva")
    fit_board: BoolProperty(name="Adatta la tavola", default=True,
                            description="BPM, durata e ottave seguono il file MIDI")

    def execute(self, context):
        comp = None if self.new_composition else active_composition(context)
        if context.mode != "OBJECT" and context.active_object is not None:
            bpy.ops.object.mode_set(mode="OBJECT")
        try:
            comp, count = import_midi(context, self.filepath, comp, self.fit_board)
        except (OSError, midi.MidiError) as error:
            self.report({"ERROR"}, f"MIDI non leggibile: {error}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"{os.path.basename(self.filepath)}: {count} note in {comp.name}")
        return {"FINISHED"}


def menu_import(self, _context):
    self.layout.operator(GP2M_OT_import_midi.bl_idname, text="MIDI → Grease Pencil (.mid)",
                         icon="FILE_SOUND")


classes = (GP2M_OT_import_midi,)


def register():
    bpy.types.TOPBAR_MT_file_import.append(menu_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_import)
