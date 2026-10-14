# SPDX-License-Identifier: GPL-3.0-or-later
"""User interface.

* Properties editor: Object Data (board, reading, layers, instruments),
  Material (instrument, sample, effects), Output (export), Scene (listening).
* File > Import / Export menus.
* 3D View sidebar "Musica": a compact panel for drawing time.
* Shift+A > Grease Pencil to Music.
"""

import bpy

from . import board, engine, music, prefs, props, reader
from .operators import active_composition


# --- Layers with their instruments ---------------------------------------------------

INSTRUMENT_GROUPS = (
    ("Melodici", ("SINE", "TRIANGLE", "SQUARE", "SAW", "STRINGS", "PLUCK", "BELL")),
    ("Percussioni", ("DRUM", "KICK", "SNARE", "HIHAT", "CRASH", "CLAP", "TOM", "COWBELL")),
    ("Suoni", ("SAMPLE", "LIBRARY")),
)
INSTRUMENT_ICONS = {"SAMPLE": "FILE_SOUND", "LIBRARY": "ASSET_MANAGER"}


class GP2M_MT_add_instrument(bpy.types.Menu):
    """Instruments that can be added to a layer (the layer comes from the context)."""

    bl_idname = "GP2M_MT_add_instrument"
    bl_label = "Aggiungi strumento"

    def draw(self, context):
        from . import synth
        layer = getattr(context, "gp2m_layer", None)
        row = self.layout.row()
        for title, idents in INSTRUMENT_GROUPS:
            col = row.column()
            col.label(text=title)
            for ident in idents:
                if ident not in synth.INSTRUMENT_BY_ID:
                    continue
                inst = synth.INSTRUMENT_BY_ID[ident]
                op = col.operator("gp2m.add_instrument", text=inst.label,
                                  icon=INSTRUMENT_ICONS.get(ident, "DOT"))
                op.instrument = ident
                op.layer = layer.name if layer is not None else ""


def _instrument_row(layout, comp, layer_name, index, material, active):
    row = layout.row(align=False)  # the color box stands apart from the name
    swatch = row.row()
    swatch.ui_units_x = 1.0
    swatch.prop(material.grease_pencil, "color", text="")
    op = row.operator("gp2m.use_instrument", text=board.material_label(material),
                      depress=active, emboss=active)
    op.layer = layer_name
    op.index = index
    volume = row.row(align=True)
    volume.ui_units_x = 4
    volume.prop(material, "gp2m_volume", text="", slider=True)
    row.prop(material.grease_pencil, "hide", text="", emboss=False)
    row.operator("gp2m.remove_instrument", text="", icon="X", emboss=False).index = index


def draw_layers_and_instruments(layout, comp, details=True):
    """One box per layer (top first) with its instruments inside."""
    gp = comp.data
    row = layout.row(align=True)
    row.operator("gp2m.add_layer", text="Nuovo livello", icon="ADD")
    row.operator("gp2m.move_layer", text="", icon="TRIA_UP").direction = "UP"
    row.operator("gp2m.move_layer", text="", icon="TRIA_DOWN").direction = "DOWN"
    active_layer = gp.layers.active
    active_slot = comp.active_material_index
    for layer in reversed(board.user_layers(gp)):
        settings = props.find_layer_settings(gp, layer.name)
        is_active = active_layer is not None and active_layer.name == layer.name
        box = layout.box()
        header = box.row(align=True)
        if settings is not None:
            header.prop(settings, "expanded", text="", emboss=False,
                        icon="TRIA_DOWN" if settings.expanded else "TRIA_RIGHT")
        op = header.operator("gp2m.use_instrument", text=layer.name, depress=is_active,
                             icon="OUTLINER_DATA_GP_LAYER")
        op.layer = layer.name
        op.index = -1
        if settings is not None:
            sub = header.row(align=True)
            sub.ui_units_x = 5
            sub.prop(settings, "mode", text="")
        header.prop(layer, "hide", text="", emboss=False)
        header.operator("gp2m.remove_layer", text="", icon="TRASH", emboss=False).name = layer.name
        if settings is None or not settings.expanded:
            continue
        col = box.column(align=True)
        own = board.layer_instruments(comp, layer.name)
        for index, material in own:
            _instrument_row(col, comp, layer.name, index, material,
                            is_active and index == active_slot)
        if not own:
            col.label(text="Nessuno strumento: aggiungine uno", icon="INFO")
        add = box.row()
        add.context_pointer_set("gp2m_layer", settings)
        add.menu("GP2M_MT_add_instrument", text="Strumento", icon="ADD")
        if details:
            add.prop(settings, "show_fx", text="", icon="MODIFIER", toggle=True)
            if settings.show_fx:
                draw_layer_details(box, gp, layer)
    loose = board.loose_instruments(comp)
    if loose:
        box = layout.box()
        box.label(text="Strumenti senza livello", icon="MATERIAL")
        col = box.column(align=True)
        for index, material in loose:
            _instrument_row(col, comp, "", index, material, index == active_slot)


# --- Shared drawing ------------------------------------------------------------------------

def draw_status(layout, comp):
    st = engine.state(comp)
    if st.get("error"):
        box = layout.box()
        box.alert = True
        box.label(text="Errore nella generazione:", icon="ERROR")
        box.label(text=st["error"][:120])
    stats = st.get("stats")
    if stats:
        layout.label(text=f"{stats['notes']} note · {stats['seconds'] * 1000:.0f} ms",
                     icon="SOUND")
        if stats.get("sections", 0) > 1:
            layout.label(text=f"{stats['sections']} sezioni · "
                         f"{engine.duration(comp):.1f} s", icon="KEYFRAME")
        if stats.get("skipped"):
            layout.label(text=f"{stats['skipped']} parti saltate (vedi la console)",
                         icon="ERROR")
        if stats["multi_keyframes"]:
            box = layout.box()
            box.label(text="Viene letto solo il keyframe all'inizio della scena:", icon="INFO")
            box.label(text=", ".join(stats["multi_keyframes"]))
            box.prop(comp.gp2m, "use_sections")
    if reader.has_unsupported_stack(comp):
        box = layout.box()
        if comp.gp2m.use_modifiers:
            box.label(text="Modificatori inclusi nel suono", icon="MODIFIER_ON")
        else:
            box.label(text="Modificatori ed effetti non cambiano il suono", icon="ERROR")
        box.prop(comp.gp2m, "use_modifiers")


def draw_actions(layout, comp):
    row = layout.row(align=True)
    row.prop(comp.gp2m, "auto_update", text="Auto", toggle=True, icon="FILE_REFRESH")
    row.operator("gp2m.regenerate", icon="PLAY_SOUND")
    row.prop(comp.gp2m, "mute", text="", icon="MUTE_IPO_ON" if comp.gp2m.mute else "MUTE_IPO_OFF")
    layout.operator("gp2m.play_keyboard", icon="KEYTYPE_KEYFRAME_VEC")


def draw_board(layout, s):
    style = prefs.get_prefs().note_naming
    layout.use_property_split = True
    layout.use_property_decorate = False
    col = layout.column(align=True)
    col.prop(s, "bpm")
    col.prop(s, "length")
    col.prop(s, "loop")
    col.prop(s, "use_sections")
    col = layout.column(align=True)
    low = s.low_note
    col.prop(s, "low_note", text=f"Nota più bassa ({music.note_name(low, style)})")
    col.prop(s, "octaves", text=f"Ottave (fino a {music.note_name(low + s.octaves * 12, style)})")
    col.prop(s, "key_labels")
    col = layout.column(align=True)
    col.prop(s, "row_height")
    col.prop(s, "seconds_width")
    col.prop(s, "show_beats")
    layout.operator("gp2m.rebuild_board", icon="GRID")


def draw_reading(layout, s):
    layout.use_property_split = True
    layout.use_property_decorate = False
    col = layout.column(align=True)
    col.prop(s, "scale")
    col.prop(s, "root")
    col = layout.column(align=True)
    col.prop(s, "time_grid")
    sub = col.column(align=True)
    sub.active = s.time_grid != "OFF"
    sub.prop(s, "swing")
    col.prop(s, "min_note")
    col = layout.column(align=True)
    col.prop(s, "master_volume")
    col.prop(s, "sample_rate")
    layout.prop(s, "use_modifiers")


def draw_effects(layout, fx):
    col = layout.column(align=True)
    col.prop(fx, "delay_mix")
    sub = col.column(align=True)
    sub.active = fx.delay_mix > 0
    sub.prop(fx, "delay_beats")
    sub.prop(fx, "delay_feedback")
    col = layout.column(align=True)
    col.prop(fx, "reverb_mix")
    sub = col.column(align=True)
    sub.active = fx.reverb_mix > 0
    sub.prop(fx, "reverb_size")
    layout.prop(fx, "lofi")


def draw_layer_details(layout, gp, layer):
    settings = props.find_layer_settings(gp, layer.name)
    box = layout.column()
    box.use_property_split = True
    box.use_property_decorate = False
    box.prop(layer, "opacity", text="Volume (opacità livello)", slider=True)
    if settings is None:
        box.label(text="Impostazioni in preparazione…")
        return
    box.prop(settings, "mode")
    if settings.mode == "LEGATO":
        box.prop(settings, "glide")
    if settings.mode in ("LEGATO", "OPTICAL_LEGATO"):
        box.prop(settings, "legato_gap")
    box.prop(settings, "fill_mode")
    col = box.column(align=True)
    col.prop(settings, "canon_voices")
    sub = col.column(align=True)
    sub.active = settings.canon_voices > 1
    sub.prop(settings, "canon_delay")
    sub.prop(settings, "canon_transpose")
    draw_effects(box, settings)


def draw_instrument_details(layout, material):
    layout.use_property_split = True
    layout.use_property_decorate = False
    layout.prop(material, "gp2m_instrument")
    layout.prop(material, "gp2m_volume", slider=True)
    if material.gp2m_instrument == "SAMPLE":
        box = layout.box()
        box.label(text="Campione", icon="FILE_SOUND")
        box.template_ID(material, "gp2m_sample", open="sound.open")
        box.operator("gp2m.load_sample", icon="FILEBROWSER")
        box.prop(material, "gp2m_sample_root")
        box.prop(material, "gp2m_sample_loop")
    if material.gp2m_instrument == "LIBRARY":
        box = layout.box()
        box.label(text="Libreria (SoundFont .sf2 o .sfz)", icon="ASSET_MANAGER")
        box.prop(material, "gp2m_library_path", text="File")
        box.prop(material, "gp2m_library_preset")
        col = box.column(align=True)
        col.scale_y = 0.8
        col.label(text="Librerie libere: GeneralUser GS, FluidR3 (SF2),")
        col.label(text="Versilian VCSL (SFZ, CC0)")
    box = layout.box()
    box.label(text="Effetti dello strumento", icon="MODIFIER")
    draw_effects(box, material.gp2m_fx)


def draw_play(layout, scene, comp=None):
    play = scene.gp2m_play
    layout.row().prop(play, "mode", expand=True)
    layout.prop(play, "fit_range")
    if comp is not None:
        col = layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(comp.gp2m, "channel", text="Canale (0 = auto)")
        sub = col.column(align=True)
        sub.active = play.mode == "SEQUENCE"
        sub.prop(comp.gp2m, "order")


def draw_export(layout):
    row = layout.row(align=True)
    for fmt in ("WAV", "MP3", "MIDI"):
        row.operator("gp2m.export", text=fmt, icon="EXPORT").format = fmt


# --- Properties editor ------------------------------------------------------------------------

class _DataPanel:
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        return active_composition(context) is not None


class GP2M_PT_data(_DataPanel, bpy.types.Panel):
    bl_label = "Musica"

    def draw_header(self, _context):
        self.layout.label(icon="FILE_SOUND")

    def draw(self, context):
        comp = active_composition(context)
        draw_status(self.layout, comp)
        draw_actions(self.layout, comp)


class GP2M_PT_data_board(_DataPanel, bpy.types.Panel):
    bl_label = "Tavola e tempo"
    bl_parent_id = "GP2M_PT_data"

    def draw(self, context):
        draw_board(self.layout, active_composition(context).gp2m)


class GP2M_PT_data_reading(_DataPanel, bpy.types.Panel):
    bl_label = "Lettura"
    bl_parent_id = "GP2M_PT_data"

    def draw(self, context):
        draw_reading(self.layout, active_composition(context).gp2m)


class GP2M_PT_data_layers(_DataPanel, bpy.types.Panel):
    bl_label = "Livelli e strumenti"
    bl_parent_id = "GP2M_PT_data"

    def draw(self, context):
        draw_layers_and_instruments(self.layout, active_composition(context))
        self.layout.label(text="Tipo, campione ed effetti di uno strumento: scheda Materiale",
                          icon="MATERIAL")


class GP2M_PT_data_play(_DataPanel, bpy.types.Panel):
    bl_label = "Sequencer e ascolto"
    bl_parent_id = "GP2M_PT_data"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        draw_play(self.layout, context.scene, active_composition(context))


class GP2M_PT_material(bpy.types.Panel):
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"
    bl_label = "Strumento musicale"

    @classmethod
    def poll(cls, context):
        material = getattr(context, "material", None)
        return (active_composition(context) is not None and material is not None
                and material.grease_pencil is not None and not board.is_board_material(material))

    def draw_header(self, _context):
        self.layout.label(icon="FILE_SOUND")

    def draw(self, context):
        draw_instrument_details(self.layout, context.material)


class GP2M_PT_output(bpy.types.Panel):
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "output"
    bl_label = "Grease Pencil to Music"

    def draw_header(self, _context):
        self.layout.label(icon="FILE_SOUND")

    def draw(self, context):
        layout = self.layout
        comp = active_composition(context)
        if comp is None:
            layout.label(text="Seleziona una composizione per esportarla.", icon="INFO")
        else:
            layout.label(text=comp.name, icon="OUTLINER_OB_GREASEPENCIL")
            draw_export(layout)
        layout.operator("sound.mixdown", text="Mix di tutta la scena…", icon="SOUND")


class GP2M_PT_scene(bpy.types.Panel):
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_label = "Composizioni musicali"

    @classmethod
    def poll(cls, context):
        return context.scene is not None and bool(engine.scene_compositions(context.scene))

    def draw_header(self, _context):
        self.layout.label(icon="FILE_SOUND")

    def draw(self, context):
        layout = self.layout
        draw_play(layout, context.scene)
        col = layout.column(align=True)
        for obj in engine.scene_compositions(context.scene):
            row = col.row(align=True)
            row.label(text=obj.name, icon="OUTLINER_OB_GREASEPENCIL")
            sub = row.row(align=True)
            sub.ui_units_x = 4
            sub.prop(obj.gp2m, "channel", text="Canale")
            if context.scene.gp2m_play.mode == "SEQUENCE":
                sub = row.row(align=True)
                sub.ui_units_x = 4
                sub.prop(obj.gp2m, "order", text="Ordine")
            row.prop(obj.gp2m, "mute", text="", icon="MUTE_IPO_ON" if obj.gp2m.mute
                     else "MUTE_IPO_OFF")


# --- 3D View sidebar (compact, for drawing) --------------------------------------------------

class _Panel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Musica"


class _CompositionPanel(_Panel):
    bl_parent_id = "GP2M_PT_main"

    @classmethod
    def poll(cls, context):
        return active_composition(context) is not None


class GP2M_PT_main(_Panel, bpy.types.Panel):
    bl_label = "Grease Pencil to Music"

    def draw(self, context):
        layout = self.layout
        comp = active_composition(context)
        if comp is None:
            layout.label(text="Nessuna composizione selezionata.")
            layout.operator("gp2m.add_composition", icon="ADD")
            layout.label(text="(oppure Shift+A → Grease Pencil to Music)")
            layout.operator("gp2m.import_midi", icon="IMPORT")
            return
        layout.label(text=comp.name, icon="OUTLINER_OB_GREASEPENCIL")
        draw_status(layout, comp)
        draw_actions(layout, comp)
        layout.row().prop(context.scene.gp2m_play, "mode", expand=True)
        layout.label(text="Altre impostazioni: Proprietà → Dati oggetto / Materiale",
                     icon="PROPERTIES")


class GP2M_PT_layers(_CompositionPanel, bpy.types.Panel):
    bl_label = "Livelli e strumenti"

    def draw(self, context):
        draw_layers_and_instruments(self.layout, active_composition(context), details=False)


# --- Menus ---------------------------------------------------------------------------------

class VIEW3D_MT_gp2m_add(bpy.types.Menu):
    bl_idname = "VIEW3D_MT_gp2m_add"
    bl_label = "Grease Pencil to Music"

    def draw(self, _context):
        self.layout.operator("gp2m.add_composition", text="Composizione Musicale",
                             icon="OUTLINER_OB_GREASEPENCIL")
        self.layout.operator("gp2m.import_midi", text="Composizione da MIDI…", icon="IMPORT")


def draw_add_menu(self, _context):
    self.layout.separator()
    self.layout.menu(VIEW3D_MT_gp2m_add.bl_idname, icon="SOUND")


def draw_export_menu(self, _context):
    for fmt, label in (("WAV", "Composizione musicale (.wav)"),
                       ("MP3", "Composizione musicale (.mp3)"),
                       ("MIDI", "Composizione musicale (.mid)")):
        self.layout.operator("gp2m.export", text=label, icon="FILE_SOUND").format = fmt


classes = (
    GP2M_MT_add_instrument,
    GP2M_PT_data,
    GP2M_PT_data_board,
    GP2M_PT_data_reading,
    GP2M_PT_data_layers,
    GP2M_PT_data_play,
    GP2M_PT_material,
    GP2M_PT_output,
    GP2M_PT_scene,
    GP2M_PT_main,
    GP2M_PT_layers,
    VIEW3D_MT_gp2m_add,
)


def register():
    bpy.types.VIEW3D_MT_add.append(draw_add_menu)
    bpy.types.TOPBAR_MT_file_export.append(draw_export_menu)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(draw_export_menu)
    bpy.types.VIEW3D_MT_add.remove(draw_add_menu)
