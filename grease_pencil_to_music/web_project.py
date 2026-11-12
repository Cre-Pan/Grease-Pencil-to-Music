# SPDX-License-Identifier: GPL-3.0-or-later
"""The web app's project file (.json) ↔ plain data for a composition.

Pure module (no ``bpy``): ``web_io.py`` turns the result into Grease Pencil strokes
and back. The web app stores the board in musical units: x in beats, y in MIDI
pitch (the row of note ``m`` spans ``[m, m + 1)``), width in rows; every point is
``[beat, pitch, width, ms since the stroke began]``. The add-on board is in
seconds × ``seconds_width`` and rows × ``row_height``.
"""

import base64
import json
import math
from dataclasses import dataclass, field

import numpy as np

APP_ID = "grease-pencil-to-music-web"
VERSION = 3
SAMPLE_RATE = 44100  # rate of the web app's recorded sounds (mono int16)

# Web instrument → add-on instrument. Missing add-on instruments fall back to the
# second choice (the add-on may not have every web sound yet).
WEB_TO_ADDON = {
    "EPIANO": ("EPIANO", "BELL"),
    "FLUTE": ("SINE",),
    "MARIMBA": ("MARIMBA", "BELL"),
    "BELL": ("BELL",),
    "GUITAR": ("PLUCK",),
    "STRINGS": ("STRINGS",),
    "PAD": ("PAD", "STRINGS"),
    "SAW": ("SAW",),
    "SQUARE": ("SQUARE",),
    "BASS": ("BASS", "PLUCK"),
    "KICK": ("KICK",),
    "SNARE": ("SNARE",),
    "CLAP": ("CLAP",),
    "HAT": ("HIHAT",),
    "OHAT": ("OPENHAT", "CRASH"),
    "TOM": ("TOM",),
    "RIM": ("RIM", "COWBELL"),
    "SHAKER": ("SHAKER", "HIHAT"),
    "ORGAN": ("SINE",),
    "BRASS": ("SAW",),
    "CHOIR": ("PAD", "STRINGS"),
    "VIBES": ("BELL",),
    "OCARINA": ("TRIANGLE", "SINE"),
    "CRASH": ("CRASH", "OPENHAT"),
    "COWBELL": ("COWBELL", "RIM"),
    "CONGA": ("TOM",),
}
ADDON_TO_WEB = {
    "SINE": "FLUTE", "TRIANGLE": "OCARINA", "SQUARE": "SQUARE", "SAW": "SAW",
    "STRINGS": "STRINGS", "PLUCK": "GUITAR", "BELL": "BELL", "EPIANO": "EPIANO",
    "MARIMBA": "MARIMBA", "PAD": "PAD", "BASS": "BASS",
    "DRUM": "SNARE", "KICK": "KICK", "SNARE": "SNARE", "HIHAT": "HAT", "OPENHAT": "OHAT",
    "CRASH": "CRASH", "CLAP": "CLAP", "TOM": "TOM", "COWBELL": "COWBELL", "RIM": "RIM",
    "SHAKER": "SHAKER",
}
WEB_DRUMS = ("KICK", "SNARE", "CLAP", "HAT", "OHAT", "TOM", "RIM", "SHAKER")
WEB_DRUM_NOTES = {"KICK": 36, "SNARE": 38, "CLAP": 39, "HAT": 42, "OHAT": 46, "TOM": 45,
                  "RIM": 37, "SHAKER": 70}
WEB_MODES = ("QUANTIZED", "LEGATO", "OPTICAL", "OPTICAL_LEGATO", "GESTURE")
SCALE_TO_ADDON = {"CHROMATIC": "CHROMATIC", "MAJOR": "MAJOR", "MINOR": "MINOR",
                  "DORIAN": "DORIAN", "PENTA": "PENTA_MAJOR", "BLUES": "BLUES"}
SCALE_TO_WEB = {"CHROMATIC": "CHROMATIC", "MAJOR": "MAJOR", "MINOR": "MINOR",
                "DORIAN": "DORIAN", "PENTA_MAJOR": "PENTA", "PENTA_MINOR": "PENTA",
                "BLUES": "BLUES"}
# (beats per grid step, add-on time grid)
GRIDS = ((0.0, "OFF"), (1.0, "1_4"), (0.5, "1_8"), (1 / 3, "1_8T"), (0.25, "1_16"),
         (1 / 6, "1_16T"), (0.125, "1_32"))
HARMONIES = ("OFF", "THIRD", "SIXTH", "TRIAD", "FIFTH", "OCTAVE")
ADDON_MIN_ROW_WIDTH = 0.04  # thinnest width (rows) written to the web file


class ProjectError(ValueError):
    pass


@dataclass
class Board:
    """The add-on board a project is converted to / from."""

    bpm: float = 100.0
    length: float = 9.6  # seconds
    low_note: int = 48
    octaves: int = 3
    row_height: float = 0.12
    seconds_width: float = 1.0

    @property
    def seconds_per_beat(self):
        return 60.0 / self.bpm


@dataclass
class Stroke:
    """One stroke in add-on board space (object local X and Z)."""

    x: np.ndarray
    z: np.ndarray
    radius: np.ndarray
    opacity: float = 1.0
    times: np.ndarray = None  # seconds since the stroke began
    instrument: str = "SINE"  # add-on instrument id, or "SMP:<id>" for a web sound
    filled: bool = False
    softness: float = 0.0


@dataclass
class Layer:
    name: str
    mode: str = "QUANTIZED"
    visible: bool = True
    muted: bool = False
    volume: float = 0.85
    reverb: float = 0.0
    harmony: str = "OFF"
    strokes: list = field(default_factory=list)


@dataclass
class Sound:
    """A sound recorded or imported in the web app."""

    ident: str
    name: str
    root: int
    data: np.ndarray = None  # mono float32 in [-1, 1] at SAMPLE_RATE, or None


@dataclass
class Project:
    name: str
    board: Board
    scale: str = "MAJOR"
    root: int = 0
    grid: str = "1_16"
    swing: float = 0.0
    layers: list = field(default_factory=list)
    sounds: list = field(default_factory=list)
    skipped: list = field(default_factory=list)  # web instruments with no match (waves)


def _clamp(value, low, high):
    return max(low, min(high, value))


def _num(value, default):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def addon_instrument(web_id, available):
    """Add-on instrument for a web instrument id (``available``: add-on ids)."""
    for ident in WEB_TO_ADDON.get(web_id, ()):
        if ident in available:
            return ident
    return None


def grid_ident(beats):
    beats = _num(beats, 0.25)
    return min(GRIDS, key=lambda g: abs(g[0] - beats))[1]


def grid_beats(ident):
    return next((b for b, i in GRIDS if i == ident), 0.25)


# --- Web → add-on -----------------------------------------------------------------------

def _stroke_from_web(st, board, instrument):
    pts = [q for q in st.get("pts", ()) if isinstance(q, (list, tuple)) and len(q) >= 3]
    pts = [q for q in pts if all(math.isfinite(_num(v, math.nan)) for v in q[:3])]
    if not pts:
        return None
    arr = np.array([[float(q[0]), float(q[1]), float(q[2]),
                     _num(q[3], math.nan) if len(q) > 3 else math.nan] for q in pts])
    spb = board.seconds_per_beat
    x = arr[:, 0] * spb * board.seconds_width
    z = (arr[:, 1] - board.low_note) * board.row_height
    radius = np.maximum(arr[:, 2], 0.02) * board.row_height / 2
    ms = arr[:, 3]
    times = None
    if np.all(np.isfinite(ms)) and len(ms) > 1 and ms[-1] > ms[0]:
        times = np.maximum.accumulate((ms - ms[0]) / 1000.0)
    brush = st.get("brush") or "smooth"
    opacity = _clamp(_num(st.get("op"), 1.0), 0.05, 1.0)
    if brush == "pencil":  # graphite: a darker sound, like the web app
        opacity *= 0.65
    filled = brush == "fill" and len(x) >= 3
    return Stroke(x=x, z=z, radius=radius, opacity=opacity, times=times,
                  instrument=instrument, filled=filled,
                  softness=0.8 if brush == "air" else 0.0)


def beat_hits(beat, bars):
    """``[(beat position, web drum id, velocity 0..1)]`` of the web Beat section."""
    if not isinstance(beat, dict) or not beat.get("on", True):
        return []
    tracks = beat.get("tracks") or {}
    steps = int(_clamp(_num(beat.get("steps"), 16), 1, 32))
    swing = _clamp(_num(beat.get("swing"), 0.0), 0.0, 1.0)
    ab = bool(beat.get("ab"))
    chain = beat.get("chain") or []
    hits = []
    for s in range(int(bars) * 16):
        i = s % steps
        which = (chain[(s // steps) % 32] if (s // steps) % 32 < len(chain) else "A") if ab else "A"
        if which == "-":
            continue
        for ident in WEB_DRUMS:
            tr = tracks.get(ident)
            if not isinstance(tr, dict) or tr.get("mute"):
                continue
            pattern = tr.get("pB" if which == "B" else "p") or []
            v = int(_num(pattern[i], 0)) if i < len(pattern) else 0
            if not v:
                continue
            pos = s * 0.25 + (swing * 0.125 if s % 2 else 0.0)
            vel = (1.0 if v == 2 else 0.7) * _clamp(_num(tr.get("vol"), 1.0), 0.0, 1.0)
            hits.append((pos, ident, vel))
    return hits


def _beat_layer(state, board, available, name):
    beat = state.get("beat")
    hits = beat_hits(beat, round(board.length / board.seconds_per_beat / 4))
    if not hits:
        return None
    volume = _clamp(_num(beat.get("volume"), 0.8), 0.0, 1.0)
    # Optical: the hits keep their exact (swung) place instead of snapping to the grid.
    layer = Layer(name=name, mode="OPTICAL", volume=volume)
    spb, h = board.seconds_per_beat, board.row_height
    for pos, ident, vel in hits:
        inst = addon_instrument(ident, available)
        if inst is None:
            continue
        pitch = _clamp(WEB_DRUM_NOTES[ident], board.low_note,
                       board.low_note + board.octaves * 12 - 1)
        x0 = pos * spb * board.seconds_width
        x = np.array([x0, x0 + 0.05 * spb * board.seconds_width])
        z = np.full(2, (pitch - board.low_note + 0.5) * h)
        radius = np.full(2, (0.35 + 0.45 * vel) * h / 2)
        layer.strokes.append(Stroke(x=x, z=z, radius=radius, instrument=inst))
    return layer


def _decode_sound(b64):
    try:
        raw = base64.b64decode(b64, validate=False)
    except (ValueError, TypeError):
        return None
    data = np.frombuffer(raw[: len(raw) // 2 * 2], dtype="<i2")
    return (data.astype(np.float32) / 32767.0) if len(data) else None


def parse(text, available, row_height=0.12, seconds_width=1.0, beat_layer_name="Beat"):
    """Read a web project (.json text) into a :class:`Project`.

    ``available``: instrument ids the add-on knows (``synth.INSTRUMENT_BY_ID``);
    ``row_height`` and ``seconds_width``: size of the board the strokes are placed on.
    """
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as error:
        raise ProjectError(f"non è un file JSON ({error})") from None
    state = data.get("state", data) if isinstance(data, dict) else None
    if not isinstance(state, dict) or not isinstance(state.get("layers"), list) \
            or not state["layers"]:
        raise ProjectError("non è un progetto della web app")
    bpm = _clamp(_num(state.get("bpm"), 100.0), 20.0, 300.0)
    bars = int(_clamp(round(_num(state.get("bars"), 4)), 1, 32))
    if data.get("version", VERSION) == 1 and "length" in state:  # oldest saves: seconds
        bars = int(_clamp(round(_num(state["length"], 8) / (60 / bpm) / 4), 1, 32))
    board = Board(bpm=bpm, length=_clamp(bars * 4 * 60.0 / bpm, 1.0, 300.0),
                  low_note=int(_clamp(round(_num(state.get("low"), 48)), 12, 96)),
                  octaves=int(_clamp(round(_num(state.get("octaves"), 3)), 1, 7)),
                  row_height=row_height, seconds_width=seconds_width)
    project = Project(
        name=str(state.get("name") or "Composizione")[:60], board=board,
        scale=SCALE_TO_ADDON.get(state.get("scale"), "MAJOR"),
        root=int(_num(state.get("root"), 0)) % 12, grid=grid_ident(state.get("grid", 0.25)),
    )
    sounds = data.get("sounds") if isinstance(data.get("sounds"), dict) else {}
    for meta in state.get("samples") or []:
        if isinstance(meta, dict) and str(meta.get("id", "")).startswith("SMP:"):
            project.sounds.append(Sound(
                ident=meta["id"], name=str(meta.get("name") or "Suono")[:60],
                root=int(_clamp(round(_num(meta.get("root"), 60)), 0, 127)),
                data=_decode_sound(sounds[meta["id"]]) if meta["id"] in sounds else None))
    sound_ids = {s.ident for s in project.sounds if s.data is not None}

    by_id = {}
    for raw in state["layers"]:
        if not isinstance(raw, dict):
            continue
        harmony = raw.get("harmony", "OFF")
        layer = Layer(
            name=str(raw.get("name") or "Livello")[:60],
            mode=raw.get("mode") if raw.get("mode") in WEB_MODES else "QUANTIZED",
            visible=raw.get("visible", True) is not False,
            muted=bool(raw.get("muted", raw.get("visible") is False)),
            volume=_clamp(_num(raw.get("volume"), 0.85), 0.0, 1.0),
            reverb=_clamp(_num(raw.get("reverb"), 0.0), 0.0, 1.0),
            harmony=harmony if harmony in HARMONIES else "OFF",
        )
        project.layers.append(layer)
        by_id[raw.get("id")] = layer
    for st in state.get("strokes") or []:
        if not isinstance(st, dict) or st.get("layer") not in by_id:
            continue
        web_inst = str(st.get("inst") or "EPIANO")
        if web_inst in sound_ids:
            inst = web_inst
        else:
            inst = addon_instrument(web_inst, available)
            if inst is None:
                if web_inst not in project.skipped:
                    project.skipped.append(web_inst)
                inst = addon_instrument("EPIANO", available) or "SINE"
        stroke = _stroke_from_web(st, board, inst)
        if stroke is not None:
            by_id[st["layer"]].strokes.append(stroke)
    beat = _beat_layer(state, board, available, beat_layer_name)
    if beat is not None:
        project.layers.append(beat)
    return project


# --- Add-on → web -----------------------------------------------------------------------

def _new_id(prefix, index):
    return f"{prefix}{index:x}gp2m"


def _web_points(stroke, board):
    spb = board.seconds_per_beat
    beats = np.asarray(stroke.x) / board.seconds_width / spb
    pitch = np.asarray(stroke.z) / board.row_height + board.low_note
    width = np.maximum(np.asarray(stroke.radius) * 2 / board.row_height, ADDON_MIN_ROW_WIDTH)
    if stroke.times is not None and len(stroke.times) == len(beats):
        ms = np.round((np.asarray(stroke.times) - stroke.times[0]) * 1000.0)
    else:  # drawn at the tempo of the music, like the web app's examples
        ms = np.round(np.abs(beats - beats[0]) * spb * 1000.0)
    ms = np.maximum.accumulate(ms)
    return [[round(float(b), 4), round(float(p), 4), round(float(w), 3), int(m)]
            for b, p, w, m in zip(beats, pitch, width, ms)]


def _blank_beat(on=False):
    return {"on": on, "steps": 16, "swing": 0, "volume": 0.8, "preset": "EMPTY", "ab": False,
            "edit": "A", "chain": ["A"] * 32,
            "tracks": {i: {"mute": False, "p": [0] * 32, "pB": [0] * 32} for i in WEB_DRUMS}}


def dump(project):
    """A web project (.json text) from a :class:`Project`."""
    board = project.board
    bars = int(_clamp(round(board.length / board.seconds_per_beat / 4), 1, 32))
    layers, strokes, samples, sounds = [], [], [], {}
    sound_ids = {}
    for index, sound in enumerate(project.sounds):
        if sound.data is None or not len(sound.data):
            continue
        ident = sound.ident if sound.ident.startswith("SMP:") else _new_id("SMP:x", index)
        sound_ids[sound.ident] = ident
        samples.append({"id": ident, "name": sound.name, "root": int(_clamp(sound.root, 24, 96))})
        pcm = (np.clip(np.asarray(sound.data, dtype=np.float32), -1, 1) * 32767).astype("<i2")
        sounds[ident] = base64.b64encode(pcm.tobytes()).decode("ascii")
    stroke_index = 0
    for li, layer in enumerate(project.layers):
        lid = _new_id("l", li)
        entry = {"id": lid, "name": layer.name, "mode": layer.mode if layer.mode in WEB_MODES
                 else "QUANTIZED", "visible": layer.visible, "muted": layer.muted,
                 "volume": round(_clamp(layer.volume, 0, 1), 3), "pan": 0,
                 "reverb": round(_clamp(layer.reverb, 0, 1), 3)}
        if layer.harmony in HARMONIES and layer.harmony != "OFF":
            entry["harmony"] = layer.harmony
        layers.append(entry)
        for stroke in layer.strokes:
            if len(stroke.x) == 0:
                continue
            inst = sound_ids.get(stroke.instrument) or ADDON_TO_WEB.get(stroke.instrument, "EPIANO")
            brush = "fill" if stroke.filled else "air" if stroke.softness >= 0.5 else "smooth"
            strokes.append({"id": _new_id("s", stroke_index), "layer": lid, "inst": inst,
                            "op": round(_clamp(stroke.opacity, 0.05, 1.0), 3), "brush": brush,
                            "pts": _web_points(stroke, board)})
            stroke_index += 1
    if not layers:
        layers.append({"id": "l0gp2m", "name": "Livello 1", "mode": "QUANTIZED",
                       "visible": True, "muted": False, "volume": 0.85, "pan": 0,
                       "reverb": 0.25})
    state = {
        "name": project.name, "example": False, "bpm": int(round(_clamp(board.bpm, 40, 220))),
        "bars": bars, "low": int(board.low_note), "octaves": int(_clamp(board.octaves, 1, 5)),
        "scale": SCALE_TO_WEB.get(project.scale, "MAJOR"), "root": int(project.root) % 12,
        "grid": grid_beats(project.grid), "layers": layers, "active": layers[-1]["id"],
        "strokes": strokes, "beat": _blank_beat(), "samples": samples, "waves": [],
    }
    return json.dumps({"app": APP_ID, "version": VERSION, "state": state, "sounds": sounds},
                      ensure_ascii=False, separators=(",", ":"))
