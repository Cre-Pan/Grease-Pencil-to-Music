# Ricerca

Appunti delle ricerche fatte per Grease Pencil to Music: progetti simili, librerie di
strumenti, librerie Python e idee. Ogni scelta del progetto qui sotto rimanda alla sua
fonte.

## Suono disegnato: da dove viene l'idea

- **Norman McLaren** e il suono ottico disegnato a mano: la colonna sonora è un disegno
  letto da una testina ottica. Da qui vengono la *lettura ottica* (altezza continua,
  glissandi) e il preset di mappatura *McLaren* (quantità di inchiostro = volume).
- **Daphne Oram, Oramics**: forme disegnate su pellicola che controllano altezza, volume e
  timbro.
  [Oramics ricreato in software](https://www.synthtopia.com/content/2011/08/02/daphne-oram%e2%80%99s-oramics-machine-recreated-in-software/),
  [app Oramics](https://www.synthtopia.com/content/2011/08/09/oramics-app-recreates-pioneering-synth-of-daphne-oram-for-ios/),
  [The Daphne Oram Browser](https://pkmital.com/home/works/the-daphne-oram-browser/).
- **Sintetizzatore ANS** e convertitori immagine→suono (Coagula, pic2wav, img2sound):
  una forma piena è una banda di frequenze. Da qui viene la modalità *Banda di rumore*
  delle forme piene.
  [Coagula](https://alternativeto.net/software/coagula/about/),
  [pic2wav](https://github.com/unreal79/pic2wav),
  [img2sound](https://github.com/xirtus/img2sound),
  [spectrographic](https://pypi.org/project/spectrographic/0.9.1).

## Pennelli e onde disegnate (web app)

- **perfect-freehand** (MIT): tratti a spessore variabile dalla pressione. La forma dei tratti
  della web app segue la stessa idea (contorno costruito dai punti con raggio), scritta da zero.
  [repository](https://github.com/steveruizok/perfect-freehand).
- **Blender Grease Pencil, Ink Rough / Randomize**: rumore su posizione, spessore e forza
  lungo il tratto. Da qui il pennello *Inchiostro ruvido* e la sua Ruvidezza.
  [BrushGpencilSettings](https://docs.blender.org/api/current/bpy.types.BrushGpencilSettings.html).
- **MyPaint brushes**: libreria di pennelli con licenza CC0, utile per pennelli futuri.
  [mypaint-brushes](https://github.com/mypaint/mypaint-brushes).
- **Norman McLaren**, suono disegnato sulla colonna ottica: la sezione *Onda* disegna il bordo
  della forma come onda sonora (sopra = sinistra, sotto = destra).
  [Synchromy (NFB)](https://www.nfb.ca/film/synchromy/),
  [Pen Point Percussion (NFB)](https://www.nfb.ca/film/pen_point_percussion/).

## Strumenti per disegnare o sonificare

- **play_music_theory**: la tavola a righe, una per semitono, con tastiera verticale.
  [playmusictheory.net](https://playmusictheory.net/play),
  [repository](https://github.com/BeiXiao/play-music-theory).
- **Chrome Music Lab** (Song Maker, Kandinsky): disegno = musica per tutti, con griglia
  semplice e strumenti scelti col colore.
  [experiments.withgoogle.com/music-lab](https://experiments.withgoogle.com/music-lab),
  [annuncio](https://developers.googleblog.com/en/introducing-chrome-music-lab/).
- **Soundsketcher**: rappresentazione grafica del suono basata sulle corrispondenze
  crossmodali (alto = acuto, spesso = forte, chiaro = brillante). Queste corrispondenze
  sono quelle della mappatura predefinita.
  [articolo](https://www.researchgate.net/publication/393703481_SOUNDSKETCHER_GRAPHICAL_REPRESENTATION_OF_SOUND_BASED_ON_CROSSMODAL_AUDIOVISUAL_CORRESPONDENCES).
- **Sonificazione**: [strauss](https://github.com/james-trayford/strauss),
  [KubikMilk](https://kubikmilk.com/sonification.html),
  [sonification.design](https://sonification.design/),
  [Highcharts Sonification Studio](https://www.researchgate.net/publication/359407302_Highcharts_Sonification_Studio_An_Online_Open-Source_Extensible_and_Accessible_Data_Sonification_Tool).
  Da qui vengono il pan stereo dal colore e i preset di mappatura.
- **Sketch → musica**:
  [sketch in stile Minecraft](https://80.lv/articles/this-website-turns-your-sketches-into-minecraft-like-music).

## Add-on di Blender vicini

| Add-on | Cosa fa | Cosa ne abbiamo preso |
|---|---|---|
| [timeline-audio-visualizer](https://github.com/OwOpq/timeline-audio-visualizer) | Forma d'onda disegnata nella Timeline | Il controller "nota musicale" nella Timeline (draw handler POST_PIXEL) |
| [SimpleMIDI](https://extensions.blender.org/add-ons/simplemidi/) | Ingresso MIDI in Blender | La conferma che una tastiera MIDI in un'estensione funziona con una wheel |
| [MidiController](https://extensions.blender.org/add-ons/midicontroller/) | Controller MIDI → proprietà | Idem; per il MIDI usiamo rtmidi2 (vedi sotto) |
| [Audionodes](https://github.com/nomelif/Audionodes) | Sintesi a nodi dentro Blender | La conferma che la sintesi in Python/NumPy dentro Blender è praticabile |
| Visualizzatori MIDI ([PianoFlare](https://superhivemarket.com/products/pianoflare/docs), [RecorderFlare](https://superhivemarket.com/products/recorderflare--midi-recorder-visualizer-for-blender), [MIDI PianoMotion](https://superhivemarket.com/products/midi-pianomotion-tools)) | MIDI → animazione | Fanno il contrario di noi (dal suono all'immagine); utili per l'import MIDI |

Nessun add-on trovato fa quello che fa questo: disegnare con Grease Pencil e ottenere
suono.

## Librerie di strumenti (campioni)

Lo strumento **Libreria** legge SoundFont 2 (`.sf2`) e SFZ (`.sfz`) con un lettore
scritto apposta (`libraries.py`, in puro Python + NumPy).

| Libreria | Formato | Licenza | Note |
|---|---|---|---|
| [VCSL, Versilian Community Sample Library](https://github.com/sgossner/VCSL) ([sito](https://versilian-studios.com/vcsl/)) | SFZ + WAV | CC0 (pubblico dominio) | Strumenti acustici registrati |
| [GeneralUser GS](https://github.com/mrbumpy409/GeneralUser-GS/blob/main/documentation/README.md) | SF2 | Libera (vedi README della libreria) | Set General MIDI completo |
| FluidR3 GM ([licenza](https://github.com/musescore/MuseScore/blob/master/share/sound/FluidR3Mono_License.md), [FreshPorts](https://www.freshports.org/audio/fluid-soundfont)) | SF2 | MIT | Il SoundFont di MuseScore |

Le librerie non sono incluse nello zip, perché sono troppo grandi. Si scaricano e si
sceglie il file nella scheda Materiale.

## Librerie Python valutate

Blender 5.2 usa Python 3.13. Un'estensione può includere wheel binarie
([manuale: Python wheels](https://docs.blender.org/manual/uk/5.0/advanced/extensions/python_wheels.html)),
ma servono wheel `cp313` per Windows x64.

| Libreria | Uso | Decisione |
|---|---|---|
| [rtmidi2](https://rtmidi2.readthedocs.io) | Tastiere MIDI (ingresso) | **Inclusa**: wheel cp313 win_amd64, licenza MIT. Il port viene letto dal thread principale |
| [python-rtmidi](https://pypi.python.org/pypi/python-rtmidi) | Tastiere MIDI | Scartata: nessuna wheel cp313 per Windows al momento della ricerca |
| [tinysoundfont](https://pypi.org/project/tinysoundfont/0.2.0) / [TinySoundFont](https://github.com/schellingb/TinySoundFont) | Lettura SF2 | Scartata: nessuna wheel cp313 per Windows. Il formato è stato reimplementato in `libraries.py` |
| [pyFluidSynth](https://pypi.org/project/pyFluidSynth) | Sintesi SF2 | Scartata: richiede la DLL nativa di FluidSynth |
| [mido](https://github.com/mido/mido), [MIDIUtil](https://midiutil.readthedocs.io/) | File MIDI | Non necessarie: lettura e scrittura MIDI in `midi.py` (formato semplice) |
| [pedalboard](https://engineering.atspotify.com/introducing-pedalboard-spotifys-audio-effects-library-for-python/) | Effetti audio | Non necessaria: eco, riverbero e lo-fi in NumPy |
| [PySynth](https://mdoege.github.io/PySynth/), [Karplus-Strong (EPFL)](https://exoset.epfl.ch/media/notebooks/COM303/KarplusStrong/KarplusStrong.html), [guitar synth (Real Python)](https://realpython.com/python-guitar-synthesizer/) | Riferimenti per la sintesi | Chitarra (Karplus-Strong), FM, onde band-limited |
| [jfxr](https://github.com/ttencate/jfxr), [bfxr](https://sourceforge.net/mirror/bfxr/) | Suoni 8-bit | Riferimento per lo strumento 8-bit e le percussioni |

## Blender: cose imparate

- **Grease Pencil v3**: dopo `drawing.add_strokes` va chiamato
  `drawing.tag_positions_changed()`, altrimenti il disegno non si vede. Il riempimento è
  per tratto (`fill_id`). Il tempo di disegno di ogni punto è l'attributo `delta_time`,
  che usa la lettura *Gesto*.
- **WAV**: lo scrittore FFmpeg di Blender fallisce con certe lunghezze a 48 kHz
  ("filling the audio frame failed"). Per questo i WAV sono scritti col modulo `wave`
  ([AUD_FFMPEGWriter](https://projects.blender.org/archive/blender-archive/src/commit/f3407e7d60d8000d71c66192d760bd5700345b21/intern/audaspace/ffmpeg/AUD_FFMPEGWriter.cpp)).
- **Driver**: le *simple expressions* (che funzionano anche con l'esecuzione automatica
  di Python disattivata) accettano `fmod`, `min`, `max`, `floor` e il condizionale
  `a if c else b`, ma non `%`. La testina con le sezioni usa solo queste.

## Idee per il futuro

- Uscita MIDI in tempo reale (rtmidi2 `MidiOut`) verso un sintetizzatore esterno o una DAW.
- Libreria di preset di strumenti scaricabile (VCSL è CC0: un sottoinsieme piccolo si
  potrebbe includere).
- Tratti che seguono l'audio: importare un WAV e disegnarne lo spettro come forme piene,
  come un ANS al contrario.
- Sincronizzazione con la Timeline per marker: un marker diventa un cambio di BPM o di
  scala.
- Stampa dello spartito (MusicXML) dalle note lette.
