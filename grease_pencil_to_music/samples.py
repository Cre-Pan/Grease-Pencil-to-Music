# SPDX-License-Identifier: GPL-3.0-or-later
"""Sound datablocks used by "Campione" (sample) instruments."""

import os
import tempfile

import bpy
import numpy as np

from . import synth

_loaded = {}  # key -> True, so files are decoded once


def _source_path(sound):
    """A readable file for the sound (packed sounds are written to a temp file)."""
    if sound.packed_file is not None:
        path = os.path.join(bpy.app.tempdir or tempfile.gettempdir(),
                            f"gp2m_sample_{sound.session_uid}{os.path.splitext(sound.filepath)[1] or '.wav'}")
        if not os.path.exists(path):
            with open(path, "wb") as handle:
                handle.write(sound.packed_file.data)
        return path
    return bpy.path.abspath(sound.filepath, library=sound.library)


def instrument_key(material):
    """Instrument identifier of a sample material (registers its audio)."""
    sound = material.gp2m_sample
    if sound is None:
        return synth.SAMPLE_PREFIX
    path = _source_path(sound)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return synth.SAMPLE_PREFIX
    key = (f"{sound.name}|{path}|{mtime}|{material.gp2m_sample_root}"
           f"|{int(material.gp2m_sample_loop)}")
    if key not in _loaded:
        import aud
        try:
            source = aud.Sound(path)
            rate = source.specs[0]
            data = source.data()
        except Exception:
            return synth.SAMPLE_PREFIX
        mono = data.mean(axis=1) if data.ndim == 2 else data
        peak = float(np.max(np.abs(mono))) if len(mono) else 0.0
        if peak > 0:
            mono = mono / peak
        synth.register_sample(key, mono, rate, material.gp2m_sample_root,
                              material.gp2m_sample_loop)
        _loaded[key] = True
    return synth.SAMPLE_PREFIX + key


# --- Libraries (SoundFont .sf2, .sfz) ---------------------------------------------------

_soundfonts = {}  # (path, mtime) -> libraries.SoundFont
_preset_items = {}  # path -> enum items (kept alive for Blender)


def read_audio(path):
    """Mono float32 data and rate of a sound file (any format Blender can read)."""
    import aud
    sound = aud.Sound(path)
    data = sound.data()
    mono = data.mean(axis=1) if data.ndim == 2 else data
    return mono.astype(np.float32), float(sound.specs[0])


def _soundfont(path):
    from . import libraries
    key = (path, os.path.getmtime(path))
    if key not in _soundfonts:
        if len(_soundfonts) >= 2:
            _soundfonts.clear()
        _soundfonts[key] = libraries.read_sf2(path)
    return _soundfonts[key]


def preset_items(material, _context):
    """Enum items of the presets of the material's SoundFont."""
    path = bpy.path.abspath(material.gp2m_library_path) if material.gp2m_library_path else ""
    if not path.lower().endswith(".sf2") or not os.path.exists(path):
        items = [("0", "(tutto il file)", "Un file .sfz è un solo strumento")]
    else:
        try:
            items = [(str(index), f"{bank:03d}:{program:03d}  {name}", "")
                     for index, bank, program, name in _soundfont(path).preset_list()]
        except Exception as error:
            items = [("0", f"Errore: {error}", "")]
    _preset_items[path] = items or [("0", "(nessun preset)", "")]
    return _preset_items[path]


def library_key(material):
    """Instrument identifier of a library material (registers its zones)."""
    from . import libraries
    if not material.gp2m_library_path:
        return synth.LIBRARY_PREFIX
    path = bpy.path.abspath(material.gp2m_library_path)
    try:
        mtime = os.path.getmtime(path)
        preset = int(material.gp2m_library_preset or "0")
    except (OSError, ValueError, TypeError):
        return synth.LIBRARY_PREFIX
    key = f"{path}|{mtime}|{preset}"
    if key not in _loaded:
        try:
            if path.lower().endswith(".sfz"):
                zones = libraries.sfz_zones(path, read_audio)
            else:
                zones = _soundfont(path).zones(preset)
        except Exception as error:
            print(f"[Doodle Music] libreria non letta: {error!r}")
            return synth.LIBRARY_PREFIX
        synth.register_zones(key, zones)
        _loaded[key] = True
    return synth.LIBRARY_PREFIX + key


# --- The web app's recorded instruments and rooms (bundled with the add-on) -----------------

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))


def sounds_dir():
    """``sounds/`` of the installed add-on; from a source checkout, the web app's docs/app."""
    bundled = os.path.join(PACKAGE_DIR, "sounds")
    if os.path.isdir(bundled):
        return bundled
    return os.path.join(os.path.dirname(PACKAGE_DIR), "docs", "app")


def _onset(data, rate):
    """Where the sound starts in the decoded file (MP3 decoders add a little silence)."""
    return synth.onset(data, rate)


def _recorded_note(path):
    """``() -> (data, rate, onset)`` of one recorded note, for :func:`synth.zone_ready`."""
    def read():
        data, rate = read_audio(path)
        return data, rate, _onset(data, rate)
    return read


ALIASES = "aliases.txt"  # in the zip, identical recordings are stored once (tools/build_zip.py)
_aliases = {}


def _sample_path(folder, name):
    """The file of a recorded note; a copy left out of the zip is read from its twin."""
    path = os.path.join(folder, name)
    if os.path.exists(path):
        return path
    samples_dir = os.path.dirname(folder)
    if samples_dir not in _aliases:
        table = {}
        try:
            with open(os.path.join(samples_dir, ALIASES), encoding="utf-8") as handle:
                for row in handle:
                    if row.strip():
                        copy, original = row.split()
                        table[copy] = original
        except OSError:
            pass
        _aliases[samples_dir] = table
    original = _aliases[samples_dir].get(f"{os.path.basename(folder)}/{name}")
    return os.path.join(samples_dir, *original.split("/")) if original else path


RECORDED_RATE = 44100.0  # every bundled recording (tools/build_samples.py)


def load_recorded(ident):
    """Zones of a recorded instrument (``synth.SAMPLE_LOADER``). Only the key map is
    built here: each note is decoded the first time it plays."""
    rec = synth.RECORDINGS[ident]
    folder = os.path.join(sounds_dir(), "samples", rec.web_id)
    zones = []
    for note in rec.zones:
        path = _sample_path(folder, f"{note}.mp3")
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        # The rate is the recordings' own until the note is read (synth.zone_ready).
        zones.append(synth.Zone(None, RECORDED_RATE, float(note), 0, 127, False, 0, 0, 1.0,
                                0, _recorded_note(path)))
    return zones


ROOM_FILES = {"ROOM": "room", "CONCERT": "concert", "CHURCH": "church"}


def load_room(room, rate):
    """Stereo impulse response of a recorded room at ``rate`` (``effects.ROOM_LOADER``)."""
    import aud
    sound = aud.Sound(os.path.join(sounds_dir(), "rooms", ROOM_FILES[room] + ".mp3"))
    data = np.asarray(sound.data(), dtype=np.float64)
    if data.ndim == 1:
        data = data[:, None]
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    source_rate = float(sound.specs[0])
    if int(source_rate) != int(rate):
        grid = np.arange(int(len(data) * rate / source_rate)) * (source_rate / rate)
        data = np.stack([np.interp(grid, np.arange(len(data)), data[:, ch]) for ch in range(2)],
                        axis=1)
    return data[:, :2]


def register():
    from . import effects
    synth.SAMPLE_LOADER = load_recorded
    effects.ROOM_LOADER = load_room


def unregister():
    from . import effects
    synth.SAMPLE_LOADER = None
    effects.ROOM_LOADER = None
