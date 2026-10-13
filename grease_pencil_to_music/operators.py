# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators: create a composition, regenerate, export, small UI helpers."""

import math
import os

import bpy
from bpy.props import EnumProperty, IntProperty, StringProperty
from mathutils import Euler, Vector

from . import board, engine, props, synth


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
        shading = area.spaces.active.shading
        shading.type = "SOLID"
        shading.color_type = "TEXTURE"  # flat material colors: the board reads well
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

        from . import prefs
        p = prefs.get_prefs()
        s = obj.gp2m
        for attr in ("bpm", "length", "low_note", "octaves", "row_height", "seconds_width",
                     "scale", "time_grid", "key_labels", "sample_rate"):
            setattr(s, attr, getattr(p, "new_" + attr))
        for material in board.instrument_materials(prefs.new_instrument_idents()):
            gp.materials.append(material)
        first_frame = min(1, scene.frame_start)
        for i in range(1, p.new_layers + 1):
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
        if p.enter_draw_mode:  # by default you stay in Object Mode
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


def _composition_poll(context):
    return active_composition(context) is not None


class GP2M_OT_add_instrument(bpy.types.Operator):
    """Aggiungi uno strumento (un materiale Grease Pencil) alla composizione"""

    bl_idname = "gp2m.add_instrument"
    bl_label = "Aggiungi strumento"
    bl_options = {"REGISTER", "UNDO"}

    instrument: EnumProperty(name="Strumento", items=props.INSTRUMENT_ITEMS)

    @classmethod
    def poll(cls, context):
        return _composition_poll(context)

    def execute(self, context):
        comp = active_composition(context)
        material = board.instrument_material(synth.get_instrument(self.instrument))
        gp = comp.data
        names = [m.name if m else "" for m in gp.materials]
        if material.name not in names:
            # Keep instruments before the board materials.
            gp.materials.append(material)
            names.append(material.name)
            first_board = next((i for i, m in enumerate(gp.materials)
                                if board.is_board_material(m)), None)
            if first_board is not None:
                _move_material_slot(comp, len(names) - 1, first_board)
                names = [m.name if m else "" for m in gp.materials]
        comp.active_material_index = names.index(material.name)
        return {"FINISHED"}


def _move_material_slot(comp, src, dst):
    """Move a material slot keeping every stroke on its material."""
    gp = comp.data
    if src == dst:
        return
    materials = list(gp.materials)
    order = list(range(len(materials)))
    order.insert(dst, order.pop(src))
    remap = {old: new for new, old in enumerate(order)}
    for layer in gp.layers:
        for frame in layer.frames:
            for stroke in frame.drawing.strokes:
                stroke.material_index = remap.get(stroke.material_index, stroke.material_index)
    for index, old in enumerate(order):
        gp.materials[index] = materials[old]


class GP2M_OT_load_sample(bpy.types.Operator):
    """Carica un file audio come campione dello strumento attivo"""

    bl_idname = "gp2m.load_sample"
    bl_label = "Carica suono…"
    bl_options = {"REGISTER", "UNDO"}

    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.wav;*.mp3;*.ogg;*.flac;*.aif;*.aiff",
                                options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        material = getattr(context, "material", None) or _active_material(context)
        return material is not None and not board.is_board_material(material)

    def invoke(self, context, _event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        material = getattr(context, "material", None) or _active_material(context)
        try:
            sound = bpy.data.sounds.load(self.filepath, check_existing=True)
        except RuntimeError as error:
            self.report({"ERROR"}, f"Suono non caricato: {error}")
            return {"CANCELLED"}
        material.gp2m_instrument = "SAMPLE"
        material.gp2m_sample = sound
        return {"FINISHED"}


def _active_material(context):
    comp = active_composition(context)
    if comp is None or not comp.material_slots:
        return None
    return comp.material_slots[comp.active_material_index].material


class GP2M_OT_remove_instrument(bpy.types.Operator):
    """Togli lo strumento attivo dalla composizione (i suoi tratti passano al primo strumento)"""

    bl_idname = "gp2m.remove_instrument"
    bl_label = "Togli strumento"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        comp = active_composition(context)
        if comp is None or not comp.material_slots:
            return False
        material = comp.material_slots[comp.active_material_index].material
        return not board.is_board_material(material)

    def execute(self, context):
        comp = active_composition(context)
        gp = comp.data
        index = comp.active_material_index
        for layer in board.user_layers(gp):
            for frame in layer.frames:
                for stroke in frame.drawing.strokes:
                    if stroke.material_index == index:
                        stroke.material_index = 0
                    elif stroke.material_index > index:
                        stroke.material_index -= 1
        for layer in gp.layers:
            if board.is_board_layer(layer):
                for frame in layer.frames:
                    for stroke in frame.drawing.strokes:
                        if stroke.material_index > index:
                            stroke.material_index -= 1
        gp.materials.pop(index=index)
        comp.active_material_index = max(0, index - 1)
        return {"FINISHED"}


class GP2M_OT_add_layer(bpy.types.Operator):
    """Aggiungi un nuovo livello alla composizione"""

    bl_idname = "gp2m.add_layer"
    bl_label = "Aggiungi livello"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _composition_poll(context)

    def execute(self, context):
        gp = active_composition(context).data
        index = len(board.user_layers(gp)) + 1
        while gp.layers.get(f"Livello {index}") is not None:
            index += 1
        layer = gp.layers.new(f"Livello {index}")
        layer.use_lights = False
        layer.frames.new(min(1, context.scene.frame_start))
        board.ensure_order(gp)  # new layers start on top: keep the playhead above them
        gp.layers.active = layer
        props.ensure_layer_settings(gp)
        return {"FINISHED"}


class GP2M_OT_remove_layer(bpy.types.Operator):
    """Elimina il livello attivo con i suoi tratti"""

    bl_idname = "gp2m.remove_layer"
    bl_label = "Elimina livello"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        comp = active_composition(context)
        if comp is None:
            return False
        active = comp.data.layers.active
        return (active is not None and not board.is_board_layer(active)
                and len(board.user_layers(comp.data)) > 1)

    def execute(self, context):
        gp = active_composition(context).data
        layer = gp.layers.active
        name = layer.name
        layers = board.user_layers(gp)
        position = [l.name for l in layers].index(name)
        gp.layers.remove(layer)
        for index, item in enumerate(gp.gp2m_layers):
            if item.name == name:
                gp.gp2m_layers.remove(index)
                break
        layers = board.user_layers(gp)
        gp.layers.active = layers[max(0, position - 1)]
        return {"FINISHED"}


class GP2M_OT_move_layer(bpy.types.Operator):
    """Sposta il livello attivo sopra o sotto"""

    bl_idname = "gp2m.move_layer"
    bl_label = "Sposta livello"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(items=(("UP", "Su", ""), ("DOWN", "Giù", "")))

    @classmethod
    def poll(cls, context):
        comp = active_composition(context)
        return (comp is not None and comp.data.layers.active is not None
                and not board.is_board_layer(comp.data.layers.active))

    def execute(self, context):
        gp = active_composition(context).data
        layer = gp.layers.active
        layers = list(gp.layers)
        index = [l.name for l in layers].index(layer.name)
        neighbour = index + (1 if self.direction == "UP" else -1)
        # Never cross the board (below) or the playhead (above).
        if not 0 <= neighbour < len(layers) or board.is_board_layer(layers[neighbour]):
            return {"CANCELLED"}
        gp.layers.move(layer, self.direction)
        return {"FINISHED"}


classes = (
    GP2M_OT_add_composition,
    GP2M_OT_regenerate,
    GP2M_OT_rebuild_board,
    GP2M_OT_export,
    GP2M_OT_add_instrument,
    GP2M_OT_load_sample,
    GP2M_OT_remove_instrument,
    GP2M_OT_add_layer,
    GP2M_OT_remove_layer,
    GP2M_OT_move_layer,
)
