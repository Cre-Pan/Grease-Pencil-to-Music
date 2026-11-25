# SPDX-License-Identifier: GPL-3.0-or-later
"""User interface.

* Properties editor: Object Data (board, reading, layers, instruments),
  Material (instrument, sample, effects), Output (export), Scene (listening).
* File > Import / Export menus.
* 3D View sidebar "Musica": a compact panel for drawing time.
* Shift+A > Doodle Music.
"""

import bpy

from . import board, engine, help, music, prefs, props, reader
from .operators import active_composition


# --- Layers with their instruments ---------------------------------------------------

INSTRUMENT_ICONS = {"SAMPLE": "FILE_SOUND", "LIBRARY": "ASSET_MANAGER"}


def _add_instrument_buttons(layout, context, idents):
    from . import synth
    layer = getattr(context, "gp2m_layer", None)
    for ident in idents:
        inst = synth.INSTRUMENT_BY_ID.get(ident)
        if inst is None:
            continue
        op = layout.operator("gp2m.add_instrument", text=inst.label,
                             icon=INSTRUMENT_ICONS.get(ident, "DOT"))
        op.instrument = ident
        op.layer = layer.name if layer is not None else ""


def _recorded_families():
    """(menu id, title, idents) of the web app's recorded families."""
    return [(f"GP2M_MT_add_recorded_{index}", title, idents)
            for index, (title, idents) in enumerate(props.INSTRUMENT_FAMILIES)
            if idents and idents[0].startswith("S_")]


def _recorded_menu(menu_id, title, idents):
    def draw(self, context):
        _add_instrument_buttons(self.layout.column(), context, idents)
    return type(menu_id, (bpy.types.Menu,), {"bl_idname": menu_id, "bl_label": title,
                                             "draw": draw})


RECORDED_MENUS = tuple(_recorded_menu(*family) for family in _recorded_families())


class GP2M_MT_add_instrument(bpy.types.Menu):
    """Instruments that can be added to a layer (the layer comes from the context)."""

    bl_idname = "GP2M_MT_add_instrument"
    bl_label = "Aggiungi strumento"

    def draw(self, context):
        row = self.layout.row()
        recorded = _recorded_families()
        for title, idents in props.INSTRUMENT_FAMILIES:
            if idents and idents[0].startswith("S_"):
                continue
            col = row.column()
            col.label(text=title)
            _add_instrument_buttons(col, context, idents)
        col = row.column()
        col.label(text="Registrati (web app)")
        for menu_id, title, _idents in recorded:
            col.menu(menu_id, text=title, icon="SOUND")


# --- Custom icons (Blender has no headphones icon) ---------------------------------------

_icons = None


def icon(name):
    """``icon_value`` of an add-on icon (``icons/<name>.png``), 0 if missing."""
    if _icons is None or name not in _icons:
        return 0
    return _icons[name].icon_id


def _load_icons():
    global _icons
    import os
    import bpy.utils.previews
    _icons = bpy.utils.previews.new()
    folder = os.path.join(os.path.dirname(__file__), "icons")
    for name in ("solo_on", "solo_off"):
        path = os.path.join(folder, f"{name}.png")
        if os.path.isfile(path):
            _icons.load(name, path, "IMAGE")


def _free_icons():
    global _icons
    if _icons is not None:
        import bpy.utils.previews
        bpy.utils.previews.remove(_icons)
        _icons = None


# --- Layer list, like Blender's Grease Pencil layers ---------------------------------------

def layer_instrument_slot(comp, layer_name):
    """Slot of the instrument the note icon changes: the active one if it belongs to
    the layer, otherwise the first instrument of the layer (None if it has none)."""
    own = board.layer_instruments(comp, layer_name)
    if not own:
        return None
    for index, _material in own:
        if index == comp.active_material_index:
            return index
    return own[0][0]


class GP2M_MT_change_instrument(bpy.types.Menu):
    """Instruments for the layer (or the instrument slot) taken from the context."""

    bl_idname = "GP2M_MT_change_instrument"
    bl_label = "Cambia strumento"

    def draw(self, context):
        from . import synth
        comp = active_composition(context)
        if comp is None:
            return
        chosen = getattr(context, "gp2m_material", None)
        layer = getattr(context, "gp2m_layer", None)
        if chosen is not None:
            index = next((i for i, slot in enumerate(comp.material_slots)
                          if slot.material == chosen), None)
        elif layer is not None:
            index = layer_instrument_slot(comp, layer.name)
        else:
            index = comp.active_material_index
        material = (comp.material_slots[index].material
                    if index is not None and 0 <= index < len(comp.material_slots) else None)
        current = material.gp2m_instrument if material is not None else None
        row = self.layout.row()
        for title, idents in INSTRUMENT_GROUPS:
            col = row.column()
            col.label(text=title)
            for ident in idents:
                if ident not in synth.INSTRUMENT_BY_ID:
                    continue
                inst = synth.INSTRUMENT_BY_ID[ident]
                icon_name = "CHECKMARK" if ident == current else INSTRUMENT_ICONS.get(ident,
                                                                                       "DOT")
                if material is None:  # a layer without instruments: add one
                    op = col.operator("gp2m.add_instrument", text=inst.label, icon=icon_name)
                    op.instrument = ident
                    op.layer = layer.name if layer is not None else ""
                else:
                    op = col.operator("gp2m.set_instrument", text=inst.label, icon=icon_name)
                    op.instrument = ident
                    op.index = index


class GP2M_UL_layers(bpy.types.UIList):
    """The layers of the composition, top first, like Blender's own layer list,
    with instrument, mute and solo on the right."""

    bl_idname = "GP2M_UL_layers"

    def draw_item(self, context, layout, data, item, _icon, _active_data, _active_prop,
                  _index=0, _flt_flag=0):
        gp = data
        layer = gp.layers.get(item.name)
        if layer is None:
            layout.label(text=item.name, icon="ERROR")
            return
        comp = active_composition(context)
        silent = props.layer_silent(gp, item.name)
        row = layout.row(align=True)
        name = row.row(align=True)
        name.active = not layer.hide and not silent
        name.prop(layer, "name", text="", emboss=False, icon="OUTLINER_DATA_GP_LAYER")

        icons = row.row(align=True)
        icons.emboss = "NONE"
        note = icons.row(align=True)
        note.context_pointer_set("gp2m_layer", item)
        slot = layer_instrument_slot(comp, item.name) if comp is not None else None
        note.menu("GP2M_MT_change_instrument", text="", icon="FILE_SOUND")
        note.active = slot is not None
        icons.prop(item, "mute", text="", emboss=False,
                   icon="MUTE_IPO_ON" if item.mute else "MUTE_IPO_OFF")
        solo_icon = icon("solo_on" if item.solo else "solo_off")
        if solo_icon:
            icons.prop(item, "solo", text="", emboss=False, icon_value=solo_icon)
        else:
            icons.prop(item, "solo", text="", emboss=False,
                       icon="SOLO_ON" if item.solo else "SOLO_OFF")
        icons.prop(layer, "use_onion_skinning", text="", emboss=False,
                   icon="ONIONSKIN_ON" if layer.use_onion_skinning else "ONIONSKIN_OFF")
        icons.prop(layer, "hide", text="", emboss=False)
        icons.prop(layer, "lock", text="", emboss=False)

    def filter_items(self, _context, data, propname):
        items = getattr(data, propname)
        stack = [layer.name for layer in reversed(board.user_layers(data))]  # top first
        position = {name: i for i, name in enumerate(stack)}
        flags = []
        order = []
        tail = len(stack)
        needle = getattr(self, "filter_name", "").lower()
        invert = getattr(self, "use_filter_invert", False)
        for item in items:
            visible = item.name in position and (not needle or needle in item.name.lower())
            if invert and needle:
                visible = item.name in position and needle not in item.name.lower()
            flags.append(self.bitflag_filter_item if visible else 0)
            if item.name in position:
                order.append(position[item.name])
            else:
                order.append(tail)
                tail += 1
        return flags, order


def _instrument_row(layout, comp, layer_name, index, material, active):
    row = layout.row(align=False)  # the color box stands apart from the name
    swatch = row.row()
    swatch.ui_units_x = 1.0
    swatch.prop(material.grease_pencil, "color", text="")
    op = row.operator("gp2m.use_instrument", text=board.material_label(material),
                      depress=active, emboss=active)
    op.layer = layer_name
    op.index = index
    change = row.row()
    change.context_pointer_set("gp2m_material", material)
    change.menu("GP2M_MT_change_instrument", text="", icon="FILE_SOUND")
    volume = row.row(align=True)
    volume.ui_units_x = 4
    volume.prop(material, "gp2m_volume", text="", slider=True)
    row.prop(material.grease_pencil, "hide", text="", emboss=False)
    row.operator("gp2m.remove_instrument", text="", icon="X", emboss=False).index = index


def draw_layers_and_instruments(layout, comp, details=True):
    """Layer list like Blender's (top first), then the active layer's instruments."""
    gp = comp.data
    rows = max(3, min(8, len(gp.gp2m_layers)))
    row = layout.row()
    row.template_list("GP2M_UL_layers", "", gp, "gp2m_layers", gp, "gp2m_layer_index",
                      rows=rows, sort_lock=True)
    col = row.column(align=True)
    col.operator("gp2m.add_layer", text="", icon="ADD")
    col.operator("gp2m.remove_layer", text="", icon="REMOVE")
    col.separator()
    col.operator("gp2m.move_layer", text="", icon="TRIA_UP").direction = "UP"
    col.operator("gp2m.move_layer", text="", icon="TRIA_DOWN").direction = "DOWN"

    layer = gp.layers.active
    if layer is not None and not board.is_board_layer(layer):
        settings = props.find_layer_settings(gp, layer.name)
        col = layout.column()
        col.use_property_split = True
        col.use_property_decorate = False
        if settings is not None:
            col.prop(settings, "mode")
        col.prop(layer, "opacity", text="Volume (opacità)", slider=True)
        if settings is not None and settings.solo_saved_opacity >= 0.0:
            col.label(text="Attenuato dal Solo di un altro livello", icon="INFO")

        box = layout.box()
        header = box.row()
        header.label(text=f"Strumenti di {layer.name}", icon="FILE_SOUND")
        inner = box.column(align=True)
        own = board.layer_instruments(comp, layer.name)
        active_slot = comp.active_material_index
        for index, material in own:
            _instrument_row(inner, comp, layer.name, index, material, index == active_slot)
        if not own:
            inner.label(text="Nessuno strumento: aggiungine uno", icon="INFO")
        add = box.row()
        if settings is not None:
            add.context_pointer_set("gp2m_layer", settings)
        add.menu("GP2M_MT_add_instrument", text="Strumento", icon="ADD")
        if details and settings is not None:
            add.prop(settings, "show_fx", text="", icon="MODIFIER", toggle=True)
            if settings.show_fx:
                draw_layer_details(box, gp, layer)
    loose = board.loose_instruments(comp)
    if loose:
        box = layout.box()
        box.label(text="Strumenti senza livello", icon="MATERIAL")
        col = box.column(align=True)
        for index, material in loose:
            _instrument_row(col, comp, "", index, material,
                            index == comp.active_material_index)


# --- Shared drawing ------------------------------------------------------------------------

def draw_status(layout, comp):
    st = engine.state(comp)
    if st.get("error"):
        box = layout.box()
        box.alert = True
        box.label(text="Errore nella generazione:", icon="ERROR")
        box.label_multiline(text=st["error"], max_lines=6)
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
            box.label_multiline(text="Viene letto solo il keyframe all'inizio della scena: "
                                + ", ".join(stats["multi_keyframes"]), icon="INFO")
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
    row = layout.row(align=True)
    row.operator("gp2m.play_keyboard", icon="KEYTYPE_KEYFRAME_VEC")
    p = prefs.get_prefs()
    if isinstance(p, bpy.types.AddonPreferences):  # "Suona mentre disegni"
        row.prop(p, "draw_sound", text="", icon="GREASEPENCIL",
                 emboss=True, toggle=True)


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
    col.prop(s, "use_master")
    sub = col.column(align=True)
    sub.active = s.use_master
    sub.prop(s, "ambience")
    col.prop(s, "room")
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
    box.prop(settings, "harmony")
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
    layout.operator("gp2m.export_web", text="Web app (.json)", icon="URL")


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

    def draw_header_preset(self, _context):
        help.button(self.layout, "MAIN")

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

    def draw_header_preset(self, _context):
        help.button(self.layout, "READING")

    def draw(self, context):
        draw_reading(self.layout, active_composition(context).gp2m)


class GP2M_PT_data_layers(_DataPanel, bpy.types.Panel):
    bl_label = "Livelli e strumenti"
    bl_parent_id = "GP2M_PT_data"

    def draw(self, context):
        draw_layers_and_instruments(self.layout, active_composition(context))


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

    def draw_header_preset(self, _context):
        help.button(self.layout, "INSTRUMENT")

    def draw(self, context):
        draw_instrument_details(self.layout, context.material)


class GP2M_PT_output(bpy.types.Panel):
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "output"
    bl_label = "Doodle Music"

    def draw_header(self, _context):
        self.layout.label(icon="FILE_SOUND")

    def draw_header_preset(self, _context):
        help.button(self.layout, "EXPORT")

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
    bl_label = "Doodle Music"

    def draw_header_preset(self, _context):
        help.button(self.layout, "MAIN")

    def draw(self, context):
        layout = self.layout
        comp = active_composition(context)
        if comp is None:
            layout.label(text="Nessuna composizione selezionata.")
            layout.operator("gp2m.add_composition", icon="ADD")
            layout.operator("gp2m.import_midi", icon="IMPORT")
            layout.operator("gp2m.import_web", icon="URL")
            return
        layout.label(text=comp.name, icon="OUTLINER_OB_GREASEPENCIL")
        draw_status(layout, comp)
        draw_actions(layout, comp)
        layout.row().prop(context.scene.gp2m_play, "mode", expand=True)


class GP2M_PT_layers(_CompositionPanel, bpy.types.Panel):
    bl_label = "Livelli e strumenti"

    def draw(self, context):
        draw_layers_and_instruments(self.layout, active_composition(context), details=False)


# --- Menus ---------------------------------------------------------------------------------

class VIEW3D_MT_gp2m_add(bpy.types.Menu):
    bl_idname = "VIEW3D_MT_gp2m_add"
    bl_label = "Doodle Music"

    def draw(self, _context):
        self.layout.operator("gp2m.add_composition", text="Composizione Musicale",
                             icon="OUTLINER_OB_GREASEPENCIL")
        self.layout.operator("gp2m.import_midi", text="Composizione da MIDI…", icon="IMPORT")
        self.layout.operator("gp2m.import_web", text="Composizione dalla web app…", icon="URL")


def draw_add_menu(self, _context):
    self.layout.separator()
    self.layout.menu(VIEW3D_MT_gp2m_add.bl_idname, icon="SOUND")


def draw_export_menu(self, _context):
    for fmt, label in (("WAV", "Composizione musicale (.wav)"),
                       ("MP3", "Composizione musicale (.mp3)"),
                       ("MIDI", "Composizione musicale (.mid)")):
        self.layout.operator("gp2m.export", text=label, icon="FILE_SOUND").format = fmt


classes = RECORDED_MENUS + (
    GP2M_MT_add_instrument,
    GP2M_MT_change_instrument,
    GP2M_UL_layers,
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
    _load_icons()
    bpy.types.VIEW3D_MT_add.append(draw_add_menu)
    bpy.types.TOPBAR_MT_file_export.append(draw_export_menu)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(draw_export_menu)
    bpy.types.VIEW3D_MT_add.remove(draw_add_menu)
    _free_icons()
