# SPDX-License-Identifier: GPL-3.0-or-later
"""Open and save the web app's project (.json) in Blender.

The same drawing moves between the iPad and Blender: layers with their reading
(Q, QL, O, OL, G), volume and reverb, strokes with instrument, width, opacity and
drawing time, filled shapes, the web app's recorded sounds (as "Campione"
instruments) and the Beat section (a "Beat" layer of drum hits).
"""

import os
import tempfile
import wave

import bpy
import numpy as np
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper

from . import board, engine, music, props, reader, synth, web_project
from .operators import active_composition, append_instrument


# --- Web → Blender ----------------------------------------------------------------------

def _write_wav(path, data, rate):
    pcm = (np.clip(data, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())


def _load_sound(sound):
    """A packed Blender sound for a web app sound."""
    folder = tempfile.mkdtemp(prefix="gp2m_web_")
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in sound.name).strip() or "suono"
    path = os.path.join(folder, f"{safe}.wav")
    _write_wav(path, sound.data, web_project.SAMPLE_RATE)
    blender_sound = bpy.data.sounds.load(path, check_existing=False)
    blender_sound.name = sound.name
    try:
        blender_sound.pack()
    except RuntimeError:
        pass  # stays linked to the temporary file; still plays in this session
    return blender_sound


def _slot_for(comp, layer_name, key, sounds, cache):
    """Material slot of ``key`` (instrument id or web sound id) for a layer."""
    if (layer_name, key) in cache:
        return cache[(layer_name, key)]
    if key in sounds:
        material = board.instrument_material(synth.get_instrument("SAMPLE"))
        sound, root = sounds[key]
        material.name = material[board.LABEL_KEY] = sound.name
        material.gp2m_sample = sound
        material.gp2m_sample_root = root
    else:
        material = board.instrument_material(synth.get_instrument(key))
    material.gp2m_layer = layer_name
    cache[(layer_name, key)] = index = append_instrument(comp, material)
    return index


def _write_attribute(drawing, name, kind, domain, start, values, default):
    attrs = drawing.attributes
    attr = attrs.get(name) or attrs.new(name, kind, domain)
    dtype = np.int32 if kind in ("INT", "BOOLEAN") else np.float32
    current = np.full(len(attr.data), default, dtype=dtype)
    attr.data.foreach_get("value", current)
    current[start:start + len(values)] = values
    attr.data.foreach_set("value", current)


def _add_strokes(drawing, strokes, slots):
    """Add ``web_project.Stroke`` objects with all their attributes."""
    if not strokes:
        return
    first_curve = len(drawing.strokes)
    position = drawing.attributes.get("position")
    first_point = len(position.data) if position is not None and first_curve else 0
    board.add_strokes_bulk(drawing, [(s.x, s.z, s.radius, slot)
                                     for s, slot in zip(strokes, slots)])
    counts = [len(s.x) for s in strokes]
    opacity = np.concatenate([np.full(n, s.opacity, np.float32) for s, n in zip(strokes, counts)])
    _write_attribute(drawing, "opacity", "FLOAT", "POINT", first_point, opacity, 1.0)
    if any(s.times is not None for s in strokes):
        times = np.concatenate([
            (s.times if s.times is not None else np.zeros(n)).astype(np.float32)
            for s, n in zip(strokes, counts)])
        _write_attribute(drawing, "delta_time", "FLOAT", "POINT", first_point, times, 0.0)
    if any(s.softness for s in strokes):
        _write_attribute(drawing, "softness", "FLOAT", "CURVE", first_curve,
                         np.array([s.softness for s in strokes], np.float32), 0.0)
    if any(s.filled for s in strokes):
        fill = np.array([first_curve + i + 1 if s.filled else 0 for i, s in enumerate(strokes)],
                        np.int32)
        _write_attribute(drawing, "fill_id", "INT", "CURVE", first_curve, fill, 0)
        for i, s in enumerate(strokes):
            if s.filled:
                drawing.strokes[first_curve + i].cyclic = True
    drawing.tag_positions_changed()


def _unique_layer(gp, name):
    base, index = name[:56] or "Livello", 2
    while gp.layers.get(name) is not None:
        name = f"{base} {index}"
        index += 1
    return name


def import_project(context, path):
    """Open a web project as a new composition; returns (object, project)."""
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    available = set(synth.INSTRUMENT_BY_ID)
    project = web_project.parse(text, available)  # validates before anything is created
    if context.mode != "OBJECT" and context.active_object is not None:
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.gp2m.add_composition()
    comp = active_composition(context)
    defaults = [layer.name for layer in board.user_layers(comp.data)]
    s = comp.gp2m
    b = project.board
    s.bpm, s.length, s.low_note, s.octaves = b.bpm, b.length, b.low_note, b.octaves
    s.scale = project.scale
    s.root = music.NOTE_NAMES[project.root]
    s.time_grid = project.grid
    # Place the strokes on the board of this composition (its row height and width).
    project = web_project.parse(text, available, s.row_height, s.seconds_width)

    sounds = {snd.ident: (_load_sound(snd), snd.root)
              for snd in project.sounds if snd.data is not None}
    gp = comp.data
    frame = min(1, context.scene.frame_start)
    cache = {}
    created = []
    for layer in project.layers:
        gp_layer = gp.layers.new(_unique_layer(gp, layer.name))
        gp_layer.use_lights = False
        gp_layer.opacity = layer.volume
        drawing = gp_layer.frames.new(frame).drawing
        slots = [_slot_for(comp, gp_layer.name, st.instrument, sounds, cache)
                 for st in layer.strokes]
        _add_strokes(drawing, layer.strokes, slots)
        created.append((gp_layer, layer))
    for name in defaults:  # the empty layers of a new composition
        old = gp.layers.get(name)
        if old is not None and not any(len(f.drawing.strokes) for f in old.frames):
            for slot_index in reversed(range(len(gp.materials))):
                material = gp.materials[slot_index]
                if material is not None and getattr(material, "gp2m_layer", "") == name:
                    from .operators import remove_material_slot
                    remove_material_slot(comp, slot_index)
            gp.layers.remove(old)
    board.ensure_order(gp)
    props.ensure_layer_settings(gp)
    for gp_layer, layer in created:
        settings = props.find_layer_settings(gp, gp_layer.name)
        if settings is not None:
            settings.mode = layer.mode
            settings.reverb_mix = layer.reverb
            if layer.harmony != "OFF" and hasattr(settings, "harmony"):
                try:
                    settings.harmony = layer.harmony
                except TypeError:
                    pass
        # Hidden in Blender = not seen and not heard.
        gp_layer.hide = not layer.visible or layer.muted
    layers = board.user_layers(gp)
    if layers:
        gp.layers.active = layers[-1]
    comp.name = project.name
    board.rebuild(comp, context.scene)
    engine.regenerate_safe(comp, context.scene, force=True)
    return comp, project


# --- Blender → web ----------------------------------------------------------------------

def _sound_data(material):
    """Mono float samples at the web app's rate, or None."""
    sound = material.gp2m_sample
    if sound is None:
        return None
    try:
        import aud
        from .samples import _source_path
        source = aud.Sound(_source_path(sound)).resample(web_project.SAMPLE_RATE, True)
        data = source.data()
    except Exception:
        return None
    mono = data.mean(axis=1) if data.ndim == 2 else data
    peak = float(np.max(np.abs(mono))) if len(mono) else 0.0
    return (mono / peak).astype(np.float32) if peak > 1.0 else mono.astype(np.float32)


def collect_project(comp, scene):
    """The composition as a :class:`web_project.Project` (keyframe at the scene start)."""
    s = comp.gp2m
    b = web_project.Board(bpm=s.bpm, length=s.length, low_note=s.low_note, octaves=s.octaves,
                          row_height=s.row_height, seconds_width=s.seconds_width)
    project = web_project.Project(name=comp.name, board=b, scale=s.scale,
                                  root=music.NOTE_NAMES.index(s.root), grid=s.time_grid)
    gp = comp.data
    materials = list(gp.materials)
    sound_keys = {}
    for layer in board.user_layers(gp):
        settings = props.find_layer_settings(gp, layer.name)
        out = web_project.Layer(
            name=layer.name, mode=settings.mode if settings else "QUANTIZED",
            visible=not layer.hide, muted=layer.hide, volume=float(layer.opacity),
            reverb=float(settings.reverb_mix) if settings else 0.0,
            harmony=getattr(settings, "harmony", "OFF") if settings else "OFF")
        project.layers.append(out)
        drawing = reader.drawing_at(layer, scene.frame_start)
        curves = len(drawing.strokes) if drawing is not None else 0
        if not curves:
            continue
        offsets = np.empty(curves + 1, dtype=np.int32)
        drawing.curve_offsets.foreach_get("value", offsets)
        points = int(offsets[-1])
        position = reader._attribute(drawing, "position", points, 3)
        radius = reader._attribute(drawing, "radius", points, default=0.01)
        opacity = reader._attribute(drawing, "opacity", points, default=1.0)
        mat_index = reader._attribute(drawing, "material_index", curves, default=0).astype(int)
        fill_id = reader._attribute(drawing, "fill_id", curves, default=0).astype(int)
        softness = reader._attribute(drawing, "softness", curves, default=0.0)
        has_time = drawing.attributes.get("delta_time") is not None
        times = reader._attribute(drawing, "delta_time", points) if has_time else None
        for i in range(curves):
            a, c = int(offsets[i]), int(offsets[i + 1])
            if c <= a:
                continue
            material = materials[mat_index[i]] if 0 <= mat_index[i] < len(materials) else None
            if material is None or board.is_board_material(material):
                continue
            ident = getattr(material, "gp2m_instrument", synth.DEFAULT_INSTRUMENT)
            if ident == "SAMPLE" and material.gp2m_sample is not None:
                key = sound_keys.get(material.name)
                if key is None:
                    data = _sound_data(material)
                    if data is not None:
                        key = f"SMP:{len(project.sounds):x}gp2m"
                        sound_keys[material.name] = key
                        project.sounds.append(web_project.Sound(
                            ident=key, name=material.get(board.LABEL_KEY, material.name),
                            root=material.gp2m_sample_root, data=data))
                ident = key or "EPIANO"
            out.strokes.append(web_project.Stroke(
                x=position[a:c, 0].astype(np.float64), z=position[a:c, 2].astype(np.float64),
                radius=radius[a:c].astype(np.float64),
                opacity=float(np.mean(opacity[a:c])) if c > a else 1.0,
                times=None if times is None else times[a:c].astype(np.float64),
                instrument=ident, filled=bool(fill_id[i]) and c - a >= 3,
                softness=float(softness[i])))
    return project


# --- Operators --------------------------------------------------------------------------

class GP2M_OT_import_web(bpy.types.Operator, ImportHelper):
    """Apri un progetto della web app (.json) come nuova composizione"""

    bl_idname = "gp2m.import_web"
    bl_label = "Apri progetto web"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        try:
            comp, project = import_project(context, self.filepath)
        except (OSError, UnicodeDecodeError, web_project.ProjectError) as error:
            self.report({"ERROR"}, f"Progetto non leggibile: {error}")
            return {"CANCELLED"}
        count = sum(len(layer.strokes) for layer in project.layers)
        message = f"{comp.name}: {count} tratti in {len(project.layers)} livelli"
        if project.skipped:
            message += " (onde disegnate suonate col piano elettrico)"
        self.report({"INFO"}, message)
        return {"FINISHED"}


class GP2M_OT_export_web(bpy.types.Operator, ExportHelper):
    """Salva la composizione come progetto della web app (.json), da aprire sull'iPad"""

    bl_idname = "gp2m.export_web"
    bl_label = "Salva per la web app"

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})
    include_sounds: BoolProperty(name="Includi i campioni", default=True,
                                 description="Gli strumenti Campione entrano nel file come "
                                 "suoni della web app")

    @classmethod
    def poll(cls, context):
        return active_composition(context) is not None

    def invoke(self, context, event):
        comp = active_composition(context)
        if comp is not None and not self.filepath:
            self.filepath = bpy.path.clean_name(comp.name) + ".json"
        return super().invoke(context, event)

    def execute(self, context):
        comp = active_composition(context)
        project = collect_project(comp, context.scene)
        if not self.include_sounds:
            project.sounds = []
        try:
            with open(self.filepath, "w", encoding="utf-8") as handle:
                handle.write(web_project.dump(project))
        except OSError as error:
            self.report({"ERROR"}, f"Salvataggio non riuscito: {error}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Salvato: {os.path.basename(self.filepath)}")
        return {"FINISHED"}


def menu_import(self, _context):
    self.layout.operator(GP2M_OT_import_web.bl_idname,
                         text="Progetto Doodle Music web (.json)", icon="URL")


def menu_export(self, _context):
    self.layout.operator(GP2M_OT_export_web.bl_idname,
                         text="Progetto Doodle Music web (.json)", icon="URL")


classes = (GP2M_OT_import_web, GP2M_OT_export_web)


def register():
    bpy.types.TOPBAR_MT_file_import.append(menu_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_export)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_export)
    bpy.types.TOPBAR_MT_file_import.remove(menu_import)
