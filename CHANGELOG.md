# Changelog

## Web app (iPad)

- Prima versione web: Disegna, Beat, MIDI, Esporta, in stile Apple (tema chiaro e scuro).
- Apple Pencil: lo spessore segue la pressione (anche dove il browser la passa solo come
  forza del tocco), indicatore della pressione in basso a destra.
- Livelli come in Procreate: tocca per scegliere, tocca di nuovo per le impostazioni; occhio
  (nascondi) e altoparlante (muto) separati; tieni premuto per vedere o sentire solo quel
  livello; miniature, Duplica, Su, Giù.
- Gesti: due dita annulla, tre ripeti, quattro play/stop.
- Installabile sulla schermata Home e utilizzabile offline (`docs/app`, GitHub Pages).
- Livelli: scorri a sinistra per eliminare (fino in fondo elimina subito), a destra per
  selezionarne più di uno e poi Unisci, Silenzia o Elimina.
- Tocco a due dita più affidabile (anche con le dita che non toccano insieme); un tocco col
  dito suona solo quando diventa davvero un tratto.
- Beat: pad quadrati.
- I tuoi suoni: registra con il microfono o importa un file audio (anche da GarageBand); la
  nota base viene riconosciuta, il suono diventa uno strumento ed entra nel progetto .json.
- Export per GarageBand: tracce separate (un WAV per livello e per il beat), WAV e MIDI
  singoli fuori da claude.ai. Import MIDI fino a 32 battute, salta le battute vuote iniziali
  e aggiunge livelli alla composizione se c'è già musica.
- Template dell'icona (`tools/icon_template.py`) e icona personalizzata da `web/icon.png`.
- Tavola: pinch per ingrandire (fino all'800%) e spostarsi con due dita, come in Procreate;
  rotella o trackpad sul Mac; da vicino compaiono i nomi di tutte le note e la griglia
  ritmica; un tocco sulla percentuale torna al 100%.
- Contagocce: tieni premuto su un tratto per prenderne strumento e opacità.
- Righello: tocca i numeri di battuta (o il piano roll in MIDI) per scegliere da dove parte il
  play; durante il play salta lì.
- Livelli: tieni premuto e trascina per cambiarne l'ordine.
- Beat: tieni premuto il nome di una traccia per volume e intonazione.
- Pennelli: Liscio, Inchiostro ruvido (rumore su posizione e spessore, come Ink Rough di
  Blender), Matita, Pennarello, Aerografo, Puntini, Pieno. Ogni pennello cambia anche il suono
  (vibrato, timbro più scuro, volume fermo, attacco lento, arpeggio, cluster).
- Lazo: seleziona i tratti del livello attivo, spostali con aggancio a griglia e semitoni,
  duplica, elimina o cambia strumento.
- Beat: pattern A e B per traccia, sequenza per battuta (A, B o pausa); i preset hanno un fill
  in B.
- Nuova sezione **Onda**: disegna un ciclo della forma d'onda (bordo sopra = sinistra, bordo
  sotto = destra, Tratto o Pieno, Simmetrico) e usala come strumento.
- Il disegno si salva subito quando l'app va in secondo piano.
- Avviso *Nuova versione pronta* quando l'app installata si aggiorna.
- Strumenti e livelli in due isole separate; le sezioni in alto diventano icone mentre disegni.
- Spessore più sensibile alla pressione (curva e spessore minimo regolabili); il cursore
  dello spessore resta dentro la barra; i pulsanti tondi non diventano ovali.
- Tratti senza buchi nelle curve strette (anche con l'Inchiostro ruvido, ora senza rumore
  all'indietro nel tempo).
- Gomma con tre modi: Tratto intero, Punti, Fino agli incroci.
- Lazo: prende ogni tratto con almeno un punto nel giro.
- Livelli: menu a pressione lunga (Duplica, Unisci sotto, Cancella, Elimina livello), via Su e
  Giù; con un solo livello Elimina diventa Cancella.
- Lettura Ottica: piano, marimba, campana e chitarra tengono il suono e scivolano.
- Beat: interruttore accanto al titolo, template nel menu ≡, pattern A/B attivabili, pallino
  sul pattern che suona; Svuota in rosso.
- Solo Pencil (automatico, sempre, mai): con la Pencil le dita scorrono e fanno i gesti.
- Onda: Tratto/Pieno cambia il disegno già fatto, gesti a due e tre dita, *Come funziona?*.
- Impostazioni in un pannello grande con categorie (Tavola, Pennello e Pencil, Audio,
  Interfaccia, Info).
- Registrazione **Live**: il tempo scorre da solo, la Pencil dà altezza e intensità.
- Audio più robusto: una nota che non si può calcolare non blocca più tutto il loop, l'audio
  riparte dopo che l'iPad lo ha interrotto, cache più leggera; pulsante ↻ *Ricarica l'audio*.
- In alto: isole separate (strumenti, Livelli con il nome, colore); **?** con l'aiuto della
  schermata; nome della composizione modificabile; menu ⋯ con Salva, Apri, Importa video ed
  Esempi; le sezioni si riducono a icone (con il nome di quella attiva) quando manca spazio.
- Gesti uguali per M, altoparlante e occhio: tocco, tieni premuto (solo questo), trascina
  (tutti come il primo). Menu vicino al dito per livelli, suoni e onde.
- Beat: modalità **Pad** per suonare la batteria dal vivo e registrarla nel pattern; con
  Solo Pencil le dita scorrono la griglia.
- MIDI: selezione e spostamento delle note, Registra e Ricarica in alto, Livelli e strumento.
- **Video** in una finestra mobile sincronizzata con il play.
- Immagini e video in finestre mobili (più di una) e come **sfondo della tavola** da ricalcare
  (opacità, Riempi / Intero / Allunga; segue zoom e play).
- Esporta **video** della tavola con la linea del tempo che scorre e la musica; **PNG** con la
  tavola o trasparente, un PNG per livello, risoluzione fino a 3×.
- Annulla nei messaggi dopo un'eliminazione; il play mostra quando l'audio si sta preparando.
- Correzioni (revisione del codice): annulla e ripeti ora riportano anche tempo, scala,
  battute e suoni; Live col dito non blocca più i gesti; i palmi non interrompono più un tratto
  della Pencil; la gomma a vuoto non cancella più Ripeti; velocity MIDI sempre valide; metronomo
  senza consumo di memoria; audio che riparte dopo telefonate e Siri, e anche con il silenzioso
  (Safari 16.4+); registrazione del microfono avviata una sola volta; esportazioni protette da
  errori e doppi tocchi; un suono eliminato torna con Annulla; disegnare sull'esempio lo rende
  tuo (l'import MIDI non lo sostituisce più); nomi dei file nello .zip in UTF-8; avviso se il
  salvataggio sul dispositivo non riesce.
- Cinque letture per livello, con icona e sigla nella riga del livello (come i metodi di fusione
  di Procreate): **Q** quantizzata, **QL** quantizzata legata, **O** ottica, **OL** ottica legata
  (nuova), **G** gesto. Legata = i tratti vicini (meno di un battito) diventano una sola voce che
  scivola, senza riattacco. Si scelgono in una riga che si scorre in su e in giù.
- **Video**: formati Tavola, 16:9, 1:1 e 9:16; inquadratura *Segue il tempo* (la tavola
  scorre sotto il cursore, le ripetizioni una dopo l'altra, la tastiera ferma a sinistra);
  **pallini sul cursore** dove la musica viene letta, con un anello dove comincia un tratto;
  titolo, tempo e barra di avanzamento; anteprima nella scheda Esporta.
- **Icone nuove**: app (il logo con i trattini colorati), favicon del browser e del sito (il
  logo da solo), logo nero/bianco in alto a sinistra che segue il tema.
- **Lingue**: italiano, inglese, francese, spagnolo, cinese e russo (Impostazioni →
  Interfaccia → Lingua); al primo avvio segue la lingua del dispositivo. I nomi che scrivi
  (livelli, composizione, suoni, onde) non vengono tradotti.

## 0.0.6

Novità
- **Timeline: audio + composizioni**. Nuova sorgente *Tutto* (ora predefinita): ogni strip
  audio del Sequencer su **qualsiasi canale** (anche il canale 1 quando non è una
  composizione), gli Speaker e le composizioni con note e curve, insieme. L'audio
  "normale" e le composizioni hanno due colori (*Colore audio*, *Colore composizioni*);
  la strip di una composizione non viene contata due volte.
- **Cinque letture** con lettere e icone, come nella web app: Q (Quantizzata), QL
  (Quantizzata legata), O (Ottica), **OL (Ottica legata, nuova)**, G (Gesto). I file
  salvati con 0.0.5 mantengono la loro lettura.
- **Legato tra i tratti** (QL e OL): i tratti dello stesso strumento (e con gli stessi
  effetti) più vicini di *Unisci tratti entro* diventano una sola voce che scivola, in
  altezza e volume, attraverso la pausa. Le percussioni non si legano.
- **Ottica per chitarra e campana**: in lettura ottica (e legata) un tono morbido tiene il
  suono dopo il pizzico e segue la linea, così il glissando si sente fino in fondo.

Miglioramenti tecnici
- **Render robusto**: un tratto o una nota che non si riesce a generare viene saltato
  (e segnalato nel pannello, *N parti saltate*, con il primo errore in console) invece di
  far fallire tutta la composizione; le parti saltate vengono riprovate al render dopo.
- **Memoria della cache limitata**: la cache dei tratti si ferma a 512 MB di audio e
  quella dei livelli a 256 MB (prima contava solo il numero di elementi); l'analisi dei
  tratti ha una cache a parte, così cambiare il legato non rilegge tutto.
- **Timeline**: i file audio che non si riescono a decodificare non vengono riletti a ogni
  ridisegno; i suoni impacchettati nel .blend ora si vedono.

## 0.0.5

Novità
- **Composizione vuota**: una nuova composizione parte con un solo livello e un solo
  strumento (Preferences per partire con più livelli o con un set di strumenti).
- **Livelli e strumenti nella stessa interfaccia**: *Nuovo livello* crea un livello; ogni
  livello è un riquadro (apri/chiudi) con lettura, occhio, cestino e dentro i **suoi
  strumenti**; *+ Strumento* aggiunge uno strumento a quel livello. Rinominare un livello
  si porta dietro i suoi strumenti.
- **Strumento "Libreria"**: suona SoundFont 2 (`.sf2`) e strumenti SFZ (`.sfz`) con scelta
  del preset (lettore incluso, nessuna dipendenza). Librerie libere consigliate in
  RESEARCH.md.
- **Tastiere MIDI**: *Suona con la tastiera* ascolta anche una tastiera MIDI collegata
  (velocity = volume, pedale di sustain, registrazione). Porta nelle Preferences.
- **Sezioni da keyframe**: ogni keyframe Grease Pencil diventa una sezione del brano che
  ripete il suo disegno fino al keyframe successivo; testina e durata della scena seguono.
- **Lettura "Gesto"**: il ritmo è la velocità della mano (tempo di disegno dei punti).
- **Canone** per livello: 2–4 voci, entrata in battiti, trasposizione in semitoni.
- **Preset di mappatura** nelle Preferences: Classico, Espressivo, McLaren, Pulito.
- **RESEARCH.md**: fonti della ricerca (progetti simili, add-on, librerie di strumenti,
  librerie Python) e idee per il futuro.

Correzioni
- Cambiando l'**inizio della scena** o gli **fps** le strip e la testina si risistemano da
  sole (prima restavano al vecchio frame finché non si ridisegnava).
- Aprendo un altro file non resta lo stato del file precedente (scala in corso, suono
  in cache con lo stesso nome di oggetto).
- L'avviso "modificatori non contati" non può più bloccare Blender quando gira senza
  interfaccia (render da riga di comando).
- *Suona con la tastiera*: porta MIDI e timer vengono liberati anche se Blender chiude
  l'operatore (caricamento di un file); il volume della velocity non dà più errore.
- Import MIDI più robusto con livelli senza keyframe; un SoundFont incompleto dà un
  messaggio chiaro invece di un errore Python; lettura SFZ di file con opcode prima di
  ogni intestazione.

## 0.0.4

Correzioni
- **Errore "filling the audio frame failed with ffmpeg"**: i WAV (suono nel Sequencer ed
  export) ora sono scritti senza FFmpeg; l'MP3 riprova con altri formati e spiega l'errore.
- **Scala della composizione**: non si moltiplica più durante il trascinamento (causa del
  blocco di Blender); viene applicata solo a gesto finito e fermo. Riverbero a blocchi:
  memoria limitata anche con loop lunghi.
- **Semicerchi, cerchi, zig-zag**: il tratto viene diviso nei pezzi che vanno avanti o
  indietro nel tempo e ognuno suona (due voci per un semicerchio, anche in lettura ottica).
- **Array e altri modificatori** non duplicano più la tavola.
- Tastiera: i tasti bianchi si allargano sopra metà dei tasti neri vicini, come su un
  pianoforte vero.

Novità
- **Lettura "Legato (morphing)"** per livello: note della scala unite da glissandi, una
  sola voce che scivola da una nota all'altra senza riattacco (tempo di legato regolabile).
- Creando una composizione si **resta in Object Mode** (Preferences: "Entra in Draw Mode"
  per il comportamento di prima).
- **Canale del Sequencer** per composizione: automatico (1, 2, 3…) o scelto a mano.
- **Import MIDI** (*File → Import → MIDI → Grease Pencil*, o Shift+A): una traccia per
  livello, programma General MIDI → strumento, batteria → percussioni, velocity → spessore,
  tavola adattata a BPM, durata e note.
- **Strumento "Campione"**: suona un suono di Blender (caricato o già nel Sequencer),
  intonato sulle righe, con nota base e loop.
- **Effetti per strumento** (eco, riverbero, lo-fi) nella scheda Materiale.
- **Volume visibile**: abbassando il volume di uno strumento i suoi tratti diventano più
  fini (o più trasparenti), secondo le Preferences; solo visivo.
- **Suona con la tastiera del PC** (A W S E D F T G Y H U J K…, Z/X ottava, R registra
  mentre la scena è in play).
- **Interfaccia fuori dal pannello N**: Proprietà → Dati oggetto (tavola, lettura, livelli,
  strumenti, Sequencer), Materiale (strumento, campione, effetti), Output (export), Scena
  (ascolto di tutte le composizioni); *File → Export*. Il pannello N resta compatto.
- **Preferences**: valori di partenza per le nuove composizioni (BPM, durata, note, ottave,
  griglia, scala, etichette, livelli, set di strumenti, frequenza), volume visibile,
  spessore dei tratti registrati.

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
