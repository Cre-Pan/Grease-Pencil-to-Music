# Changelog

## Web app (iPad)

- Ottica legata e Quantizzata legata: due tratti dello stesso strumento sovrapposti nel tempo
  (per esempio una nota molto alta sopra una molto bassa) suonano tutti e due. Prima si univano in
  una sola voce e quello iniziato dopo interrompeva l'altro.
- Isola delle sezioni più fluida: cambiando sezione, o quando i nomi si chiudono mentre disegni,
  i nomi e la pillola si muovono insieme sulla stessa curva (prima i nomi scattavano e la pillola li
  rincorreva). Le isole in alto hanno tutte la stessa altezza; quelle che arrivano con una sezione
  (Livelli, colore, trasporto) crescono al loro posto.
- Switch come in iOS 26: toccato, il pallino diventa una lente di vetro sopra la levetta; si può
  trascinare e lasciarlo dal lato voluto. Anche il pallino dei cursori diventa una lente mentre lo tieni.
- Supercerchi ovunque: schede, gruppi, isole di Esporta, campi, pulsanti, anteprime e menu hanno gli
  angoli a supercerchio, gli stessi in tutta l'app. Su Safari (che non ha ancora `corner-shape`)
  la stessa curva è disegnata con `clip-path: shape()`.
- Esporta: le scelte (Formato, Risoluzione, Codifica...) occupano tutta la riga. Ascoltando da In a
  Out l'onda non viene più ridisegnata a ogni fotogramma: resta pronta e si aggiunge solo la testina.
- Disegnando con la Pencil il suggerimento in basso non viene più riscritto a ogni campione.
- Esporta video: dove il browser ha WebCodecs (Safari recente, Chrome, Edge) il video è codificato
  fotogramma per fotogramma con [Mediabunny](https://github.com/Vanilagy/mediabunny) invece di essere
  registrato in tempo reale: è più veloce della durata del brano, non perde fotogrammi se l'iPad
  rallenta e l'audio è esattamente a tempo. Dove non si può, resta la registrazione di prima.
- Strumenti: nuovi strumenti registrati dalla [Versilian Community Sample Library](https://github.com/sgossner/VCSL)
  (CC0): Pianoforte a coda (Steinway B), Clavicembalo, Organo a canne, Xilofono, Campane tubolari,
  Kalimba, Flauto dolce, Armonica, Darbuka e Cajón. Marimba, Vibrafono, Ocarina, Sassofono (tenore)
  e Conga, che erano sintetizzati, ora sono registrati. Anche l'import MIDI li usa (clavicembalo,
  xilofono, campane, organo a canne, armonica, flauto dolce, kalimba).
- Riverbero: in *Preferenze → Audio* si sceglie l'ambiente di tutta la composizione: Sala (il
  riverbero sintetico di prima), Stanza, Auditorium o Chiesa, dalle risposte all'impulso del
  database di HybridReverb2 (Ruhr-Universität Bochum, CC BY-SA 4.0). Si salva con la composizione
  e vale anche per gli export.
- **Importa MIDI** ora apre una finestra con le tracce del file: le scegli una per una (con lo
  strumento che suoneranno), poi decidi se farne una nuova composizione o nuovi livelli in
  quella aperta, se quantizzare (1/4, 1/8, 1/16), se usare il tempo del file e se allargare
  battute e ottave perché ci stia tutto. Anche da *File → Importa MIDI…* o trascinando il .mid
  nella sezione MIDI (o in Tracce).
- Lettura dei MIDI più fedele: pedale di risonanza (CC 64), note ripetute sulla stessa nota,
  note senza fine, cambi di strumento a metà traccia (diventano livelli separati), file di tipo 0
  divisi per canale, metro e numero di cambi di tempo mostrati. Aggiungendo a una composizione,
  la batteria va sulle sue righe invece che tutta su una.
- **Esporta MIDI**: un canale per livello e strumento, con volume (CC 7) e pan (CC 10) del
  livello, e il titolo della composizione nel file.
- Tastiera MIDI (Chrome, Edge): il pedale di risonanza tiene le note (e le registra lunghe);
  i pad di batteria sul canale 10 suonano il Beat e, in Pad, registrano nel pattern.
- Nuova sezione **Tracce** (tasto 4), come la linea del tempo di un programma di montaggio: una
  riga per livello, il beat e le tracce audio, con volume e muto a sinistra. I tratti vicini di un
  livello formano una clip: trascinala per spostarla nel tempo o su un altro livello (doppio
  tocco: la apre nel Disegna). Aggancio a battuta, battito o libero.
- **Importa audio** (o trascina i file nella sezione): WAV, MP3, M4A diventano una traccia con la
  forma d'onda, dal cursore del tempo; se il file è più lungo del loop la durata si allunga (fino
  a 32 battute). Le clip audio si spostano, si accorciano dai bordi, si dividono sul cursore, si
  duplicano e si eliminano. Le tracce audio suonano nel loop, finiscono nell'export (anche nelle
  tracce separate) e nel file .json del progetto; sul dispositivo stanno in IndexedDB.
- Onda non è più una sezione: disegnare la forma d'onda è il modo di creare uno strumento, quindi
  si fa in una finestra che si apre da *Strumento → Crea strumento* (o da *Onde disegnate → Disegna
  un'onda*, o tenendo premuta un'onda → Modifica). *Disegna con questa onda* chiude la finestra e
  sceglie lo strumento; *Fine*, Esc o un tocco fuori la chiudono. Le sezioni in alto sono quattro
  (tasti 1–4); il link #onda apre la finestra.
- Progetti: una galleria con tutte le composizioni salvate sul dispositivo, con le anteprime del
  disegno, le cartelle (anche una dentro l'altra) e la ricerca. Si apre dal tasto accanto a File
  o da *File → Progetti…*. Tocca un progetto per aprirlo, una cartella per entrarci; tieni premuto
  per il menu (Rinomina, Duplica, Sposta in…, Esporta .json, Elimina) o tieni premuto e trascina
  su una cartella (o sul percorso in alto) per spostarlo. *Seleziona* lavora su più elementi.
  Ogni modifica si salva da sola. *File → Nuova* ora crea una nuova composizione (la precedente
  resta nei Progetti) e *File → Apri…* aggiunge il file ai Progetti; la composizione che avevi
  diventa il primo progetto.
- Galleria: tieni premuto e trascina per riordinare i progetti (ordine *Personale*); un progetto
  lasciato sopra un altro crea una cartella con entrambi. Tolto *Chiudi* in alto a destra.
- Galleria: tocca il nome di un progetto o di una cartella per rinominarlo; scorri a sinistra su
  una card per Condividi (un .json, o un .zip per una cartella) ed Elimina.
- L'app si apre sulla galleria, come Procreate: titolo Doodle Music, comandi in una capsula e +
  tondo a destra. Un link a una sezione (#disegna, #beat…) apre ancora la sezione.
- Cursore e icona di Trasforma: la freccia di iPad, piena e con gli angoli tondi.
- Selezione: l'isola mostra il colore dello strumento (toccalo per cambiare lo strumento dei
  tratti selezionati), Specchia (nel tempo o in altezza), Duplica ed Elimina. Niente più Fine né
  conteggio dei tratti: per uscire basta toccare altrove.
- Lazo come in Blender: l'interno si illumina e il bordo è tratteggiato bianco su nero.
- Il tasto CTRL della barra non torna più al centro con il doppio clic.
- iPad: tenendo premuto CTRL con un dito, la Pencil (o un altro dito) usa davvero la gomma; il dito
  sul tasto non conta più come tocco a due dita né come palmo. Il doppio tocco non fa più zoomare
  Safari.
- Modificatori: il tasto, ora una stella a sei punte, sta a sinistra di Livelli. Trascinandone
  uno su o giù gli altri si spostano per mostrare dove andrà; trascinato a sinistra si elimina.
- Livelli: con il mouse o la Pencil si riordinano trascinandoli su o giù (con il dito: tieni
  premuto e trascina), e gli altri fanno spazio.
- MIDI: Seleziona note, Registra e Ricarica l'audio sono in basso a sinistra. La tastiera,
  abbassata fino al limite, si chiude del tutto (resta la maniglia: un tocco o un trascinamento
  verso l'alto la riapre).
- Selezione: l'isola con i comandi sta sotto il riquadro della selezione e lo segue quando lo
  sposti (sopra, se sotto non c'è spazio). Duplica ed Elimina sono solo icone.
- Barra a sinistra: il tasto tra opacità e spessore fa da CTRL. Tenuto premuto passa alla gomma
  finché lo tieni (dal pennello); con la gomma diventa una gomma a lazo che cancella tutto quello
  che il lazo racchiude. Per spostare la barra si trascina il tasto verso il centro e poi su o giù.
- Rec, Pennello e Gomma ora sono in basso a sinistra, accanto a Lazo e Trasforma.
- Cursore e icona di Trasforma come la freccia di iPad: un triangolo pieno con gli angoli tondi.
- Strumenti: la finestra ha le famiglie a sinistra e i suoni della famiglia scelta a destra, in
  righe tutte uguali (in MIDI la finestra è larga e i suoni stanno su tre colonne).
- Lazo: l'area interna si illumina leggermente mentre la disegni (rossa con la gomma a lazo).
- Bordi: il tratto cresce in modo più graduale vicino al cursore, arriva anche sopra e sotto la
  tastiera a sinistra e si ferma appena dopo la curva dell'angolo.
- MIDI: le note spostate con il lazo restano dove le lasci, senza tornare per un attimo al posto di
  prima mentre il disegno viene riletto.
- Barra a sinistra: via Annulla e Ripeti (due e tre dita, ⌘Z); il trattino in mezzo la sposta su
  o giù (doppio clic: torna al centro).
- Modificatori: si riordinano trascinandoli per il titolo, spenti si chiudono, Copia e Incolla
  (con le impostazioni, anche verso un altro livello o i globali). La chiave inglese ha un'isola
  sua, come il metronomo.
- Bordi della tavola: niente più + e − né maniglia sul righello. Uno swipe sul bordo cambia
  l'estensione (in basso giù/su: un'ottava sotto in più o in meno; in alto il contrario; a destra
  destra/sinistra: una battuta in più o in meno). Il bordo si illumina seguendo gli angoli
  arrotondati, sottile ai lati e più spesso vicino al cursore.
- Tocco sulla posizione (1.1): battute e battiti o secondi.
- Cursore: il cerchio solo per Pennello e Gomma; Lazo e Trasforma hanno il loro puntatore.
- Tastiera laterale: i Do in evidenza con l'ottava ("Do 4"), le altre note più tenui e senza numero.
- Menu ≡: Tema sulla stessa riga del testo.
- Beat: "+ Strumento" aggiunge qualunque percussione (fino a 16); il nome in Griglia si trascina
  per cambiare ordine, in Pad si tiene premuto un pad e lo si sposta; dal menu della traccia
  Cambia strumento (il ritmo resta) o Rimuovi.
- MIDI: via la riga con i tasti A W S E D F…; la scelta dello strumento è una finestra larga, con
  le famiglie affiancate. I tuoi suoni: via la descrizione.
- Tastiera MIDI: la barra del MIDI dice sempre cosa succede (collegata, nessuna tastiera, accesso
  negato). Su iPad dice che Safari non supporta le tastiere MIDI, perché iPadOS non ha Web MIDI.
  Le note partono subito, il motore audio è pronto prima del primo tasto e, se l'uscita audio ha
  molto ritardo (Bluetooth, alcuni driver), lo indica.
- Livelli: la scritta della lettura ("Quantizzata"...) non compare più passando sopra con la
  Pencil o il mouse; la sigla (Q, QL...) resta.
- **Trasforma** (in basso a sinistra, accanto al Lazo): un riquadro attorno alla selezione, o a
  tutti i tratti dei livelli selezionati se non hai lazzato niente, come in Procreate. Gli angoli
  scalano mantenendo le proporzioni, i perni sui lati allungano solo il tempo o solo l'altezza, il
  pallino in alto ruota (con uno scatto a 0°, 45°, 90°), dentro sposti. Con la Pencil, il mouse o
  un dito; ogni gesto è un passo di annulla.
- Strumenti come in Procreate: Pennello e Gomma in alto vicino a Livelli, Live in un'isola a sé;
  Lazo, Trasforma e Modificatori in un'isola in basso a sinistra, per la mano libera.
- **Modificatori** in una finestra mobile (la chiave inglese in basso a sinistra), fuori da
  Livelli: quelli dei livelli selezionati (con "Aggiungi a tutti") o quelli globali. Resta aperta
  mentre disegni e si sposta trascinando il titolo.
- I livelli selezionati scorrendo a destra diventano azzurri (non più verdi) e restano selezionati
  anche chiudendo Livelli: il Lazo e Trasforma lavorano su tutti.
- **Modificatori** come in Blender, per livello (nelle impostazioni del livello) o per tutto il
  file (sotto i livelli): Fade, Array, Simmetria, Trasponi e Umanizza. Non distruttivi, dal vivo
  anche mentre disegni (anche il suono sotto la Pencil), con interruttore, ordine nella pila,
  Duplica, Applica ed Elimina; valgono per tavola, suono, MIDI, video e miniature.
- Esporta: Immagine e Video con l'anteprima a sinistra e le impostazioni a destra; il video
  sceglie codifica (MP4 o WebM), sfondo (tema, bianco, nero), tavola sì/no, cursore, pallini,
  titolo e cornice, barra di avanzamento, nome dell'app e autore. Audio anche in MP3 (128, 192
  o 320 kbps, con lamejs). Il MIDI da solo è in File › Esporta MIDI.
- Esporta ridisegnata: la durata a destra del titolo, i numeri in piccole isole; una linea del
  tempo con due maniglie gialle (a passi di un battito, doppio tocco per tornare a tutto) per esportare solo una parte, con
  ascolto da In a Out; un'isola Immagine / Audio / Video / MIDI mostra un pannello alla volta e
  il grande pulsante Esporta resta sempre in basso. Audio, video e MIDI rispettano In e Out.
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
  titolo, tempo e barra di avanzamento; anteprima nella scheda Esporta. I pallini compaiono
  anche sulla tavola durante il play. Nel video che segue il tempo il lato destro della tavola
  è stondato come sullo schermo e le giunzioni tra i loop sono continue (ora si vedono anche i
  numeri delle battute).
- **Correzione: il disegno nuovo a volte non suonava.** Se un render dell'audio non finiva
  (succede su iPadOS: memoria, interruzioni), bloccava tutti i successivi fino al ricaricamento
  della pagina; ora ogni render ha un tempo massimo, uno bloccato viene abbandonato e rifatto,
  e dopo tre errori di fila compare l'invito a toccare ↻. Ogni render finito entra subito nel
  play (prima, disegnando di continuo, si sentiva solo quando ti fermavi). Ogni tratto ora
  viene generato da solo e tenuto da parte: un tratto nuovo costa un render breve invece di
  tutto il livello (circa la metà del tempo in un disegno con molti tratti).
- **Interfaccia più essenziale**: via i testi fissi (riga in basso a destra, «di N battute»,
  spiegazioni nei livelli, nel Beat, nell'Onda, in Esporta e nelle Preferenze). Le spiegazioni
  compaiono solo dove appoggi il mouse o la Apple Pencil sospesa sopra lo schermo; col solo
  tocco l'interfaccia resta minimale e il **?** spiega tutto.
- **Hover** (mouse o Pencil sospesa, iPad Pro / Air): i nomi delle sezioni tornano quando ci
  passi sopra; **File**, **Livelli** e lo strumento si aprono da soli dopo un attimo e si
  richiudono quando ti allontani (toccarli li tiene aperti); il tasto della tastiera sotto la
  penna si illumina.
- **Menu File** al posto di ⋯ e dell'icona delle impostazioni: Nuova, Apri, Salva, Importa
  immagine o video, Sfondo della tavola, **Rimuovi lo sfondo**, **Preferenze…** (anche ⌘,),
  Carica l'esempio.
- **La tastiera a sinistra della tavola suona**: tocca un tasto per sentire la nota con lo
  strumento scelto, scorri per un glissando; non disegna niente (anche con un dito in modalità
  Solo Pencil).
- **Doodle Music**: il progetto, l'app e l'add-on cambiano nome (prima *Grease Pencil to Music*);
  i disegni salvati restano. Icona del logo su sfondo bianco anche nella scheda del browser
  quando l'app è aperta da sola.
- Mentre disegni, la nota si risente solo quando il tratto passa a un'altra nota (prima la
  chitarra e gli altri strumenti pizzicati si ripetevano anche su un tratto dritto).
- Durante il play resta solo il pallino sul cursore (l'anello che si allarga è solo nel video).
- Il pulsante del logo resta un cerchio in ogni formato della finestra.
- Squeeze della Pencil = play/pausa, doppio tocco = pennello ↔ gomma, per quando la web app
  gira dentro un'app che li inoltra (Safari non li passa alle pagine).
- Toccando il logo: *Open-source project made by Alessandro Pannoli* con il link a
  Instagram [@cre.pan](https://www.instagram.com/cre.pan/).
- **Icone nuove**: app (il logo con i trattini colorati), favicon del browser e del sito (il
  logo da solo), logo nero/bianco in alto a sinistra che segue il tema.
- **Lingue**: italiano, inglese, francese, spagnolo, cinese e russo (Impostazioni →
  Interfaccia → Lingua); al primo avvio segue la lingua del dispositivo. I nomi che scrivi
  (livelli, composizione, suoni, onde) non vengono tradotti.
- **Gesti a due e tre dita sistemati**: dopo aver suonato la tastiera a sinistra con un dito
  quel dito restava contato per sempre e i tocchi a due (annulla) e tre dita (ripeti) non
  funzionavano più; ora i tocchi si leggono dagli eventi touch, che su iPad contano ogni dito,
  e c'è un po' più di tempo per alzare le dita.
- **Durata del loop dalla tavola**: − e + accanto ai BPM aggiungono o tolgono battute
  (tenendo premuto scorrono), oppure trascina la maniglia alla fine del righello. Accorciando,
  i tratti oltre la fine restano: riallunga e tornano.
- Niente lente d'ingrandimento, selezione del testo o menu tenendo premuto su tastiere,
  tavola, pad, cursori e pulsanti.
- **Tastiera della tavola**: il tasto suonato illumina tutta la riga, che resta accesa un
  attimo dopo aver alzato il dito, così sai dove disegnare quella nota.
- Play: il cursore non compare più per un istante alla fine della timeline prima di partire.
- Il cursore del tempo si trascina: sul righello della tavola e su tutto il piano roll MIDI
  (durante il play la musica riparte da dove lo lasci).
- MIDI: una linea molto trasparente segue il mouse o la Pencil sospesa.
- Bordi della tavola (mouse o Pencil sospesa): sopra e sotto compaiono − e + per togliere o
  aggiungere un'ottava da quel lato, a destra per togliere o aggiungere una battuta.
- Livelli: via il testo di spiegazione al passaggio e quelli dentro le impostazioni del
  livello; toccando la lettura (Quantizzata, Ottica…) si apre la tendina con tutte, le frecce
  vanno a quella prima o dopo; Armonia è una tendina.
- Cursori: tocca a destra o a sinistra della manopola per un passo preciso (Pan 10, volumi 5);
  il Pan si aggancia al centro con più forza e lì la manopola mostra un pallino pieno.
- Il cerchio del pennello si vede solo sulla tavola e svanisce piano quando la Pencil si
  allontana.
- Le sezioni in alto non si allargano più passandoci sopra col puntatore (si spostavano
  sotto il cursore e, in MIDI, la bolla traballava): i nomi sono nei suggerimenti, e un tocco
  sulla sezione attiva li mostra tutti.
- Nuovo menu ≡ accanto a File con Preferenze, Tema e Aiuto (il pulsante ? è sparito); il
  titolo del brano sta fuori dall'isola, alla sua destra.
- Gomma: lo spessore si regola col cursore a sinistra quando hai in mano la gomma (non più
  nella tendina); nuova gomma **Morbida** che assottiglia il tratto (e quindi il volume)
  prima di toglierlo, per dissolvenze.
- Il cerchio del pennello sotto la Pencil sospesa si vede di nuovo.
- Pennarello opaco al 100%; con un'opacità più bassa non si scurisce dove si incrocia, nemmeno
  con un altro tratto a pennarello dello stesso colore sul livello.
- Palm rejection: un contatto largo (il palmo), un tocco nella fascia del bordo dalla parte
  della mano che disegna (Preferenze → Pennello e Pencil → Mano che disegna) dopo aver usato
  la Pencil, o un tocco appena la Pencil si alza non disegnano e non fanno annulla/ripeti.
- Palm rejection più leggera: i tocchi con due e tre dita tornano a funzionare. Conta come
  palmo solo un contatto molto largo, un tocco nei 300 ms dopo che la Pencil si alza, o la
  fascia del bordo dalla parte della mano mentre la Pencil è in uso (negli ultimi 2 secondi).
- Preferenze: in *Mano che disegna* Sinistra è a sinistra e Destra a destra.
- Lazo: con una selezione, un dito la sposta da qualunque punto della tavola (come in
  Procreate); ingrandendo l'aggancio diventa più fine (metà griglia dal 200%, un quarto e
  mezzi semitoni dal 400%, libero dal 600%).
- Live accende il metronomo in basso, che ora si può spegnere; uscendo da Live si spegne.
- **Tempo e Durata** in due finestrine in basso a destra: Tempo con TAP, − + e il numero da
  scrivere; Durata in battute o in secondi (il righello mostra i secondi), − +, *Adatta al
  disegno* e *+4 battute*.
- *Carica l'esempio* è nel menu ≡, sopra Aiuto.
- MIDI: trascina la maniglia sopra la tastiera per farla più alta o più bassa (doppio clic:
  altezza normale).
- **Nuovi strumenti**: *Organo* (registri a canne con clic del tasto e rotary), *Ottoni*
  (il filtro si apre col fiato, la nota entra con un piccolo scivolo), *Coro* (vocale «a»),
  *Vibrafono* (tremolo del motore, tiene il glissando nella lettura Ottica), *Ocarina*; tra
  le percussioni da disegnare *Piatto*, *Campanaccio* e *Conga*. Il MIDI importato usa
  organi, ottoni, cori, vibrafono e ocarina quando il file li chiede; nell'add-on diventano
  il suono più vicino (Ocarina, Piatto e Campanaccio tornano uguali).
- **Pianoforte** acustico (corde percosse: armonici leggermente stonati come nelle corde
  vere, battimenti tra le corde, attacco del martelletto, coda che dura di più sulle note
  gravi), **fiati** (*Clarinetto*, *Oboe*, *Sassofono*) e **ottoni** (*Tromba*, *Trombone*,
  *Corno*). Gli strumenti melodici sono in ordine di famiglia: tastiere, percussioni
  intonate, corde, voci, fiati, ottoni, synth.
- **Strumenti campionati** (VS Chamber Orchestra CE, pubblico dominio): Pianoforte, Flauto,
  Clarinetto, Oboe, Tromba, Trombone e Corno ora suonano registrazioni vere; nuovi *Violino*,
  *Violoncello*, *Arpa*, *Fagotto*, *Tuba* e *Glockenspiel*. Le note lunghe di fiati, ottoni e
  archi continuano con un loop morbido; finché i campioni non sono scaricati (o nell'artifact)
  suona il synth dello strumento. Circa 6 MB, salvati per l'uso offline al primo avvio.
- **Archi veri** (sezioni di violoncelli, viole e violini) e **articolazioni**: *Archi tremolo*,
  *Archi pizzicato*, *Violino* e *Violoncello* anche *staccato* e *pizzicato*. Per il legato:
  Violino, Violoncello o Archi con la lettura *Quantizzata legata*.
- **34 percussioni registrate**: membrane (gran cassa, rullante orchestrale, tamburo grande, a
  cornice, bongo, tumba), metalli (gong, piatto sospeso, piatti a due, triangolo, campane
  nepalesi, sonagli, agogô, freno, albero di campanelli), legni (claves, temple block, tamburo a
  fessura), fruscii e sfregamenti (maracas, cabasa, tamburello, güiro, raganella, gran cassa
  sfregata, piatto con l'archetto, gong strisciato, tamburello rullato) e suoni concreti
  (incudine, lamiera, cucchiai, catena, mattone, bolle, vetro). Gli sfregamenti e i rullati
  durano quanto la linea disegnata.
- **Lista strumenti per famiglie** richiudibili (con i colori della famiglia in anteprima);
  tenendo premuto uno strumento lo senti suonare di più: un accordo arpeggiato che resta, o un
  piccolo ritmo per le percussioni.

## 0.0.45

- **In e Out cambiati dalla Timeline restano**: con *Adatta l'intervallo della scena* acceso
  (e la composizione che non segue In/Out della scena) l'End tornava subito alla fine delle
  composizioni appena si cambiavano Start o End. Ora la fine della scena le segue solo quando
  si allungano o si accorciano (Durata, tavola scalata, ordine, Solo...); Start ed End messi a
  mano restano. Riaccendendo l'opzione l'End si adatta subito.

## 0.0.44

- **Forza quantizzazione** (*Ritmica*, sotto lo Swing): quanto le note si spostano verso la
  griglia. 100% come prima (sulla griglia), 50% a metà strada, 0% dove le hai disegnate: il
  tempo della mano resta, solo un po' più ordinato. Vale per Quantizzata e Quantizzata legata.
- **Forza del legato** (lettura *QL* e *OL* del livello): 100% come prima, le note si legano
  senza riattacco; più bassa, il suono cala un attimo prima di ogni nota nuova e la riattacca
  (0% = ogni nota staccata), mentre l'altezza continua a scivolare. Vale dentro un tratto e
  tra i tratti uniti.

## 0.0.43

- **Il suono arriva quando la testina tocca il tratto.** Archi, violino, violoncello, flauto,
  clarinetto, organo a canne, armonica, corno e gli altri strumenti registrati con l'attacco
  lento impiegano 0,05-0,2 s a farsi sentire: partendo esattamente sul tratto si sentivano
  dopo. Ora l'attacco comincia un attimo prima (al massimo 0,2 s, come fanno i musicisti e le
  librerie orchestrali), così la nota è piena dove inizia il tratto. Lo stesso per Archi,
  Pad e Coro sintetizzati. Colpi, percussioni e pizzicati erano già a tempo e non cambiano.
  All'inizio del loop l'attacco anticipato si sente alla fine del giro prima. Si spegne in
  *Preferenze → Cosa suona nel tratto → Attacco a tempo*.
- **Campione e Libreria senza silenzio iniziale**: un suono importato (o un campione SF2/SFZ)
  che comincia con un po' di silenzio suonava in ritardo; ora parte da dove inizia il suono.
- **Ritardo dell'audio di Blender**: Blender mescola l'audio a blocchi (*Preferenze →
  Sistema → Suono → Mixing Buffer*, 2048 campioni = 43-46 ms). Quando il ritardo si sente,
  o la riproduzione non segue l'audio, il pannello *Ascolto* lo dice e **Riduci il ritardo
  dell'audio** mette il buffer a 512 (circa 11 ms) e *Sync to Audio*. Se l'audio gracchia,
  rimetti un buffer più grande.
- **Quantizzata legata e Ottica legata più precise**: il glissando tra due note arriva sulla
  nuova nota proprio dove il tratto entra nella sua riga (prima era centrato lì, e la nota
  arrivava mezzo glissando dopo).
- **Quantizzata legata resta sulla scala nelle pause**: tra due tratti uniti tiene la nota
  di prima e scivola nella successiva solo alla fine della pausa (per il *Tempo di legato*),
  invece di attraversare lentamente tutte le note intermedie. Ottica legata continua a
  tracciare una linea dritta nella pausa, come prima.

## 0.0.42

- **In e Out per ogni composizione** (*Ascolto e Sequencer*): il primo e l'ultimo fotogramma
  della sua clip nel Video Sequencer. Cambiando l'In (o trascinando la clip) la composizione
  si sposta liberamente nel tempo, senza rifare il suono; cambiando l'Out (o trascinando la
  fine della clip) si allunga o si accorcia. **Allinea alla clip attiva** le dà In e Out della
  clip selezionata nel Sequencer (un video, un suono...): così ogni composizione può stare
  sotto la sua clip video. Ascoltando *Una dopo l'altra* l'In lo decide l'ordine.
- **Lista dei livelli**: occhio e lucchetto sono le prime icone a sinistra, allineate su ogni
  riga; dopo vengono la scaletta dei gruppi, le frecce, l'icona e il nome.
- **Gruppi colorati**: l'icona di un gruppo è quella dei gruppi Grease Pencil, nel colore del
  gruppo; il colore è lo stesso della clip del gruppo nel Sequencer e del gruppo Grease
  Pencil. Colorando la clip nel Sequencer si colora il gruppo, e viceversa. I gruppi nuovi
  prendono un colore da soli, come i livelli.
- Tolta la *clip propria* dei gruppi della 0.0.41: i gruppi restano dentro la meta-clip
  della composizione, che ora si sposta liberamente con In e Out.

## 0.0.41

- **L'occhio segue i gruppi, come le cuffie**: nella lista dei livelli, chiudendo l'occhio di un
  gruppo si chiudono quelli di tutti i suoi livelli (e sottogruppi), e riaprendolo si riaprono;
  quando tutti i livelli di un gruppo sono nascosti si chiude anche l'occhio del gruppo, e
  mostrando di nuovo un livello il gruppo torna visibile.
- **Clip propria per un gruppo di livelli** (opzione, icona clip sulla riga del gruppo o
  *Clip propria* nel pannello *Gruppo* del Sequencer): con *Un canale per livello* il gruppo
  esce dalla meta-clip della composizione e diventa una clip a sé nel Video Sequencer, sul
  canale sopra, con i suoi livelli dentro. Parte e si sposta con la composizione, tace quando
  la composizione o il gruppo sono muti; spegnendo l'opzione torna dentro la meta-clip.
- Questa versione contiene anche la 0.0.38, la 0.0.39 e la 0.0.40 insieme.

## 0.0.40

- **Copia, Incolla e Applica in ogni modificatore** (Array, Simmetria, Trasponi, Fade, Noise),
  sotto le sue impostazioni. *Copia* prende le impostazioni del modificatore; *Incolla* le mette
  nello stesso modificatore del livello attivo, anche di un'altra composizione, e lo accende
  (dal pannello *Ultima operazione* si può incollare in tutti i livelli). *Applica*, come in
  Blender, rende il modificatore parte dei tratti in tutti i keyframe e lo spegne: le copie di
  Array diventano tratti veri, Fade e Noise cambiano spessore e punti, il suono resta lo stesso
  (Noise prende la forma che si vede sul tratto). Va anche da Edit Mode e su un livello bloccato.

## 0.0.39

- Tratti sovrapposti: nelle letture *Quantizzata legata* e *Ottica legata* due tratti dello stesso
  strumento che si sovrappongono nel tempo (una nota molto alta sopra una molto bassa, o le copie di
  Array e Simmetria) ora suonano ognuno per conto suo. Prima il legato li univa in una sola voce,
  che suona una nota alla volta: quello iniziato dopo copriva l'altro, che si interrompeva. I tratti
  uno dopo l'altro (anche sovrapposti di meno di 50 ms) si uniscono come prima, e dove più linee
  continuano insieme ogni tratto prosegue quella con l'altezza più vicina. Le altre letture
  suonavano già i tratti separati. Stessa correzione nella web app.

## 0.0.38

- **Testi "fisici" sulla tavola.** Il nome della composizione (sulla linguetta sotto la
  tavola), il fotogramma nel riquadro blu della testina e i nomi di tasti e corsie non sono
  più disegnati sopra il viewport: sono riempimenti Grease Pencil della tavola, col font di
  Blender (anche i buchi di o, e, 8). Si muovono, ruotano e scalano con la composizione,
  si vedono anche in Draw Mode e compaiono nei render. Il riquadro della testina è grande
  quanto la tavola (come le linguette) e si allarga col numero; il numero si aggiorna a ogni
  fotogramma, anche nel render di un'animazione. Rinominando la composizione, il nome sulla
  tavola cambia da solo. Le tavole dei file salvati prima si rifanno all'apertura.
- **Use Preview Range aggiorna subito la tavola**: attivandolo o spegnendolo (o cambiandone
  inizio e fine) la zona fuori anteprima si scurisce o si schiarisce subito, senza aspettare
  il prossimo aggiornamento della scena.
- **Lista dei livelli a scaletta**: i livelli e i gruppi dentro un gruppo sono rientrati di due
  icone vuote per livello; i gruppi si aprono e chiudono con le frecce ▾ / ▸
  (`DOWNARROW_HLT` / `RIGHTARROW`).
- **Grip**: sotto il mouse e mentre li trascini (o selezionati) i pallini si illuminano del
  giallo-arancio dell'oggetto attivo del tema di Blender, come il bordo del riquadro della
  testina.

## 0.0.37

Tutto insieme: le novità di 0.0.36 (pannelli a tendine e Array/Trasponi che spostano il
tratto intero, qui sotto) e la correzione del box select.

- **Box select in Edit Mode di nuovo funzionante.** Con un modificatore del livello acceso
  (Array, Simmetria, Trasponi, Fade o Noise, con *Mostra sul tratto*) il box select (B o
  trascinando) non trovava i tratti: Blender li cercava spostati di quanto dista l'origine sul
  Do dall'angolo della tavola, così un riquadro attorno al tratto non prendeva niente (A invece
  selezionava tutto). Ora le copie si fanno sul tratto come disegnato e la selezione (box,
  lazo, clic) trova i punti dove sono. I file già salvati si sistemano da soli all'apertura.

## 0.0.36

Pannelli più ordinati, a tendine come in Blender
- **Tavola e tempo** è diviso in tre sottopannelli: *Tempo* (BPM, durata, In/Out della scena,
  Loop e sezioni da keyframe), *Estensione* (nota più bassa, ottave, tasti in più; nella
  Composizione Ritmica le corsie con le loro percussioni) e *Aspetto* (etichette, opacità della
  griglia, altezza riga, larghezza secondo, battiti; chiuso all'inizio). *Ricostruisci tavola* è
  l'icona ↻ nell'intestazione del pannello.
- **Ottave in cima / in fondo**: la riga "Sopra + − Sotto + −" diventa due righe allineate alle
  altre proprietà, con l'etichetta a sinistra e i pulsanti *Mostra* / *Nascondi* a destra
  (*Aggiungi* / *Togli* per le corsie). L'etichetta non esce più dal bordo.
- **Sequencer e ascolto** è diviso in *Ascolto* (tutte insieme, solo l'attiva, una dopo l'altra) e
  *Clip nel Sequencer* (un canale per livello, canale, partenza, ordine).
- **Effetti dello strumento** (Materiale) ha un sottopannello per effetto, come gli effetti del
  livello: *Eco*, *Riverbero* e *Lo-fi*, con l'elenco di quelli accesi in cima.

Livelli e icone
- **Solo di gruppo e livelli insieme**: le cuffie di un gruppo accendono (e spengono) quelle di
  tutti i livelli dentro, e un gruppo si accende da solo quando tutti i suoi livelli sono in Solo.
  Spegnendo il Solo di un livello dentro un gruppo in Solo, si spegne quello del gruppo e gli
  altri livelli restano in Solo.
- **Muto**: l'altoparlante con le onde (`MUTE_IPO_ON`) è il suono acceso, quello vuoto
  (`MUTE_IPO_OFF`) il muto, nella lista dei livelli, nelle composizioni e nel pannello Musica.
- *Aggiungi strumento* ha l'icona dell'altoparlante (`SPEAKER`).
- **Icone delle composizioni**: un piano roll per la Composizione Musicale e una griglia di passi
  per la Composizione Ritmica, in *Shift+A → Doodle Music*, nella lista Composizioni e nei pannelli.
- **Niente più sfarfallio nella lista dei livelli**: le icone dell'add-on (cuffie del Solo,
  strumenti, composizioni) vengono caricate subito all'avvio. Prima Blender le caricava la prima
  volta che comparivano e per un attimo disegnava al loro posto un cerchio di caricamento.
- Nella tendina delle categorie, la categoria in uso tiene la sua icona (prima diventava una
  spunta, che sui Piatti sembrava una "v").

Modificatori sul tratto
- **Array e Trasponi non deformano più il tratto.** Spostando "di grado" (nella scala) ogni
  punto andava sulla sua nota della scala, così una curva diventava a zigzag e a scalini, nel
  disegno e nel suono. Ora il tratto si sposta intero: il primo punto sale (o scende) dei gradi
  scelti e tutto il resto lo segue dello stesso numero di semitoni, quindi le copie hanno
  esattamente la forma dell'originale.

## 0.0.35

Tutto insieme: le novità di 0.0.31, 0.0.32, 0.0.33 e 0.0.34 (qui sotto) e i modificatori sul tratto.

Modificatori sul tratto
- **I modificatori dei livelli si vedono sul tratto.** Array, Simmetria, Trasponi, Fade e Noise
  non cambiano più solo il suono: cambia anche il disegno, con gli stessi calcoli. Il Fade
  assottiglia l'inizio (In), la fine (Out) o tutte e due le punte di ogni tratto (o del loop,
  con *Su: Loop*); Array mostra le copie, che salgono di grado e si assottigliano con *Smorza*;
  Simmetria mostra il tratto specchiato nel tempo e/o in altezza (e nasconde l'originale se
  *Tieni l'originale* è spento); Trasponi sposta il tratto sulle righe della scala; Noise lo fa
  tremare di altezza, spessore e tempo come lo si sente.
- I tratti disegnati non cambiano: ogni livello con modificatori accesi riceve un modificatore
  Geometry Nodes *GP2M Modificatori <livello>* che segue da solo le impostazioni del livello
  (anche cambiando scala, tonalità, BPM o durata). Spegni il modificatore e il tratto torna come
  l'hai disegnato. In Edit Mode si modificano i punti originali e si vede il risultato.
- *Mostra sul tratto* (pannello Modificatori del livello) lascia cambiare solo il suono, come prima.
- Con *Usa modificatori* acceso i modificatori del livello non vengono applicati due volte.

## 0.0.34

Tavola
- **Si sposta e si ruota dove vuoi**: un clic sulla tavola prende la composizione (prima prendeva
  la griglia, che è bloccata: trascinando con Tweak o con lo strumento Move non si muoveva nulla e
  sembrava tornare indietro). La lettura usa le coordinate locali della composizione: spostata o
  ruotata suona uguale, e il disegno resta sul suo piano anche ruotata.
- **Origine sul pallino del Do centrale (C4)**: l'origine della composizione è al centro del
  pallino. L'ottava di C4 resta sempre (maniglie, pulsanti e *Nota più bassa* non la tolgono).
  Nella Composizione Ritmica l'origine è nello stesso punto, nella corsia in basso (che resta).
- **Il grip in basso fa crescere solo verso il basso**: la composizione e il disegno non si
  spostano, scende solo il bordo della tavola. Le composizioni salvate prima prendono la nuova
  origine all'apertura, senza muoversi.
- **Linguette dietro la finestra**: i tre grip e la linguetta del nome sono disegnati sotto la
  finestra (escono da dietro), grandi come nel Figma e non si ingrandiscono più allontanandosi.
  Sotto il mouse si accendono i puntini. Il nome rimpicciolisce se non ci sta.
- **Selezione**: selezionata, diventa arancione solo il bordo della finestra (non cursore, tratti
  o linguette).
- *Shift+A → Doodle Music → Composizione Ritmica* (era "Composizione Bit").

Anteprima degli strumenti
- Le percussioni nelle tendine si sentono ripetute: tre volte i colpi corti, due quelli lunghi,
  una volta gong e piatti.

## 0.0.33

Composizione Ritmica (dal Figma "Composizione Bit")
- **Nuovo tipo di composizione**: *Shift+A → Doodle Music → Composizione Ritmica*. Stessa finestra,
  maniglie, cursore blu e anteprima della tavola delle note; al posto di tastiera e righe ci sono
  **8 corsie**, una percussione ciascuna (dal basso: Cassa, Rullante, Battimani, Tom, Rimshot,
  Charleston, Charleston aperto, Piatto).
- **La corsia sceglie il suono**: ogni tratto suona la percussione della corsia dove sta (la sua
  altezza mediana), qualunque sia la penna. Più in alto o più in basso dentro la corsia non cambia
  nulla: un tratto storto resta un solo colpo. Spessore e volume della penna danno la forza del colpo.
- **Bordi come nel disegno**: corsie #272727 / #242424 a righe alterne (la prima in alto è la più
  chiara), bordo di 2 px #1C1C1C tra una corsia e l'altra, pannelli #1B1B1B tagliati dagli angoli
  arrotondati (raggio 25) e contorno di 2 px #323232 sopra tutto, a sinistra e sulla griglia.
- **Nomi delle corsie** sul pannello di sinistra (si spengono con *Nomi delle corsie → Nessuna*).
- **Corsie dalle maniglie**: la maniglia in alto e quella in basso aggiungono o tolgono una corsia
  alla volta (da 1 a 16), il disegno non si sposta e ogni corsia tiene la sua percussione.
- Nel pannello *Tavola* si sceglie la percussione di ogni corsia; *Suona mentre disegni* fa
  sentire la percussione della corsia dove inizi il tratto.

## 0.0.32

**Tavola nuova, dal disegno in Figma.** La tavola ora è una finestra scura (#181818, bordo #252525,
angoli arrotondati) con dentro la tastiera e la griglia, anche loro arrotondate:
- **Tastiera:** tasti bianchi chiari (#DBDBDB) come su un pianoforte vero (Do, Re, Mi si dividono
  5 semitoni, Fa, Sol, La, Si 7), tasti neri scuri arrotondati verso i bianchi, allineati alle loro
  righe; un pallino su ogni Do (con *Etichette tasti: Solo Do*; le altre scelte scrivono ancora i
  nomi delle note).
- **Griglia:** righe dei tasti bianchi #2D2D2D e dei neri #262626, una linea dove due bianchi si
  toccano (Mi-Fa, Si-Do), linee dei secondi e dei battiti appena accennate. Fuori dal Preview
  Range la griglia è scurita al 65%. Le etichette dei secondi sopra la griglia non ci sono più.
- **Cursore blu** (#407FB7) con il numero del fotogramma nel riquadro sopra la finestra.
- **Maniglie a linguetta:** sopra e sotto la tastiera (tasti) e a destra (durata), linguette scure
  con otto puntini che escono dalla finestra; sotto il mouse i puntini si accendono, trascinandole
  diventano blu. Sono grandi quanto la tavola, ma da lontano non diventano più piccole di così.
- **Nome:** sotto la finestra una linguetta con il nome della composizione (si allarga per i nomi
  lunghi).
- I colori sono quelli del disegno, qualunque sia il tema di Blender.

Ogni composizione si porta dietro il suo cursore, anche la copia appena fatta con Shift+D; i
numeri del cursore stanno piatti sulla tavola; la tavola segue il mouse mentre ne trascini
altezza e larghezza, anche dalla fine della clip nel Sequencer.

- **Shift+D:** la copia ha subito la sua tavola, il suo cursore e le sue maniglie e li porta con
  sé mentre la sposti; resta dove la lasci. Prima, durante lo spostamento dopo Shift+D, il
  l'add-on non si accorgeva che stavi ancora trascinando: dopo un attimo rifaceva tavola e
  suono della copia sotto il mouse (lo stesso lavoro che con G aspetta la fine del movimento).
  Ora con Shift+D e Alt+D aspetta come con G; solo la tavola della copia viene creata subito.
- **Numeri del cursore piatti:** il numero del fotogramma nel riquadro del cursore, e il valore
  che compare trascinando le maniglie (durata, tasti), sono disegnati sul piano della
  composizione come il cursore: guardando di lato si inclinano con il riquadro invece di girarsi
  verso la vista.
- **Tasti in basso:** trascinando la maniglia sotto la tastiera le righe compaiono (o spariscono)
  sotto mentre trascini; la cima della tavola e il disegno restano fermi. Prima la tavola si
  aggiornava solo al rilascio e per un attimo veniva disegnata con le righe vecchie sulla nuova
  origine, così saltava su o giù. Esc o clic destro la rimettono com'era.
- **In tempo reale:** altezza (tasti sopra e sotto) e larghezza (durata) della tavola seguono
  il mouse mentre trascini le maniglie; il suono si rifà al rilascio.
- **Fine della clip nel Sequencer:** trascinando la maniglia destra della clip di una
  composizione la tavola si allunga o si accorcia mentre trascini (prima solo al rilascio,
  quando cambiava anche l'End della scena). Al rilascio l'End della scena segue come prima; con
  Esc tavola e clip tornano come erano.

## 0.0.31

Icone degli strumenti più chiare e minimal, strumenti in nuove categorie, due tendine per
sceglierli e l'anteprima del suono.

- **Icone ridisegnate:** pianoforte (tre tasti bianchi divisi e due neri), percussioni intonate
  (barre viste dall'alto e una bacchetta), campana, archi (violino con archetto), chitarra (la
  paletta, inclinata al contrario degli archi), arpa (ora una lira), pad (tre note lunghe tenute),
  dente di sega e onda quadra (meno onde, senza la linea sotto), percussioni (bacchette incrociate
  sul tamburo).
- **Icone solo per le categorie:** i singoli strumenti non hanno più un'icona. Fiati (una folata
  di vento), ottoni (una tromba minimal), piatti e strumenti concreti (una bottiglia) hanno la loro.
  Da 34 icone a 11.
- **Categorie nuove:** il sassofono è negli ottoni; Batteria, Tamburi, Legni e blocchi e Fruscii
  diventano **Percussioni**; hi-hat, crash, piatti, gong, campane nepalesi, sonagli, albero di
  campanelli, tamburello e freno sono nei **Piatti**; triangolo, campanaccio e agogo nelle
  **Percussioni intonate**; gli Oggetti diventano **Strumenti concreti**.
- **Due tendine:** nella lista dei livelli l'icona dello strumento apre le categorie (scegliendone
  una passi al suo primo strumento) e accanto la seconda tendina mostra solo gli strumenti di
  quella categoria; il pennello rende attivo lo strumento per disegnare. Le stesse due tendine
  sono nel pannello *Strumento musicale* del materiale.
- **Anteprima:** nei menu degli strumenti, fermandoti con il mouse su una voce senti una nota di
  quello strumento (parte con il suggerimento, dopo circa mezzo secondo, che ora descrive lo
  strumento). Si spegne in
  *Preferenze → Anteprima degli strumenti*.

## 0.0.30

Ctrl+Z e Ctrl+Shift+Z provati azione per azione in Blender 5.3 (tasti e mouse veri): crea
composizione, tratti, strumenti, rig, livelli, gruppi, impostazioni, composizioni, Sequencer.

- **Niente più crash di Blender con Ctrl+Z / Ctrl+Shift+Z.** Dopo *Nuovo livello* (o un'altra
  azione che crea clip nuove), qualche Ctrl+Z e Ctrl+Shift+Z potevano chiudere Blender. Le clip
  arrivano un momento dopo il passo di Undo (il suono si calcola dopo) e Blender, che rilegge solo
  i dati diversi fra due passi, teneva la scena con clip che puntavano a suoni appena buttati.
  Ora scena, composizioni, griglie e collezioni sono sempre rilette.
- **Rig: Ctrl+Z della durata non la accorcia più.** Trascinata la maniglia della durata da 8 a
  9,3 s, Ctrl+Z dava 6,7 s e Ctrl+Shift+Z 10,6 s: la clip ridata indietro sembrava trascinata nel
  Sequencer. Quello che la lettura del Sequencer confronta ora è salvato nel file con il passo.
- **Rig e pannello: Ctrl+Shift+Z ridà anche la griglia giusta** (ottave, tasti sopra e sotto,
  durata, BPM): prima tornavano le impostazioni nuove con la griglia vecchia.
- **Durata con *Segui In/Out della scena*:** Ctrl+Z tornava indietro di due passi (anche la
  Durata di prima). Ora il passo sa se è cambiata la Durata o l'End della scena.
- **Sequencer:** Ctrl+Shift+Z di una clip spostata (G, *Parte dopo*) o allungata dalla maniglia
  ora tiene lo spostamento; Ctrl+Z di H su un livello e di Ctrl+G sui livelli ora li annulla
  davvero (il livello restava muto, il gruppo restava).
- **H / Alt+H sulla clip di una composizione** ora la mette muta o la riaccende (*Muto*), come
  per i livelli; prima la clip tornava subito accesa.
- **Livello muto + Ctrl+Shift+Z:** la sua clip non resta più senza file. I file dei suoni
  vecchi restano su disco per un po' (fino a 160 file o 768 MB, nella cartella temporanea che
  Blender svuota all'uscita): dopo Ctrl+Z le clip suonano subito quello di prima, poi il suono si
  ricalcola.

## 0.0.29

- **Il volume di uno strumento non risintetizza più i tratti.** Le voci di uno strumento
  sono proporzionali al suo volume: si riusano quelle calcolate a volume 1 e si scalano
  (anche nelle letture legate). Le note MIDI tengono la loro velocity. Solo dove il volume
  porterebbe una voce oltre il tetto di ampiezza (dove veniva tagliata) il tratto si
  ricalcola come prima. Differenza con la sintesi completa sotto 1e-5.

## 0.0.28

Meno lag mentre disegni, modifichi e scolpisci (il suono è identico)

- **Il suono si calcola in sottofondo.** L'aggiornamento automatico calcola mix e bus master
  in un thread a parte: Blender legge i tratti prima (circa 2 ms) e scrive i file dopo
  (circa 3 ms), e nel frattempo il disegno, Edit e Sculpt non si fermano. Prima ogni
  aggiornamento bloccava Blender per 75–150 ms (3 livelli, loop di 8 s). Se nel frattempo
  cambi ancora qualcosa, il calcolo vecchio si butta e vale quello nuovo. Si può spegnere in
  *Preferenze → Avanzate → Calcola il suono in sottofondo*.
- **Niente aggiornamenti con la penna giù.** Mentre tieni premuto in Draw, Sculpt, Vertex o
  Weight Paint (anche fermo), il suono aspetta che alzi la penna, come già succedeva con G, R, S.
- **Bus master 3 volte più veloce.** La sala comune e il taglio dei bassi sono un solo prodotto
  nel dominio della frequenza (2 FFT invece di 4) quando la durata del loop in campioni ha
  fattori piccoli, cioè quasi sempre (8 s, 4 battute a 90 o 100 BPM...): da 84 a 25 ms per
  livello. La differenza con prima è sotto 1e-7, cento volte meno di un passo di un file a 16 bit.
- **Opacità del livello, volume master e muto non ricalcolano il riverbero comune.** La sala
  del bus master di ogni livello resta in memoria e si scala col volume: cambiare l'opacità
  passa da 175 a 95 ms, il volume master da 330 a 90 ms (e in sottofondo). Volume e pan della
  clip, come prima, non ricalcolano nulla.
- Disegnare o scolpire non ricontrolla più le impostazioni dei livelli a ogni movimento: solo
  quando aggiungi, rinomini, sposti o elimini livelli e gruppi.
- Corretto: con le *Sezioni da keyframe* gli effetti di riverbero dei livelli usavano sempre la
  Sala, anche con un altro ambiente scelto (Stanza, Auditorium, Chiesa).
- Corretto: se l'ambiente registrato non si legge, non viene riletto a ogni aggiornamento.
- `tests/bench_lag.py` misura cosa costa ogni aggiornamento (depsgraph, rigenerazione, volume,
  pan, opacità, muto).

## 0.0.27

Gruppi nel Sequencer, come i gruppi di Blender

- **Ctrl+G sulle clip di più composizioni**: diventano un **gruppo**. Sul tavolo restano
  composizioni separate, ognuna con i suoi livelli; nel Sequencer si muovono insieme, su un
  solo canale. Un gruppo può stare dentro un altro gruppo.
- **Alt+G su un gruppo** lo scioglie: le composizioni tornano fuori. **Alt+G sulla clip di una
  composizione** invece non si fa: la clip torna com'era, con un avviso.
- **Il gruppo è un bus**: volume, pan e muto del gruppo valgono per tutte le sue composizioni,
  anche nell'export. Si cambiano nella barra laterale del Sequencer (scheda Musica, pannello
  Gruppo); anche il Volume della meta-clip diventa il volume del gruppo. Un gruppo muto non
  viene ricalcolato; togliendo il muto le sue composizioni si aggiornano.
- **Ctrl+G sulle clip di alcuni livelli** (dentro la clip di una composizione): diventano un
  **gruppo di livelli** nella stessa composizione. Ogni gruppo di livelli, anche quelli fatti
  dalla lista dei livelli, è una meta-clip dentro la clip della composizione.
- **Alt+G sulla clip di un gruppo di livelli** scioglie il gruppo; incollare la clip di un
  livello dentro quella di un gruppo sposta il livello nel gruppo; eliminare la clip di un
  gruppo mette il gruppo in muto; spostare le clip su altri canali riordina anche dentro il
  gruppo.
- Anche il gruppo di livelli è un bus: il suo "Volume clip" e il suo pan valgono per tutti i
  suoi livelli (nel Sequencer e nell'export); muto e volume della sua meta-clip sono quelli
  del gruppo.
- Ctrl+Z riporta indietro gruppo e composizioni insieme.

## 0.0.26

Le clip delle composizioni nel Sequencer: cosa succede

- **Taglio (K) e scala (S, velocità)**: le clip di una composizione non si tagliano e non
  si scalano; se succede, la composizione torna intera da sola (con un avviso nella barra
  di stato). La durata si cambia dalla fine della clip. Anche l'**inizio** non si taglia.
- **Fine della clip con *Segui In/Out***: allungarla o accorciarla sposta l'End della scena.
- **Shift+D** sulla clip di una composizione crea una **nuova composizione** (copia del
  disegno, sul tavolo sopra le altre), sul canale e nel punto dove hai lasciato la copia.
  Nel viewport Shift+D faceva già così.
- **Rinominare la clip rinomina la composizione** (prima la composizione perdeva la clip e
  ne creava un'altra, con il suono doppio).
- **Eliminare la clip mette in muto la composizione**: togliendo il muto torna.
- **Muto = nessun calcolo**: una composizione muta non viene ricalcolata; mutare un livello
  muta solo la sua clip, senza rifare il suono degli altri (togliendo il muto il livello
  viene ricalcolato, nel caso sia cambiato).
- **Spostare nel tempo la clip di un livello** (dentro la meta) sposta i suoi tratti sulla
  tavola di altrettanto: quello che vedi è quello che senti.
- **Incollare o trascinare la clip di un livello nella meta di un'altra composizione**
  sposta il livello in quella composizione, con i suoi strumenti e le sue impostazioni;
  i tratti tengono tempi e note anche se le due tavole sono diverse.
- **Clip bloccata (lucchetto)**: l'add-on non la sposta e non legge più le sue modifiche.
- **Annulla (Ctrl+Z)** riporta indietro insieme la clip e il livello.

## 0.0.25

Tutto insieme: rig e colori del tema (0.0.23, 0.0.24) con la meta-clip per composizione e la
sincronizzazione tra Sequencer e livelli (vedi 0.0.22: muto, ordine, ritardo d'inizio, volume,
pan e colore tra livelli e clip). Provato insieme in Blender 5.3. In più:

- **Opacità della griglia** (*Tavola e tempo*): sfondo, righe, tastiera ed etichette diventano
  trasparenti quanto vuoi; il disegno resta pieno.
- **Maniglie delle ottave un tasto alla volta**: trascinandole aggiungi o togli un semitono
  per volta (in alto e in basso); con **Ctrl** un'ottava intera. Il disegno non si sposta.
- **Maniglia della durata senza aggancio**: si ferma su ogni fotogramma e, mentre trascini,
  la tavola e la meta-clip nel Sequencer cambiano insieme (il suono segue appena ti fermi).
  Al contrario, allungando o accorciando la fine della meta-clip nel Sequencer la
  composizione cambia durata e la tavola con il suo rig la segue.
- **Ctrl nel viewport aggancia alle battute** (4/4 al BPM della composizione): per la
  durata e per la testina.
- **Pan da 0 a 100** sotto il volume di ogni livello: 0 tutto a sinistra, 50 al centro,
  100 tutto a destra (è il Pan della clip del livello).

## 0.0.24

Ritocchi al rig

- Niente più messaggio in alto nel viewport: le maniglie non hanno il tooltip e durante il
  trascinamento l'header resta com'è. Il valore (durata in secondi, ottave) compare accanto
  alla maniglia mentre la sposti.
- Maniglie "spente" quando il mouse non è sopra: grigie e più trasparenti; si accendono
  al passaggio del mouse e prendono il colore dell'*Oggetto attivo* quando le selezioni
  o le trascini.
- **Clic per selezionare, G per spostare**: un clic su una maniglia la seleziona; premendo
  **G** la sposti con il mouse come un oggetto (clic o Invio conferma, Esc o tasto destro
  annulla). Un clic altrove o Esc la deseleziona. Senza maniglia selezionata G sposta gli
  oggetti come sempre.
- Il riquadro della testina ha sempre il colore esatto della testina della Timeline (prima
  sotto il mouse diventava più chiaro); hover e selezione si vedono sul bordo.

## 0.0.23

Rig in stile Frame by Plane e colori del tema di Blender

- **Maniglie come in Frame by Plane**: non sono più tratti di un terzo Grease Pencil ma
  gizmo disegnati a **dimensione fissa sullo schermo** (non diventano minuscole allontanando
  la vista né enormi avvicinandola), chiari con un bordo scuro; sotto il mouse e mentre le
  trascini prendono il colore dell'*Oggetto attivo* del tema. A destra la durata (◂ ▸),
  sopra e sotto la tastiera le ottave (▴ ▾). Gli oggetti *· Rig* della 0.0.22 vengono
  rimossi all'apertura del file.
- **Testina come nella Timeline**: la linea e il riquadro in cima hanno il colore della
  testina del tema (*Temi → Comune → Animazione → Playhead*) e il riquadro mostra il numero
  del fotogramma, come nella Timeline. Si trascina per spostare il cursore.
- **Tavola nei colori del tema**: sfondo, righe, linee dei secondi e dei battiti ed etichette
  vengono dal Dope Sheet del tema, i Do dal colore dei keyframe selezionati, l'ombra fuori
  dall'anteprima dal *Scene Strip Range*. Se cambi tema (o un suo colore) la tavola si
  aggiorna da sola entro un secondo, senza ricostruirla e senza rigenerare il suono.
- **Provato in Blender 5.3 con il mouse**: le quattro maniglie sono state trascinate con
  eventi del mouse veri (durata 8 → 9,5 s, un'ottava sopra, una sotto, testina dal
  fotogramma 30 al 69).
- GitHub Pages: il deploy fallito a volte ("No artifacts named github-pages") ora è in due
  job, come nel modello di GitHub, così l'artefatto è già registrato quando parte il deploy.

## 0.0.22

Il viewport come un tavolo: composizioni come livelli e maniglie disegnate

- **Composizioni come livelli**: nella sidebar (*Musica → Composizioni*) le composizioni
  della scena sono in una lista come i livelli, in alto la più alta nel Video Sequencer.
  Per ognuna canale, muto, occhio e lucchetto (valgono anche per la sua tavola); accanto
  aggiungi, duplica, elimina, su / giù (scambiano i canali con la vicina), inquadra e
  **Riordina** (impila le tavole nell'ordine dei canali). Cliccando una riga la
  composizione viene selezionata.
- **Una composizione, una clip**: nel Video Sequencer ogni composizione è una meta-clip
  su un solo canale, con dentro una clip per livello (con il loro colore). *Tab* per
  entrarci e regolare volume, pan e muto di ogni livello; il muto e il volume della
  meta valgono per tutta la composizione. Le strip dei livelli dei file salvati prima
  entrano nella meta da sole, tenendo volume e pan.
- **Il Sequencer comanda come la lista dei livelli** (nei due sensi):
  - *muto*: mutare un livello muta subito la sua clip (resta nella meta, muta, senza
    rifare il suono), e mutare la clip nel Sequencer muta il livello;
  - *ordine*: spostando la clip di un livello su un altro canale dentro la meta il livello
    sale o scende anche in Grease Pencil (dentro un gruppo, solo tra i livelli del gruppo);
    spostando la meta su un altro canale cambia l'ordine nella lista Composizioni;
  - *tempo*: spostando la meta più avanti la composizione parte dopo (*Parte dopo*, in
    *Sequencer e ascolto*), con testina e suono;
  - *volume, pan e colore* della clip sono quelli del livello (*Volume clip* e *Pan* sotto
    il volume del livello); valgono anche negli export. I valori animati con keyframe
    restano dei keyframe.
- **Una nuova composizione è un nuovo livello**: nel Sequencer va sopra tutte le altre e
  salta i canali che hanno già una clip; sul tavolo nasce sopra la più alta, allineata,
  invece che sul 3D cursor sopra le altre. Se dopo si aggiunge una clip (un video) su un
  suo canale, la composizione sale fino al primo canale libero: le clip non vengono
  mai spostate.
- **Ottave sopra e sotto senza spostare il disegno** (*Tavola e tempo → Sopra / Sotto*,
  o con le maniglie): aggiungere un'ottava sotto abbassa la nota più bassa e allarga la
  tavola verso il basso, ma ogni tratto resta dov'è nel mondo e suona le stesse note.
- **Maniglie disegnate (rig) in Object Mode**: *<composizione> · Rig* è un terzo
  Grease Pencil, bloccato e mai renderizzato, con maniglie a tratto: a destra la durata
  (si aggancia ai battiti, *Ctrl* per un valore libero; con *Segui In/Out* sposta l'End
  della scena), una goccia sulla testina che sposta il cursore della timeline, e sopra
  e sotto la tastiera le ottave. Si trascinano direttamente (sono gizmo invisibili sopra
  i tratti, quindi il click non seleziona la tavola); mentre trascini si muove solo la
  maniglia, tavola e suono cambiano al rilascio, con un solo passo di Annulla. In Draw,
  Edit e Sculpt Mode spariscono.

## 0.0.21

La griglia è un Grease Pencil a parte

- **Tavola separata**: tastiera, griglia, righe, etichette e ombra del Preview Range stanno in
  *<composizione> · Tavola*, un Grease Pencil figlio della composizione, bloccato e un poco
  dietro al disegno. Cliccando la griglia viene selezionata la composizione, quindi Draw Mode, G/R/S
  e i pannelli lavorano sempre sul Grease Pencil del disegno. La testina resta in cima alla
  composizione. Nella composizione restano solo i tuoi livelli e i tuoi strumenti.
- I file salvati prima spostano la griglia fuori dalla composizione all'apertura (i tratti
  mantengono i loro strumenti). Duplicando una composizione (Shift+D) la copia ha la sua tavola;
  cancellandola sparisce anche la tavola.

## 0.0.20

La composizione segue In e Out della scena; un colore per livello

- **Segui In/Out della scena** (*Tavola e tempo*, attivo per le nuove composizioni): la
  composizione dura da Start a End della scena. Cambiando In o Out la tavola e il suono si
  adattano subito; cambiando la *Durata* (o scalando la tavola) si sposta l'End della scena e le
  altre composizioni che la seguono si adeguano. La prima composizione che la segue porta la
  scena alla sua durata, quindi il suono non cambia. Con le *Sezioni da keyframe* il loop tiene
  la sua durata e l'ultima sezione arriva fino all'End; i keyframe dopo l'End non suonano.
  Ascoltando *Una dopo l'altra* ogni composizione tiene la sua durata. I file salvati prima
  restano com'erano: l'opzione si accende a mano. Il Preview Range continua a scurire la tavola
  fuori dall'intervallo, senza cambiare il suono. Nelle Preferenze: *Nuove composizioni → Segui
  In/Out della scena*.
- **Un colore per livello**: ogni livello ha un suo colore (scelto in automatico, il meno usato,
  o a mano dal pallino nella lista dei livelli) e la sua strip nel Video Sequencer, con *Un
  canale per livello*, ha lo stesso colore. Un livello duplicato prende un colore nuovo.

## 0.0.19

Passata di correzioni (livelli, Solo, file del suono, strumenti registrati)

- **Auto sul livello attivo sente anche gli altri livelli**: in Modalità Modifica e Scultura
  (e con *Usa modificatori*) si possono cambiare i tratti di tutti i livelli insieme, ma veniva
  rigenerato solo il livello attivo e gli altri restavano col suono vecchio. Ora un'impronta
  leggera dei tratti di ogni livello dice se è cambiato: se sì, si rigenera tutto.
- **Eliminare il livello in Solo riaccende gli altri**: con *Elimina livello*, con *Unisci* o
  con la lista dei livelli di Blender, gli altri livelli restavano attenuati al 10%.
- **Annulla/Ripeti con l'aggiornamento automatico spento**: Ctrl+Z riporta le strisce del
  Sequencer a file del suono già cancellati, e la composizione restava muta finché non si
  premeva *Rigenera*. Ora il suono viene riscritto. Anche su Windows, dove il file vecchio a
  volte resta sul disco, la striscia non suona più il suono di prima.
- **Strumenti registrati che non si leggono al primo colpo** (file bloccato per un attimo,
  add-on appena aggiornato): restavano muti per tutta la sessione. Ora la nota viene saltata
  come errore e riletta al render successivo; anche la tastiera non si blocca più.
- **Più robustezza**: una composizione con un errore nella tavola non ferma più
  l'aggiornamento delle altre; la tavola non viene mai ricostruita durante un G/R/S;
  disattivando l'add-on o aprendo un altro file non restano timer o richieste del file
  precedente.

## 0.0.18

Icone degli strumenti più semplici

- **Icone minimali a due toni**: le 34 icone degli strumenti sono ridisegnate con meno
  dettagli, poche forme grandi e due toni come le icone di Blender: la forma principale piena e
  una parte secondaria (manico, asta, bacchette, corde, supporto) più tenue. Si leggono meglio
  a 16 px nei menu e sotto i livelli.

## 0.0.17

Strumenti riordinati, con le loro icone

- **Strumenti per famiglia, registrati e synth insieme**: *+ Strumento* e il menu per cambiare
  strumento hanno tre colonne, *Melodici*, *Percussioni* e *Suoni tuoi*. Ogni famiglia
  (Tastiere, Archi, Legni, Ottoni, Batteria, Metalli...) è un sottomenu con prima gli strumenti
  registrati e poi quelli sintetizzati dello stesso tipo: non c'è più una colonna di synth da
  una parte e i registrati nascosti in *Registrati (web app)* dall'altra. Il menu *Strumento*
  della scheda Materiale segue lo stesso ordine. I file salvati tengono i loro strumenti.
- **Icone degli strumenti nello stile di Blender**: 34 icone monocromatiche e piatte
  (pianoforte, organo, violino, chitarra, arpa, clarinetto, flauto, sassofono, tromba, corno,
  coro, tamburo, cassa, piatto, gong, triangolo, maracas...), leggibili a 16 px. Ogni strumento
  ha la sua o quella della famiglia; si vedono accanto al nome dello strumento sotto i livelli,
  nei menu e nella scheda Materiale. Le disegna `tools/build_icons.py`
  (`tools/instrument_icons.py`).

## 0.0.16

Più veloce e più leggero, con lo stesso suono

Misurato con `tests/bench_perf.py` (3 livelli, 45 tratti, strumenti sintetici e registrati,
eco e riverbero su un livello, *Suono finito* acceso). L'audio calcolato è lo stesso di prima
(differenza massima sotto 1e-5 su mix e strip, verificata dal benchmark).

| | 0.0.15 | 0.0.16 |
|---|---|---|
| Primo calcolo della composizione | 1,0 s | 0,7 s |
| *Auto* dopo un tratto | 0,24 s | 0,19 s |
| *Auto* quando non cambia niente (selezione, undo, cambio modo) | 70 ms | 7 ms |
| *Rigenera* senza cambiamenti | 90 ms | 7 ms |
| Prima nota di tutti gli strumenti registrati | 1,8 s | 0,2 s |
| Memoria dei campioni dopo una nota di ogni strumento | 294 MB | 33 MB |
| Zip | 15,9 MB | 14,9 MB |

- **Strumenti registrati letti nota per nota**: scegliendo il pianoforte non vengono più
  decodificate tutte le sue 23 registrazioni, ma solo quelle delle note che suonano, la prima
  volta che servono. Il primo suono (anche disegnando dal vivo e con la tastiera) arriva prima e
  la memoria resta piccola.
- **Il mix finito resta in memoria**: quando una rigenerazione trova gli stessi livelli di prima
  (un aggiornamento senza modifiche, un undo, *Rigenera*) il *Suono finito* non viene ricalcolato.
- **Riverberi e low cut più rapidi**: una sola FFT di lunghezza veloce invece di blocchi, sui
  canali contigui; la saturazione calcola la curva solo dove il suono la raggiunge.
- **Meno lavoro per le strip**: per capire se il suono di un livello è cambiato i campioni
  vengono confrontati direttamente invece di calcolarne l'hash.
- **Zip più piccolo senza toccare la qualità**: le registrazioni identiche (6 note di
  *Archi* e *Archi pizzicato*, uguali a quelle del violoncello) sono nello zip una volta sola e
  gli MP3 sono compressi anche dallo zip.

## 0.0.15

Pannelli più compatti, modificatori ed effetti per livello

- **Pannelli riordinati** come quelli di Blender (*Proprietà → Dati oggetto → Musica*):
  *Livelli* subito sotto i pulsanti, poi *Tavola e tempo*, *Scala e ritmo*, *Mix* e
  *Sequencer e ascolto*, chiusi di base. Etichette a sinistra e valori a destra, niente
  riquadri: lo stato (note, tempo di calcolo, sezioni) è una riga sola sotto *Auto / Rigenera*.
- **Sotto la lista dei livelli**, per il livello attivo: *Lettura* e *Volume*, poi le tendine
  *Strumenti*, *Lettura e armonia*, *Modificatori* ed *Effetti*. Le stesse tendine ci sono
  anche nella barra laterale della Vista 3D.
- **Modificatori non distruttivi per livello**, come nella web app: *Array*, *Simmetria*,
  *Trasponi*, *Fade* (entrata, uscita o entrambi, su ogni tratto o su tutto il loop) e *Noise*.
  Ognuno ha la sua tendina con la spunta nell'intestazione per accenderlo e spegnerlo; i
  tratti disegnati non cambiano, cambia solo il suono (anche negli export e nel MIDI).
  Lavorano nell'ordine delle tendine. Il "?" del pannello spiega cosa fa ciascuno.
- **Effetti per livello con la spunta**: *Eco*, *Riverbero*, *Lo-fi* e *Canone*. Accesi con
  la quantità a zero partono da un valore che si sente. I file salvati prima tengono accesi
  gli effetti che usavano.
- **Copia e incolla le impostazioni di un livello** (le icone nell'intestazione *Livelli* o il
  menu ▾ della lista): lettura, armonia, modificatori ed effetti; *Incolla in tutti i livelli*
  li dà a tutta la composizione.
- **Web app**: i modificatori dei livelli (e quelli globali) arrivano dal file .json e tornano
  nell'export; il riverbero spento non viene esportato.
- *Suono finito* è una sotto-tendina di *Mix* con la spunta; gli effetti di uno strumento sono
  una tendina chiusa nel pannello *Materiale*.

## 0.0.14

Un canale per livello e volumi giusti

- **Volumi**: lo spessore ora è un volume assoluto, come nella web app (un tratto largo 0,8
  righe suona al massimo, i più sottili più piano). Prima il tratto più spesso di tutta la
  composizione diventava il "100%" e tutti gli altri tratti, di ogni livello e strumento,
  venivano abbassati di conseguenza: aggiungere un tratto spesso abbassava il resto del mix.
  Ora ogni strumento tiene il suo volume, qualunque cosa ci sia negli altri livelli. Anche il
  suono mentre disegni usa la stessa scala.
- **Un canale per livello** (Proprietà → Musica → Riproduzione, attivo di base): ogni livello
  suona su una sua strip nel Video Sequencer, su canali consecutivi a partire da *Canale*
  (il livello più in basso sul canale più basso), con le sue letture ed effetti. Nel Sequencer
  si può cambiare volume, pan o silenziare un singolo livello: le rigenerazioni lo mantengono.
  Ambiente, compressore e limiter del *Suono finito* sono calcolati sul mix e applicati uguali a
  ogni livello, così le strip insieme suonano esattamente come l'export. I livelli dentro i
  gruppi hanno ciascuno la loro strip; un gruppo muto, nascosto o fuori dal Solo toglie le strip
  dei suoi livelli. Spento, torna una strip unica con il mix.
- **Auto solo sul livello attivo** (il pulsante con il livello accanto ad *Auto*): mentre
  disegni, modifichi in Edit Mode o scolpisci, viene rigenerato solo il livello attivo e gli
  altri tengono il suono che avevano. Se cambia qualcos'altro (livelli aggiunti o tolti, muto,
  Solo, volume o lettura di un altro livello, strumenti, tavola) si rigenera tutto, e
  *Rigenera* aggiorna sempre tutti i livelli. Viene scritto un file solo per le strip il cui
  suono è cambiato.

## 0.0.13

Duplicare i livelli, gruppi di livelli, lista come quella di Blender

- Corretto un **crash** duplicando un livello dalla lista dei livelli Grease Pencil di Blender:
  la lista *Livelli e strumenti* restava un attimo indietro rispetto ai livelli e chiedeva a
  Blender un ordine con un buco. Ora l'ordine è sempre valido, e un livello aggiunto,
  duplicato o rinominato nella lista di Blender riceve subito le sue impostazioni (anche con
  Auto spento).
- **Lista dei livelli come quella di Blender**: ogni riga ha icona del livello (o del gruppo),
  lucchetto, occhio, nome, **audio** acceso/spento (si spegne e diventa grigio quando un altro
  livello è in Solo) e **Solo**. Il ♪ non è più nella lista: lo strumento si cambia sotto,
  con il pulsante icona + tendina accanto a ogni strumento. A destra: +, **nuovo gruppo**, −,
  ▾, ↑, ↓.
- Menu **▾** come quello di Blender: *Duplica* e *Duplica con keyframe vuoti* (la copia ha la
  stessa lettura, gli stessi effetti e le **sue copie degli strumenti**), *Mostra tutti*,
  *Nascondi gli altri*, *Blocca tutti*, *Sblocca tutti*, *Blocca i livelli inattivi*,
  *Ignora il blocco dei materiali*, *Unisci sotto*, *Unisci gruppo* (gli strumenti dei livelli
  uniti passano a quello che resta), poi *Nuovo gruppo*, *Sposta nel gruppo*, *Sciogli gruppo*.
  La tavola non viene mai toccata.
- **Gruppi di livelli**: si aprono e chiudono come in Blender; audio, Solo, occhio e lucchetto
  del gruppo valgono per tutti i suoi livelli (un gruppo spento o nascosto non suona, un
  gruppo in Solo fa suonare tutti i suoi livelli). ↑ / ↓ entrano ed escono dai gruppi. Anche
  i gruppi creati nella lista di Blender funzionano, e la testina resta sempre sopra.
- Il gruppo della tavola si chiama **Tavola Composizione** (i file salvati prima vengono
  rinominati all'apertura).

## 0.0.12

Livelli, Solo e Preview Range

- **Lista dei livelli** come quella dei livelli Grease Pencil di Blender (il livello in alto è
  il primo, + / −, ↑ / ↓, doppio clic per rinominare). A destra di ogni livello:
  - **♪** apre gli strumenti e **cambia quello del livello** (lo strumento attivo, se è del
    livello, altrimenti il primo); un livello senza strumenti ne riceve uno;
  - **muto**: il livello resta visibile ma non suona (neanche negli export);
  - **cuffie (Solo)**: suonano solo i livelli in Solo; gli altri tacciono e scendono al 10% di
    opacità, che torna quella di prima togliendo il Solo (se nel frattempo l'hai cambiata a
    mano, resta la tua);
  - onion skin, occhio e lucchetto, come nella lista di Blender.
- Sotto la lista: lettura, volume e strumenti del **livello attivo**; anche accanto a ogni
  strumento c'è **♪** per cambiarlo. I tratti restano dove sono e suonano con il nuovo
  strumento; colore e nome seguono il nuovo strumento, a meno che non li avessi cambiati tu.
- **Preview Range** nella tavola: con l'intervallo di anteprima della scena attivo, la griglia
  prima dell'In e dopo l'Out è oscurata (solo la tavola: tratti e musica non cambiano). Segue
  la testina, anche in "una dopo l'altra" e con le sezioni da keyframe.
- Web app: un livello silenziato nella web app diventa un livello **muto** (visibile) invece
  che nascosto, e viceversa all'export.
- Corretto un crash: con Auto attivo, la rigenerazione aspetta la fine di G/R/S/Alt+S in Edit
  Mode.
- Il menu **♪ Cambia strumento** ha anche i 69 strumenti registrati della 0.0.11, per famiglia
  in *Registrati (web app)* (la famiglia dello strumento attuale ha la spunta).

## 0.0.11

Tutti gli strumenti della web app
- **69 strumenti registrati**, con i loro suoni dentro l'add-on (gli stessi file MP3 della web
  app, VSCO 2 CE e VCSL, CC0): pianoforti, clavicembalo, organo a canne, percussioni intonate,
  archi (anche tremolo, staccato e pizzicato), arpa, legni, ottoni e 37 percussioni registrate.
  Si scelgono per famiglia in *+ Strumento → Registrati (web app)* e nel menu *Strumento* del
  materiale. Suonano come nella web app: la nota registrata più vicina riaccordata sulla linea,
  le note tenute in loop con dissolvenze oltre la fine della registrazione, i colpi interi, gli
  sfregamenti e i rullati lunghi quanto il tratto.
- **Organo, Coro e Ottoni**: i tre synth della web app che mancavano.
- **Ambiente del riverbero** (scheda Composizione, sotto *Ambiente*): Sala (sintetica, come
  prima), Stanza, Auditorium o Chiesa, dalle stesse risposte all'impulso della web app
  (HybridReverb2, CC BY-SA 4.0). Vale per tutti i riverberi della composizione.
- **Progetti della web app**: ogni strumento della web app si apre col suo strumento
  dell'add-on (prima i registrati diventavano il synth più vicino) e torna uguale salvando;
  anche l'ambiente del riverbero va e viene.
- **Importa MIDI**: un programma General MIDI che ha uno strumento registrato (violoncello,
  pianoforte, tromba…) usa quello; le note di batteria senza synth (conga, bongo, triangolo…)
  usano il colpo registrato.
- I synth con lo stesso nome di un registrato si chiamano ora *Flauto (synth)*, *Ocarina
  (synth)*, *Archi (synth)* e *Marimba (synth)*. I file .blend salvati prima tengono i loro
  strumenti.
- Lo zip passa da ~0,4 a ~16 MB per i suoni. `tools/build_addon_instruments.py` rigenera la
  lista degli strumenti dalla web app.

## 0.0.10

Timeline e finestre
- **Senza Timeline** (nessun Dope Sheet, Sequencer o 3D Viewport aperto, ad esempio solo
  Proprietà): la riproduzione fermata da Ctrl+Z riparte lo stesso (prima non ripartiva) e
  l'avviso dei modificatori sceglie una finestra con uno schermo valido. Tutti i giri sulle
  finestre saltano quelle senza schermo.
- **Timeline ridotta a barra** (solo l'intestazione): il suono nella Timeline non viene più
  calcolato né disegnato in una regione alta pochi pixel; in una Timeline bassa la forma d'onda
  resta dentro la regione invece di uscire sopra i numeri dei fotogrammi.
- *Suona con la tastiera*: il testo di aiuto va nell'intestazione dell'editor da cui è partito e
  viene tolto da lì all'uscita, anche se nel frattempo il mouse è su un altro editor; se l'editor
  non c'è (o è stato chiuso) va nella barra di stato.
- Creando una composizione, la vista frontale salta gli editor 3D senza vista; la composizione
  si crea anche quando il contesto non ha una collezione attiva (nella collezione della scena).
- Una composizione non collegata a nessuna scena non fa più fallire la rigenerazione chiamata da
  un timer senza finestra.

Prestazioni
- Il suono nella Timeline non rilegge più tutte le strip e i file audio (un `os.stat` per strip)
  e non ricrea la geometria a ogni ridisegno: durante la riproduzione disegna ciò che ha già
  pronto e ricalcola solo quando cambia qualcosa (suono rigenerato, strip spostate, impostazioni,
  zoom o scorrimento della vista).
- Linee della Timeline (curve del flusso ottico, contorni) con lo shader `POLYLINE_UNIFORM_COLOR`:
  restano spesse 2 px anche con Vulkan e Metal, dove `line_width_set` non ha effetto.
- **Suono finito più veloce**: il taglio dei bassi del master usava una sola FFT lunga quanto il
  loop, lentissima quando la lunghezza in campioni ha fattori primi grandi (quasi sempre, con
  durate libere): ora è una convoluzione circolare equivalente (differenza < 1e-9). Il master di
  un loop di 30 s passa da 1,7 s a 0,4 s, uno di 16 s da 0,6 a 0,2 s.
- La risposta all'impulso del riverbero e il suo spettro si calcolano una volta sola e i due
  canali si convolvono insieme.

## 0.0.9

- **Progetti della web app (.json)**: importando una composizione della web app, i nuovi strumenti
  (strumenti campionati di pianoforte, archi, fiati e ottoni, percussioni registrate, articolazioni
  degli archi, pianoforte a coda, clavicembalo, organo a canne, xilofono, campane tubolari, kalimba,
  flauto dolce, armonica, darbuka e cajón) diventano il suono più vicino dell'add-on invece di
  perdersi.
- Esportando verso la web app, triangolo, crash e campanaccio diventano ocarina, piatto crash e
  campanaccio della web app (prima flauto, charleston aperto e rimshot).

## 0.0.8

Blender 5.3
- Richiede **Blender 5.3** (tutti i test passano sulla 5.3.0).
- **?** nell'intestazione dei pannelli (Musica, Lettura, Strumento musicale, Output e barra
  laterale *Musica*): l'aiuto di quella parte in testo formattato (`label_markdown`, nuovo
  nella 5.3), come il **?** della web app. Via i testi fissi dai pannelli: restano i tooltip.
- Messaggi lunghi su più righe (`label_multiline`, 5.3): l'errore di generazione si legge per
  intero e non viene più tagliato a 120 caratteri; l'avviso dei keyframe va a capo.
- Blender 5.3 ha tolto la durata dei frame Grease Pencil: una pausa è un keyframe vuoto
  (*Insert Blank Frame*); con *Sezioni da keyframe* diventa una sezione muta (con test).
- I tratti chiusi con l'opzione **Ciclico** dei nuovi strumenti di disegno della 5.3 suonano
  anche il tratto di ritorno (già letto dall'add-on, ora spiegato nel **?** della Lettura).
- La barra laterale *Musica* funziona con la nuova ricerca della 5.3 (Ctrl+F), senza
  modifiche.

Allineamento con la web app
- **Progetto della web app (.json)**: *File → Import* lo apre come composizione (tratti,
  livelli con lettura, volume e riverbero, pennelli, tempo del disegno, suoni registrati come
  Campione, Beat come livello di colpi); *File → Export* (o *Output → Web app*) salva la
  composizione da aprire sull'iPad.
- *Shift+A → Doodle Music → Composizione dalla web app…*.

Suona mentre disegni
- **Suona mentre disegni** (come nella web app): in Draw Mode senti la punta del tratto mentre
  lo disegni, con lo strumento del tratto e la lettura del livello. Quantizzata, Legato e
  Gesto: una nota ogni volta che la punta entra in un'altra riga (nella scala scelta);
  Ottica: un suono tenuto che segue la punta (theremin); percussioni: un colpo all'inizio.
  Lo spessore dà il volume, insieme al volume dello strumento e del livello. Si spegne nelle
  Preferences o con il pulsante a matita accanto a *Suona con la tastiera*.

Strumenti e suono finito
- **Suono finito** (Lettura, attivo di default): sul mix della composizione passano una sala
  comune (*Ambiente*), un compressore morbido che lega i livelli, una saturazione dolce e un
  limiter. Il suono resta pieno e non distorce mai, anche con tanti tratti spessi insieme;
  il loop resta senza giunture. È la stessa catena della web app.
- **Armonia** per livello (add-on e web app): *Terza sopra*, *Sesta sotto*, *Accordo*,
  *Quinta*, *Ottava sotto*. Le voci aggiunte restano nella scala della composizione (con la
  scala cromatica armonizzano in maggiore), suonano più piano della melodia e finiscono anche
  nel MIDI. Le percussioni e le forme piene non vengono armonizzate; nelle letture legate le
  voci aggiunte non si legano alla melodia.
- **Nuovi strumenti** nell'add-on, come nella web app: *Piano elettrico* (FM), *Marimba*,
  *Pad*, *Basso*; percussioni *Charleston aperto*, *Rimshot*, *Shaker*. L'import MIDI li usa
  per pianoforti, marimba/xilofono, bassi, pad e per le note GM della batteria corrispondenti.
- Le nuove composizioni partono in scala **Maggiore** (come la web app): ogni nota cade in
  scala. Si cambia in *Lettura* o nelle Preferences; le composizioni esistenti non cambiano.
  L'import MIDI in una nuova composizione usa la scala cromatica, così le note del file
  restano esatte.

Correzioni
- **Eliminare uno strumento spostava i tratti degli strumenti successivi su un altro
  strumento** (due slot più in basso): Blender li sposta già da solo quando toglie lo slot.
- **Tastiera e griglia nere dopo Ctrl+Z** in Draw Mode su uno strumento appena aggiunto: la
  tavola ritrova i suoi colori subito dopo l'annullamento (con test).

## 0.0.7

- Nuovo nome: **Doodle Music** (menu Shift+A, pannelli, Preferences). L'identificativo
  dell'estensione resta `grease_pencil_to_music`, così si aggiorna sopra la 0.0.6 e i file
  .blend restano compatibili.

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
