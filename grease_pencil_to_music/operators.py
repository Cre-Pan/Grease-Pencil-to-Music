# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators: create a composition, regenerate, export, small UI helpers."""

import math
import os

import bpy
from bpy.props import EnumProperty, IntProperty, StringProperty
from mathutils import Euler, Vector

from . import board, engine, props


def active_composition(context):
    obj = context.active_object
    if obj is None:
        return None
    if obj.type == "GREASEPENCIL" and obj.gp2m.is_composition:
        return obj
    parent = obj.parent
    if parent is not None and parent.type == "GREASEPENCIL" and parent.gp2m.is_composition:
        return parent
    return None


def _next_name():
    index = 1
    while bpy.data.objects.get(f"Composizione Musicale {index}") is not None:
        index += 1
    return f"Composizione Musicale {index}"


def frame_view(context, comp):
    """Front orthographic view centred on the board, in every 3D viewport."""
    screen = context.screen
    if screen is None:
        return
    s = comp.gp2m
    _rows, width, top = board.dimensions(s)
    kw = board.key_width(s)
    center = comp.matrix_world @ Vector(((width - kw) / 2.0, 0.0, top / 2.0))
    for area in screen.areas:
        if area.type != "VIEW_3D":
            continue
        region_3d = area.spaces.active.region_3d
        region_3d.view_perspective = "ORTHO"
        region_3d.view_rotation = Euler((math.pi / 2.0, 0.0, 0.0)).to_quaternion()
        region_3d.view_location = center
        region_3d.view_distance = max(width + kw, top) * 0.85
        area.tag_redraw()


class GP2M_OT_add_composition(bpy.types.Operator):
    """Crea una tavola musicale con pianoforte e un oggetto Grease Pencil su cui disegnare"""

    bl_idname = "gp2m.add_composition"
    bl_label = "Composizione Musicale"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if context.mode != "OBJECT" and context.active_object is not None:
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except RuntimeError:
                pass
        scene = context.scene
        name = _next_name()
        gp = bpy.data.grease_pencils.new(name)
        obj = bpy.data.objects.new(name, gp)
        context.collection.objects.link(obj)
        obj.location = scene.cursor.location
        obj.show_in_front = True
        obj.gp2m.is_composition = True

        for material in board.instrument_materials():
            gp.materials.append(material)
        first_frame = min(1, scene.frame_start)
        for i in range(1, 4):
            layer = gp.layers.new(f"Livello {i}")
            layer.use_lights = False  # instrument colors stay readable
            layer.frames.new(first_frame)
        gp.layers.active = gp.layers[0]
        props.ensure_layer_settings(gp)

        board.rebuild(obj, scene)
        for other in context.selected_objects:
            other.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        obj.active_material_index = 0

        scene.sync_mode = "AUDIO_SYNC"
        tool_settings = scene.tool_settings
        tool_settings.gpencil_stroke_placement_view3d = "ORIGIN"
        tool_settings.gpencil_sculpt.lock_axis = "AXIS_Y"  # draw on the X-Z wall
        engine.regenerate_safe(obj, scene, force=True)
        frame_view(context, obj)
        try:
            bpy.ops.object.mode_set(mode="PAINT_GREASE_PENCIL")
        except RuntimeError:
            pass  # e.g. no 3D viewport (background mode)
        return {"FINISHED"}


class GP2M_OT_regenerate(bpy.types.Operator):
    """Rigenera subito il suono della composizione"""

    bl_idname = "gp2m.regenerate"
    bl_label = "Genera suono"

    @classmethod
    def poll(cls, context):
        return active_composition(context) is not None

    def execute(self, context):
        comp = active_composition(context)
        result = engine.regenerate_safe(comp, context.scene, force=True)
        if result is None:
            self.report({"ERROR"}, engine.state(comp).get("error") or "Errore")
            return {"CANCELLED"}
        self.report({"INFO"}, f"{len(result.notes)} note generate")
        return {"FINISHED"}


class GP2M_OT_rebuild_board(bpy.types.Operator):
    """Ricrea tavola, pianoforte, etichette e testina"""

    bl_idname = "gp2m.rebuild_board"
    bl_label = "Ricostruisci tavola"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return active_composition(context) is not None

    def execute(self, context):
        comp = active_composition(context)
        board.rebuild(comp, context.scene)
        frame_view(context, comp)
        return {"FINISHED"}


EXPORT_FORMATS = (
    ("WAV", "WAV", "Audio non compresso"),
    ("MP3", "MP3", "Audio compresso"),
    ("MIDI", "MIDI", "Note per DAW e notazione (una traccia per livello e strumento)"),
)
EXTENSIONS = {"WAV": ".wav", "MP3": ".mp3", "MIDI": ".mid"}


class GP2M_OT_export(bpy.types.Operator):
    """Esporta la composizione (livelli e materiali nascosti sono esclusi)"""

    bl_idname = "gp2m.export"
    bl_label = "Esporta"

    format: EnumProperty(name="Formato", items=EXPORT_FORMATS, default="WAV")
    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.wav;*.mp3;*.mid", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return active_composition(context) is not None

    def _with_extension(self, path):
        ext = EXTENSIONS[self.format]
        root, current = os.path.splitext(path)
        return path if current.lower() == ext else root + ext

    def check(self, _context):
        fixed = self._with_extension(self.filepath)
        if fixed != self.filepath:
            self.filepath = fixed
            return True
        return False

    def invoke(self, context, _event):
        comp = active_composition(context)
        folder = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.path.expanduser("~")
        self.filepath = os.path.join(folder, engine._safe(comp.name) + EXTENSIONS[self.format])
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        comp = active_composition(context)
        path = self._with_extension(bpy.path.abspath(self.filepath))
        try:
            result = engine.export(comp, context.scene, path, self.format)
        except Exception as error:
            self.report({"ERROR"}, f"Esportazione non riuscita: {error}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Esportato {os.path.basename(path)} ({len(result.notes)} note)")
        return {"FINISHED"}


class GP2M_OT_set_active_material(bpy.types.Operator):
    """Disegna con questo strumento"""

    bl_idname = "gp2m.set_active_material"
    bl_label = "Usa strumento"
    bl_options = {"INTERNAL", "UNDO"}

    index: IntProperty()

    def execute(self, context):
        comp = active_composition(context)
        if comp is None:
            return {"CANCELLED"}
        comp.active_material_index = self.index
        return {"FINISHED"}


class GP2M_OT_set_active_layer(bpy.types.Operator):
    """Disegna su questo livello"""

    bl_idname = "gp2m.set_active_layer"
    bl_label = "Usa livello"
    bl_options = {"INTERNAL", "UNDO"}

    name: StringProperty()

    def execute(self, context):
        comp = active_composition(context)
        layer = comp.data.layers.get(self.name) if comp else None
        if layer is None:
            return {"CANCELLED"}
        comp.data.layers.active = layer
        return {"FINISHED"}


class GP2M_OT_add_layer(bpy.types.Operator):
    """Aggiungi un nuovo livello alla composizione"""

    bl_idname = "gp2m.add_layer"
    bl_label = "Aggiungi livello"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return active_composition(context) is not None

    def execute(self, context):
        gp = active_composition(context).data
        index = len(gp.layers) + 1
        while gp.layers.get(f"Livello {index}") is not None:
            index += 1
        layer = gp.layers.new(f"Livello {index}")
        layer.use_lights = False
        layer.frames.new(min(1, context.scene.frame_start))
        gp.layers.active = layer
        props.ensure_layer_settings(gp)
        return {"FINISHED"}


classes = (
    GP2M_OT_add_composition,
    GP2M_OT_regenerate,
    GP2M_OT_rebuild_board,
    GP2M_OT_export,
    GP2M_OT_set_active_material,
    GP2M_OT_set_active_layer,
    GP2M_OT_add_layer,
)
