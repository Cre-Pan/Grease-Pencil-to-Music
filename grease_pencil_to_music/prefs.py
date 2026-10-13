# SPDX-License-Identifier: GPL-3.0-or-later
"""Add-on preferences: how each Grease Pencil attribute becomes sound."""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty

from . import music
from .board import KEY_LABEL_ITEMS
from .interpret import Mapping

THICKNESS_ITEMS = (
    ("VOLUME", "Volume", "Lo spessore è il volume (il jitter diventa tremolo)"),
    ("VOLUME_VIBRATO", "Volume + Vibrato",
     "L'andamento lento dello spessore è il volume, la sua irregolarità (jitter) è il vibrato"),
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


NAMING_ITEMS = (
    ("EN", "C D E F G A B", "Nomi inglesi (C4 = Do centrale)"),
    ("IT", "Do Re Mi Fa Sol La Si", "Nomi italiani (Do4 = Do centrale)"),
)

def _changed(_self, _context):
    from . import handlers
    handlers.mark_all_dirty()


def _naming_changed(_self, _context):
    from . import board, handlers
    for obj in handlers.compositions():
        board.request_rebuild(obj)


INSTRUMENT_SET_ITEMS = (
    ("ONE", "Uno (Flauto)", "Si parte con un solo strumento; gli altri si aggiungono nel livello"),
    ("NONE", "Nessuno", "Livello vuoto: gli strumenti si aggiungono con '+ Strumento'"),
    ("ALL", "Tutti", "Tutti gli strumenti sintetizzati (Campione e Libreria si aggiungono con +)"),
    ("ESSENTIAL", "Essenziali", "Flauto, 8-bit, Synth, Archi, Chitarra, Cassa, Rullante, "
     "Charleston"),
    ("MELODIC", "Solo melodici", "Gli strumenti intonati, senza percussioni"),
)
INSTRUMENT_SETS = {
    "ONE": ("SINE",),
    "NONE": (),
    "ESSENTIAL": ("SINE", "SQUARE", "SAW", "STRINGS", "PLUCK", "KICK", "SNARE", "HIHAT"),
    "MELODIC": ("SINE", "TRIANGLE", "SQUARE", "SAW", "STRINGS", "PLUCK", "BELL"),
}
FEEDBACK_ITEMS = (
    ("AUTO", "Automatico", "Spessore se lo spessore è il volume, altrimenti trasparenza"),
    ("THICKNESS", "Spessore", "Il volume dello strumento rende i tratti più fini o più spessi "
     "(modificatore Thickness, solo visivo)"),
    ("OPACITY", "Trasparenza", "Il volume dello strumento rende i tratti più trasparenti"),
    ("NONE", "Niente", "Il volume non cambia l'aspetto dei tratti"),
)


def _feedback_changed(_self, _context):
    from . import feedback, handlers
    for obj in handlers.compositions():
        feedback.sync(obj)


class GP2M_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    note_naming: EnumProperty(name="Nomi delle note", items=NAMING_ITEMS, default="EN",
                              update=_naming_changed)
    resume_after_undo: BoolProperty(name="Riprendi il play dopo Ctrl+Z", default=True,
                                    description="Se Ctrl+Z ferma la riproduzione, la fa "
                                    "ripartire subito")
    map_thickness: EnumProperty(name="Spessore", items=THICKNESS_ITEMS,
                                default="VOLUME", update=_changed)
    map_opacity: EnumProperty(name="Opacità", items=OPACITY_ITEMS, default="BRIGHTNESS",
                              update=_changed)
    map_vertex_color: EnumProperty(name="Vertex color", items=VERTEX_COLOR_ITEMS,
                                   default="NONE", update=_changed)
    map_softness: EnumProperty(name="Morbidezza", items=SOFTNESS_ITEMS, default="ATTACK",
                               update=_changed)
    volume_feedback: EnumProperty(name="Volume visibile", items=FEEDBACK_ITEMS,
                                  default="AUTO", update=_feedback_changed,
                                  description="Come il volume di uno strumento si vede sui "
                                  "suoi tratti")
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

    # Defaults for new compositions (each composition keeps its own copy).
    new_bpm: FloatProperty(name="BPM", default=120.0, min=20.0, max=300.0)
    new_length: FloatProperty(name="Durata (s)", default=8.0, min=1.0, max=300.0)
    new_low_note: IntProperty(name="Nota più bassa", default=48, min=12, max=96)
    new_octaves: IntProperty(name="Ottave", default=3, min=1, max=7)
    new_row_height: FloatProperty(name="Altezza riga", default=0.12, min=0.02, max=1.0)
    new_seconds_width: FloatProperty(name="Larghezza secondo", default=1.0, min=0.1, max=10.0)
    new_scale: EnumProperty(name="Scala", items=[(i, l, "") for i, l, _ in music.SCALES],
                            default="CHROMATIC")
    new_time_grid: EnumProperty(name="Quantizzazione",
                                items=[(i, l, "") for i, l, _ in music.TIME_GRIDS],
                                default="1_16")
    new_key_labels: EnumProperty(name="Etichette tasti", items=KEY_LABEL_ITEMS, default="C")
    new_layers: IntProperty(name="Livelli", default=1, min=1, max=16)
    enter_draw_mode: BoolProperty(name="Entra in Draw Mode", default=False,
                                  description="Dopo aver creato una composizione passa subito "
                                  "al Draw Mode (altrimenti resta in Object Mode)")
    new_instruments: EnumProperty(name="Strumenti", items=INSTRUMENT_SET_ITEMS, default="ONE")
    new_sample_rate: EnumProperty(name="Frequenza audio",
                                  items=(("44100", "44.1 kHz", ""), ("48000", "48 kHz", "")),
                                  default="44100")
    record_thickness: FloatProperty(name="Spessore registrazione", default=0.25, min=0.05,
                                    max=1.0, subtype="FACTOR",
                                    description="Spessore dei tratti registrati con la "
                                    "tastiera, rispetto all'altezza della riga")
    use_midi_input: BoolProperty(name="Tastiera MIDI", default=True,
                                 description="Nella modalità 'Suona con la tastiera' ascolta "
                                 "anche una tastiera MIDI collegata")
    midi_port: StringProperty(name="Porta MIDI", default="",
                              search=lambda _self, _context, _text: _midi_ports(),
                              description="Nome della porta MIDI (vuoto = la prima trovata; "
                              "accetta * come jolly)")

    def draw(self, _context):
        layout = self.layout
        box = layout.box()
        box.label(text="Tavola e riproduzione", icon="SEQ_PREVIEW")
        grid = box.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
        for attr, label in (("note_naming", "Nomi delle note"),
                            ("volume_feedback", "Volume visibile sui tratti")):
            grid.label(text=label)
            grid.prop(self, attr, text="")
        box.prop(self, "resume_after_undo")
        box = layout.box()
        box.label(text="Cosa suona nel tratto", icon="SOUND")
        grid = box.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
        for attr, label in (("map_thickness", "Spessore"), ("map_opacity", "Opacità"),
                            ("map_vertex_color", "Vertex color"),
                            ("map_softness", "Morbidezza (softness)")):
            grid.label(text=label)
            grid.prop(self, attr, text="")
        col = box.column(align=True)
        col.prop(self, "vibrato_depth")
        col.prop(self, "vibrato_rate")
        box = layout.box()
        box.label(text="Nuove composizioni", icon="OUTLINER_OB_GREASEPENCIL")
        grid = box.grid_flow(row_major=True, columns=2, even_columns=True, align=False)
        for attr in ("new_bpm", "new_length", "new_low_note", "new_octaves", "new_row_height",
                     "new_seconds_width", "new_scale", "new_time_grid", "new_key_labels",
                     "new_layers", "new_instruments", "new_sample_rate", "enter_draw_mode"):
            grid.prop(self, attr)
        box = layout.box()
        box.label(text="Avanzate", icon="PREFERENCES")
        col = box.column(align=True)
        col.prop(self, "debounce")
        col.prop(self, "mp3_bitrate")
        col.prop(self, "record_thickness")
        box = layout.box()
        box.label(text="Tastiera MIDI", icon="EVENT_M")
        row = box.row()
        row.prop(self, "use_midi_input", text="")
        sub = row.row()
        sub.active = self.use_midi_input
        sub.prop(self, "midi_port", text="Porta")


def _midi_ports():
    from . import midi_input
    return midi_input.port_names()


class _Defaults:
    note_naming = "EN"
    resume_after_undo = True
    map_thickness = "VOLUME"
    map_opacity = "BRIGHTNESS"
    map_vertex_color = "NONE"
    map_softness = "ATTACK"
    volume_feedback = "AUTO"
    vibrato_depth = 0.6
    vibrato_rate = 5.5
    debounce = 0.35
    mp3_bitrate = 192
    new_bpm = 120.0
    new_length = 8.0
    new_low_note = 48
    new_octaves = 3
    new_row_height = 0.12
    new_seconds_width = 1.0
    new_scale = "CHROMATIC"
    new_time_grid = "1_16"
    new_key_labels = "C"
    new_layers = 1
    enter_draw_mode = False
    new_instruments = "ONE"
    new_sample_rate = "44100"
    record_thickness = 0.25
    use_midi_input = True
    midi_port = ""


def new_instrument_idents():
    p = get_prefs()
    if p.new_instruments in INSTRUMENT_SETS:
        return INSTRUMENT_SETS[p.new_instruments]
    from . import synth
    return tuple(i.ident for i in synth.INSTRUMENTS if i.ident not in ("SAMPLE", "LIBRARY"))


def feedback_mode():
    """The effective 'volume visible' mode."""
    p = get_prefs()
    if p.volume_feedback != "AUTO":
        return p.volume_feedback
    if p.map_thickness in ("VOLUME", "VOLUME_VIBRATO"):
        return "THICKNESS"
    return "OPACITY"


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
