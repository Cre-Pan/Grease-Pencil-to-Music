# SPDX-License-Identifier: GPL-3.0-or-later
"""The "?" buttons: what each part does, like the web app's help.

The panels stay free of fixed explanations (as in the web app): hovering a
control shows its tooltip, the "?" in a panel header opens the whole story.
Written in Markdown and shown with ``UILayout.label_markdown`` (Blender 5.3).
"""

import bpy

HELP = {
    "MAIN": """\
## Doodle Music

Disegna sulla tavola e ascolta: **X è il tempo**, **Z è l'altezza** (una riga per
semitono), il **materiale è lo strumento**.

- *Shift+A → Doodle Music* crea una composizione (anche da un file MIDI).
- Disegna in **Draw Mode**: ogni tratto rigenera il suono e lo mette nel Sequencer.
- **Spessore** = volume, **opacità** = brillantezza, **morbidezza** = attacco
  (si cambia nelle Preferences dell'add-on).
- Un livello nascosto non si vede e non si sente.
- *Suona con la tastiera*: la tastiera del PC o una tastiera MIDI suonano lo
  strumento attivo; **R** registra mentre la scena è in play.

Altre impostazioni in *Proprietà → Dati oggetto* (tavola, lettura, livelli) e
*Materiale* (strumento, campione, effetti).

**Con la web app**: *File → Importa / Esporta → Progetto Doodle Music web (.json)*
porta lo stesso disegno tra l'iPad e Blender.
""",
    "READING": """\
## Le cinque letture

Ogni livello ha la sua lettura, con le stesse lettere della web app:

- **Q · Quantizzata**: cambia nota a ogni riga, agganciata a scala e griglia.
- **QL · Quantizzata legata**: le note della scala scivolano l'una nell'altra.
- **O · Ottica**: alla McLaren, l'altezza segue la linea con glissandi.
- **OL · Ottica legata**: come Ottica, ma i tratti vicini diventano una voce sola.
- **G · Gesto**: il ritmo è quello della mano (tempo del disegno).

Le **forme piene** suonano tutte le note che coprono (*Cluster tonale*) oppure
rumore filtrato tra il bordo sotto e sopra (*Banda di rumore*). Un tratto chiuso
con l'opzione **Ciclico** degli strumenti di disegno di Blender 5.3 torna al primo
punto e suona anche il ritorno.

Il **canone** ripete il livello in 2–4 voci che entrano una dopo l'altra.
""",
    "INSTRUMENT": """\
## Strumenti

Lo strumento è il **materiale** del tratto: ogni livello ha i suoi.

- **Sintetizzati**: flauto, ocarina, 8-bit, synth, archi, chitarra, campana e
  le percussioni (cassa, rullante, charleston, piatto…).
- **Campione**: un suono di Blender, intonato sulla *Nota del campione*.
  I suoni registrati nella web app arrivano così.
- **Libreria**: un SoundFont (`.sf2`) o uno strumento SFZ (`.sfz`).
  Librerie libere: *GeneralUser GS*, *FluidR3* (SF2), *Versilian VCSL* (SFZ, CC0).

Gli **effetti dello strumento** (eco, riverbero, lo-fi) si sommano a quelli del
livello.
""",
    "EXPORT": """\
## Esporta

- **WAV / MP3**: il suono della composizione (il loop, o tutte le sezioni).
- **MIDI**: una traccia per livello e strumento; le percussioni usano le note
  General MIDI della batteria.
- **Web app (.json)**: il progetto da aprire sull'iPad con *File → Apri*: livelli,
  letture, tratti, forme piene e i campioni.
- *Mix di tutta la scena* mette insieme ogni composizione e l'audio del Sequencer.
""",
}


def _help_panel(key, space="PROPERTIES"):
    class Panel(bpy.types.Panel):
        bl_space_type = space
        bl_region_type = "HEADER"
        bl_label = "Aiuto"
        bl_ui_units_x = 20

        def draw(self, _context):
            self.layout.label_markdown(text=HELP[key])

    Panel.__name__ = f"GP2M_PT_help_{key.lower()}"
    Panel.bl_idname = Panel.__name__
    return Panel


GP2M_PT_help_main = _help_panel("MAIN")
GP2M_PT_help_reading = _help_panel("READING")
GP2M_PT_help_instrument = _help_panel("INSTRUMENT")
GP2M_PT_help_export = _help_panel("EXPORT")


def button(layout, key):
    """The "?" button that opens the help ``key`` (for a panel's ``draw_header_preset``)."""
    layout.popover(panel=f"GP2M_PT_help_{key.lower()}", text="", icon="QUESTION")


classes = (GP2M_PT_help_main, GP2M_PT_help_reading, GP2M_PT_help_instrument,
           GP2M_PT_help_export)
