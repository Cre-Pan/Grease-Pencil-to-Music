# Changelog

## 0.0.3

- **Tastiera**: tasti neri sul lato della griglia (come un pianoforte vero), nomi
  delle note sul lato libero.
- **Controller nella Timeline**: pulsante con la nota musicale accanto agli Overlay
  (acceso/spento + menu). Sorgente: composizione attiva, tutte, una a scelta, mix del
  Sequencer, un canale del Sequencer, Speaker. Forma d'onda: picchi, piena, contorno,
  inviluppo RMS o nessuna; note MIDI; **flusso ottico** (curve di altezza dei tratti
  in lettura ottica); altezza, opacità e colore.
- **Ogni composizione ha le sue regole**: materiali-strumento propri (muto, volume e
  strumento non si influenzano più tra composizioni); dopo Shift+D / Alt+D dati e
  materiali vengono separati automaticamente.
- **Ascolto**: *Tutte insieme*, *Solo l'attiva* (segue la composizione su cui disegni),
  *Una dopo l'altra* (in fila per "Ordine", con la testina che parte al momento giusto).
  L'intervallo della scena si adatta.
- **Scala in Object Mode**: S + X allunga o accorcia la composizione, S + Z mostra più
  o meno ottave; i tratti non vengono deformati.
- Lista strumenti: il riquadro colore è separato dal nome.

## 0.0.2

- **Un unico oggetto**: tavola, tastiera, etichette e testina sono livelli bloccati
  (gruppi "GP2M Tavola" e "GP2M Testina") dentro la composizione. Niente più linee di
  parentela; **Shift+D** crea un nuovo piano di lavoro con il suo suono. I file 0.0.1
  vengono convertiti automaticamente.
- Tastiera con tasti bianchi e neri alti quanto le righe; etichette grigie sui tasti
  (solo Do, tasti bianchi, tutte, nessuna) disegnate con un font a tratto singolo.
- Preferenza **Nomi delle note**: C D E… oppure Do Re Mi…
- **UI List** per livelli (+, −, su, giù) e strumenti (+ con menu degli strumenti, −),
  con occhio aperto/chiuso corretto e **volume per strumento**.
- **Timeline**: forma d'onda e blocchetti delle note nella Timeline / Dope Sheet.
- **Percussioni**: Cassa, Rullante, Charleston, Piatto, Battimani, Tom, Campanaccio
  (note General MIDI nell'export).
- **Cluster**: le forme piene suonano come cluster tonale o banda di rumore.
- **Usa modificatori**: legge i tratti dopo Noise, Array, ecc.
- **Swing** sulla quantizzazione ritmica; tasto **Muto** per composizione.
- Playback: il file audio viene sostituito senza ricreare la strip, suono caricato in RAM,
  meno lavoro negli handler durante la riproduzione; **Ctrl+Z durante il play** riprende la
  riproduzione se Blender la ferma.
- Spessore = **Volume** di default; alla creazione la vista passa a *Solid → Texture*.
- Riempimenti colorati con il colore dello strumento.

## 0.0.1 — primo prototipo

- Shift+A → Grease Pencil to Music → Composizione Musicale: tavola nel piano X-Z
  con pianoforte verticale, righe dei semitoni, Do evidenziati (C3…C6), linee dei
  secondi e dei battiti, etichette, testina animata; 3 livelli, 8 materiali-strumento, Draw Mode.
- Lettura per livello: Quantizzata (scala, tonica, griglia ritmica) oppure Ottica (glissandi).
- 8 strumenti sintetizzati: Flauto, Ocarina, 8-bit, Synth, Archi, Chitarra, Campana, Percussioni.
- Mappatura degli attributi nelle Preferences: spessore (volume + vibrato), opacità,
  vertex color (pan), morbidezza (attacco).
- Effetti per livello: eco ping-pong, riverbero, lo-fi. Volume = opacità del livello.
- Mute: livelli e materiali nascosti non suonano (anche negli export).
- Aggiornamento automatico da Draw, Edit e Sculpt Mode, undo e apertura file.
- Suono nel Video Sequencer, intervallo della scena = loop; export WAV, MP3, MIDI.
- Avviso quando sono presenti modificatori o effetti (non ancora interpretati).
