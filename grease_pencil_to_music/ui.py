# SPDX-License-Identifier: GPL-3.0-or-later
"""N panel (sidebar tab "Musica") and the Shift+A menu entry."""

import bpy

from . import engine, music, props, reader
from .operators import active_composition


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
            return

        layout.label(text=comp.name, icon="OUTLINER_OB_GREASEPENCIL")
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
            if stats["multi_keyframes"]:
                box = layout.box()
                box.label(text="Viene letto solo il keyframe all'inizio della scena:",
                          icon="INFO")
                box.label(text=", ".join(stats["multi_keyframes"]))
        if reader.has_unsupported_stack(comp):
            box = layout.box()
            box.label(text="Modificatori ed effetti non cambiano il suono", icon="ERROR")
            box.label(text="(viene letto il tratto originale)")

        row = layout.row(align=True)
        row.prop(comp.gp2m, "auto_update", text="Auto", toggle=True, icon="FILE_REFRESH")
        row.operator("gp2m.regenerate", icon="PLAY_SOUND")


class GP2M_PT_board(_CompositionPanel, bpy.types.Panel):
    bl_label = "Tavola e tempo"

    def draw(self, context):
        s = active_composition(context).gp2m
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        col = layout.column(align=True)
        col.prop(s, "bpm")
        col.prop(s, "length")
        col.prop(s, "loop")
        col = layout.column(align=True)
        low = s.low_note
        col.prop(s, "low_note", text=f"Nota più bassa ({music.note_name(low)})")
        col.prop(s, "octaves",
                 text=f"Ottave (fino a {music.note_name(low + s.octaves * 12)})")
        col = layout.column(align=True)
        col.prop(s, "row_height")
        col.prop(s, "seconds_width")
        col.prop(s, "show_beats")
        layout.operator("gp2m.rebuild_board", icon="GRID")


class GP2M_PT_reading(_CompositionPanel, bpy.types.Panel):
    bl_label = "Lettura"

    def draw(self, context):
        s = active_composition(context).gp2m
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        col = layout.column(align=True)
        col.prop(s, "scale")
        col.prop(s, "root")
        col = layout.column(align=True)
        col.prop(s, "time_grid")
        col.prop(s, "min_note")
        col = layout.column(align=True)
        col.prop(s, "master_volume")
        col.prop(s, "sample_rate")


class GP2M_PT_instruments(_CompositionPanel, bpy.types.Panel):
    bl_label = "Strumenti"

    def draw(self, context):
        comp = active_composition(context)
        layout = self.layout
        layout.label(text="Clic sul nome per disegnare con quello strumento.")
        col = layout.column(align=True)
        for index, slot in enumerate(comp.material_slots):
            material = slot.material
            if material is None or material.grease_pencil is None:
                continue
            style = material.grease_pencil
            row = col.row(align=True)
            swatch = row.row(align=True)
            swatch.ui_units_x = 1.2
            swatch.prop(style, "color", text="")
            op = row.operator("gp2m.set_active_material", text=material.name,
                              depress=comp.active_material_index == index)
            op.index = index
            row.prop(material, "gp2m_instrument", text="")
            row.prop(style, "hide", text="", emboss=False,
                     icon="HIDE_ON" if style.hide else "HIDE_OFF")
        layout.label(text="Occhio chiuso = nascosto e muto.", icon="INFO")


class GP2M_PT_layers(_CompositionPanel, bpy.types.Panel):
    bl_label = "Livelli"

    def draw(self, context):
        comp = active_composition(context)
        gp = comp.data
        layout = self.layout
        col = layout.column(align=True)
        active = gp.layers.active
        for layer in reversed(list(gp.layers)):
            row = col.row(align=True)
            row.prop(layer, "hide", text="", emboss=False,
                     icon="HIDE_ON" if layer.hide else "HIDE_OFF")
            op = row.operator("gp2m.set_active_layer", text=layer.name,
                              depress=active is not None and active.name == layer.name)
            op.name = layer.name
            settings = props.find_layer_settings(gp, layer.name)
            if settings is not None:
                row.prop(settings, "mode", text="")
        layout.operator("gp2m.add_layer", icon="ADD")

        if active is None:
            return
        settings = props.find_layer_settings(gp, active.name)
        box = layout.box()
        box.label(text=f"{active.name}: volume ed effetti", icon="MODIFIER")
        box.use_property_split = True
        box.use_property_decorate = False
        box.prop(active, "opacity", text="Volume (opacità livello)", slider=True)
        if settings is None:
            box.label(text="Impostazioni in preparazione…")
            return
        col = box.column(align=True)
        col.prop(settings, "delay_mix")
        sub = col.column(align=True)
        sub.active = settings.delay_mix > 0
        sub.prop(settings, "delay_beats")
        sub.prop(settings, "delay_feedback")
        col = box.column(align=True)
        col.prop(settings, "reverb_mix")
        sub = col.column(align=True)
        sub.active = settings.reverb_mix > 0
        sub.prop(settings, "reverb_size")
        box.prop(settings, "lofi")


class GP2M_PT_export(_CompositionPanel, bpy.types.Panel):
    bl_label = "Esporta"

    def draw(self, _context):
        row = self.layout.row(align=True)
        for fmt in ("WAV", "MP3", "MIDI"):
            row.operator("gp2m.export", text=fmt, icon="EXPORT").format = fmt


class VIEW3D_MT_gp2m_add(bpy.types.Menu):
    bl_idname = "VIEW3D_MT_gp2m_add"
    bl_label = "Grease Pencil to Music"

    def draw(self, _context):
        self.layout.operator("gp2m.add_composition", text="Composizione Musicale",
                             icon="OUTLINER_OB_GREASEPENCIL")


def draw_add_menu(self, _context):
    self.layout.separator()
    self.layout.menu(VIEW3D_MT_gp2m_add.bl_idname, icon="SOUND")


classes = (
    GP2M_PT_main,
    GP2M_PT_board,
    GP2M_PT_reading,
    GP2M_PT_instruments,
    GP2M_PT_layers,
    GP2M_PT_export,
    VIEW3D_MT_gp2m_add,
)


def register():
    bpy.types.VIEW3D_MT_add.append(draw_add_menu)


def unregister():
    bpy.types.VIEW3D_MT_add.remove(draw_add_menu)
