# Grease Pencil to Music

Add-on per **Blender 5.2** che trasforma i disegni Grease Pencil in musica.
Si ispira al *suono disegnato* di Norman McLaren e Daphne Oram (Oramics): si
disegna su una tavola, e la tavola suona.

![La tavola musicale](docs/tavola.png)

- **X = tempo** (linee verticali = secondi, più tenui i battiti)
- **Z = altezza** (una riga per semitono, pianoforte verticale a sinistra, linee arancioni sui Do)
- **Materiale = strumento**
- **Spessore, opacità, vertex color, morbidezza** modellano il suono (configurabile)

> Stato: **0.0.x, prototipo**. Pacchetto solo per Windows x64 per ora.

## Installazione

1. Scarica `grease_pencil_to_music-<versione>-windows_x64.zip`.
2. In Blender: *Edit → Preferences → Get Extensions → ▾ (in alto a destra) → Install from Disk…*
3. Scegli lo zip. L'add-on si attiva da solo.

## Uso

1. Nel viewport 3D: **Shift+A → Grease Pencil to Music → Composizione Musicale**.
   Viene creata la tavola nel piano X-Z (vista frontale), un oggetto
   *Composizione Musicale 1* con tre livelli e otto materiali-strumento, e si entra in **Draw Mode**.
2. Disegna. Appena stacchi la penna il suono viene rigenerato (dopo ~0,35 s).
3. Premi **Spazio**: la testina rossa scorre e senti il disegno, in loop.
4. Modifica pure in **Edit Mode** o **Sculpt Mode** (sposta, appiattisci, cambia
   spessore o materiale): il suono si aggiorna.

Tutto si controlla dalla barra laterale **N → Musica**:

| Pannello | Cosa contiene |
|---|---|
| Grease Pencil to Music | stato, avvisi, *Auto* (aggiornamento automatico), *Genera suono* |
| Tavola e tempo | BPM, durata del loop, nota più bassa, ottave, dimensioni della griglia |
| Lettura | scala e tonica, quantizzazione ritmica, nota minima, volume |
| Strumenti | un materiale per riga: clic sul nome = disegna con quello; strumento; **occhio = nascosto e muto** |
| Livelli | occhio = nascosto e muto; lettura **Quantizzata** o **Ottica**; volume (opacità del livello); eco, riverbero, lo-fi |
| Esporta | **WAV**, **MP3**, **MIDI** |

### Come viene letto un tratto

- **Quantizzata**: il tratto cambia nota ogni volta che attraversa una riga.
  Le note vengono agganciate alla scala scelta e alla griglia ritmica.
- **Ottica (libera)**: alla McLaren, l'altezza segue la linea in modo continuo, con glissandi.
- Un punto (un tocco) è una nota breve. Tratti disegnati da destra a sinistra
  valgono come da sinistra a destra; i pezzi che "tornano indietro" nel tempo vengono ignorati.

### Strumenti (sintetizzati)

Flauto, Ocarina, 8-bit, Synth, Archi, Chitarra (Karplus-Strong), Campana (FM),
Percussioni (rumore filtrato: in basso cassa, in alto charleston).
Ogni materiale Grease Pencil può diventare uno strumento dal pannello *Strumenti*.

### Attributi del tratto (Preferences dell'add-on)

| Attributo | Opzioni (default in grassetto) |
|---|---|
| Spessore | **Volume + Vibrato**, Volume, Vibrato, Brillantezza, Nessuno |
| Opacità | **Brillantezza**, Volume, Nessuno |
| Vertex color | **Nessuno**, Pan stereo (rosso = sinistra, blu = destra), Brillantezza |
| Morbidezza | **Attacco**, Nessuno |

*Volume + Vibrato* separa lo spessore in due: l'andamento lento è il volume
(crescendo e diminuendo con la pressione della penna), l'irregolarità veloce
(per esempio il jitter del pennello Ink) diventa vibrato.

## Limiti noti (0.0.x)

- Modificatori ed effetti Grease Pencil **non** cambiano il suono (compare un avviso).
- Viene letto solo il keyframe Grease Pencil attivo all'inizio della scena.
- I riempimenti non sono ancora interpretati (in arrivo: cluster sonori).
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

GPL-3.0-or-later.
