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
           ("MARIMBA", "VIBES", "XYLO", "GLOCK", "KALIMBA", "TUBULAR", "TRIANGLE", "COWBELL",
            "AGOGO"),
           ("MARIMBA", "BELL", "COWBELL")),
    Family("STRINGS", "Archi", "violin",
           ("STRINGS", "STRINGS_TREM", "STRINGS_PIZZ", "VIOLIN", "VIOLIN_STAC", "VIOLIN_PIZZ",
            "CELLO", "CELLO_STAC", "CELLO_PIZZ"), ("STRINGS",)),
    Family("PLUCKED", "Corde pizzicate", "guitar", ("HARP",), ("PLUCK", "BASS")),
    Family("WOODWINDS", "Legni", "wind",
           ("FLUTE", "RECORDER", "OCARINA", "CLARINET", "OBOE", "BASSOON", "HARMONICA"),
           ("SINE", "TRIANGLE")),
    Family("BRASS", "Ottoni", "trumpet", ("TRUMPET", "TROMBONE", "HORN", "TUBA", "SAX"),
           ("BRASS",)),
    Family("VOICES", "Voci e pad", "choir", (), ("CHOIR", "PAD")),
    Family("SYNTH", "Synth", "saw", (), ("SAW", "SQUARE")),
)

PERCUSSION = (
    Family("DRUMS", "Percussioni", "snare",
           ("GRANCASSA", "SNARE_ORCH", "TAIKO", "FRAME", "BONGO", "CONGA", "TUMBA", "DARBUKA",
            "CAJON", "RUB", "CLAVES", "TEMPLE", "LOGDRUM", "SHAKER", "MARACAS", "CABASA",
            "GUIRO", "RATCHET"),
           ("DRUM", "KICK", "SNARE", "TOM", "RIM", "CLAP", "SHAKER")),
    Family("CYMBALS", "Piatti", "cymbal",
           ("SUSCYMB", "CLASH", "BOW", "GONG", "GONGSCRAPE", "NEPAL", "SLEIGH", "BELLTREE",
            "TAMB", "TAMBROLL", "BRAKE"),
           ("HIHAT", "OPENHAT", "CRASH")),
    Family("FOUND", "Strumenti concreti", "found",
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
    """Name of the add-on icon of an instrument: its category's ('' for Blender's own
    icons). The instruments themselves have no icon of their own."""
    if ident in BUILTIN_ICONS:
        return ""
    family = family_of(ident)
    return family.icon if family is not None else ""


def icon_names():
    """Every instrument icon name used (one PNG each)."""
    names = {f.icon for f in ALL if f.icon}
    return tuple(sorted(names))
