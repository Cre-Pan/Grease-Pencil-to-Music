# Grease Pencil to Music

Add-on per **Blender 5.2** che trasforma i disegni Grease Pencil in musica.
Si ispira al *suono disegnato* di Norman McLaren e Daphne Oram (Oramics): si
disegna su una tavola, e la tavola suona.

![La tavola musicale](docs/tavola.png)

- **X = tempo** (linee verticali = secondi, più tenui i battiti)
- **Z = altezza** (una riga per semitono, tastiera verticale a sinistra: tasti alti quanto le righe, neri verso la griglia)
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
   griglia, etichette e testina) sta in gruppi di livelli bloccati dentro l'oggetto stesso.
   La composizione parte **vuota**: un livello con un solo strumento (Flauto). La vista
   passa a frontale, *Solid → Texture*; si resta in Object Mode (passa a **Draw Mode** per
   disegnare).
2. In *Proprietà → Dati oggetto → Livelli e strumenti*: **Nuovo livello** aggiunge un
   livello; dentro ogni livello ci sono i suoi strumenti e **+ Strumento** ne aggiunge
   altri (sintetizzati, percussioni, Campione, Libreria). Il pulsante accanto a uno
   strumento lo rende quello con cui disegni.
3. Disegna. Appena stacchi la penna il suono viene rigenerato.
4. Premi **Spazio**: la testina rossa scorre e senti il disegno, in loop.
   Nella **Timeline** vedi la forma d'onda e i blocchetti delle note (vedi sotto).
5. Modifica in **Edit Mode** o **Sculpt Mode**: il suono si aggiorna.
6. **Shift+D** duplica tutta la composizione: ogni copia è un nuovo "piano di lavoro"
   con le sue regole (strumenti, volumi, muti) e il suo suono.
7. **Ascolto** (pannello principale): *Tutte insieme*, *Solo l'attiva* oppure
   *Una dopo l'altra*.
8. In **Object Mode**, **S X** allunga o accorcia la composizione e **S Z** mostra più o
   meno ottave, senza deformare i tratti.

### Dove sono le impostazioni

| Dove | Cosa |
|---|---|
| Proprietà → **Dati oggetto** → Musica | stato, tavola e tempo, lettura, **livelli con i loro strumenti**, canone, canale del Sequencer |
| Proprietà → **Materiale** → Strumento musicale | tipo di strumento, volume, campione, effetti dello strumento |
| Proprietà → **Output** | export WAV / MP3 / MIDI, mix di tutta la scena |
| Proprietà → **Scena** | ascolto delle composizioni (canali, ordine, muto) |
| *File → Import / Export* | MIDI → Grease Pencil; composizione in WAV / MP3 / MIDI |
| Barra laterale **N → Musica** | versione compatta per quando disegni |
| Preferences dell'add-on | mappatura degli attributi (con preset), valori delle nuove composizioni, tastiera MIDI |

### Suonare con la tastiera

*Suona con la tastiera* (pannello N o Dati oggetto): **A W S E D F T G Y H U J K** sono le
note (come i tasti di un pianoforte), **Z / X** cambiano ottava, **R** registra (e fa partire
il play): ogni tasto tenuto diventa un tratto sul livello attivo. **Esc** esce.

Una **tastiera MIDI** collegata suona insieme alla tastiera del PC (velocity = volume, pedale
di sustain); la porta si sceglie nelle Preferences (vuoto = la prima trovata). Con le
sezioni da keyframe la nota registrata finisce nel disegno della sezione che sta suonando.

### Suono nella Timeline

Nell'header della Timeline / Dope Sheet, accanto agli Overlay, c'è il pulsante con la
**nota musicale**: lo accende e lo spegne, la freccia apre le opzioni.

| Opzione | Scelte |
|---|---|
| Sorgente | **tutto** (predefinita: ogni strip audio del Sequencer su qualsiasi canale, gli Speaker e le composizioni con le loro note), composizione attiva, tutte le composizioni, una composizione, mix del Sequencer, un canale del Sequencer, Speaker |
| Forma d'onda | picchi, piena, contorno, inviluppo RMS, nessuna |
| Mostra | note (MIDI), flusso ottico (curve dei tratti in lettura ottica) |
| Aspetto | altezza, opacità, **colore audio** (il suono che non è una composizione) e **colore composizioni** |

Con *Tutto* vedi insieme l'audio "normale" (una voce, una base, la musica di un video) e
le composizioni, ognuno col suo colore: la strip di una composizione non viene contata due
volte. Si leggono anche i suoni impacchettati nel .blend.

Tutto si controlla dalla barra laterale **N → Musica**:

| Pannello | Cosa contiene |
|---|---|
| Grease Pencil to Music | stato, muto, avvisi, *Auto* (aggiornamento automatico), *Genera suono*, **Ascolto** (insieme / solo l'attiva / una dopo l'altra) |
| Tavola e tempo | BPM, durata del loop, nota più bassa, ottave, **etichette dei tasti** (solo Do, tasti bianchi, tutte, nessuna), griglia |
| Lettura | scala e tonica, quantizzazione ritmica, **swing**, nota minima, volume, **Usa modificatori** |
| Livelli e strumenti | **Nuovo livello**, ↑ / ↓; ogni livello è un riquadro con lettura, occhio (nascosto e muto), cestino e i suoi **strumenti** (colore, nome, **volume**, occhio); **+ Strumento**; volume, forme piene, canone ed effetti del livello |
| Esporta | **WAV**, **MP3**, **MIDI** |

### Come viene letto un tratto

Cinque letture per livello, con le stesse lettere della web app (come i metodi di
fusione di Procreate):

- **Q · Quantizzata**: il tratto cambia nota ogni volta che attraversa una riga.
  Le note vengono agganciate alla scala scelta e alla griglia ritmica (con swing).
- **QL · Quantizzata legata**: le note sono quelle della scala, ma il tratto è un'unica voce
  che scivola da una nota all'altra senza riattaccare (tempo di legato regolabile); anche
  i tratti vicini dello stesso strumento si legano tra loro.
- **O · Ottica**: alla McLaren, l'altezza segue la linea in modo continuo, con glissandi.
  Chitarra e campana tengono il suono (un tono morbido sotto il pizzico) e scivolano con
  la linea; le percussioni restano colpi.
- **OL · Ottica legata**: come Ottica, ma i tratti dello stesso strumento più vicini di
  *Unisci tratti entro* (1 battito di default) diventano una sola voce, che scivola
  nella pausa invece di riattaccare. Il MIDI conserva le note di ogni tratto.
- **G · Gesto (tempo del disegno)**: il ritmo è quello della mano. Il tratto parte dove inizia
  e dura quanto hai impiegato a disegnarlo: una linea verticale tracciata in fretta è una
  scala rapida, una lenta è un arpeggio lento. I tratti senza tempo di disegno (import MIDI,
  registrati) vengono letti come *Quantizzata*.
- **Canone** (per livello): il livello si ripete in 2–4 voci che entrano dopo N battiti,
  ognuna trasposta di N semitoni rispetto alla precedente; in loop le voci rientrano
  dall'inizio, come in un canone a ruota.
- **Sezioni da keyframe** (*Tavola e tempo*): ogni keyframe Grease Pencil apre una sezione
  (strofa, ritornello…) che ripete il suo disegno fino al keyframe successivo; l'ultima
  suona un loop. La testina riparte a ogni sezione e la scena dura quanto il brano.
- **Forma piena** (tratto riempito): *Cluster tonale* suona tutte le note della scala che
  copre; *Banda di rumore* è rumore filtrato tra il bordo inferiore e superiore della forma
  (come il sintetizzatore ANS).
- Un punto (un tocco) è una nota breve; le percussioni suonano sempre un colpo solo.
- Un tratto che torna indietro nel tempo (semicerchio, cerchio, zig-zag) suona in ogni sua
  parte, come sotto un lettore ottico: un semicerchio sono due voci.

### Strumenti (sintetizzati)

Melodici: Flauto, Ocarina, 8-bit, Synth, Archi, Chitarra (Karplus-Strong), Campana (FM).
Percussioni: Percussioni (generiche, dipendono dalla riga), Cassa, Rullante, Charleston,
Piatto, Battimani, Tom (intonato sulla riga), Campanaccio.
**Campione**: qualsiasi suono di Blender (*Carica suono…* o un suono del Sequencer),
intonato sulla nota base. **Libreria**: un SoundFont (`.sf2`) o uno strumento SFZ (`.sfz`),
con scelta del preset; librerie libere: GeneralUser GS, FluidR3 (SF2), Versilian VCSL (SFZ,
CC0) — vedi [RESEARCH.md](RESEARCH.md). Ogni strumento ha anche i suoi effetti (scheda Materiale). Nel MIDI le percussioni usano
le note General MIDI della batteria.

### Preferences dell'add-on

| Voce | Opzioni (default in grassetto) |
|---|---|
| Nomi delle note | **C D E F G A B**, Do Re Mi Fa Sol La Si |
| Riprendi il play dopo Ctrl+Z | **sì** |
| Spessore | **Volume**, Volume + Vibrato, Vibrato, Brillantezza, Nessuno |
| Opacità | **Brillantezza**, Volume, Nessuno |
| Vertex color | **Nessuno**, Pan stereo (rosso = sinistra, blu = destra), Brillantezza |
| Morbidezza | **Attacco**, Nessuno |

**Preset**: *Classico* (quello sopra), *Espressivo* (jitter = vibrato, colore = pan),
*McLaren* (spessore e opacità = volume, colore chiaro = brillante), *Pulito* (ogni tratto
suona uguale).

*Volume + Vibrato* separa lo spessore in due: l'andamento lento è il volume,
l'irregolarità veloce (per esempio il jitter del pennello Ink) diventa vibrato.

## Web app per iPad (senza App Store)

La stessa idea gira anche nel browser, pensata per iPad e Apple Pencil: sezioni **Disegna**,
**Beat** (step sequencer con pattern A e B), **MIDI** (piano roll, tastiera sul vetro, import
.mid), **Onda** (disegni la forma d'onda di uno strumento) ed **Esporta** (WAV + MIDI in .zip,
PNG, progetto .json).

Per installarla come app sulla schermata Home, che funziona anche offline:

1. Su GitHub: *Settings → Pages → Build and deployment → Deploy from a branch*, scegli il
   branch con questa cartella `docs/` (oggi `claude/v0.0.1-prototype`, `main` dopo il merge)
   e la cartella **/docs**, poi *Save*.
2. Dopo un minuto apri in **Safari** sull'iPad
   `https://cre-pan.github.io/Grease-Pencil-to-Music/app/`.
3. *Condividi → Aggiungi alla schermata Home* (anche da Chrome per iPad: Condividi nella barra
   degli indirizzi → Aggiungi alla schermata Home). Si apre a tutto schermo e funziona anche
   senza connessione; i disegni restano salvati nell'app. Per esportare usa il foglio di
   condivisione → *Salva su File*.

**Aggiornamenti**: quando il branch di GitHub Pages cambia, l'app installata scarica la nuova
versione la prima volta che la apri con la connessione e mostra *Nuova versione pronta →
Aggiorna*. I disegni restano. Il link di GitHub Pages è pubblico: chi lo ha può usare l'app,
ognuno con i propri disegni sul proprio dispositivo.

Il sorgente è `web/app.html`; `python tools/build_web.py` rigenera `docs/app/` (pagina,
manifest, icone e service worker).

**Lingue**: italiano, inglese, francese, spagnolo, cinese (semplificato) e russo, da
*Impostazioni → Interfaccia → Lingua*. Al primo avvio l'app sceglie la lingua dell'iPad. Le
frasi sono scritte in italiano nel sorgente: `python tools/i18n_extract.py` le raccoglie in
`web/i18n/source.json`, le traduzioni stanno in `web/i18n/<lingua>.json` e
`python tools/build_i18n.py` le inserisce in `web/app.html` (poi `tools/build_web.py`).
Per aggiungere una lingua basta un nuovo file `.json` con le stesse chiavi.

**Icona personalizzata**: `web/icon-template.png` (e `.svg`) è una griglia di costruzione a
sezione aurea, nello stile della griglia delle icone Apple, con in rosso la maschera
arrotondata che applica iPadOS. Disegna il logo su una tela quadrata 1024 o 2048 px con il
template come livello in alto, esporta un PNG quadrato senza angoli arrotondati come
`web/icon.png` e rilancia `tools/build_web.py`. I template ufficiali sono negli
[Apple Design Resources](https://developer.apple.com/design/resources/).

### Pennelli

Tocca il pennello (in alto a destra) quando è già attivo per aprire la libreria. Ogni pennello
cambia anche il suono.

| Pennello | Aspetto | Suono |
|---|---|---|
| Liscio | segue la pressione | lo spessore è il volume |
| Inchiostro ruvido | rumore su posizione e spessore, come *Ink Rough* di Blender (slider Ruvidezza) | vibrato e tremolo irregolari |
| Matita | grana di grafite, sottile | più scuro |
| Pennarello | spessore costante, punta piatta | volume fermo |
| Aerografo | bordi sfumati | attacco lento |
| Puntini | un punto a ogni passo della griglia | arpeggio di note brevi |
| Pieno | chiude la forma da solo e la riempie | cluster: tutte le note coperte |

**Gomma**: tocca la gomma già attiva per scegliere *Tratto intero*, *Punti* (cancella solo dove
passi e divide il tratto) o *Fino agli incroci* (toglie il pezzo tra i due incroci più vicini
con altri tratti, come in Blender), e la dimensione.

**Lazo** (icona tratteggiata, tasto S): disegna un giro sopra i tratti del livello attivo: viene
preso ogni tratto che ha almeno un punto dentro. Trascinali (si agganciano alla griglia e ai
semitoni), poi Duplica, Strumento attuale, Elimina o Fine.

**Live** (icona registra, tasto R): appoggia la Pencil sulla tavola e il tempo scorre da solo
con il play; muovi la Pencil solo in alto e in basso per la nota, premi di più per suonare più
forte, alzala per una pausa. Ogni giro del loop diventa un nuovo tratto.

**In alto**: a sinistra il menu ⋯ (Nuova, Salva, Apri composizione, Importa un video, Carica
l'esempio), le Impostazioni e il nome (toccalo per rinominare); a parte il **?**, che spiega
ogni cosa della schermata in cui sei. A destra tre isole: strumenti, **Livelli** e il colore
(lo strumento). Se manca spazio le sezioni mostrano solo le icone e le isole si mettono in
colonna.

**Livelli**: tieni premuto un livello per *Duplica*, *Unisci sotto*, *Cancella* (toglie i
tratti, il livello resta) ed *Elimina livello*, in un menu vicino al dito; tienilo e
trascinalo per spostarlo. Con un solo livello, scorrere a sinistra lo cancella.

**Gesti uguali ovunque** per i pulsanti acceso/spento (M del beat, altoparlante e occhio dei
livelli): tocco = solo quello; tieni premuto = solo quello acceso, gli altri spenti (di nuovo:
tutti accesi); trascina in verticale = tutti quelli che tocchi come il primo. Tenere premuto
un livello, un tuo suono o un'onda apre il suo menu vicino al dito.

**Immagini e video**: *⋯ → Importa immagine o video…* li apre in finestre mobili sopra la
tavola (anche più di una); il video segue play, stop e ogni giro del loop. Si spostano dalla
barra e si ridimensionano dall'angolo; l'audio del video è spento finché non lo accendi; dove
il browser lo permette c'è anche il picture in picture di sistema. Il pulsante con
l'immagine (o *⋯ → Sfondo della tavola…*) mette il file **dietro i tratti**, per ricalcarlo:
opacità e adattamento in *Impostazioni → Tavola*.

**Esporta**: Audio e MIDI (.zip, WAV, MIDI, tracce separate), **Video** della tavola con la
linea del tempo che scorre e la musica (MP4 su iPad, 720p o 1080p, registrato in tempo reale),
**Immagine** PNG (con la tavola o trasparente, livelli insieme o un PNG per livello in un
.zip, 1×–3×), Progetto (.json). Dopo un'eliminazione il messaggio in basso ha **Annulla**.

**MIDI**: in alto a destra *Seleziona* (fai un giro sulle note e trascinale: si spostano i
tratti da cui vengono), *Registra* e **↻ Ricarica l'audio** (se non senti più niente), più
Livelli e strumento.

**Impostazioni** (icona con i cursori): un pannello grande con le categorie Tavola, Pennello e
Pencil (sensibilità della pressione con la curva, spessore minimo, *Solo Pencil*), Audio,
Interfaccia (tema, nomi delle note, sezioni come icone) e Info con le scorciatoie.

**Solo Pencil**: in automatico, appena usi la Pencil le dita non disegnano più: scorrono il
Beat, ingrandiscono la tavola e fanno i gesti.

**Beat**: l'interruttore accanto al titolo accende o spegne il beat; i template sono nel menu
≡ a destra. *Griglia | Pad*: in Pad suoni la batteria dal vivo su otto pad colorati (anche con
i tasti A S D F G H J K) e con *Registra nel pattern* i colpi entrano nel passo più vicino
mentre il loop gira. Con *Pattern A e B* acceso ogni traccia ha due pattern: *Modifica A | B* sceglie
quale modifichi (il pallino verde dice quale sta suonando), *Copia A in B* parte da una copia,
la *Sequenza* dice quale suona in ogni battuta (tocca: A → B → pausa). I template mettono in
B una variazione con un fill e suonano A A A B.

**Onda**: disegni un ciclo del suono, come la colonna sonora ottica di Norman McLaren. Il
bordo sopra della forma è il canale sinistro, quello sotto il destro; il riempimento tra i
due è il suono. *Tratto* disegna un bordo (sopra o sotto, l'altro è lo specchio), *Pieno*
chiude ogni linea in una forma che dà entrambi i bordi; passando dall'uno all'altro il disegno
resta. *Simmetrico* fa sentire lo stesso suono nelle due orecchie; il **?** in alto spiega i passi;
due dita annullano, tre ripetono. *Disegna con questa onda* la usa come strumento; le onde sono anche in *Strumento →
Onde disegnate* ed entrano nel progetto .json.

### Gesti della web app

| Gesto | Azione |
|---|---|
| Tocco con due / tre / quattro dita | annulla / ripeti / play-stop |
| Pinch, due dita che trascinano | ingrandisci, sposta la tavola |
| Tieni premuto su un tratto | contagocce: strumento e opacità |
| Tocco sui numeri di battuta | da dove parte il play |
| Livello: scorri a sinistra / a destra | elimina / seleziona più livelli |
| Livello: tieni premuto e trascina | cambia l'ordine |
| Occhio o altoparlante tenuti premuti | solo quel livello visibile / udibile |
| Nome di una traccia del beat tenuto premuto | volume e intonazione |
| Pennello o gomma già attivi, tocco | libreria dei pennelli / modi della gomma |
| Livello, suono o onda tenuti premuti | menu vicino al dito |
| M / altoparlante / occhio: tocco · tieni · trascina | solo questo · solo questo acceso · tutti come il primo |
| Lazo: cerchia, poi trascina | sposta i tratti scelti |

## Limiti noti (0.0.x)

- Senza *Sezioni da keyframe* viene letto solo il keyframe attivo all'inizio della scena.
- Le librerie SF2/SFZ usano un campione per tasto (niente strati di velocity né inviluppi
  del SoundFont).
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

Vedi [DESIGN.md](DESIGN.md) per decisioni e roadmap, [RESEARCH.md](RESEARCH.md) per le fonti, [CHANGELOG.md](CHANGELOG.md) per le versioni.

## Licenza

GPL-3.0-or-later. La visualizzazione nella Timeline si ispira a
[Timeline Audio Visualizer](https://github.com/OwOpq/timeline-audio-visualizer) (GPL-3.0).
