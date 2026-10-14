"""Inline web/i18n/<lang>.json into web/app.html (between the I18N:BEGIN/END markers).

Each file maps the Italian interface strings of web/i18n/source.json to one language.
Missing strings are reported; extra keys (no longer in the source) are dropped.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "web" / "app.html"
I18N = ROOT / "web" / "i18n"
LANGS = ["en", "fr", "es", "zh", "ru"]

source = json.loads((I18N / "source.json").read_text(encoding="utf-8"))
table = {}
for lang in LANGS:
    path = I18N / f"{lang}.json"
    if not path.exists():
        print(f"{lang}: missing file")
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = [s for s in source if s not in data]
    bad = [s for s in source if s in data and set(re.findall(r"\{\d\}", s)) - set(re.findall(r"\{\d\}", data[s]))]
    table[lang] = {s: data[s] for s in source if s in data and data[s] and s not in bad}
    print(f"{lang}: {len(table[lang])}/{len(source)}" + (f", missing {missing[:5]}" if missing else "") + (f", bad placeholders {bad[:5]}" if bad else ""))

html = APP.read_text(encoding="utf-8")
block = "// I18N:BEGIN\nconst I18N = " + json.dumps(table, ensure_ascii=False, separators=(",", ":")) + ";\n// I18N:END"
html, n = re.subn(r"// I18N:BEGIN\n.*?// I18N:END", lambda _: block, html, flags=re.S)
assert n == 1, "markers not found"
APP.write_text(html, encoding="utf-8")
print("inlined", sum(len(v) for v in table.values()), "strings")
