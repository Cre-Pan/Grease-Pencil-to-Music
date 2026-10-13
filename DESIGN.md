# Design

Documento di riferimento: decisioni prese e strada da fare.

## Idea

Disegnare il suono come McLaren (*Synchromy*, *Dots*) e Daphne Oram (Oramics),
dentro Blender, con la Grease Pencil al posto della pellicola. Riferimento
contemporaneo: *play_music_theory* di Tala Schlossberg (X = tempo, Y = altezza,
colore = voce).

## Decisioni

| Tema | Decisione |
|---|---|
| Blender | 5.2 (Grease Pencil v3), poi 5.3 |
| Distribuzione | Extension zip, solo Windows x64 per le 0.0.x |
| Piano di disegno | X-Z ("il muro"), vista frontale |
| Tempo | X; linee verticali ai secondi, battiti più tenui |
| Altezza | Z; una riga per semitono, bande scure sui tasti neri, Do evidenziati |
| Lettura | per livello: **Quantizzata** o **Ottica** |
| Strumento | dal **materiale** (livello e materiale sono indipendenti) |
| Mute | materiale o livello nascosto = non si vede e non si sente (anche negli export) |
| Spessore / opacità / vertex color / morbidezza | mappatura scelta nelle Preferences, da menu con opzioni limitate |
| Strumenti | solo sintetizzati (niente campioni realistici per ora) |
| Effetti | per livello: eco (ping-pong), riverbero (convoluzione), lo-fi |
| Uscite | strip nel Video Sequencer (Play in Blender), export WAV, MP3, MIDI |
| Edit / Sculpt Mode | qualsiasi modifica ai tratti rigenera il suono |
| Modificatori ed effetti GP | ignorati, con avviso (popup e pannello) |
| Dipendenze | nessuna: NumPy e `aud` sono già in Blender (anche l'MP3) |

## Architettura

```
reader.py      Grease Pencil  →  StrokeData (NumPy)           [bpy]
interpret.py   StrokeData     →  Voice + MidiNote              [puro]
synth.py       Voice          →  buffer stereo                 [puro]
effects.py     buffer livello →  eco / riverbero / lo-fi       [puro]
mixer.py       livelli        →  loop stereo (+ cache per tratto e per livello)  [puro]
midi.py        MidiNote       →  file .mid                     [puro]
engine.py      render → WAV in cartella temporanea → strip nel VSE; export  [bpy]
handlers.py    depsgraph / undo / load → rigenerazione con debounce        [bpy]
board.py       tavola, pianoforte, etichette, testina (driver sul frame)   [bpy]
props.py prefs.py operators.py ui.py                                       [bpy]
```

I moduli "puri" non importano `bpy` e sono testati direttamente; i test
d'integrazione installano lo zip in Blender 5.2 (`bpy` da PyPI) ed eseguono il
flusso completo.

Note tecniche su Blender 5.2 emerse durante lo sviluppo:

- dopo aver scritto posizioni via Python serve `drawing.tag_positions_changed()`,
  altrimenti il disegno ha limiti vuoti e non viene mostrato;
- il riempimento è per tratto (`fill_id`, `hide_stroke`), `show_fill` del materiale è deprecato;
- i livelli hanno `use_lights = False` per avere colori piatti;
- le proprietà personalizzate non si possono agganciare ai livelli GP: le
  impostazioni di livello stanno in una collection sui dati GP, per nome
  (la rinomina di un livello viene riconosciuta).

## Roadmap

- **0.0.x**: stabilizzazione dopo le prove su Windows; feedback su interfaccia e suoni.
- **Cluster**: una forma piena diventa una banda sonora (alla ANS): rumore filtrato
  tra il bordo inferiore e superiore, oppure cluster tonale delle note coperte.
- **Modificatori**: opzione "Usa modificatori" (lettura dei dati valutati; con
  l'Array le ripetizioni suonano automaticamente).
- **Keyframe come pattern**: i keyframe GP diventano sezioni del brano.
- **Riproduzione del gesto** (`delta_time`), più testine, canone.
- Swing, preset di mappatura, pennelli-asset per strumento.
- Altre piattaforme (Linux, macOS).
