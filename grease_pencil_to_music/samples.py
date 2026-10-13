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
