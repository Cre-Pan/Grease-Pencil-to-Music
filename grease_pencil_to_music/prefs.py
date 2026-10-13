# SPDX-License-Identifier: GPL-3.0-or-later
"""Add-on preferences: how each Grease Pencil attribute becomes sound."""

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty

from .interpret import Mapping

THICKNESS_ITEMS = (
    ("VOLUME_VIBRATO", "Volume + Vibrato",
     "L'andamento lento dello spessore è il volume, la sua irregolarità (jitter) è il vibrato"),
    ("VOLUME", "Volume", "Lo spessore è il volume (il jitter diventa tremolo)"),
    ("VIBRATO", "Vibrato", "L'irregolarità dello spessore è il vibrato"),
    ("BRIGHTNESS", "Brillantezza", "Tratto spesso = suono brillante, tratto fine = suono scuro"),
    ("NONE", "Nessuno", "Lo spessore non influisce sul suono"),
)
OPACITY_ITEMS = (
    ("BRIGHTNESS", "Brillantezza", "Tratto opaco = suono brillante, trasparente = suono scuro"),
    ("VOLUME", "Volume", "L'opacità è il volume"),
    ("NONE", "Nessuno", "L'opacità non influisce sul suono"),
)
VERTEX_COLOR_ITEMS = (
    ("NONE", "Nessuno", "Il vertex color non influisce sul suono"),
    ("PAN", "Pan stereo", "Rosso = sinistra, blu = destra (pesato dall'alpha del vertex color)"),
    ("BRIGHTNESS", "Brillantezza", "Colori chiari = suono brillante"),
)
SOFTNESS_ITEMS = (
    ("ATTACK", "Attacco", "Tratto morbido (softness) = attacco lento"),
    ("NONE", "Nessuno", "La morbidezza non influisce sul suono"),
)


def _changed(_self, _context):
    from . import handlers
    handlers.mark_all_dirty()


class GP2M_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    map_thickness: EnumProperty(name="Spessore", items=THICKNESS_ITEMS,
                                default="VOLUME_VIBRATO", update=_changed)
    map_opacity: EnumProperty(name="Opacità", items=OPACITY_ITEMS, default="BRIGHTNESS",
                              update=_changed)
    map_vertex_color: EnumProperty(name="Vertex color", items=VERTEX_COLOR_ITEMS,
                                   default="NONE", update=_changed)
    map_softness: EnumProperty(name="Morbidezza", items=SOFTNESS_ITEMS, default="ATTACK",
                               update=_changed)
    vibrato_depth: FloatProperty(name="Profondità vibrato", default=0.6, min=0.0, max=2.0,
                                 subtype="FACTOR", description="Semitoni di vibrato con il "
                                 "massimo jitter dello spessore", update=_changed)
    vibrato_rate: FloatProperty(name="Velocità vibrato", default=5.5, min=1.0, max=12.0,
                                unit="NONE", description="Oscillazioni al secondo (Hz)",
                                update=_changed)
    debounce: FloatProperty(name="Ritardo aggiornamento", default=0.35, min=0.05, max=3.0,
                            description="Secondi di pausa dopo una modifica prima di "
                            "rigenerare il suono")
    mp3_bitrate: IntProperty(name="Bitrate MP3 (kbps)", default=192, min=64, max=320)

    def draw(self, _context):
        layout = self.layout
        box = layout.box()
        box.label(text="Cosa suona nel tratto", icon="SOUND")
        grid = box.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
        for attr, label in (("map_thickness", "Spessore"), ("map_opacity", "Opacità"),
                            ("map_vertex_color", "Vertex color"),
                            ("map_softness", "Morbidezza (softness)")):
            grid.label(text=label)
            grid.prop(self, attr, text="")
        box.label(text="Materiale → Strumento (si sceglie nel pannello N)", icon="MATERIAL")
        col = layout.column(align=True)
        col.prop(self, "vibrato_depth")
        col.prop(self, "vibrato_rate")
        col = layout.column(align=True)
        col.prop(self, "debounce")
        col.prop(self, "mp3_bitrate")


class _Defaults:
    map_thickness = "VOLUME_VIBRATO"
    map_opacity = "BRIGHTNESS"
    map_vertex_color = "NONE"
    map_softness = "ATTACK"
    vibrato_depth = 0.6
    vibrato_rate = 5.5
    debounce = 0.35
    mp3_bitrate = 192


def get_prefs():
    addon = bpy.context.preferences.addons.get(__package__)
    if addon is None or addon.preferences is None:
        return _Defaults
    return addon.preferences


def get_mapping():
    p = get_prefs()
    return Mapping(thickness=p.map_thickness, opacity=p.map_opacity,
                   vertex_color=p.map_vertex_color, softness=p.map_softness,
                   vibrato_depth=p.vibrato_depth, vibrato_rate=p.vibrato_rate)


classes = (GP2M_Preferences,)
