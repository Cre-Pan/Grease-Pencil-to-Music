# SPDX-License-Identifier: GPL-3.0-or-later
"""Properties stored in the .blend file."""

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       FloatVectorProperty, IntProperty, PointerProperty, StringProperty)

from . import music, synth
from .board import KEY_LABEL_ITEMS


def _sound_changed(self, _context):
    from . import handlers
    owner = self.id_data
    if isinstance(owner, bpy.types.Object):
        handlers.mark_dirty(owner)
    elif isinstance(owner, bpy.types.Material):
        handlers.mark_material_dirty(owner)
    else:
        handlers.mark_data_dirty(owner)


def _board_changed(self, _context):
    from . import board, handlers
    obj = self.id_data
    if isinstance(obj, bpy.types.Object) and obj.gp2m.is_composition:
        board.request_rebuild(obj)
        handlers.mark_dirty(obj)


def _instrument_changed(self, _context):
    from . import feedback, handlers
    handlers.mark_material_dirty(self)
    feedback.sync_material(self)


def _arrangement_changed(self, context):
    from . import engine
    scene = self.id_data if isinstance(self.id_data, bpy.types.Scene) else context.scene
    if scene is not None:
        engine.arrange_safe(scene)


def _timeline_changed(_self, _context):
    from . import timeline
    timeline.tag_redraw()


def _composition_poll(_self, obj):
    return obj.type == "GREASEPENCIL" and obj.gp2m.is_composition


# Explicit numbers keep the values saved in older .blend files (enums are stored
# by number); the letters are the ones of the web app, like Procreate's blend modes.
LAYER_MODES = (
    ("QUANTIZED", "Q · Quantizzata",
     "Il tratto diventa note: cambia nota ogni volta che attraversa una riga, agganciata "
     "alla scala e alla griglia; ogni nota attacca da capo", "IPO_CONSTANT", 0),
    ("LEGATO", "QL · Quantizzata legata",
     "Le note della scala unite da glissandi, senza riattacco: anche da un tratto al "
     "successivo dello stesso strumento, se sono vicini", "IPO_LINEAR", 2),
    ("OPTICAL", "O · Ottica",
     "Stile McLaren: l'altezza segue la linea in modo continuo, con glissandi. Chitarra e "
     "campana tengono il suono e scivolano", "IPO_SINE", 1),
    ("OPTICAL_LEGATO", "OL · Ottica legata",
     "Come Ottica, ma i tratti vicini dello stesso strumento diventano una sola voce: la "
     "linea continua anche nelle pause, senza riattacco", "IPO_BEZIER", 4),
    ("GESTURE", "G · Gesto",
     "Il ritmo è quello della mano: il tratto parte dove inizia e dura quanto hai impiegato "
     "a disegnarlo (una linea verticale veloce diventa una scala rapida)", "HAND", 3),
)


FILL_MODES = (
    ("TONAL", "Cluster tonale",
     "Una forma piena suona tutte le note della scala che copre"),
    ("NOISE", "Banda di rumore",
     "Una forma piena è rumore filtrato tra il suo bordo inferiore e superiore (alla ANS)"),
)


SOLO_OPACITY = 0.1  # opacity of the other layers while a layer is in Solo


def _solo_changed(self, _context):
    apply_solo(self.id_data)
    _sound_changed(self, _context)


def apply_solo(gp_data):
    """Dim the layers that are not in Solo to 10% opacity, restore them after.

    The opacity a layer had is kept in its settings: the volume of the layer is
    still that one (a dimmed layer is silent anyway, and exports read the saved
    value). If the opacity was changed by hand while dimmed, that value wins.
    """
    settings = list(gp_data.gp2m_layers)
    any_solo = any(item.solo for item in settings)
    for item in settings:
        layer = gp_data.layers.get(item.name)
        if layer is None:
            continue
        dim = any_solo and not item.solo
        if dim and item.solo_saved_opacity < 0.0:
            item.solo_saved_opacity = layer.opacity
            layer.opacity = SOLO_OPACITY
        elif not dim and item.solo_saved_opacity >= 0.0:
            if abs(layer.opacity - SOLO_OPACITY) < 1e-4:
                layer.opacity = item.solo_saved_opacity
            item.solo_saved_opacity = -1.0


def layer_volume(gp_data, layer):
    """The volume of a layer: its opacity, or the one it had before a Solo dimmed it."""
    item = find_layer_settings(gp_data, layer.name)
    if item is not None and item.solo_saved_opacity >= 0.0:
        return float(item.solo_saved_opacity)
    return float(layer.opacity)


def layer_silent(gp_data, layer_name):
    """Muted, or another layer is in Solo."""
    settings = gp_data.gp2m_layers
    item = find_layer_settings(gp_data, layer_name)
    if item is not None and item.mute:
        return True
    return any(other.solo for other in settings) and (item is None or not item.solo)


class GP2M_LayerSettings(bpy.types.PropertyGroup):
    """Settings of one Grease Pencil layer, matched by layer name."""

    name: StringProperty()
    mute: BoolProperty(name="Muto", default=False, update=_sound_changed,
                       description="Il livello resta visibile ma non suona (anche negli export)")
    solo: BoolProperty(name="Solo", default=False, update=_solo_changed,
                       description="Ascolta solo questo livello: gli altri tacciono e scendono "
                       "al 10% di opacità (anche negli export)")
    solo_saved_opacity: FloatProperty(default=-1.0, options={"HIDDEN"},
                                      description="Opacità del livello prima del Solo "
                                      "(-1 = non attenuato)")
    expanded: BoolProperty(name="Mostra strumenti", default=True)
    show_fx: BoolProperty(name="Mostra volume ed effetti", default=False)
    mode: EnumProperty(name="Lettura", items=LAYER_MODES, default="QUANTIZED",
                       update=_sound_changed)
    fill_mode: EnumProperty(name="Forme piene", items=FILL_MODES, default="TONAL",
                            update=_sound_changed)
    glide: FloatProperty(name="Tempo di legato", default=0.12, min=0.01, max=1.0,
                         subtype="TIME_ABSOLUTE", unit="TIME_ABSOLUTE",
                         description="Durata dello scivolamento da una nota all'altra",
                         update=_sound_changed)
    legato_gap: FloatProperty(name="Unisci tratti entro (battiti)", default=1.0, min=0.0,
                              max=8.0, step=25,
                              description="Nelle letture legate, i tratti dello stesso "
                              "strumento più vicini di così diventano una sola voce che "
                              "scivola nella pausa (0 = solo quelli che si toccano)",
                              update=_sound_changed)
    delay_mix: FloatProperty(name="Eco", default=0.0, min=0.0, max=1.0, subtype="FACTOR",
                             update=_sound_changed)
    delay_beats: FloatProperty(name="Tempo eco (battiti)", default=0.75, min=0.125, max=4.0,
                               step=12.5, update=_sound_changed)
    delay_feedback: FloatProperty(name="Ripetizioni", default=0.35, min=0.0, max=0.9,
                                  subtype="FACTOR", update=_sound_changed)
    reverb_mix: FloatProperty(name="Riverbero", default=0.0, min=0.0, max=1.0,
                              subtype="FACTOR", update=_sound_changed)
    reverb_size: FloatProperty(name="Ampiezza stanza", default=0.5, min=0.0, max=1.0,
                               subtype="FACTOR", update=_sound_changed)
    lofi: FloatProperty(name="Lo-fi", default=0.0, min=0.0, max=1.0, subtype="FACTOR",
                        update=_sound_changed)
    harmony: EnumProperty(name="Armonia", items=[(i, l, d) for i, l, d, _ in music.HARMONIES],
                          default="OFF", update=_sound_changed,
                          description="Aggiunge voci che accompagnano le note disegnate, "
                          "sempre dentro la scala della composizione")
    canon_voices: IntProperty(name="Voci del canone", default=1, min=1, max=4,
                              description="Il livello si ripete in altre voci che entrano una "
                              "dopo l'altra (1 = nessun canone)", update=_sound_changed)
    canon_delay: FloatProperty(name="Entrata (battiti)", default=4.0, min=0.25, max=32.0,
                               step=25, description="Battiti tra l'entrata di una voce e "
                               "la successiva", update=_sound_changed)
    canon_transpose: IntProperty(name="Trasposizione (semitoni)", default=0, min=-24, max=24,
                                 description="Ogni voce è trasposta rispetto alla precedente "
                                 "(12 = un'ottava sopra, -5 = una quarta sotto…)",
                                 update=_sound_changed)


class GP2M_Effects(bpy.types.PropertyGroup):
    """Effects of one instrument (material), applied before the layer effects."""

    delay_mix: FloatProperty(name="Eco", default=0.0, min=0.0, max=1.0, subtype="FACTOR",
                             update=_sound_changed)
    delay_beats: FloatProperty(name="Tempo eco (battiti)", default=0.75, min=0.125, max=4.0,
                               step=12.5, update=_sound_changed)
    delay_feedback: FloatProperty(name="Ripetizioni", default=0.35, min=0.0, max=0.9,
                                  subtype="FACTOR", update=_sound_changed)
    reverb_mix: FloatProperty(name="Riverbero", default=0.0, min=0.0, max=1.0,
                              subtype="FACTOR", update=_sound_changed)
    reverb_size: FloatProperty(name="Ampiezza stanza", default=0.5, min=0.0, max=1.0,
                               subtype="FACTOR", update=_sound_changed)
    lofi: FloatProperty(name="Lo-fi", default=0.0, min=0.0, max=1.0, subtype="FACTOR",
                        update=_sound_changed)


SAMPLE_RATES = (("44100", "44.1 kHz", ""), ("48000", "48 kHz", ""))


ROOM_ITEMS = (
    ("HALL", "Sala", "Il riverbero sintetico (la sua grandezza si regola)"),
    ("ROOM", "Stanza", "Un soggiorno registrato (HybridReverb2, CC BY-SA 4.0)"),
    ("CONCERT", "Auditorium", "Una grande sala da concerto registrata (HybridReverb2)"),
    ("CHURCH", "Chiesa", "Una chiesa registrata, coda lunga (HybridReverb2)"),
)


class GP2M_CompositionSettings(bpy.types.PropertyGroup):
    is_composition: BoolProperty(default=False)
    channel: IntProperty(name="Canale Sequencer", default=0, min=0, max=128,
                         description="Canale del Video Sequencer della sua strip audio "
                         "(0 = scegli automaticamente il primo libero)",
                         update=_arrangement_changed)
    order: IntProperty(name="Ordine", default=0, min=0, max=999,
                       description="Posizione nella riproduzione 'Una dopo l'altra'",
                       update=_arrangement_changed)
    mute: BoolProperty(name="Muto", default=False,
                       description="Silenzia questa composizione (la tavola resta visibile)",
                       update=_sound_changed)

    bpm: FloatProperty(name="BPM", default=120.0, min=20.0, max=300.0,
                       description="Battiti al minuto: griglia ritmica, quantizzazione ed eco",
                       update=_board_changed)
    length: FloatProperty(name="Durata (s)", default=8.0, min=1.0, max=300.0,
                          description="Durata del loop in secondi", update=_board_changed)
    low_note: IntProperty(name="Nota più bassa", default=48, min=12, max=96,
                          description="Nota MIDI della riga più bassa (48 = C3)",
                          update=_board_changed)
    octaves: IntProperty(name="Ottave", default=3, min=1, max=7, update=_board_changed)
    row_height: FloatProperty(name="Altezza riga", default=0.12, min=0.02, max=1.0,
                              description="Altezza di un semitono sulla tavola",
                              update=_board_changed)
    seconds_width: FloatProperty(name="Larghezza secondo", default=1.0, min=0.1, max=10.0,
                                 description="Larghezza di un secondo sulla tavola",
                                 update=_board_changed)
    show_beats: BoolProperty(name="Mostra battiti", default=True, update=_board_changed)
    key_labels: EnumProperty(name="Etichette tasti", items=KEY_LABEL_ITEMS, default="C",
                             update=_board_changed)

    scale: EnumProperty(name="Scala", items=[(i, l, "") for i, l, _ in music.SCALES],
                        default="CHROMATIC", update=_sound_changed)
    root: EnumProperty(name="Tonica", items=[(n, n, "") for n in music.NOTE_NAMES],
                       default="C", update=_sound_changed)
    time_grid: EnumProperty(name="Quantizzazione ritmica",
                            items=[(i, l, "") for i, l, _ in music.TIME_GRIDS],
                            default="1_16", update=_sound_changed)
    swing: FloatProperty(name="Swing", default=0.0, min=0.0, max=0.5, subtype="FACTOR",
                         description="Ritarda le note sui contrattempi della griglia ritmica",
                         update=_sound_changed)
    use_modifiers: BoolProperty(name="Usa modificatori", default=False,
                                description="Legge i tratti dopo modificatori come Noise o "
                                "Array (dati valutati) invece dei tratti originali",
                                update=_sound_changed)
    min_note: FloatProperty(name="Nota minima (s)", default=0.06, min=0.0, max=1.0,
                            description="Pezzi di tratto più corti vengono assorbiti dalla "
                            "nota vicina", update=_sound_changed)
    master_volume: FloatProperty(name="Volume", default=0.9, min=0.0, max=2.0,
                                 subtype="FACTOR", update=_sound_changed)
    use_master: BoolProperty(name="Suono finito", default=True,
                             description="Ambiente, compressore, saturazione morbida e "
                             "limiter sul mix: il suono resta pieno, rotondo e non distorce "
                             "mai, qualunque cosa disegni", update=_sound_changed)
    ambience: FloatProperty(name="Ambiente", default=0.25, min=0.0, max=1.0,
                            subtype="FACTOR", description="Quanto si sente la sala comune "
                            "(un riverbero che lega tutti i livelli)", update=_sound_changed)
    room: EnumProperty(name="Ambiente del riverbero", items=ROOM_ITEMS, default="HALL",
                       description="La sala di tutti i riverberi della composizione (livelli, "
                       "strumenti e ambiente comune), come nella web app",
                       update=_sound_changed)
    loop: BoolProperty(name="Loop", default=True,
                       description="Le code (eco, riverbero, note lunghe) rientrano "
                       "dall'inizio del loop",
                       update=_sound_changed)
    use_sections: BoolProperty(name="Sezioni da keyframe", default=False,
                               description="Ogni keyframe del Grease Pencil apre una sezione: "
                               "il suo disegno si ripete in loop fino al keyframe successivo "
                               "(strofa, ritornello…). L'ultima sezione suona un loop",
                               update=_sound_changed)
    auto_update: BoolProperty(name="Aggiornamento automatico", default=True,
                              description="Rigenera il suono a ogni modifica dei tratti")
    sample_rate: EnumProperty(name="Frequenza", items=SAMPLE_RATES, default="44100",
                              update=_sound_changed)


def _instrument_items():
    """Every instrument, by family. The numbers are the instruments' places in
    ``synth.INSTRUMENTS``, so .blend files saved by older versions (where the list was
    shorter) keep their instruments."""
    number = {inst.ident: index for index, inst in enumerate(synth.INSTRUMENTS)}
    items, listed = [], set()
    for title, idents in INSTRUMENT_FAMILIES:
        items.append(("", title, ""))
        for ident in idents:
            inst = synth.INSTRUMENT_BY_ID[ident]
            items.append((ident, inst.label, inst.description, number[ident]))
            listed.add(ident)
    rest = [i for i in synth.INSTRUMENTS if i.ident not in listed]
    if rest:
        items.append(("", "Altri", ""))
        items += [(i.ident, i.label, i.description, number[i.ident]) for i in rest]
    return items


def _families():
    """(title, add-on idents): the synths, then the web app's recorded families."""
    from . import web_instruments
    synths = (
        ("Synth melodici", ("EPIANO", "ORGAN", "SINE", "TRIANGLE", "MARIMBA", "BELL", "PLUCK",
                            "STRINGS", "CHOIR", "PAD", "BRASS", "SAW", "SQUARE", "BASS")),
        ("Batteria synth", ("DRUM", "KICK", "SNARE", "CLAP", "HIHAT", "OPENHAT", "TOM", "RIM",
                            "SHAKER", "CRASH", "COWBELL")),
    )
    recorded = tuple(
        (title, tuple(synth.SAMPLED_PREFIX + w for w in ids
                      if synth.SAMPLED_PREFIX + w in synth.RECORDINGS))
        for title, ids in web_instruments.MELODIC_FAMILIES + web_instruments.DRUM_FAMILIES)
    return synths + tuple(f for f in recorded if f[1]) + (
        ("Suoni", ("SAMPLE", "LIBRARY")),)


INSTRUMENT_FAMILIES = _families()
INSTRUMENT_ITEMS = _instrument_items()


def _get_active_layer(gp_data):
    """Index of the active layer, so a UIList can show and set it."""
    active = gp_data.layers.active
    if active is None:
        return -1
    for index, layer in enumerate(gp_data.layers):
        if layer.name == active.name:
            return index
    return -1


def _set_active_layer(gp_data, index):
    layers = gp_data.layers
    if 0 <= index < len(layers):
        from .board import is_board_layer
        if not is_board_layer(layers[index]):
            layers.active = layers[index]

PLAY_MODES = (
    ("TOGETHER", "Tutte insieme", "Tutte le composizioni suonano contemporaneamente"),
    ("SOLO", "Solo l'attiva",
     "Suona solo la composizione attiva (quella su cui stai disegnando)"),
    ("SEQUENCE", "Una dopo l'altra",
     "Le composizioni suonano in fila, nell'ordine indicato da 'Ordine'"),
)


class GP2M_PlaySettings(bpy.types.PropertyGroup):
    """How the compositions of a scene are heard together."""

    mode: EnumProperty(name="Ascolto", items=PLAY_MODES, default="TOGETHER",
                       update=_arrangement_changed)
    fit_range: BoolProperty(name="Adatta l'intervallo della scena", default=True,
                            description="Inizio e fine della scena seguono le composizioni "
                            "(così il play va in loop)", update=_arrangement_changed)


TIMELINE_SOURCES = (
    ("EVERYTHING", "Tutto (audio + composizioni)",
     "Ogni suono della scena: le strip audio del Sequencer su qualsiasi canale, gli "
     "Speaker e le composizioni con le loro note"),
    ("ACTIVE", "Composizione attiva", "La composizione attiva (o tutte, se nessuna è attiva)"),
    ("ALL", "Tutte le composizioni", "Tutte le composizioni della scena, al loro posto"),
    ("PICK", "Una composizione", "Solo la composizione scelta qui sotto"),
    ("VSE_MIX", "Mix del Sequencer", "Somma di tutte le strip audio udibili del Sequencer"),
    ("VSE_CHANNEL", "Canale del Sequencer", "Solo le strip audio di un canale"),
    ("SPEAKERS", "Speaker", "I suoni degli oggetti Speaker (strip NLA)"),
)
WAVE_STYLES = (
    ("PEAKS", "Picchi", "Una barra verticale per ogni istante"),
    ("FILLED", "Pieno", "Forma d'onda piena e simmetrica"),
    ("OUTLINE", "Contorno", "Solo il bordo della forma d'onda"),
    ("RMS", "Inviluppo RMS", "Volume medio, più morbido dei picchi"),
    ("NONE", "Nessuna", "Nessuna forma d'onda"),
)


class GP2M_TimelineSettings(bpy.types.PropertyGroup):
    """What is drawn in the Timeline / Dope Sheet."""

    enabled: BoolProperty(name="Mostra suono nella Timeline", default=True,
                          update=_timeline_changed)
    source: EnumProperty(name="Sorgente", items=TIMELINE_SOURCES, default="EVERYTHING",
                         update=_timeline_changed)
    composition: PointerProperty(name="Composizione", type=bpy.types.Object,
                                 poll=_composition_poll, update=_timeline_changed)
    channel: IntProperty(name="Canale", default=1, min=1, max=128, update=_timeline_changed)
    wave_style: EnumProperty(name="Forma d'onda", items=WAVE_STYLES, default="PEAKS",
                             update=_timeline_changed)
    show_notes: BoolProperty(name="Note (MIDI)", default=True, update=_timeline_changed,
                             description="Blocchetti delle note, come un piano roll")
    show_optical: BoolProperty(name="Flusso ottico", default=True, update=_timeline_changed,
                               description="Curve di altezza dei tratti in lettura ottica")
    height: FloatProperty(name="Altezza", default=1.0, min=0.1, max=1.0, subtype="FACTOR",
                          update=_timeline_changed)
    opacity: FloatProperty(name="Opacità", default=0.8, min=0.05, max=1.0, subtype="FACTOR",
                           update=_timeline_changed)
    audio_color: FloatVectorProperty(name="Colore audio", subtype="COLOR", size=3, min=0.0,
                                     max=1.0, default=(1.0, 0.72, 0.38),
                                     update=_timeline_changed,
                                     description="Forma d'onda dell'audio che non è una "
                                     "composizione (Sequencer, Speaker)")
    wave_color: FloatVectorProperty(name="Colore composizioni", subtype="COLOR", size=3, min=0.0,
                                    max=1.0, default=(0.85, 0.9, 1.0),
                                    update=_timeline_changed)


classes = (GP2M_LayerSettings, GP2M_Effects, GP2M_CompositionSettings, GP2M_PlaySettings,
           GP2M_TimelineSettings)


def register_properties():
    bpy.types.Object.gp2m = PointerProperty(type=GP2M_CompositionSettings)
    bpy.types.Scene.gp2m_play = PointerProperty(type=GP2M_PlaySettings)
    bpy.types.Scene.gp2m_timeline = PointerProperty(type=GP2M_TimelineSettings)
    bpy.types.GreasePencil.gp2m_layers = CollectionProperty(type=GP2M_LayerSettings)
    bpy.types.GreasePencil.gp2m_layer_index = IntProperty(
        name="Livello attivo", get=_get_layer_index, set=_set_layer_index,
        options={"SKIP_SAVE"})
    bpy.types.Material.gp2m_instrument = EnumProperty(
        name="Strumento", items=INSTRUMENT_ITEMS, default=synth.DEFAULT_INSTRUMENT,
        update=_instrument_changed)
    bpy.types.Material.gp2m_fx = PointerProperty(type=GP2M_Effects)
    bpy.types.Material.gp2m_layer = StringProperty(
        name="Livello", description="Livello della composizione a cui appartiene lo strumento")
    bpy.types.Material.gp2m_sample = PointerProperty(
        name="Suono", type=bpy.types.Sound, update=_instrument_changed,
        description="Suono del campione (importato o già usato nel Sequencer)")
    bpy.types.Material.gp2m_sample_root = IntProperty(
        name="Nota del campione", default=60, min=0, max=127, update=_instrument_changed,
        description="Nota MIDI a cui il suono suona alla sua altezza originale (60 = C4)")
    bpy.types.Material.gp2m_sample_loop = BoolProperty(
        name="Loop", default=False, update=_instrument_changed,
        description="Ripete il suono finché dura il tratto")
    from . import samples
    bpy.types.Material.gp2m_library_path = StringProperty(
        name="File libreria", subtype="FILE_PATH", update=_instrument_changed,
        description="SoundFont (.sf2) o strumento SFZ (.sfz)")
    bpy.types.Material.gp2m_library_preset = EnumProperty(
        name="Preset", items=samples.preset_items, update=_instrument_changed,
        description="Strumento del SoundFont (banco:programma)")
    bpy.types.Material.gp2m_volume = FloatProperty(
        name="Volume", default=1.0, min=0.0, max=2.0, subtype="FACTOR",
        description="Volume di questo strumento", update=_instrument_changed)
    bpy.types.GreasePencil.gp2m_active_layer = IntProperty(
        name="Livello attivo", get=_get_active_layer, set=_set_active_layer)


def unregister_properties():
    del bpy.types.GreasePencil.gp2m_active_layer
    del bpy.types.Material.gp2m_volume
    del bpy.types.Material.gp2m_library_preset
    del bpy.types.Material.gp2m_library_path
    del bpy.types.Material.gp2m_sample_loop
    del bpy.types.Material.gp2m_sample_root
    del bpy.types.Material.gp2m_sample
    del bpy.types.Material.gp2m_fx
    del bpy.types.Material.gp2m_layer
    del bpy.types.Material.gp2m_instrument
    del bpy.types.GreasePencil.gp2m_layer_index
    del bpy.types.GreasePencil.gp2m_layers
    del bpy.types.Scene.gp2m_timeline
    del bpy.types.Scene.gp2m_play
    del bpy.types.Object.gp2m


def _get_layer_index(self):
    """Index in ``gp2m_layers`` of the active layer (for the UI list)."""
    active = self.layers.active
    if active is None:
        return -1
    for index, item in enumerate(self.gp2m_layers):
        if item.name == active.name:
            return index
    return -1


def _set_layer_index(self, value):
    if not 0 <= value < len(self.gp2m_layers):
        return
    from . import board, operators
    layer = self.layers.get(self.gp2m_layers[value].name)
    if layer is None or board.is_board_layer(layer):
        return
    for obj in bpy.data.objects:
        if obj.data == self and obj.gp2m.is_composition:
            operators.use_instrument(obj, layer.name)
            return
    self.layers.active = layer


def find_layer_settings(gp_data, layer_name):
    for item in gp_data.gp2m_layers:
        if item.name == layer_name:
            return item
    return None


def ensure_layer_settings(gp_data):
    """Add settings for new layers (writes only when something is missing)."""
    from .board import is_board_layer
    layer_names = [layer.name for layer in gp_data.layers if not is_board_layer(layer)]
    existing = {item.name for item in gp_data.gp2m_layers}
    missing = [name for name in layer_names if name not in existing]
    if not missing:
        return
    orphans = [item for item in gp_data.gp2m_layers if item.name not in layer_names]
    if len(missing) == 1 and len(orphans) == 1:
        # Most likely a renamed layer: keep its settings and its instruments.
        old = orphans[0].name
        orphans[0].name = missing[0]
        for material in gp_data.materials:
            if material is not None and getattr(material, "gp2m_layer", "") == old:
                material.gp2m_layer = missing[0]
        return
    for name in missing:
        gp_data.gp2m_layers.add().name = name
    if any(item.solo for item in gp_data.gp2m_layers):
        apply_solo(gp_data)  # a new layer joins the dimmed ones
