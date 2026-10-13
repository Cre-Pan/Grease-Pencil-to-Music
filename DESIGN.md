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
| Uscite | strip nel Video Sequencer (Play in Blender), export WAV, MP3, MIDI, overlay nella Timeline |
| Oggetto | un solo oggetto per composizione: la tavola è fatta di livelli bloccati dentro di esso |
| Indipendenza | ogni composizione ha dati e materiali-strumento propri (anche dopo Shift+D / Alt+D) |
| Ascolto | per scena: tutte insieme, solo l'attiva, una dopo l'altra (strip spostate, testina con offset) |
| Scala oggetto | X = durata del loop, Z = ottave; la scala torna a 1 a fine trasformazione |
| Edit / Sculpt Mode | qualsiasi modifica ai tratti rigenera il suono |
| Modificatori GP | ignorati per default (avviso), letti con "Usa modificatori"; gli effetti visivi non suonano |
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
board.py       tavola, tastiera, etichette, testina come livelli della composizione  [bpy]
glyphs.py      font a tratto singolo per le etichette                     [puro]
timeline.py    suono nella Timeline: sorgenti, stili, note, flusso ottico;
               pulsante nell'header del Dope Sheet (draw handler POST_PIXEL)  [bpy]
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
  (la rinomina di un livello viene riconosciuta);
- i livelli nuovi nascono sempre in cima e `layers.move` salta un gruppo intero:
  dopo ogni aggiunta il gruppo della testina torna in cima;
- la testina è un livello la cui `translation` è pilotata da un driver sui dati GP;
- l'icona dell'occhio di `hide` cambia da sola: non va passata un'icona esplicita;
- lo scrittore WAV di FFmpeg in Blender fallisce a 48 kHz su certe lunghezze
  ("filling the audio frame failed"): i WAV si scrivono con il modulo `wave`;
- i modificatori GP hanno un filtro per pass index del livello: la tavola usa il pass 77
  e ogni modificatore lo esclude;
- `Window.modal_operators` dice se uno Scala è ancora in corso: la scala dell'oggetto
  viene convertita in durata/ottave solo a trasformazione finita;
- `SoundStrip.content_start` sposta una strip senza tagliarla (`frame_start` è deprecato);
- cambiare `Sound.filepath` ricarica l'audio senza ricreare la strip (ma la durata
  della strip non si aggiorna: se cambia la lunghezza del loop la strip viene ricreata).

## Roadmap

- ~~Cluster~~ (0.0.2), ~~Usa modificatori~~ (0.0.2), ~~Swing~~ (0.0.2).
- ~~Import MIDI, Campione, effetti per strumento, tastiera del PC, UI nelle Proprietà~~ (0.0.4).
- Ingresso da tastiere MIDI esterne (richiede una libreria esterna, es. python-rtmidi).
- **Keyframe come pattern**: i keyframe GP diventano sezioni del brano.
- **Riproduzione del gesto** (`delta_time`), più testine, canone.
- Preset di mappatura, pennelli-asset per strumento.
- Altre piattaforme (Linux, macOS).
