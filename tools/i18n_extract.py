"""Collect the Italian interface strings of web/app.html into web/i18n/source.json.

Markup: text nodes and title / aria-label / placeholder attributes.
Script: string literals that read like interface text; in template literals every
${...} becomes {0}, {1}, ... (the same placeholders the runtime matches).
"""
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "web" / "app.html").read_text(encoding="utf-8")
script_at = SRC.index("<script>")
MARKUP, SCRIPT = SRC[:script_at], SRC[script_at:]
SCRIPT = SCRIPT[: SCRIPT.find("// I18N:BEGIN")] + SCRIPT[SCRIPT.find("// I18N:END"):] if "// I18N:BEGIN" in SCRIPT else SCRIPT

found = []
def add(s):
    s = " ".join(s.split())
    if s and s not in found and re.search(r"[A-Za-zÀ-ÿ]{2}", s):
        found.append(s)

class P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("style", "svg"):
            self.skip += 1
        for k, v in attrs:
            if k in ("title", "aria-label", "placeholder") and v:
                add(v)
    def handle_endtag(self, tag):
        if tag in ("style", "svg"):
            self.skip -= 1
    def handle_data(self, data):
        if not self.skip and data.strip():
            add(data)

body = MARKUP[MARKUP.index("</style>") + 8:]
P().feed(body)

CODEY = re.compile(r"^(#|\.|[a-z]+[A-Z]|[a-z-]+$|[a-z]+:|<|M[\d ]|\d|var\(|rgba|https?:|data-|aria-|image/|audio/|video/|application/|[A-Z_]+$|[a-z]+\.[a-z]+)")
ITALIAN = re.compile(r"[a-zàèéìòù]{3,}", re.I)
def literal_ok(s):
    if not ITALIAN.search(s) or CODEY.search(s):
        return False
    if "<" in s or "=>" in s or "function" in s or "px" in s.split()[:1]:
        return False
    return " " in s.strip() or s[:1].isupper()

for m in re.finditer(r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'|`((?:[^`\\]|\\.)*)`', SCRIPT):
    s = m.group(1) if m.group(1) is not None else m.group(2) if m.group(2) is not None else m.group(3)
    if s is None:
        continue
    if m.group(3) is not None:
        if "<" in s:
            continue
        n = iter(range(20))
        s = re.sub(r"\$\{[^}]*\}", lambda _: "{%d}" % next(n), s)
    s = s.encode().decode("unicode_escape").encode("latin-1").decode("utf-8") if "\\" in s else s
    if literal_ok(s):
        add(s)

out = ROOT / "web" / "i18n" / "source.json"
print(len(found), "strings found")

# ---- curation: code that looks like text, and the composite phrases built with "+" ----
DROP = {"use strict", "SMP:", "WAV:", "Nota saltata:", "Render non riuscito:", "MThd", "MTrk", ").trim() ||",
        "(prefers-color-scheme: dark)", "top left", "top right", "bottom center", "ctx-menu glass", "ArrowUp",
        "ArrowDown", 'width="16" height="16" viewBox', "swatch sample", "chip wave-chip", "Enter", "Escape",
        "input, select, textarea", "Space", "XxxxXxxxXxxxXxxx", "Sol", "Sol♯", "AbortError", "Pronto:", "Salvato:",
        "Ora suonano:", "» è nascosto: rendilo visibile per disegnare.", "è fuori dalla tavola: cambia la nota più bassa in Tavola.",
        "Tastiera MIDI:", "MIDI non leggibile:", "Progetto aperto:", "Progetto non leggibile:", "Come funziona:",
        "· due dita per annullare", "· vuoto", "Fai suonare", "(tieni premuto: solo questo)", "s · tocca per fermare",
        "· {0} tratti ora suonano Piano elettrico", "Strumento:", "Battuta", "Registrazione", "Nascondi", "Mostra", "Silenzia",
        "Spazio · B · E · S · L", "Do Re Mi", "Italiano", "English", "Français", "Español", "script, style, [data-notr]"}
ADD = ["Pronto: {0}", "Salvato: {0}", "Ora suonano: {0}", "«{0}» è nascosto: rendilo visibile per disegnare.",
       "{0} è fuori dalla tavola: cambia la nota più bassa in Tavola.", "Tastiera MIDI: {0}", "MIDI non leggibile: {0}",
       "Progetto aperto: {0}", "Progetto non leggibile: {0}", "Come funziona: {0}", "due dita per annullare",
       "tocca con due dita per annullare", "Tela nuova", "Eliminato", "vuoto", "Fai suonare {0} (tieni premuto: solo questo)",
       "Silenzia {0} (tieni premuto: solo questo)", "Nascondi {0} (tieni premuto: solo questo)",
       "Mostra {0} (tieni premuto: solo questo)", "Silenzia {0}", "tocca per fermare", "{0} tratti ora suonano Piano elettrico",
       "Strumento: {0}", "Battuta {0}", "Battute {0}", "{0}: pausa", "{0}: pattern {1}", "Registrazione {0}", "Onda {0}",
       "Livello {0}", "{0} battute", "{0} battuta", "1 tratto", "1 livello", "rilevata", "leggera", "decisa", "media",
       "pausa", "spessore", "Registrazione", "Spazio", "nessuna nota chiara: {0}"]
found = [s for s in found if s not in DROP]
# keep the strings added by hand earlier (labels built in code the scan cannot see)
prev = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
for s in ADD:
    if s not in found:
        found.append(s)
for s in prev:
    if s not in found and s not in DROP:
        found.append(s)
out.write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(found), "after curation")
