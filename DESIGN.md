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
| Lettura | per livello: **Quantizzata**, **Ottica**, **Legato** o **Gesto** (tempo del disegno) |
| Strumento | dal **materiale**; ogni strumento appartiene a un livello (UI unica livelli → strumenti) |
| Mute | materiale o livello nascosto = non si vede e non si sente (anche negli export) |
| Spessore / opacità / vertex color / morbidezza | mappatura scelta nelle Preferences, da menu con opzioni limitate |
| Strumenti | sintetizzati, più "Campione" (un suono) e "Libreria" (SoundFont .sf2 / .sfz, non incluse) |
| Effetti | per livello e per strumento: eco (ping-pong), riverbero (convoluzione), lo-fi; canone per livello |
| Uscite | strip nel Video Sequencer (Play in Blender), export WAV, MP3, MIDI, overlay nella Timeline |
| Oggetto | un solo oggetto per composizione: la tavola è fatta di livelli bloccati dentro di esso |
| Indipendenza | ogni composizione ha dati e materiali-strumento propri (anche dopo Shift+D / Alt+D) |
| Ascolto | per scena: tutte insieme, solo l'attiva, una dopo l'altra (strip spostate, testina con offset) |
| Scala oggetto | X = durata del loop, Z = ottave; la scala torna a 1 a fine trasformazione |
| Edit / Sculpt Mode | qualsiasi modifica ai tratti rigenera il suono |
| Modificatori GP | ignorati per default (avviso), letti con "Usa modificatori"; gli effetti visivi non suonano |
| Dipendenze | NumPy e `aud` di Blender; unica wheel inclusa: `rtmidi2` (MIT) per le tastiere MIDI |
| Nuova composizione | vuota, un livello e uno strumento (Preferences per cambiare) |
| Forma del brano | facoltativa: ogni keyframe GP apre una sezione che ripete il suo loop fino al keyframe dopo |

## Architettura

```
reader.py      Grease Pencil  →  StrokeData (NumPy)           [bpy]
interpret.py   StrokeData     →  Voice + MidiNote              [puro]
synth.py       Voice          →  buffer stereo                 [puro]
effects.py     buffer livello →  eco / riverbero / lo-fi       [puro]
mixer.py       livelli        →  loop stereo (+ cache per tratto e per livello),
               canone, sezioni da keyframe affiancate             [puro]
midi.py        MidiNote       ↔  file .mid (scrittura e lettura) [puro]
libraries.py   .sf2 / .sfz    →  zone campionate (Zone)        [puro]
midi_input.py  tastiera MIDI  →  eventi nota (rtmidi2, letto dal thread principale)
engine.py      render → WAV in cartella temporanea → strip nel VSE; export  [bpy]
handlers.py    depsgraph / undo / load → rigenerazione con debounce        [bpy]
board.py       tavola, tastiera, etichette, testina come livelli della composizione  [bpy]
glyphs.py      font a tratto singolo per le etichette                     [puro]
timeline.py    suono nella Timeline: sorgenti, stili, note, flusso ottico;
               pulsante nell'header del Dope Sheet (draw handler POST_PIXEL)  [bpy]
keyboard.py    suonare e registrare con tastiera del PC o MIDI               [bpy]
midi_import.py file .mid → tratti Grease Pencil                           [bpy]
props.py prefs.py operators.py ui.py samples.py feedback.py                 [bpy]
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
- le espressioni "semplici" dei driver accettano `fmod` e `a if c else b` (non `%`):
  la testina delle sezioni da keyframe usa solo queste, così funziona anche con
  l'esecuzione automatica di Python disattivata;
- il tempo di disegno di ogni punto è l'attributo `delta_time` (secondi dall'inizio del
  tratto); i tratti creati da script non lo hanno;
- `SoundStrip.content_start` sposta una strip senza tagliarla (`frame_start` è deprecato);
- cambiare `Sound.filepath` ricarica l'audio senza ricreare la strip (ma la durata
  della strip non si aggiorna: se cambia la lunghezza del loop la strip viene ricreata).

## Roadmap

- ~~Cluster~~ (0.0.2), ~~Usa modificatori~~ (0.0.2), ~~Swing~~ (0.0.2).
- ~~Import MIDI, Campione, effetti per strumento, tastiera del PC, UI nelle Proprietà~~ (0.0.4).
- ~~Tastiere MIDI, librerie SF2/SFZ, sezioni da keyframe, lettura Gesto, canone, preset di
  mappatura~~ (0.0.5).
- Uscita MIDI in tempo reale verso sintetizzatori esterni / DAW.
- Più testine (letture a velocità diverse dello stesso disegno).
- Pennelli-asset per strumento.
- Marker della Timeline come cambi di BPM o di scala.
- Altre piattaforme (Linux, macOS).

### Web app

- ~~Pennelli con effetto sul suono, lazo, beat A/B, sezione Onda~~.
- ~~Video in una finestra mobile sincronizzata col play~~. Prossimo passo: esportare il video
  con la musica disegnata (MediaRecorder) e scegliere da quale secondo del video parte il loop.
- Onda che cambia nel tempo (più cicli disegnati, interpolati lungo la nota).
- Pennelli importati da librerie libere (MyPaint, CC0).

Le fonti delle ricerche sono in [RESEARCH.md](RESEARCH.md).
