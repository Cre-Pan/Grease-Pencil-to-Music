# Grease Pencil to Music

Add-on per **Blender 5.2** che trasforma i disegni Grease Pencil in musica.
Si ispira al *suono disegnato* di Norman McLaren e Daphne Oram (Oramics): si
disegna su una tavola, e la tavola suona.

![La tavola musicale](docs/tavola.png)

- **X = tempo** (linee verticali = secondi, più tenui i battiti)
- **Z = altezza** (una riga per semitono, tastiera verticale a sinistra con i tasti alti quanto le righe)
- **Materiale = strumento**, con volume per strumento
- **Spessore, opacità, vertex color, morbidezza** modellano il suono (configurabile)
- **Forme piene = cluster** (note della scala coperte dalla forma, oppure banda di rumore)

> Stato: **0.0.x, prototipo**. Pacchetto solo per Windows x64 per ora.

## Installazione

1. Scarica `grease_pencil_to_music-<versione>-windows_x64.zip`.
2. In Blender: *Edit → Preferences → Get Extensions → ▾ (in alto a destra) → Install from Disk…*
3. Scegli lo zip. L'add-on si attiva da solo (un aggiornamento sostituisce la versione precedente).

## Uso

1. Nel viewport 3D: **Shift+A → Grease Pencil to Music → Composizione Musicale**.
   Viene creato **un unico oggetto** *Composizione Musicale 1*: la tavola (tastiera,
   griglia, etichette e testina) sta in gruppi di livelli bloccati dentro l'oggetto stesso,
   insieme a tre livelli di disegno e ai materiali-strumento. La vista passa a
   frontale, *Solid → Texture*, e si entra in **Draw Mode**.
2. Disegna. Appena stacchi la penna il suono viene rigenerato.
3. Premi **Spazio**: la testina rossa scorre e senti il disegno, in loop.
   Nella **Timeline** vedi la forma d'onda e i blocchetti delle note.
4. Modifica in **Edit Mode** o **Sculpt Mode**: il suono si aggiorna.
5. **Shift+D** duplica tutta la composizione: ogni copia è un nuovo "piano di lavoro"
   con il suo suono (tasto muto nel pannello per ascoltarne una sola).

Tutto si controlla dalla barra laterale **N → Musica**:

| Pannello | Cosa contiene |
|---|---|
| Grease Pencil to Music | stato, muto, avvisi, *Auto* (aggiornamento automatico), *Genera suono* |
| Tavola e tempo | BPM, durata del loop, nota più bassa, ottave, **etichette dei tasti** (solo Do, tasti bianchi, tutte, nessuna), griglia |
| Lettura | scala e tonica, quantizzazione ritmica, **swing**, nota minima, volume, **Usa modificatori** |
| Strumenti | lista con **+ / −**: colore, nome, **volume**, occhio = nascosto e muto; sotto, il tipo di strumento |
| Livelli | lista con **+ / − / ↑ / ↓**: lettura *Quantizzata* o *Ottica*, occhio = nascosto e muto; per il livello attivo volume, forme piene, eco, riverbero, lo-fi |
| Esporta | **WAV**, **MP3**, **MIDI** |

### Come viene letto un tratto

- **Quantizzata**: il tratto cambia nota ogni volta che attraversa una riga.
  Le note vengono agganciate alla scala scelta e alla griglia ritmica (con swing).
- **Ottica (libera)**: alla McLaren, l'altezza segue la linea in modo continuo, con glissandi.
- **Forma piena** (tratto riempito): *Cluster tonale* suona tutte le note della scala che
  copre; *Banda di rumore* è rumore filtrato tra il bordo inferiore e superiore della forma
  (come il sintetizzatore ANS).
- Un punto (un tocco) è una nota breve; le percussioni suonano sempre un colpo solo.

### Strumenti (sintetizzati)

Melodici: Flauto, Ocarina, 8-bit, Synth, Archi, Chitarra (Karplus-Strong), Campana (FM).
Percussioni: Percussioni (generiche, dipendono dalla riga), Cassa, Rullante, Charleston,
Piatto, Battimani, Tom (intonato sulla riga), Campanaccio. Nel MIDI le percussioni usano
le note General MIDI della batteria.

### Preferences dell'add-on

| Voce | Opzioni (default in grassetto) |
|---|---|
| Nomi delle note | **C D E F G A B**, Do Re Mi Fa Sol La Si |
| Nella Timeline | **Onda + note**, Forma d'onda, Note, Nessuno |
| Riprendi il play dopo Ctrl+Z | **sì** |
| Spessore | **Volume**, Volume + Vibrato, Vibrato, Brillantezza, Nessuno |
| Opacità | **Brillantezza**, Volume, Nessuno |
| Vertex color | **Nessuno**, Pan stereo (rosso = sinistra, blu = destra), Brillantezza |
| Morbidezza | **Attacco**, Nessuno |

*Volume + Vibrato* separa lo spessore in due: l'andamento lento è il volume,
l'irregolarità veloce (per esempio il jitter del pennello Ink) diventa vibrato.

## Limiti noti (0.0.x)

- Viene letto solo il keyframe Grease Pencil attivo all'inizio della scena.
- Con *Usa modificatori* vengono letti i tratti del frame corrente.
- Gli effetti visivi (shader effects) non cambiano il suono.
- La Chitarra non fa glissandi in modalità ottica.

## Sviluppo

I test usano Blender come modulo Python (`bpy` da PyPI):

```bash
python -m venv .venv
.venv/bin/pip install bpy==5.2.2 pytest
.venv/bin/python -m pytest
python tools/build_zip.py          # -> dist/grease_pencil_to_music-<versione>-windows_x64.zip
```

Vedi [DESIGN.md](DESIGN.md) per decisioni e roadmap, [CHANGELOG.md](CHANGELOG.md) per le versioni.

## Licenza

GPL-3.0-or-later. La visualizzazione nella Timeline si ispira a
[Timeline Audio Visualizer](https://github.com/OwOpq/timeline-audio-visualizer) (GPL-3.0).
