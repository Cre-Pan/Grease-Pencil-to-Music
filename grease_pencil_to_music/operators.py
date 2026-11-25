# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators: create a composition, regenerate, export, small UI helpers."""

import math
import os

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from mathutils import Euler, Vector

from . import board, engine, props, synth


def active_composition(context):
    obj = context.active_object
    if obj is None:
        return None
    if obj.type == "GREASEPENCIL" and obj.gp2m.is_composition:
        return obj
    parent = obj.parent  # the grid (or a legacy child) of a composition
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
        space = area.spaces.active
        region_3d = getattr(space, "region_3d", None)
        if region_3d is None:
            continue
        region_3d.view_perspective = "ORTHO"
        region_3d.view_rotation = Euler((math.pi / 2.0, 0.0, 0.0)).to_quaternion()
        region_3d.view_location = center
        region_3d.view_distance = max(width + kw, top) * 0.85
        shading = space.shading
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
        collection = getattr(context, "collection", None) or scene.collection
        collection.objects.link(obj)
        obj.location = scene.cursor.location
        obj.show_in_front = True
        obj.gp2m.is_composition = True

        from . import prefs
        p = prefs.get_prefs()
        s = obj.gp2m
        for attr in ("bpm", "length", "low_note", "octaves", "row_height", "seconds_width",
                     "scale", "time_grid", "key_labels", "sample_rate"):
            setattr(s, attr, getattr(p, "new_" + attr))
        first_frame = min(1, scene.frame_start)
        for i in range(1, p.new_layers + 1):
            layer = gp.layers.new(f"Livello {i}")
            layer.use_lights = False  # instrument colors stay readable
            layer.frames.new(first_frame)
        gp.layers.active = gp.layers[0]
        # The starting instruments live in the first layer.
        for material in board.instrument_materials(prefs.new_instrument_idents()):
            material.gp2m_layer = gp.layers[0].name
            gp.materials.append(material)
        props.ensure_layer_settings(gp)
        s.follow_scene = p.new_follow_scene  # In/Out of the scene (or the scene takes its length)
        # A new level of the timeline: above the other compositions and any clip.
        s.channel = engine.new_composition_channel(
            scene, len(board.user_layers(gp)) if s.layer_channels else 1)

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


def append_instrument(comp, material):
    """Add a material slot before the board materials; returns its index."""
    gp = comp.data
    gp.materials.append(material)
    index = len(gp.materials) - 1
    first_board = next((i for i, m in enumerate(gp.materials) if board.is_board_material(m)),
                       None)
    if first_board is not None and first_board < index:
        _move_material_slot(comp, index, first_board)
        index = first_board
    return index


def remove_material_slot(comp, index):
    """Remove a slot; its strokes go to the first instrument of the composition."""
    gp = comp.data
    for layer in gp.layers:
        for frame in layer.frames:
            for stroke in frame.drawing.strokes:
                if stroke.material_index == index:
                    stroke.material_index = 0
    # Blender shifts the strokes of the following slots down by itself: shifting them
    # here too moved them onto the wrong instrument (two slots down).
    gp.materials.pop(index=index)


def use_instrument(comp, layer_name, index=None):
    """Draw on ``layer_name`` with the instrument at slot ``index`` (or its first one)."""
    gp = comp.data
    layer = gp.layers.get(layer_name)
    if layer is not None and not board.is_board_layer(layer):
        gp.layers.active = layer
    if index is None:
        own = board.layer_instruments(comp, layer_name)
        index = own[0][0] if own else None
    if index is not None and 0 <= index < len(comp.material_slots):
        comp.active_material_index = index


class GP2M_OT_add_instrument(bpy.types.Operator):
    """Aggiungi uno strumento al livello"""

    bl_idname = "gp2m.add_instrument"
    bl_label = "Aggiungi strumento"
    bl_options = {"REGISTER", "UNDO"}

    instrument: EnumProperty(name="Strumento", items=props.INSTRUMENT_ITEMS)
    layer: StringProperty(name="Livello", description="Vuoto = livello attivo")

    @classmethod
    def poll(cls, context):
        return _composition_poll(context)

    def execute(self, context):
        comp = active_composition(context)
        gp = comp.data
        layer_name = self.layer
        if not layer_name or gp.layers.get(layer_name) is None:
            active = gp.layers.active
            layers = board.user_layers(gp)
            layer_name = (active.name if active is not None and not board.is_board_layer(active)
                          else (layers[-1].name if layers else ""))
        material = board.instrument_material(synth.get_instrument(self.instrument))
        material.gp2m_layer = layer_name
        index = append_instrument(comp, material)
        use_instrument(comp, layer_name, index)
        return {"FINISHED"}


class GP2M_OT_set_instrument(bpy.types.Operator):
    """Cambia lo strumento: i tratti restano dove sono e suonano con quello nuovo"""

    bl_idname = "gp2m.set_instrument"
    bl_label = "Cambia strumento"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    instrument: EnumProperty(name="Strumento", items=props.INSTRUMENT_ITEMS)
    index: IntProperty(default=-1, description="Slot dello strumento (-1 = strumento attivo)")

    @classmethod
    def poll(cls, context):
        return _composition_poll(context)

    def execute(self, context):
        comp = active_composition(context)
        index = comp.active_material_index if self.index < 0 else self.index
        if not 0 <= index < len(comp.material_slots):
            return {"CANCELLED"}
        material = comp.material_slots[index].material
        if material is None or board.is_board_material(material) or material.grease_pencil is None:
            return {"CANCELLED"}
        board.change_instrument(material, synth.get_instrument(self.instrument))
        return {"FINISHED"}


class GP2M_OT_use_instrument(bpy.types.Operator):
    """Disegna su questo livello con questo strumento"""

    bl_idname = "gp2m.use_instrument"
    bl_label = "Usa strumento"
    bl_options = {"INTERNAL", "UNDO"}

    layer: StringProperty()
    index: IntProperty(default=-1)

    @classmethod
    def poll(cls, context):
        return _composition_poll(context)

    def execute(self, context):
        use_instrument(active_composition(context), self.layer,
                       None if self.index < 0 else self.index)
        return {"FINISHED"}


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
    """Togli lo strumento (i suoi tratti passano al primo strumento della composizione)"""

    bl_idname = "gp2m.remove_instrument"
    bl_label = "Togli strumento"
    bl_options = {"REGISTER", "UNDO"}

    index: IntProperty(default=-1, description="Slot da togliere (-1 = strumento attivo)")

    @classmethod
    def poll(cls, context):
        comp = active_composition(context)
        if comp is None or not comp.material_slots:
            return False
        material = comp.material_slots[comp.active_material_index].material
        return not board.is_board_material(material)

    def execute(self, context):
        comp = active_composition(context)
        index = comp.active_material_index if self.index < 0 else self.index
        if not 0 <= index < len(comp.material_slots) or board.is_board_material(
                comp.material_slots[index].material):
            return {"CANCELLED"}
        remove_material_slot(comp, index)
        comp.active_material_index = max(0, min(index, len(comp.material_slots) - 1) - 1)
        return {"FINISHED"}


class GP2M_OT_add_layer(bpy.types.Operator):
    """Aggiungi un nuovo livello (poi aggiungi i suoi strumenti con "+ Strumento")"""

    bl_idname = "gp2m.add_layer"
    bl_label = "Nuovo livello"
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
    """Elimina il livello attivo con i suoi tratti e i suoi strumenti"""

    bl_idname = "gp2m.remove_layer"
    bl_label = "Elimina livello"
    bl_options = {"REGISTER", "UNDO"}

    name: StringProperty(description="Vuoto = livello attivo")

    @classmethod
    def poll(cls, context):
        comp = active_composition(context)
        return comp is not None and len(board.user_layers(comp.data)) > 1

    def execute(self, context):
        comp = active_composition(context)
        gp = comp.data
        layer = gp.layers.get(self.name) if self.name else gp.layers.active
        if layer is None or board.is_board_layer(layer):
            return {"CANCELLED"}
        name = layer.name
        layers = board.user_layers(gp)
        position = [l.name for l in layers].index(name)
        gp.layers.remove(layer)
        for index, item in enumerate(gp.gp2m_layers):
            if item.name == name:
                gp.gp2m_layers.remove(index)
                break
        # Its instruments go too, unless strokes of other layers still use them.
        used = {stroke.material_index for other in board.user_layers(gp)
                for frame in other.frames if frame.drawing is not None
                for stroke in frame.drawing.strokes}
        for index, material in sorted(board.layer_instruments(comp, name), reverse=True):
            if index in used:
                material.gp2m_layer = ""
            else:
                remove_material_slot(comp, index)
        props.apply_solo(gp)  # the layer in Solo is gone: the others light up again
        layers = board.user_layers(gp)
        use_instrument(comp, layers[max(0, position - 1)].name)
        return {"FINISHED"}


def _siblings(gp, node):
    """The nodes next to ``node`` in its group (or at the root), bottom first."""
    parent = node.parent_group
    return list(parent.children) if parent is not None else list(gp.root_nodes)


def _sibling_index(gp, node):
    return [n.name for n in _siblings(gp, node)].index(node.name)


def _move_node(gp, node, direction):
    if board.is_group(node):
        gp.layer_groups.move(node, direction)
    else:
        gp.layers.move(node, direction)


def _place_next_to(gp, node, target, above=True):
    """Move ``node`` right above (or below) ``target``, a node of the same group."""
    for _ in range(len(gp.layers) + len(gp.layer_groups) + 2):
        names = [n.name for n in _siblings(gp, node)]
        if target.name not in names:
            return
        index = names.index(node.name)
        wanted = names.index(target.name) + (1 if above else -1)
        if index == wanted:
            return
        _move_node(gp, node, "DOWN" if index > wanted else "UP")
        if [n.name for n in _siblings(gp, node)] == names:
            return  # could not move further


def _move_out_of_group(gp, layer, above):
    """Take ``layer`` out of its group, right above or below the group."""
    group = layer.parent_group
    gp.layers.move_to_layer_group(layer, group.parent_group)
    _place_next_to(gp, layer, group, above=above)


def _unique_node_name(gp, base):
    index = 1
    while (gp.layers.get(f"{base} {index}") is not None
           or gp.layer_groups.get(f"{base} {index}") is not None):
        index += 1
    return f"{base} {index}"


def _after_tree_change(comp):
    gp = comp.data
    board.ensure_order(gp)
    props.ensure_layer_settings(gp)


class GP2M_OT_move_layer(bpy.types.Operator):
    """Sposta il livello attivo sopra o sotto (entra ed esce dai gruppi)"""

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
        comp = active_composition(context)
        gp = comp.data
        layer = gp.layers.active
        up = self.direction == "UP"
        siblings = _siblings(gp, layer)
        index = _sibling_index(gp, layer)
        neighbour_index = index + (1 if up else -1)
        if not 0 <= neighbour_index < len(siblings):
            if layer.parent_group is None:
                return {"CANCELLED"}
            _move_out_of_group(gp, layer, above=up)  # past the edge of its group
        else:
            neighbour = siblings[neighbour_index]
            if board.is_group(neighbour):
                # Never cross the board (below) or the playhead (above).
                if neighbour.name in board.BOARD_GROUPS:
                    return {"CANCELLED"}
                # Into the group, at its bottom going up and at its top going down.
                gp.layers.move_to_layer_group(layer, neighbour)
                if up:
                    gp.layers.move_bottom(layer)
            else:
                gp.layers.move(layer, self.direction)
        gp.layers.active = layer
        _after_tree_change(comp)
        return {"FINISHED"}


class GP2M_OT_duplicate_layer(bpy.types.Operator):
    """Duplica il livello attivo con i suoi tratti, le sue impostazioni e i suoi strumenti
    (copiati: puoi cambiarli senza toccare l'originale)"""

    bl_idname = "gp2m.duplicate_layer"
    bl_label = "Duplica livello"
    bl_options = {"REGISTER", "UNDO"}

    empty_keyframes: BoolProperty(name="Keyframe vuoti", default=False,
                                  description="Copia i keyframe senza i tratti")

    @classmethod
    def poll(cls, context):
        comp = active_composition(context)
        return (comp is not None and comp.data.layers.active is not None
                and not board.is_board_layer(comp.data.layers.active))

    def execute(self, context):
        comp = active_composition(context)
        gp = comp.data
        with context.temp_override(active_object=comp, object=comp):
            result = bpy.ops.grease_pencil.layer_duplicate(empty_keyframes=self.empty_keyframes)
        if result != {"FINISHED"}:
            return {"CANCELLED"}
        _after_tree_change(comp)
        if gp.layers.active is not None:
            use_instrument(comp, gp.layers.active.name)
        return {"FINISHED"}


class GP2M_OT_add_group(bpy.types.Operator):
    """Metti il livello attivo in un nuovo gruppo. Un gruppo si può silenziare, mettere in
    Solo e nascondere tutto insieme"""

    bl_idname = "gp2m.add_group"
    bl_label = "Nuovo gruppo"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return GP2M_OT_duplicate_layer.poll(context)

    def execute(self, context):
        comp = active_composition(context)
        gp = comp.data
        layer = gp.layers.active
        group = gp.layer_groups.new(_unique_node_name(gp, "Gruppo"),
                                    parent_group=layer.parent_group)
        group.is_expanded = True
        _place_next_to(gp, group, layer, above=True)
        gp.layers.move_to_layer_group(layer, group)
        gp.layers.active = layer
        _after_tree_change(comp)
        return {"FINISHED"}


class GP2M_OT_move_to_group(bpy.types.Operator):
    """Sposta il livello attivo in un gruppo (in cima), o fuori dal suo gruppo"""

    bl_idname = "gp2m.move_to_group"
    bl_label = "Sposta nel gruppo"
    bl_options = {"REGISTER", "UNDO"}

    group: StringProperty(name="Gruppo", description="Vuoto = fuori dal gruppo")

    @classmethod
    def poll(cls, context):
        return GP2M_OT_duplicate_layer.poll(context)

    def execute(self, context):
        comp = active_composition(context)
        gp = comp.data
        layer = gp.layers.active
        if not self.group:
            if layer.parent_group is None:
                return {"CANCELLED"}
            _move_out_of_group(gp, layer, above=True)
        else:
            group = gp.layer_groups.get(self.group)
            if group is None or board.is_board_group(group):
                return {"CANCELLED"}
            gp.layers.move_to_layer_group(layer, group)
            group.is_expanded = True
        gp.layers.active = layer
        _after_tree_change(comp)
        return {"FINISHED"}


class GP2M_OT_ungroup(bpy.types.Operator):
    """Sciogli il gruppo del livello attivo: i suoi livelli restano al loro posto"""

    bl_idname = "gp2m.ungroup"
    bl_label = "Sciogli gruppo"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        comp = active_composition(context)
        return comp is not None and _target_group(comp.data) is not None

    def execute(self, context):
        comp = active_composition(context)
        gp = comp.data
        group = _target_group(gp)
        if group is None:
            return {"CANCELLED"}
        layer = gp.layers.active
        name = group.name
        gp.layer_groups.remove(group, keep_children=True)
        for index, item in enumerate(gp.gp2m_layers):
            if item.name == name and item.is_group:
                gp.gp2m_layers.remove(index)
                break
        if layer is not None:
            gp.layers.active = layer
        _after_tree_change(comp)
        props.apply_solo(gp)  # a Solo of the group no longer holds
        return {"FINISHED"}


class GP2M_OT_layers_reveal(bpy.types.Operator):
    """Mostra tutti i livelli e i gruppi (la tavola non cambia)"""

    bl_idname = "gp2m.layers_reveal"
    bl_label = "Mostra tutti"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _composition_poll(context)

    def execute(self, context):
        gp = active_composition(context).data
        for node, _depth in board.user_tree(gp):
            if node.hide:
                node.hide = False
        return {"FINISHED"}


class GP2M_OT_layers_hide_others(bpy.types.Operator):
    """Nascondi tutti i livelli tranne quello attivo (la tavola non cambia)"""

    bl_idname = "gp2m.layers_hide_others"
    bl_label = "Nascondi gli altri"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return GP2M_OT_duplicate_layer.poll(context)

    def execute(self, context):
        gp = active_composition(context).data
        active = gp.layers.active
        keep = {active.name} | {group.name for group in board.ancestors(active)}
        for node, _depth in board.user_tree(gp):
            if board.is_group(node):
                if node.name in keep and node.hide:
                    node.hide = False
                continue
            hide = node.name not in keep
            if node.hide != hide:
                node.hide = hide
        return {"FINISHED"}


class GP2M_OT_layers_lock(bpy.types.Operator):
    """Blocca o sblocca tutti i livelli (la tavola resta bloccata)"""

    bl_idname = "gp2m.layers_lock"
    bl_label = "Blocca tutti"
    bl_options = {"REGISTER", "UNDO"}

    lock: BoolProperty(name="Blocca", default=True)

    @classmethod
    def poll(cls, context):
        return _composition_poll(context)

    def execute(self, context):
        gp = active_composition(context).data
        for node, _depth in board.user_tree(gp):
            if node.lock != self.lock:
                node.lock = self.lock
        return {"FINISHED"}


def _layer_below(gp, layer):
    layers = list(gp.layers)
    index = [l.name for l in layers].index(layer.name)
    return layers[index - 1] if index > 0 else None


class GP2M_OT_merge_layer(bpy.types.Operator):
    """Unisci il livello attivo a quello sotto, o tutti i livelli di un gruppo in uno.
    Gli strumenti dei livelli uniti passano al livello che resta"""

    bl_idname = "gp2m.merge_layer"
    bl_label = "Unisci"
    bl_options = {"REGISTER", "UNDO"}

    mode: EnumProperty(items=(("ACTIVE", "Unisci sotto", ""), ("GROUP", "Unisci gruppo", "")))

    @classmethod
    def poll(cls, context):
        comp = active_composition(context)
        if comp is None:
            return False
        gp = comp.data
        if _target_group(gp) is not None:
            return True
        layer = gp.layers.active
        if layer is None or board.is_board_layer(layer):
            return False
        below = _layer_below(gp, layer)
        return below is not None and not board.is_board_layer(below)

    def execute(self, context):
        comp = active_composition(context)
        gp = comp.data
        before = {layer.name for layer in board.user_layers(gp)}
        if self.mode == "GROUP":
            group = _target_group(gp)
            if group is None:
                return {"CANCELLED"}
            gp.layer_groups.active = group
        else:
            layer = gp.layers.active
            below = _layer_below(gp, layer) if layer is not None else None
            if below is None or board.is_board_layer(below):
                return {"CANCELLED"}
        with context.temp_override(active_object=comp, object=comp):
            result = bpy.ops.grease_pencil.layer_merge(mode=self.mode)
        if result != {"FINISHED"} or gp.layers.active is None:
            return {"CANCELLED"}
        merged = gp.layers.active.name
        gone = before - {layer.name for layer in board.user_layers(gp)}
        for material in gp.materials:
            if material is not None and getattr(material, "gp2m_layer", "") in gone:
                material.gp2m_layer = merged
        for index in reversed(range(len(gp.gp2m_layers))):
            item = gp.gp2m_layers[index]
            if item.name in gone and not item.is_group:
                gp.gp2m_layers.remove(index)
        _after_tree_change(comp)
        props.apply_solo(gp)  # a Solo of a merged layer or group no longer holds
        use_instrument(comp, merged)
        return {"FINISHED"}


# Settings copied with "Copia impostazioni" (kept for the session, like Blender's
# own copy of modifiers between objects).
_clipboard = {}


def _active_settings(context):
    comp = active_composition(context)
    if comp is None:
        return None, None
    layer = comp.data.layers.active
    if layer is None or board.is_board_layer(layer):
        return comp, None
    return comp, props.find_layer_settings(comp.data, layer.name)


class GP2M_OT_copy_layer_settings(bpy.types.Operator):
    """Copia lettura, armonia, modificatori ed effetti del livello attivo"""

    bl_idname = "gp2m.copy_layer_settings"
    bl_label = "Copia impostazioni del livello"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return _active_settings(context)[1] is not None

    def execute(self, context):
        _comp, settings = _active_settings(context)
        _clipboard.clear()
        _clipboard.update(props.layer_values(settings))
        self.report({"INFO"}, f"Impostazioni di {settings.name} copiate")
        return {"FINISHED"}


class GP2M_OT_paste_layer_settings(bpy.types.Operator):
    """Incolla le impostazioni copiate nel livello attivo, o in tutti i livelli"""

    bl_idname = "gp2m.paste_layer_settings"
    bl_label = "Incolla impostazioni del livello"
    bl_options = {"REGISTER", "UNDO"}

    every: BoolProperty(name="In tutti i livelli", default=False,
                        description="Incolla in tutti i livelli della composizione")

    @classmethod
    def poll(cls, context):
        if not _clipboard:
            cls.poll_message_set("Prima copia le impostazioni di un livello")
            return False
        return _active_settings(context)[1] is not None

    def execute(self, context):
        comp, settings = _active_settings(context)
        gp = comp.data
        targets = ([props.find_layer_settings(gp, layer.name) for layer in board.user_layers(gp)]
                   if self.every else [settings])
        targets = [item for item in targets if item is not None]
        for item in targets:
            props.set_layer_values(item, _clipboard)
        engine.state(comp).pop("layers", None)  # every layer may have changed
        self.report({"INFO"}, f"Impostazioni incollate in {len(targets)} livell"
                    + ("o" if len(targets) == 1 else "i"))
        return {"FINISHED"}


def _target_group(gp):
    """The active group, or the group of the active layer."""
    group = gp.layer_groups.active
    if group is None and gp.layers.active is not None:
        group = gp.layers.active.parent_group
    if group is None or board.is_board_group(group):
        return None
    return group


classes = (
    GP2M_OT_add_composition,
    GP2M_OT_regenerate,
    GP2M_OT_rebuild_board,
    GP2M_OT_export,
    GP2M_OT_add_instrument,
    GP2M_OT_set_instrument,
    GP2M_OT_use_instrument,
    GP2M_OT_load_sample,
    GP2M_OT_remove_instrument,
    GP2M_OT_add_layer,
    GP2M_OT_remove_layer,
    GP2M_OT_move_layer,
    GP2M_OT_duplicate_layer,
    GP2M_OT_add_group,
    GP2M_OT_move_to_group,
    GP2M_OT_ungroup,
    GP2M_OT_layers_reveal,
    GP2M_OT_layers_hide_others,
    GP2M_OT_layers_lock,
    GP2M_OT_merge_layer,
    GP2M_OT_copy_layer_settings,
    GP2M_OT_paste_layer_settings,
)
