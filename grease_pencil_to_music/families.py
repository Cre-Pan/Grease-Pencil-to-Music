# SPDX-License-Identifier: GPL-3.0-or-later
"""The instruments in families, with their icons.

Every instrument of the add-on sits in exactly one family: the recorded ones (the web app's
VSCO 2 CE / VCSL sounds) first, then the synthesized ones of the same kind, so "Flauto" and
"Flauto (synth)" are next to each other. Families are grouped in sections (melodic,
percussion, own sounds), one column each in the instrument menus.

Icons are ``icons/inst_<name>.png`` (drawn by tools/build_icons.py); ``icon_name`` gives
the one of an instrument (its own if it has one, else its family's).

Pure Python: no ``bpy`` import.
"""

from dataclasses import dataclass

from . import synth


@dataclass(frozen=True)
class Family:
    key: str
    title: str
    icon: str
    recorded: tuple  # the web app's ids (S_ + id in the add-on) of the recorded ones
    synths: tuple  # add-on idents of the synthesized ones


MELODIC = (
    Family("KEYS", "Tastiere", "keys",
           ("PIANO", "GRAND", "HARPSI", "PIPEORGAN"), ("EPIANO", "ORGAN")),
    Family("MALLETS", "Percussioni intonate", "mallets",
           ("MARIMBA", "VIBES", "XYLO", "GLOCK", "KALIMBA", "TUBULAR"), ("MARIMBA", "BELL")),
    Family("STRINGS", "Archi", "violin",
           ("STRINGS", "STRINGS_TREM", "STRINGS_PIZZ", "VIOLIN", "VIOLIN_STAC", "VIOLIN_PIZZ",
            "CELLO", "CELLO_STAC", "CELLO_PIZZ"), ("STRINGS",)),
    Family("PLUCKED", "Corde pizzicate", "guitar", ("HARP",), ("PLUCK", "BASS")),
    Family("WOODWINDS", "Legni", "clarinet",
           ("FLUTE", "RECORDER", "OCARINA", "CLARINET", "OBOE", "BASSOON", "SAX", "HARMONICA"),
           ("SINE", "TRIANGLE")),
    Family("BRASS", "Ottoni", "trumpet", ("TRUMPET", "TROMBONE", "HORN", "TUBA"), ("BRASS",)),
    Family("VOICES", "Voci e pad", "choir", (), ("CHOIR", "PAD")),
    Family("SYNTH", "Synth", "saw", (), ("SAW", "SQUARE")),
)

PERCUSSION = (
    Family("KIT", "Batteria", "snare", (),
           ("DRUM", "KICK", "SNARE", "TOM", "RIM", "CLAP", "HIHAT", "OPENHAT", "CRASH")),
    Family("SKINS", "Tamburi", "conga",
           ("GRANCASSA", "SNARE_ORCH", "TAIKO", "FRAME", "BONGO", "CONGA", "TUMBA", "DARBUKA",
            "CAJON"), ()),
    Family("METALS", "Metalli", "cymbal",
           ("GONG", "SUSCYMB", "CLASH", "TRIANGLE", "NEPAL", "SLEIGH", "BELLTREE", "AGOGO",
            "COWBELL", "BRAKE"), ("COWBELL",)),
    Family("WOODS", "Legni e blocchi", "block", ("CLAVES", "TEMPLE", "LOGDRUM"), ()),
    Family("SHAKERS", "Fruscii e sfregamenti", "maracas",
           ("SHAKER", "MARACAS", "CABASA", "TAMB", "TAMBROLL", "GUIRO", "RATCHET", "RUB", "BOW",
            "GONGSCRAPE"), ("SHAKER",)),
    Family("FOUND", "Oggetti", "hammer",
           ("ANVIL", "METAL", "SPOONS", "CHAIN", "BRICK", "BUBBLES", "GLASS"), ()),
)

OWN = (
    Family("OWN", "Suoni tuoi", "", (), ("SAMPLE", "LIBRARY")),
)

SECTIONS = (
    ("Melodici", MELODIC),
    ("Percussioni", PERCUSSION),
    ("Suoni tuoi", OWN),
)

ALL = MELODIC + PERCUSSION + OWN

# Blender's own icons for the instruments that are not an instrument.
BUILTIN_ICONS = {"SAMPLE": "FILE_SOUND", "LIBRARY": "ASSET_MANAGER"}

# Instruments with an icon of their own (add-on idents); the rest use their family's.
_OWN_ICONS = {
    "organ": ("ORGAN", "S_PIPEORGAN"),
    "bell": ("BELL", "S_TUBULAR"),
    "harp": ("S_HARP",),
    "flute": ("SINE", "S_FLUTE", "S_RECORDER"),
    "ocarina": ("TRIANGLE", "S_OCARINA"),
    "sax": ("S_SAX",),
    "harmonica": ("S_HARMONICA",),
    "horn": ("S_HORN", "S_TUBA"),
    "pad": ("PAD",),
    "square": ("SQUARE",),
    "kick": ("KICK", "S_GRANCASSA", "S_RUB"),
    "clap": ("CLAP",),
    "cymbal": ("HIHAT", "OPENHAT", "CRASH"),
    "gong": ("S_GONG", "S_GONGSCRAPE", "S_NEPAL"),
    "triangle": ("S_TRIANGLE",),
    "cowbell": ("COWBELL", "S_COWBELL", "S_AGOGO"),
    "jingle": ("S_SLEIGH", "S_BELLTREE"),
    "tambourine": ("S_TAMB", "S_TAMBROLL", "S_FRAME"),
    "snare": ("S_SNARE_ORCH",),
    "claves": ("S_CLAVES", "S_GUIRO", "S_RATCHET"),
    "bubbles": ("S_BUBBLES",),
    "glass": ("S_GLASS",),
}
_ICON_OF = {ident: name for name, idents in _OWN_ICONS.items() for ident in idents}


def idents(family):
    """Add-on idents of a family: the recorded ones that are bundled, then the synths."""
    rec = tuple(synth.SAMPLED_PREFIX + w for w in family.recorded
                if synth.SAMPLED_PREFIX + w in synth.RECORDINGS)
    return rec + tuple(i for i in family.synths if i in synth.INSTRUMENT_BY_ID)


def split(family):
    """(recorded idents, synth idents) of a family."""
    both = idents(family)
    return (tuple(i for i in both if synth.is_sampled(i)),
            tuple(i for i in both if not synth.is_sampled(i)))


def family_of(ident):
    for family in ALL:
        if ident in idents(family):
            return family
    return None


def icon_name(ident):
    """Name of the add-on icon of an instrument ('' for Blender's own icons)."""
    if ident in BUILTIN_ICONS:
        return ""
    if ident in _ICON_OF:
        return _ICON_OF[ident]
    family = family_of(ident)
    return family.icon if family is not None else ""


def icon_names():
    """Every instrument icon name used (one PNG each)."""
    names = {f.icon for f in ALL if f.icon} | set(_OWN_ICONS)
    return tuple(sorted(names))
