# SPDX-License-Identifier: GPL-3.0-or-later
"""User interface.

* Properties editor: Object Data (board, reading, layers, instruments),
  Material (instrument, sample, effects), Output (export), Scene (listening).
* File > Import / Export menus.
* 3D View sidebar "Musica": a compact panel for drawing time.
* Shift+A > Doodle Music.
"""

import bpy

from . import beat, board, engine, families, help, music, prefs, props, reader
from .icons import family_icon, icon, icon_kwargs, instrument_icon
from .operators import active_composition


# --- Instruments menus: sections of families, each family a submenu ----------------------

def _instrument_button(layout, context, ident, target, text=None, kwargs=None):
    """Add the instrument to the layer, or (with a target) change the instrument."""
    from . import synth
    inst = synth.INSTRUMENT_BY_ID.get(ident)
    if inst is None:
        return
    given = kwargs
    if target is None:
        kwargs = {}  # only the categories have icons
        material, layer = None, getattr(context, "gp2m_layer", None)
    else:
        _comp, index, material, layer = target
        current = material.gp2m_instrument if material is not None else None
        kwargs = {"icon": "CHECKMARK"} if ident == current else {}
    if given is not None:
        kwargs = given
    text = inst.label if text is None else text
    if material is None:  # adding, or a layer without instruments: add one
        op = layout.operator("gp2m.add_instrument", text=text, **kwargs)
        op.instrument = ident
        op.layer = layer.name if layer is not None else ""
    else:
        op = layout.operator("gp2m.set_instrument", text=text, **kwargs)
        op.instrument = ident
        op.index = index


def _family_buttons(layout, context, family, change):
    """The instruments of a family: the recorded ones, then the synthesized ones."""
    target = None
    if change:
        target = _change_target(context)
        if target[0] is None:
            return
    recorded, synths = families.split(family)
    both = recorded and synths
    for title, idents in (("Registrati", recorded), ("Sintetizzati", synths)):
        if not idents:
            continue
        if both:
            if title == "Sintetizzati":
                layout.separator()
            layout.label(text=title)
        for ident in idents:
            _instrument_button(layout, context, ident, target)


def _family_menu_id(family, change):
    return f"GP2M_MT_{'change' if change else 'add'}_family_{family.key.lower()}"


def _family_menu(family, change):
    def draw(self, context):
        _family_buttons(self.layout.column(), context, family, change)
    menu_id = _family_menu_id(family, change)
    return type(menu_id, (bpy.types.Menu,), {"bl_idname": menu_id, "bl_label": family.title,
                                             "draw": draw})


ADD_FAMILY_MENUS = tuple(_family_menu(f, False) for f in families.ALL if f not in families.OWN)
CHANGE_FAMILY_MENUS = tuple(_family_menu(f, True) for f in families.ALL)


def _draw_sections(layout, context, change):
    """One column per section (melodic, percussion, own sounds): a submenu per family,
    the own sounds as buttons."""
    current = None
    if change:
        _comp, _index, material, _layer = _change_target(context)
        if _comp is None:
            return
        current = material.gp2m_instrument if material is not None else None
    row = layout.row()
    for title, section in families.SECTIONS:
        col = row.column()
        col.label(text=title)
        for family in section:
            if family in families.OWN:
                _family_buttons(col, context, family, change)
                continue
            if current is not None and current in families.idents(family):
                kwargs = {"icon": "CHECKMARK"}
            else:
                kwargs = icon_kwargs(*family_icon(family))
            col.menu(_family_menu_id(family, change), text=family.title, **kwargs)


class GP2M_MT_add_instrument(bpy.types.Menu):
    """Instruments that can be added to a layer (the layer comes from the context)."""

    bl_idname = "GP2M_MT_add_instrument"
    bl_label = "Aggiungi strumento"

    def draw(self, context):
        _draw_sections(self.layout, context, change=False)


class GP2M_MT_change_instrument(bpy.types.Menu):
    """Instruments for the layer (or the instrument slot) taken from the context."""

    bl_idname = "GP2M_MT_change_instrument"
    bl_label = "Cambia strumento"

    def draw(self, context):
        _draw_sections(self.layout, context, change=True)


class GP2M_MT_instrument_category(bpy.types.Menu):
    """The categories of instruments: choosing one gives its first instrument (the one
    in use if it is already there); the instrument is chosen in the menu beside it."""

    bl_idname = "GP2M_MT_instrument_category"
    bl_label = "Categoria"

    def draw(self, context):
        target = _change_target(context)
        if target[0] is None:
            return
        material = target[2]
        current = material.gp2m_instrument if material is not None else None
        mine = families.family_of(current) if current else None
        row = self.layout.row()
        for title, section in families.SECTIONS:
            col = row.column()
            col.label(text=title)
            for family in section:
                idents = families.idents(family)
                if not idents:
                    continue
                if family is mine:
                    _instrument_button(col, context, current, target, text=family.title,
                                       kwargs={"icon": "CHECKMARK"})
                else:
                    _instrument_button(col, context, idents[0], target, text=family.title,
                                       kwargs=icon_kwargs(*family_icon(family)))


def draw_instrument_pickers(layout, material, label=True, icon_only=False):
    """Two dropdowns: the category, then the instrument of that category."""
    from . import synth
    ident = material.gp2m_instrument
    family = families.family_of(ident)
    row = layout.row(align=True)
    row.context_pointer_set("gp2m_material", material)
    if icon_only:
        row.menu(GP2M_MT_instrument_category.bl_idname, text="",
                 **icon_kwargs(*instrument_icon(ident)))
    else:
        row.menu(GP2M_MT_instrument_category.bl_idname,
                 text=family.title if family is not None else "Categoria",
                 **icon_kwargs(*(family_icon(family) if family is not None else ("SOUND", 0))))
    inst = synth.INSTRUMENT_BY_ID.get(ident)
    text = board.material_label(material) if label else (inst.label if inst else ident)
    if family is not None:
        row.menu(_family_menu_id(family, True), text=text)
    else:
        row.menu(GP2M_MT_change_instrument.bl_idname, text=text)
    return row


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


def _change_target(context):
    """(composition, slot index, material, layer) the change-instrument menus act on."""
    comp = active_composition(context)
    if comp is None:
        return None, None, None, None
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
    return comp, index, material, layer


class GP2M_MT_layer_specials(bpy.types.Menu):
    """Like Blender's layer specials menu (the board layers are never touched)."""

    bl_idname = "GP2M_MT_layer_specials"
    bl_label = "Livelli e gruppi"

    def draw(self, context):
        layout = self.layout
        comp = active_composition(context)
        layout.operator("gp2m.copy_layer_settings", icon="COPYDOWN")
        layout.operator("gp2m.paste_layer_settings", icon="PASTEDOWN")
        layout.operator("gp2m.paste_layer_settings", text="Incolla in tutti i livelli",
                        icon="PASTEDOWN").every = True
        layout.separator()
        layout.operator("gp2m.duplicate_layer", icon="DUPLICATE")
        layout.operator("gp2m.duplicate_layer",
                        text="Duplica con keyframe vuoti").empty_keyframes = True
        layout.separator()
        layout.operator("gp2m.layers_reveal", icon="HIDE_OFF")
        layout.operator("gp2m.layers_hide_others", icon="HIDE_ON")
        layout.separator()
        layout.operator("gp2m.layers_lock", text="Blocca tutti", icon="LOCKED").lock = True
        layout.operator("gp2m.layers_lock", text="Sblocca tutti", icon="UNLOCKED").lock = False
        if comp is not None:
            layout.separator()
            layout.prop(comp.data, "use_autolock_layers", text="Blocca i livelli inattivi")
            layer = comp.data.layers.active
            if layer is not None and not board.is_board_layer(layer):
                layout.prop(layer, "ignore_locked_materials",
                            text="Ignora il blocco dei materiali")
        layout.separator()
        layout.operator("gp2m.merge_layer", text="Unisci sotto").mode = "ACTIVE"
        layout.operator("gp2m.merge_layer", text="Unisci gruppo").mode = "GROUP"
        layout.separator()
        layout.operator("gp2m.add_group", icon="NEWFOLDER")
        layout.menu("GP2M_MT_move_to_group", icon="FILE_FOLDER")
        layout.operator("gp2m.ungroup", icon="X")


class GP2M_MT_move_to_group(bpy.types.Menu):
    bl_idname = "GP2M_MT_move_to_group"
    bl_label = "Sposta nel gruppo"

    def draw(self, context):
        layout = self.layout
        comp = active_composition(context)
        if comp is None:
            return
        gp = comp.data
        layer = gp.layers.active
        current = layer.parent_group.name if layer is not None and layer.parent_group else ""
        groups = [node for node, _depth in board.user_tree(gp) if board.is_group(node)]
        for group in groups:
            row = layout.row()
            row.enabled = group.name != current
            row.operator("gp2m.move_to_group", text=group.name,
                         icon="FILE_FOLDER").group = group.name
        if groups:
            layout.separator()
        row = layout.row()
        row.enabled = bool(current)
        row.operator("gp2m.move_to_group", text="Fuori dal gruppo",
                     icon="PANEL_CLOSE").group = ""


def _solo_prop(layout, item):
    solo_icon = icon("solo_on" if item.solo else "solo_off")
    if solo_icon:
        layout.prop(item, "solo", text="", emboss=False, icon_value=solo_icon)
    else:
        layout.prop(item, "solo", text="", emboss=False,
                    icon="SOLO_ON" if item.solo else "SOLO_OFF")


def _audio_prop(layout, gp, item):
    """Audio on/off (the inverse of mute): shown off and greyed while another
    layer or group is in Solo."""
    silent = props.layer_silent(gp, item.name)
    sub = layout.row(align=True)
    sub.active = item.mute or not silent
    on = not silent
    value = icon("audio_on" if on else "audio_off")
    if value:
        sub.prop(item, "mute", text="", emboss=False, icon_value=value, invert_checkbox=True)
    else:
        sub.prop(item, "mute", text="", emboss=False, invert_checkbox=True,
                 icon="OUTLINER_DATA_SPEAKER" if on else "MUTE_IPO_ON")


def _indent(layout, depth):
    for _ in range(depth):
        layout.separator(factor=1.6)


def _lock_and_eye(layout, node):
    icons = layout.row(align=True)
    icons.emboss = "NONE"
    icons.prop(node, "lock", text="", emboss=False)
    icons.prop(node, "hide", text="", emboss=False)


class GP2M_UL_layers(bpy.types.UIList):
    """The layers and groups of the composition, top first, like Blender's own
    layer tree: icon, lock, eye, name, then audio on/off and Solo."""

    bl_idname = "GP2M_UL_layers"

    def draw_item(self, context, layout, data, item, _icon, _active_data, _active_prop,
                  _index=0, _flt_flag=0):
        gp = data
        if item.is_group:
            GP2M_UL_layers._draw_group(layout, gp, item)
            return
        layer = gp.layers.get(item.name)
        if layer is None:
            layout.label(text=item.name, icon="ERROR")
            return
        row = layout.row(align=True)
        _indent(row, len(board.ancestors(layer)))
        row.label(text="", icon="OUTLINER_DATA_GP_LAYER")
        _lock_and_eye(row, layer)
        name = row.row(align=True)
        name.active = not board.is_hidden(layer) and not props.layer_silent(gp, item.name)
        name.prop(layer, "name", text="", emboss=False)
        right = row.row(align=True)
        right.prop(item, "color", text="", icon_only=True, emboss=False)
        _audio_prop(right, gp, item)
        _solo_prop(right, item)

    @staticmethod
    def _draw_group(layout, gp, item):
        group = gp.layer_groups.get(item.name)
        if group is None:
            layout.label(text=item.name, icon="ERROR")
            return
        row = layout.row(align=True)
        _indent(row, len(board.ancestors(group)))
        row.prop(group, "is_expanded", text="", emboss=False,
                 icon="DISCLOSURE_TRI_DOWN" if group.is_expanded else "DISCLOSURE_TRI_RIGHT")
        row.label(text="", icon="FILE_FOLDER")
        _lock_and_eye(row, group)
        name = row.row(align=True)
        name.active = not group.hide and not props.layer_silent(gp, item.name)
        name.prop(group, "name", text="", emboss=False)
        right = row.row(align=True)
        _audio_prop(right, gp, item)
        _solo_prop(right, item)

    def filter_items(self, _context, data, propname):
        """Tree order, children of closed groups hidden.

        The order is always a permutation of all the items, also while the
        settings lag behind the layers (a layer just duplicated or deleted in
        Blender's own list): an order with gaps makes Blender crash."""
        items = getattr(data, propname)
        rows = board.user_tree(data)
        position = {}
        folded = set()
        for index, (node, _depth) in enumerate(rows):
            position[node.name] = index
            if any(not group.is_expanded for group in board.ancestors(node)):
                folded.add(node.name)
        needle = getattr(self, "filter_name", "").lower().strip("*")
        invert = getattr(self, "use_filter_invert", False)
        flags = []
        keys = []
        for index, item in enumerate(items):
            visible = item.name in position
            if visible and needle:
                visible = (needle in item.name.lower()) != invert
            elif visible:
                visible = item.name not in folded
            flags.append(self.bitflag_filter_item if visible else 0)
            keys.append((position.get(item.name, len(rows)), index))
        order = [0] * len(keys)
        for rank, (_key, index) in enumerate(sorted(keys)):
            order[index] = rank
        return flags, order


def _instrument_row(layout, comp, layer_name, index, material, active):
    row = layout.row(align=False)  # the color box stands apart from the name
    swatch = row.row()
    swatch.ui_units_x = 1.0
    swatch.prop(material.grease_pencil, "color", text="")
    sub = draw_instrument_pickers(row, material, icon_only=True)
    op = sub.operator("gp2m.use_instrument", text="", icon="GREASEPENCIL", depress=active)
    op.layer = layer_name
    op.index = index
    volume = row.row(align=True)
    volume.ui_units_x = 3.5
    volume.prop(material, "gp2m_volume", text="", slider=True)
    icons = row.row(align=True)
    icons.prop(material.grease_pencil, "hide", text="", emboss=False)
    icons.operator("gp2m.remove_instrument", text="", icon="X", emboss=False).index = index


def active_layer(context):
    """``(composition, active user layer, its settings)``; None for what is missing."""
    comp = active_composition(context)
    if comp is None:
        return None, None, None
    layer = comp.data.layers.active
    if layer is None or board.is_board_layer(layer):
        return comp, None, None
    return comp, layer, props.find_layer_settings(comp.data, layer.name)


def draw_layer_list(layout, comp):
    """Layer list like Blender's (top first), then reading and volume of the active layer."""
    gp = comp.data
    rows = max(4, min(10, len(gp.gp2m_layers)))
    row = layout.row()
    row.template_list("GP2M_UL_layers", "", gp, "gp2m_layers", gp, "gp2m_layer_index",
                      rows=rows, sort_lock=True)
    col = row.column(align=True)
    col.operator("gp2m.add_layer", text="", icon="ADD")
    col.operator("gp2m.add_group", text="", icon="NEWFOLDER")
    col.operator("gp2m.remove_layer", text="", icon="REMOVE")
    col.separator()
    col.menu("GP2M_MT_layer_specials", text="", icon="DOWNARROW_HLT")
    col.separator()
    col.operator("gp2m.move_layer", text="", icon="TRIA_UP").direction = "UP"
    col.operator("gp2m.move_layer", text="", icon="TRIA_DOWN").direction = "DOWN"

    layer = gp.layers.active
    if layer is None or board.is_board_layer(layer):
        return
    settings = props.find_layer_settings(gp, layer.name)
    col = layout.column()
    col.use_property_split = True
    col.use_property_decorate = False
    if settings is not None:
        col.prop(settings, "mode")
    col.prop(layer, "opacity", text="Volume", slider=True)
    if settings is not None:
        col.prop(settings, "pan_percent", slider=True)
    _clip_mix_props(col, settings)
    if settings is not None and settings.solo_saved_opacity >= 0.0:
        col.label(text="Attenuato dal Solo di un altro livello", icon="INFO")


def _clip_mix_props(col, settings):
    """Volume and pan of the layer's clip in the Sequencer (the same values)."""
    if settings is None:
        return
    sub = col.column(align=True)
    sub.prop(settings, "clip_volume", slider=True)


def draw_layer_instruments(layout, comp, layer, settings):
    col = layout.column(align=True)
    own = board.layer_instruments(comp, layer.name)
    for index, material in own:
        _instrument_row(col, comp, layer.name, index, material,
                        index == comp.active_material_index)
    if not own:
        col.label(text="Nessuno strumento", icon="INFO")
    add = layout.row()
    if settings is not None:
        add.context_pointer_set("gp2m_layer", settings)
    add.menu("GP2M_MT_add_instrument", text="Aggiungi strumento", icon="ADD")
    loose = board.loose_instruments(comp)
    if loose:
        layout.label(text="Senza livello", icon="MATERIAL")
        col = layout.column(align=True)
        for index, material in loose:
            _instrument_row(col, comp, "", index, material,
                            index == comp.active_material_index)


def draw_layers_and_instruments(layout, comp, details=True):
    """The layer list and the active layer's instruments in one column (kept for
    callers outside the panels)."""
    draw_layer_list(layout, comp)
    layer = comp.data.layers.active
    if layer is not None and not board.is_board_layer(layer):
        settings = props.find_layer_settings(comp.data, layer.name)
        draw_layer_instruments(layout, comp, layer, settings)
        if details:
            draw_layer_details(layout, comp.data, layer)


# --- Settings of the active layer (sub-panels under the list) --------------------------------

def _split(layout):
    col = layout.column()
    col.use_property_split = True
    col.use_property_decorate = False
    return col


def draw_layer_reading(layout, s):
    col = _split(layout)
    sub = col.column(align=True)
    if s.mode == "LEGATO":
        sub.prop(s, "glide")
    if s.mode in ("LEGATO", "OPTICAL_LEGATO"):
        sub.prop(s, "legato_gap", text="Unisci entro (battiti)")
    col.prop(s, "fill_mode")
    col.prop(s, "harmony")


def _unit_row(col, s, amount, unit, text):
    row = col.row(align=True)
    row.prop(s, amount, text=text)
    row.prop(s, unit, text="")


def draw_mod_array(layout, s):
    col = _split(layout)
    sub = col.column(align=True)
    count = sub.row(align=True)
    count.active = not s.array_fill
    count.prop(s, "array_count")
    sub.prop(s, "array_beats")
    col.prop(s, "array_fill")
    _unit_row(col, s, "array_pitch", "array_unit", "Sali di")
    col.prop(s, "array_decay", slider=True)


def draw_mod_mirror(layout, s):
    col = _split(layout)
    sub = col.column(heading="Specchia", align=True)
    sub.prop(s, "mirror_time")
    sub.prop(s, "mirror_pitch")
    sub.prop(s, "mirror_keep")
    sub = col.column(align=True)
    row = sub.row(align=True)
    row.active = s.mirror_time
    row.prop(s, "mirror_time_center", text="Centro tempo", slider=True)
    row = sub.row(align=True)
    row.active = s.mirror_pitch
    row.prop(s, "mirror_pitch_center", text="Centro altezza", slider=True)


def draw_mod_transpose(layout, s):
    col = _split(layout)
    _unit_row(col, s, "transpose_steps", "transpose_unit", "Di")


def draw_mod_fade(layout, s):
    col = _split(layout)
    col.row().prop(s, "fade_direction", expand=True)
    col.prop(s, "fade_scope")
    sub = col.column(align=True)
    sub.prop(s, "fade_length", slider=True)
    sub.prop(s, "fade_minimum", slider=True)


def draw_mod_noise(layout, s):
    col = _split(layout)
    sub = col.column(align=True)
    sub.prop(s, "noise_pitch", text="Altezza")
    sub.prop(s, "noise_width", slider=True)
    sub.prop(s, "noise_time", text="Tempo")
    sub = col.column(align=True)
    sub.prop(s, "noise_scale")
    sub.prop(s, "noise_seed")


def draw_fx_echo(layout, s):
    col = _split(layout).column(align=True)
    col.prop(s, "delay_mix", text="Quantità", slider=True)
    col.prop(s, "delay_beats", text="Tempo (battiti)")
    col.prop(s, "delay_feedback", slider=True)


def draw_fx_reverb(layout, s):
    col = _split(layout).column(align=True)
    col.prop(s, "reverb_mix", text="Quantità", slider=True)
    col.prop(s, "reverb_size", slider=True)


def draw_fx_lofi(layout, s):
    _split(layout).prop(s, "lofi", text="Quantità", slider=True)


def draw_fx_canon(layout, s):
    col = _split(layout).column(align=True)
    col.prop(s, "canon_voices", text="Voci")
    col.prop(s, "canon_delay")
    col.prop(s, "canon_transpose", text="Trasposizione")


# (key, label, parent key, draw, checkbox, help) of the sub-panels under the layer list,
# in the order they are shown. The modifiers are applied in this same order.
LAYER_PANELS = (
    ("instruments", "Strumenti", None, None, None, None),
    ("reading", "Lettura e armonia", None, draw_layer_reading, None, "READING"),
    ("mods", "Modificatori", None, None, None, "MODIFIERS"),
    ("mod_array", "Array", "mods", draw_mod_array, "use_array", None),
    ("mod_mirror", "Simmetria", "mods", draw_mod_mirror, "use_mirror", None),
    ("mod_transpose", "Trasponi", "mods", draw_mod_transpose, "use_transpose", None),
    ("mod_fade", "Fade", "mods", draw_mod_fade, "use_fade", None),
    ("mod_noise", "Noise", "mods", draw_mod_noise, "use_noise", None),
    ("fx", "Effetti", None, None, None, None),
    ("fx_echo", "Eco", "fx", draw_fx_echo, "use_echo", None),
    ("fx_reverb", "Riverbero", "fx", draw_fx_reverb, "use_reverb", None),
    ("fx_lofi", "Lo-fi", "fx", draw_fx_lofi, "use_lofi", None),
    ("fx_canon", "Canone", "fx", draw_fx_canon, "use_canon", None),
)


def _group_summary(layout, settings, keys):
    """The body of "Modificatori" / "Effetti": how many are on, or a hint."""
    on = [label for key, label, _p, _d, toggle, _h in LAYER_PANELS
          if key in keys and toggle and getattr(settings, toggle)]
    row = layout.row()
    row.active = bool(on)
    row.label(text=", ".join(on) if on else "Nessuno attivo")


def _layer_panel(base, prefix, layer_parent, key, label, parent, draw, toggle, help_key):
    idname = f"GP2M_PT_{prefix}_layer_{key}"
    parent_id = f"GP2M_PT_{prefix}_layer_{parent}" if parent else layer_parent
    children = tuple(k for k, _l, p, _d, _t, _h in LAYER_PANELS if p == key)

    def poll(cls, context):
        _comp, layer, settings = active_layer(context)
        return layer is not None and (key == "instruments" or settings is not None)

    def draw_header(self, context):
        _comp, _layer, settings = active_layer(context)
        self.layout.prop(settings, toggle, text="")

    def draw_header_preset(self, _context):
        help.button(self.layout, help_key)

    def draw_panel(self, context):
        comp, layer, settings = active_layer(context)
        if key == "instruments":
            draw_layer_instruments(self.layout, comp, layer, settings)
        elif children:
            _group_summary(self.layout, settings, children)
        else:
            self.layout.active = getattr(settings, toggle) if toggle else True
            draw(self.layout, settings)

    attrs = {"bl_idname": idname, "bl_label": label, "bl_parent_id": parent_id,
             "bl_options": set() if key == "instruments" else {"DEFAULT_CLOSED"},
             "poll": classmethod(poll), "draw": draw_panel}
    if toggle:
        attrs["draw_header"] = draw_header
    if help_key:
        attrs["draw_header_preset"] = draw_header_preset
    return type(idname, (base, bpy.types.Panel), attrs)


def _layer_panels(base, prefix, layer_parent):
    return tuple(_layer_panel(base, prefix, layer_parent, *spec) for spec in LAYER_PANELS)


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
        parts = [f"{stats['notes']} note", f"{stats['seconds'] * 1000:.0f} ms"]
        if stats.get("sections", 0) > 1:
            parts.append(f"{stats['sections']} sezioni · {engine.duration(comp):.1f} s")
        if stats.get("only_active"):
            parts.append("solo il livello attivo")
        row = layout.row()
        row.active = False
        row.label(text=" · ".join(parts), icon="SOUND")
        if stats.get("skipped"):
            layout.label(text=f"{stats['skipped']} parti saltate (vedi la console)",
                         icon="ERROR")
        if stats["multi_keyframes"]:
            box = layout.box()
            box.label_multiline(text="Viene letto solo il keyframe all'inizio della scena: "
                                + ", ".join(stats["multi_keyframes"]), icon="INFO")
            box.prop(comp.gp2m, "use_sections")
    if reader.has_unsupported_stack(comp) and not comp.gp2m.use_modifiers:
        row = layout.row(align=True)
        row.label(text="I modificatori di Blender non cambiano il suono", icon="ERROR")
        row.prop(comp.gp2m, "use_modifiers", text="", icon="MODIFIER_ON")


def draw_actions(layout, comp):
    row = layout.row(align=True)
    row.prop(comp.gp2m, "auto_update", text="Auto", toggle=True, icon="FILE_REFRESH")
    sub = row.row(align=True)
    sub.active = comp.gp2m.auto_update and comp.gp2m.layer_channels
    sub.prop(comp.gp2m, "auto_active_layer", text="", toggle=True,
             icon="OUTLINER_DATA_GP_LAYER")
    row.operator("gp2m.regenerate", icon="PLAY_SOUND")
    row.prop(comp.gp2m, "mute", text="", icon="MUTE_IPO_ON" if comp.gp2m.mute else "MUTE_IPO_OFF")
    row.separator()
    row.operator("gp2m.play_keyboard", text="", icon="KEYTYPE_KEYFRAME_VEC")
    p = prefs.get_prefs()
    if isinstance(p, bpy.types.AddonPreferences):  # "Suona mentre disegni"
        row.prop(p, "draw_sound", text="", icon="GREASEPENCIL", toggle=True)


def draw_board(layout, s):
    style = prefs.get_prefs().note_naming
    layout.use_property_split = True
    layout.use_property_decorate = False
    col = layout.column(align=True)
    col.prop(s, "bpm")
    col.prop(s, "length")
    col = layout.column(align=True)
    col.prop(s, "follow_scene")
    scene = bpy.context.scene
    if s.follow_scene and scene is not None:
        sub = col.column(align=True)
        sub.active = scene.gp2m_play.mode != "SEQUENCE"
        sub.prop(scene, "frame_start", text="In (Start)")
        sub.prop(scene, "frame_end", text="Out (End)")
    col = layout.column(heading="Ripeti", align=True)
    col.prop(s, "loop")
    col.prop(s, "use_sections")
    if beat.is_beat(s):
        draw_lanes(layout, s)
    else:
        col = layout.column(align=True)
        low = s.low_note
        col.prop(s, "low_note", text=f"Nota più bassa ({music.note_name(low, style)})")
        col.prop(s, "octaves",
                 text=f"Ottave (fino a {music.note_name(low + board.span(s), style)})")
        if s.extra_keys:
            col.prop(s, "extra_keys")
        _octave_buttons(col)
        col.prop(s, "key_labels")
    layout.prop(s, "grid_opacity", slider=True)
    col = layout.column(align=True)
    col.prop(s, "row_height")
    col.prop(s, "seconds_width")
    layout.prop(s, "show_beats")
    layout.operator("gp2m.rebuild_board", icon="GRID")


def draw_lanes(layout, s):
    """Bit: the lanes from the top, each with its percussion."""
    col = layout.column(align=True)
    col.prop(s, "lanes")
    _octave_buttons(col)
    col = layout.column(align=True)
    for lane in reversed(range(beat.lane_count(s))):
        if lane < len(s.lane_drums):
            col.prop(s.lane_drums[lane], "drum", text=f"Corsia {beat.lane_count(s) - lane}")
    layout.prop(s, "key_labels", text="Nomi delle corsie")


def _octave_buttons(layout):
    """Octaves on top / at the bottom: the drawing stays where it is."""
    row = layout.row(align=True)
    for edge, label in (("TOP", "Sopra"), ("BOTTOM", "Sotto")):
        sub = row.row(align=True)
        sub.label(text=label)
        for delta, icon in ((1, "ADD"), (-1, "REMOVE")):
            op = sub.operator("gp2m.board_octaves", text="", icon=icon)
            op.edge, op.delta = edge, delta


def draw_reading(layout, s):
    layout.use_property_split = True
    layout.use_property_decorate = False
    if not beat.is_beat(s):  # Bit: the lanes choose the sound, not the height
        col = layout.column(align=True)
        col.prop(s, "scale")
        col.prop(s, "root")
    col = layout.column(align=True)
    col.prop(s, "time_grid")
    sub = col.column(align=True)
    sub.active = s.time_grid != "OFF"
    sub.prop(s, "swing", slider=True)
    col.prop(s, "min_note")
    layout.prop(s, "use_modifiers", text="Modificatori di Blender")


def draw_mix(layout, s):
    layout.use_property_split = True
    layout.use_property_decorate = False
    layout.prop(s, "master_volume", slider=True)
    layout.prop(s, "room")
    layout.prop(s, "sample_rate")


def draw_master(layout, s):
    layout.use_property_split = True
    layout.use_property_decorate = False
    layout.active = s.use_master
    layout.prop(s, "ambience", slider=True)


def draw_effects(layout, fx):
    """Instrument effects (no checkboxes: an amount at zero is off)."""
    col = layout.column(align=True)
    col.prop(fx, "delay_mix", slider=True)
    sub = col.column(align=True)
    sub.active = fx.delay_mix > 0
    sub.prop(fx, "delay_beats")
    sub.prop(fx, "delay_feedback", slider=True)
    col = layout.column(align=True)
    col.prop(fx, "reverb_mix", slider=True)
    sub = col.column(align=True)
    sub.active = fx.reverb_mix > 0
    sub.prop(fx, "reverb_size", slider=True)
    layout.prop(fx, "lofi", slider=True)


def draw_layer_details(layout, gp, layer):
    """Every setting of a layer in one column (used outside the panels)."""
    settings = props.find_layer_settings(gp, layer.name)
    col = _split(layout)
    col.prop(layer, "opacity", text="Volume", slider=True)
    if settings is not None:
        col.prop(settings, "pan_percent", slider=True)
    _clip_mix_props(col, settings)
    if settings is None:
        col.label(text="Impostazioni in preparazione…")
        return
    col.prop(settings, "mode")
    draw_layer_reading(layout, settings)
    for _key, label, parent, draw, toggle, _help in LAYER_PANELS:
        if parent and toggle:
            layout.prop(settings, toggle, text=label)
            if getattr(settings, toggle):
                draw(layout, settings)


def draw_instrument_details(layout, material):
    layout.use_property_split = True
    layout.use_property_decorate = False
    col = layout.column(align=True)
    split = col.split(factor=0.4, align=True)
    split.alignment = "RIGHT"
    split.label(text="Strumento")
    draw_instrument_pickers(split, material, label=False)
    col.prop(material, "gp2m_volume", slider=True)
    if material.gp2m_instrument == "SAMPLE":
        col = layout.column(align=True)
        col.template_ID(material, "gp2m_sample", open="sound.open")
        col.operator("gp2m.load_sample", icon="FILEBROWSER")
        col = layout.column(align=True)
        col.prop(material, "gp2m_sample_root")
        col.prop(material, "gp2m_sample_loop")
    if material.gp2m_instrument == "LIBRARY":
        col = layout.column(align=True)
        col.prop(material, "gp2m_library_path", text="File")
        col.prop(material, "gp2m_library_preset")


def draw_play(layout, scene, comp=None):
    play = scene.gp2m_play
    layout.row().prop(play, "mode", expand=True)
    col = layout.column()
    col.use_property_split = True
    col.use_property_decorate = False
    row = col.row()
    row.active = not (comp is not None and engine.follows_scene(comp, scene))
    row.prop(play, "fit_range")
    if comp is not None:
        col.prop(comp.gp2m, "layer_channels")
        sub = col.column(align=True)
        sub.prop(comp.gp2m, "channel", text="Canale (0 = auto)")
        sub.prop(comp.gp2m, "start_delay")
        row = sub.row(align=True)
        row.active = play.mode == "SEQUENCE"
        row.prop(comp.gp2m, "order")


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
        draw_actions(self.layout, comp)
        draw_status(self.layout, comp)


def _copy_paste_header(layout):
    row = layout.row(align=True)
    row.operator("gp2m.copy_layer_settings", text="", icon="COPYDOWN", emboss=False)
    row.operator("gp2m.paste_layer_settings", text="", icon="PASTEDOWN", emboss=False)


class GP2M_PT_data_layers(_DataPanel, bpy.types.Panel):
    bl_label = "Livelli"
    bl_parent_id = "GP2M_PT_data"

    def draw_header_preset(self, _context):
        _copy_paste_header(self.layout)

    def draw(self, context):
        draw_layer_list(self.layout, active_composition(context))


DATA_LAYER_PANELS = _layer_panels(_DataPanel, "data", "GP2M_PT_data_layers")


class GP2M_PT_data_board(_DataPanel, bpy.types.Panel):
    bl_label = "Tavola e tempo"
    bl_parent_id = "GP2M_PT_data"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        draw_board(self.layout, active_composition(context).gp2m)


class GP2M_PT_data_reading(_DataPanel, bpy.types.Panel):
    bl_label = "Scala e ritmo"
    bl_parent_id = "GP2M_PT_data"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header_preset(self, _context):
        help.button(self.layout, "READING")

    def draw(self, context):
        draw_reading(self.layout, active_composition(context).gp2m)


class GP2M_PT_data_mix(_DataPanel, bpy.types.Panel):
    bl_label = "Mix"
    bl_parent_id = "GP2M_PT_data"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        draw_mix(self.layout, active_composition(context).gp2m)


class GP2M_PT_data_master(_DataPanel, bpy.types.Panel):
    bl_label = "Suono finito"
    bl_parent_id = "GP2M_PT_data_mix"

    def draw_header(self, context):
        self.layout.prop(active_composition(context).gp2m, "use_master", text="")

    def draw(self, context):
        draw_master(self.layout, active_composition(context).gp2m)


class GP2M_PT_data_play(_DataPanel, bpy.types.Panel):
    bl_label = "Sequencer e ascolto"
    bl_parent_id = "GP2M_PT_data"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        draw_play(self.layout, context.scene, active_composition(context))


class _MaterialPanel:
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"

    @classmethod
    def poll(cls, context):
        material = getattr(context, "material", None)
        return (active_composition(context) is not None and material is not None
                and material.grease_pencil is not None and not board.is_board_material(material))


class GP2M_PT_material(_MaterialPanel, bpy.types.Panel):
    bl_label = "Strumento musicale"

    def draw_header(self, _context):
        self.layout.label(icon="FILE_SOUND")

    def draw_header_preset(self, _context):
        help.button(self.layout, "INSTRUMENT")

    def draw(self, context):
        draw_instrument_details(self.layout, context.material)


class GP2M_PT_material_fx(_MaterialPanel, bpy.types.Panel):
    bl_label = "Effetti dello strumento"
    bl_parent_id = "GP2M_PT_material"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        draw_effects(layout, context.material.gp2m_fx)


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
            col = layout.column(align=True)
            col.operator("gp2m.add_composition", icon="ADD")
            col.operator("gp2m.import_midi", icon="IMPORT")
            col.operator("gp2m.import_web", icon="URL")
            return
        draw_actions(layout, comp)
        draw_status(layout, comp)
        layout.row().prop(context.scene.gp2m_play, "mode", expand=True)


class GP2M_PT_layers(_CompositionPanel, bpy.types.Panel):
    bl_label = "Livelli"

    def draw_header_preset(self, _context):
        _copy_paste_header(self.layout)

    def draw(self, context):
        draw_layer_list(self.layout, active_composition(context))


VIEW_LAYER_PANELS = _layer_panels(_Panel, "view", "GP2M_PT_layers")


# --- Menus ---------------------------------------------------------------------------------

class VIEW3D_MT_gp2m_add(bpy.types.Menu):
    bl_idname = "VIEW3D_MT_gp2m_add"
    bl_label = "Doodle Music"

    def draw(self, _context):
        self.layout.operator("gp2m.add_composition", text="Composizione Musicale",
                             icon="OUTLINER_OB_GREASEPENCIL")
        self.layout.operator("gp2m.add_composition", text="Composizione Bit",
                             icon="SEQ_HISTOGRAM").kind = "BEAT"
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


# --- Sequencer sidebar: the groups (Ctrl+G) ------------------------------------------

def _sequencer_group(context):
    """``(strip, composition, settings)`` of the active strip when it is a group: of
    compositions (composition and settings None) or of layers."""
    editor = context.scene.sequence_editor if context.scene else None
    strip = editor.active_strip if editor is not None else None
    if strip is None or strip.type != "META":
        return None
    if engine.is_group_meta(strip):
        return strip, None, None
    name = strip.get(engine.LAYER_GROUP_KEY)
    comp = bpy.data.objects.get(strip.get(engine.OWNER_KEY) or "")
    if name is None or comp is None or comp.type != "GREASEPENCIL":
        return None
    return strip, comp, props.find_layer_settings(comp.data, name)


class GP2M_PT_sequencer_group(bpy.types.Panel):
    """Volume, pan and mute of a group: they apply to everything in it."""

    bl_space_type = "SEQUENCE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Musica"
    bl_label = "Gruppo"

    @classmethod
    def poll(cls, context):
        return _sequencer_group(context) is not None

    def draw(self, context):
        strip, comp, settings = _sequencer_group(context)
        col = self.layout.column(align=True)
        if comp is None:
            col.label(text="Composizioni: " + str(sum(
                1 for inner in strip.strips if engine._is_composition_strip(inner))))
            if engine.BUS_VOLUME in strip:
                col.prop(strip, f'["{engine.BUS_VOLUME}"]', text="Volume", slider=True)
            if engine.BUS_PAN in strip:
                col.prop(strip, f'["{engine.BUS_PAN}"]', text="Pan", slider=True)
            col.prop(strip, "mute", text="Muto")
        elif settings is not None:
            col.label(text=comp.name, icon="OUTLINER_OB_GREASEPENCIL")
            col.prop(settings, "clip_volume", text="Volume", slider=True)
            col.prop(settings, "pan_percent", text="Pan", slider=True)
            col.prop(settings, "mute", text="Muto")


classes = ADD_FAMILY_MENUS + CHANGE_FAMILY_MENUS + (
    GP2M_MT_add_instrument,
    GP2M_MT_change_instrument,
    GP2M_MT_instrument_category,
    GP2M_MT_layer_specials,
    GP2M_MT_move_to_group,
    GP2M_UL_layers,
    GP2M_PT_data,
    GP2M_PT_data_layers,
) + DATA_LAYER_PANELS + (
    GP2M_PT_data_board,
    GP2M_PT_data_reading,
    GP2M_PT_data_mix,
    GP2M_PT_data_master,
    GP2M_PT_data_play,
    GP2M_PT_material,
    GP2M_PT_material_fx,
    GP2M_PT_output,
    GP2M_PT_scene,
    GP2M_PT_main,
    GP2M_PT_layers,
) + VIEW_LAYER_PANELS + (
    VIEW3D_MT_gp2m_add,
    GP2M_PT_sequencer_group,
)


def register():
    bpy.types.VIEW3D_MT_add.append(draw_add_menu)
    bpy.types.TOPBAR_MT_file_export.append(draw_export_menu)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(draw_export_menu)
    bpy.types.VIEW3D_MT_add.remove(draw_add_menu)
