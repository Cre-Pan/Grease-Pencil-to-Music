# SPDX-License-Identifier: GPL-3.0-or-later
"""N panel (sidebar tab "Musica") and the Shift+A menu entry."""

import bpy

from . import board, engine, music, prefs, props, reader
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


class GP2M_UL_layers(bpy.types.UIList):
    """User layers of the composition (the board layers are hidden)."""

    def draw_item(self, _context, layout, data, layer, _icon, _active_data, _active_prop,
                  _index=0, _flt_flag=0):
        row = layout.row(align=True)
        row.prop(layer, "name", text="", emboss=False, icon="OUTLINER_DATA_GP_LAYER")
        settings = props.find_layer_settings(data, layer.name)
        if settings is not None:
            sub = row.row(align=True)
            sub.ui_units_x = 5
            sub.prop(settings, "mode", text="")
        # No explicit icon: Blender switches the eye open/closed by itself.
        row.prop(layer, "hide", text="", emboss=False)

    def filter_items(self, _context, data, _propname):
        layers = list(data.layers)
        flags = [0 if board.is_board_layer(layer) else self.bitflag_filter_item
                 for layer in layers]
        order = list(reversed(range(len(layers))))  # top layer first, like Blender
        neworder = [0] * len(layers)
        for position, index in enumerate(order):
            neworder[index] = position
        return flags, neworder


class GP2M_UL_instruments(bpy.types.UIList):
    """Instrument materials (the board materials are hidden)."""

    def draw_item(self, _context, layout, _data, slot, _icon, _active_data, _active_prop,
                  _index=0, _flt_flag=0):
        material = slot.material
        row = layout.row(align=False)  # the color box stands apart from the name
        if material is None or material.grease_pencil is None:
            row.label(text="(vuoto)")
            return
        swatch = row.row()
        swatch.ui_units_x = 1.0
        swatch.prop(material.grease_pencil, "color", text="")
        row.label(text=board.material_label(material))
        volume = row.row(align=True)
        volume.ui_units_x = 4
        volume.prop(material, "gp2m_volume", text="", slider=True)
        row.prop(material.grease_pencil, "hide", text="", emboss=False)

    def filter_items(self, _context, data, _propname):
        flags = [0 if board.is_board_material(slot.material) else self.bitflag_filter_item
                 for slot in data.material_slots]
        return flags, []


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

        row = layout.row(align=True)
        row.label(text=comp.name, icon="OUTLINER_OB_GREASEPENCIL")
        row.prop(comp.gp2m, "mute", text="", emboss=False,
                 icon="MUTE_IPO_ON" if comp.gp2m.mute else "MUTE_IPO_OFF")
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
            if comp.gp2m.use_modifiers:
                box.label(text="Modificatori inclusi nel suono", icon="MODIFIER_ON")
            else:
                box.label(text="Modificatori ed effetti non cambiano il suono", icon="ERROR")
            box.prop(comp.gp2m, "use_modifiers")

        row = layout.row(align=True)
        row.prop(comp.gp2m, "auto_update", text="Auto", toggle=True, icon="FILE_REFRESH")
        row.operator("gp2m.regenerate", icon="PLAY_SOUND")

        play = context.scene.gp2m_play
        box = layout.box()
        box.label(text="Ascolto delle composizioni", icon="SPEAKER")
        box.row().prop(play, "mode", expand=True)
        if play.mode == "SEQUENCE":
            box.prop(comp.gp2m, "order")
        box.prop(play, "fit_range")


class GP2M_PT_board(_CompositionPanel, bpy.types.Panel):
    bl_label = "Tavola e tempo"

    def draw(self, context):
        s = active_composition(context).gp2m
        style = prefs.get_prefs().note_naming
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        col = layout.column(align=True)
        col.prop(s, "bpm")
        col.prop(s, "length")
        col.prop(s, "loop")
        col = layout.column(align=True)
        low = s.low_note
        col.prop(s, "low_note", text=f"Nota più bassa ({music.note_name(low, style)})")
        col.prop(s, "octaves",
                 text=f"Ottave (fino a {music.note_name(low + s.octaves * 12, style)})")
        col.prop(s, "key_labels")
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
        sub = col.column(align=True)
        sub.active = s.time_grid != "OFF"
        sub.prop(s, "swing")
        col.prop(s, "min_note")
        col = layout.column(align=True)
        col.prop(s, "master_volume")
        col.prop(s, "sample_rate")
        layout.prop(s, "use_modifiers")


class GP2M_PT_instruments(_CompositionPanel, bpy.types.Panel):
    bl_label = "Strumenti"

    def draw(self, context):
        comp = active_composition(context)
        layout = self.layout
        row = layout.row()
        row.template_list("GP2M_UL_instruments", "", comp, "material_slots", comp,
                          "active_material_index", rows=6)
        col = row.column(align=True)
        col.operator_menu_enum("gp2m.add_instrument", "instrument", text="", icon="ADD")
        col.operator("gp2m.remove_instrument", text="", icon="REMOVE")
        slots = comp.material_slots
        if 0 <= comp.active_material_index < len(slots):
            material = slots[comp.active_material_index].material
            if material is not None and not board.is_board_material(material):
                col = layout.column(align=True)
                col.use_property_split = True
                col.use_property_decorate = False
                col.prop(material, "gp2m_instrument")
                col.prop(material, "gp2m_volume")
        layout.label(text="Strumento attivo = quello con cui disegni. Occhio = muto.",
                     icon="INFO")


class GP2M_PT_layers(_CompositionPanel, bpy.types.Panel):
    bl_label = "Livelli"

    def draw(self, context):
        comp = active_composition(context)
        gp = comp.data
        layout = self.layout
        row = layout.row()
        row.template_list("GP2M_UL_layers", "", gp, "layers", gp, "gp2m_active_layer",
                          rows=4)
        col = row.column(align=True)
        col.operator("gp2m.add_layer", text="", icon="ADD")
        col.operator("gp2m.remove_layer", text="", icon="REMOVE")
        col.separator()
        col.operator("gp2m.move_layer", text="", icon="TRIA_UP").direction = "UP"
        col.operator("gp2m.move_layer", text="", icon="TRIA_DOWN").direction = "DOWN"

        active = gp.layers.active
        if active is None or board.is_board_layer(active):
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
        box.prop(settings, "fill_mode")
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
    GP2M_UL_layers,
    GP2M_UL_instruments,
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
