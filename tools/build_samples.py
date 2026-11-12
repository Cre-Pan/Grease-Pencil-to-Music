# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the sampled instruments of the web app from VS Chamber Orchestra: Community Edition.

    git clone https://github.com/sgossner/VSCO-2-CE        # CC0 1.0 (public domain)
    python tools/build_samples.py path/to/VSCO-2-CE         # -> docs/app/samples/, web/app.html

One velocity layer per instrument, a few notes per octave, mono MP3. Every file is trimmed
to its first sound, cut to a few seconds with a fade, levelled note by note, and named
after the MIDI note it was measured to be (the library's octave numbers vary by
instrument). The zone list is written into web/app.html between the SAMPLES markers.
Needs ffmpeg and numpy.
"""

import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "app" / "samples"  # served next to the web app; tools/build_web.py lists them
APP = ROOT / "web" / "app.html"
SR = 44100
NOTE = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}

# id: (folder, file filter, preferred layers in order, longest seconds, fade seconds)
SETS = {
    "PIANO": ("Keys/Upright Piano", r"Player_dyn2_rr1_(\d+)\.wav", (), 6.0, 0.6),
    "FLUTE": ("Woodwinds/Flute/susvib", r"_([A-G]#?\d)_v1_1\.wav", (), 4.0, 0.3),
    "CLARINET": ("Woodwinds/Clarinet/susLong", r"_([A-G]#?\d)_v(\d)_rr1_sum\.wav", ("2", "3", "1"), 4.0, 0.3),
    "OBOE": ("Woodwinds/Oboe/Vib", r"_([A-G]#?\d)_v(\d)_Main\.wav", ("3", "1"), 4.0, 0.3),
    "BASSOON": ("Woodwinds/Bassoon/sus", r"_([A-G]#?\d)_v(\d)_1\.wav", ("2", "1"), 4.0, 0.3),
    "TRUMPET": ("Brass/Trumpet/sus", r"_([A-G]#?\d)_v(\d)_rr1\.wav", ("3", "1"), 4.0, 0.3),
    "HORN": ("Brass/F Horn/sus", r"_([A-G]#?\d)_v(\d)_1\.wav", ("2", "3", "1", "4"), 4.0, 0.3),
    "TROMBONE": ("Brass/Tenor Trombone/sus", r"_([A-G]#?\d)_v(\d)_1\.wav", ("2", "3", "1"), 4.0, 0.3),
    "TUBA": ("Brass/Tuba/sus", r"_([A-G]#?\d)_v(\d)_rr1_Mid\.wav", ("2", "3", "1"), 4.0, 0.3),
    "VIOLIN": ("Strings/Solo Violin/Arco Vib", r"_([A-G]#?\d)_([fp])\.wav", ("f", "p"), 4.0, 0.3),
    "CELLO": ("Strings/Cello Section/susvib", r"_([A-G]#?\d)_v(\d)_1\.wav", ("3", "1"), 4.0, 0.3),
    "HARP": ("Strings/Harp", r"_([A-G]#?\d)_(\w+)\.wav", ("mf", "f", "mp"), 4.0, 0.5),
    "GLOCK": ("Percussion/Glock", r"_([A-G]#?\d)\.wav", (), 3.0, 0.4),
    "VIOLIN_STAC": ("Strings/Solo Violin/spic", r"_([A-G]#?\d)_v(\d)_rr1\.wav", ("2", "1"), 1.2, 0.15),
    "VIOLIN_PIZZ": ("Strings/Solo Violin/Pizz", r"_([A-G]#?\d)_([fp])_RR1\.wav", ("f", "p"), 2.0, 0.3),
    "CELLO_STAC": ("Strings/Cello Section/spic", r"_([A-G]#?\d)_v(\d)_RR1\.wav", ("2", "1"), 1.2, 0.15),
    "CELLO_PIZZ": ("Strings/Cello Section/pizzT", r"_([A-G]#?\d)_v(\d)_RR1\.wav", ("2", "1"), 2.0, 0.3),
    # sections: one recording per range (cellos, violas, violins), each with its own MIDI span
    "STRINGS": [("Strings/Cello Section/susvib", r"_([A-G]#?\d)_v(\d)_1\.wav", ("3", "1"), 0, 54),
                ("Strings/Viola Section/susvib", r"_([A-G]#?\d)_v(\d)_1\.wav", ("2", "1"), 55, 66),
                ("Strings/Violin Section/susVib", r"_([A-G]#?\d)_v(\d)\.wav", ("2", "1"), 67, 127), 4.0, 0.3],
    "STRINGS_PIZZ": [("Strings/Cello Section/pizzT", r"_([A-G]#?\d)_v(\d)_RR1\.wav", ("2", "1"), 0, 54),
                     ("Strings/Viola Section/pizz", r"_([A-G]#?\d)_v(\d)_rr1\.wav", ("2", "1"), 55, 66),
                     ("Strings/Violin Section/Pizz", r"_([A-G]#?\d)_v(\d)_rr1\.wav", ("2", "1"), 67, 127), 2.0, 0.3],
    "STRINGS_TREM": [("Strings/Cello Section/trem", r"_([A-G]#?\d)_v(\d)_1\.wav", ("2", "1"), 0, 54),
                     ("Strings/Violin Section/Trem", r"_([A-G]#?\d)_v(\d)\.wav", ("2", "1"), 55, 127), 4.0, 0.3],
}
# Percussion: one recording each (id: file, longest seconds, fade seconds)
PERC = {
    "GRANCASSA": ("Percussion/BDrumNewhit_v4_rr1_Sum.wav", 3.0, 0.5),
    "SNARE_ORCH": ("Percussion/Snare2-HitSN_v5_rr1_Sum.wav", 1.5, 0.3),
    "BONGO": ("VSCO 1 Percussion/drums/other/Bongos/HighBongo1.wav", 1.0, 0.2),
    "TUMBA": ("Percussion/Tumba-HitN_v2_rr1_Sum.wav", 1.2, 0.2),
    "FRAME": ("Miscellania Raw/Misc 2/rtomtom_frame.wav", 2.0, 0.4),
    "TAIKO": ("VSCO 1 Percussion/drums/other/ethnic/giant/hand/EthnicLargeHand_hit_f_1.wav", 2.5, 0.5),
    "GONG": ("VSCO 1 Percussion/varMetal/Gong/gong_hit_mf.wav", 6.0, 1.5),
    "SUSCYMB": ("Percussion/susCymb1-hit_f_rr1.wav", 4.0, 1.0),
    "CLASH": ("VSCO 1 Percussion/varMetal/Cymbals/clash/crash_hit_ff_loose.wav", 4.0, 1.0),
    "TRIANGLE": ("Percussion/Triangle6-Hit_v2_rr1_Sum.wav", 3.0, 0.8),
    "NEPAL": ("Miscellania Raw/Misc 2/NepaleseBells/fx1_short_r01_main.wav", 4.0, 1.0),
    "SLEIGH": ("Percussion/Sleighbells_Hit_v1_rr1_Mid.wav", 1.5, 0.4),
    "AGOGO": ("VSCO 1 Percussion/varMetal/various/agogoBell_mf1.wav", 1.2, 0.3),
    "ANVIL": ("Percussion/Anvil_Hit1_v2_Sum.wav", 2.0, 0.5),
    "BRAKE": ("Percussion/BrakeDrum1_Hammer_v2_Sum.wav", 1.5, 0.4),
    "BELLTREE": ("Percussion/BellTree_Stroke1_v1_Sum.wav", 3.0, 0.6),
    "CLAVES": ("Percussion/Claves1_Hit_v2_rr1_Sum.wav", 0.6, 0.1),
    "TEMPLE": ("Percussion/TB_hit_C5_v4_rr1.wav", 0.6, 0.1),
    "LOGDRUM": ("Percussion/LogDrumLo_MedM_v2_rr1_Sum.wav", 1.0, 0.2),
    "TAMB": ("Percussion/Tamb1-Hit_v2_rr1_Sum.wav", 1.0, 0.2),
    "MARACAS": ("VSCO 1 Percussion/varWood/maraca1.wav", 0.6, 0.1),
    "CABASA": ("VSCO 1 Percussion/varMetal/various/cabasa_1.wav", 0.8, 0.15),
    "GUIRO": ("Percussion/Guiro-M_v1_Sum.wav", 2.0, 0.3),
    "RATCHET": ("Percussion/Ratchet1-Slow_v1_rr1_Sum.wav", 2.5, 0.3),
    "TAMBROLL": ("Percussion/Tamb1-Roll_v2_rr1_Sum.wav", 4.0, 0.5),
    "RUB": ("Percussion/bassdrum_rub1_v1.wav", 4.0, 0.5),
    "BOW": ("Percussion/susCymb1-bow-1.wav", 6.0, 1.0),
    "GONGSCRAPE": ("Percussion/gongscrape_mf.wav", 5.0, 1.0),
    "SPOONS": ("Miscellania Raw/Misc 2/spoons_fun.wav", 2.0, 0.3),
    "METAL": ("Miscellania Raw/Misc 1/metal_hit3.wav", 2.0, 0.4),
    "CHAIN": ("Miscellania Raw/Misc 1/chain_grind.wav", 3.0, 0.5),
    "BRICK": ("Miscellania Raw/Misc 1/brick_scrape.wav", 3.0, 0.5),
    "BUBBLES": ("Miscellania Raw/Misc 1/bubbles.wav", 3.0, 0.5),
    "GLASS": ("Miscellania Raw/Misc 1/glass_break.wav", 2.5, 0.5),
}
PIANO_MAP = "Keys/Upright Piano/MappingChart.txt"


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def name_midi(name):
    m = re.fullmatch(r"([A-G]#?)(-?\d)", name)
    return 12 * (int(m.group(2)) + 1) + NOTE[m.group(1)]


def detect_midi(x):
    """Pitch of the steady part (autocorrelation), as a fractional MIDI note."""
    start = int(len(x) * 0.25)
    seg = x[start:start + 8192]
    if len(seg) < 4096:
        seg = x[:8192]
    seg = seg - seg.mean()
    n = len(seg)
    spec = np.fft.rfft(seg * np.hanning(n), 2 * n)
    ac = np.fft.irfft(np.abs(spec) ** 2)[:n]
    lo, hi = int(SR / 2200), int(SR / 25)
    lag = lo + int(np.argmax(ac[lo:hi]))
    # prefer the shortest lag that is nearly as strong (avoids octave-low errors)
    for div in (4, 3, 2):
        cand = lag // div
        if cand >= lo:
            w = max(1, cand // 20)
            local = cand - w + int(np.argmax(ac[cand - w:cand + w + 1]))
            if ac[local] > 0.85 * ac[lag]:
                lag = local
                break
    return 69 + 12 * math.log2(SR / lag / 440)


def onset(x):
    peak = np.max(np.abs(x)) or 1
    idx = int(np.argmax(np.abs(x) > peak * 0.02))
    return max(0, idx - int(SR * 0.004))


def cut(x, longest, fade):
    x = x[: int(SR * longest)].copy()
    n = min(len(x), int(SR * fade))
    x[len(x) - n:] *= np.linspace(1, 0, n) ** 2
    return x


def mp3(x, path):
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", "-",
                    "-codec:a", "libmp3lame", "-q:a", "4", str(path)], input=pcm, check=True)


def main(src):
    src = Path(src)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    piano_map = {}
    for line in (src / PIANO_MAP).read_text().splitlines():
        if "=" in line and line[:3].isdigit():
            k, v = line.split("=")
            piano_map[k] = int(v)
    zones = {}
    for ident, spec in SETS.items():
        if isinstance(spec, tuple):
            folder, pattern, layers, longest, fade = spec
            parts = [(folder, pattern, layers, 0, 127)]
        else:
            *parts, longest, fade = spec
        notes = []
        for folder, pattern, layers, lo, hi in parts:
            picked = {}
            for f in sorted((src / folder).glob("*.wav")):
                m = re.search(pattern, f.name)
                if not m:
                    continue
                if ident == "PIANO":
                    midi = piano_map[m.group(1)]
                    rank = 0
                else:
                    midi = name_midi(m.group(1))
                    layer = m.group(2) if m.lastindex and m.lastindex >= 2 else ""
                    if layers and layer not in layers:
                        continue
                    rank = layers.index(layer) if layers else 0
                if midi not in picked or rank < picked[midi][0]:
                    picked[midi] = (rank, f)
            sounds = []
            for named, (_, f) in sorted(picked.items()):
                x = load(f)
                x = x[onset(x):]
                sounds.append((named, x, detect_midi(x), f.name))
            # the library names octaves differently per instrument: one shift for the whole set,
            # the most common whole-octave gap between the names and the measured pitches
            gaps = [12 * round((heard - named) / 12) for named, _, heard, _ in sounds]
            shift = 0 if ident == "PIANO" else max(set(gaps), key=gaps.count)
            for named, x, heard, fname in sounds:
                midi = named + shift
                if not lo <= midi <= hi:
                    continue
                if abs(midi - heard) > 0.6:
                    print(f"  {ident} {fname}: {midi}, measured {heard:.2f} (pitch detection disagrees)")
                notes.append((midi, cut(x, longest, fade)))
        notes.sort(key=lambda n: n[0])
        # every note equally loud over its first second and a half (so neighbouring notes
        # match), without clipping
        (OUT / ident).mkdir()
        for midi, x in notes:
            head = x[: int(SR * 1.5)]
            gain = min(0.16 / (np.sqrt(np.mean(head ** 2)) or 1), 0.95 / (np.max(np.abs(x)) or 1))
            mp3(x * gain, OUT / ident / f"{midi}.mp3")
        zones[ident] = [m for m, _ in notes]
        size = sum(p.stat().st_size for p in (OUT / ident).iterdir())
        print(f"{ident}: {len(notes)} notes {zones[ident][0]}-{zones[ident][-1]}, {size / 1e6:.2f} MB")
    for ident, (path, longest, fade) in PERC.items():
        x = load(src / path)
        x = cut(x[onset(x):], longest, fade)
        (OUT / ident).mkdir()
        mp3(x * (0.9 / (np.max(np.abs(x)) or 1)), OUT / ident / "0.mp3")  # hits: the peak, not the body
        zones[ident] = [0]
        print(f"{ident}: {len(x) / SR:.1f} s, {(OUT / ident / '0.mp3').stat().st_size / 1e3:.0f} kB")
    (OUT / "LICENSE.txt").write_text(
        "Samples from VS Chamber Orchestra: Community Edition (https://github.com/sgossner/VSCO-2-CE),\n"
        "recorded by Sam Gossner and Simon Dalzell (upright piano: Simon Dalzell, Ivy Audio),\n"
        "Versilian Studios. Released under CC0 1.0 Universal (public domain). Converted to mono MP3\n"
        "by tools/build_samples.py.\n", encoding="utf-8")
    html = APP.read_text(encoding="utf-8")
    block = "// SAMPLES:BEGIN\nconst SAMPLE_ZONES = " + json.dumps(zones, separators=(",", ":")) + ";\n// SAMPLES:END"
    html, n = re.subn(r"// SAMPLES:BEGIN\n.*?// SAMPLES:END", lambda _: block, html, flags=re.S)
    assert n == 1, "SAMPLES markers not found in web/app.html"
    APP.write_text(html, encoding="utf-8")
    total = sum(p.stat().st_size for p in OUT.rglob("*.mp3"))
    print(f"total {total / 1e6:.2f} MB")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
