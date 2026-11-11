# SPDX-License-Identifier: GPL-3.0-or-later
"""Hear the stroke while drawing it (like "Suona mentre disegni" in the web app).

In Draw Mode the Grease Pencil v3 brush writes the stroke into the drawing
while the pen moves, so a light timer watches the active drawing of the active
composition: when its last stroke grows, the tip of the stroke is played with
the stroke's instrument.

* Quantized, Legato and Gesture readings: a note every time the tip enters
  another row (snapped to the scale); a straight line is one note.
* Optical readings: one held sound whose pitch follows the tip (theremin).
* Percussion: one hit when the stroke starts.

The thickness gives the volume (like the stroke itself, when the thickness is
mapped to volume); the instrument and layer volumes are applied too.

The decision logic (:class:`Tracker`, :func:`tip_pitch`, :func:`tip_volume`)
does not touch ``bpy`` and is tested on its own.
"""

import time

import numpy as np

from . import music

IDLE_INTERVAL = 0.25  # seconds between checks outside Draw Mode
DRAW_INTERVAL = 0.02  # seconds between checks in Draw Mode
SILENCE_AFTER = 0.3  # the stroke stopped growing for this long: the pen is up
OPTICAL_MODES = ("OPTICAL", "OPTICAL_LEGATO")


# --- pure logic ------------------------------------------------------------------

class Tracker:
    """Follows the stroke and point counts of one drawing between checks.

    :meth:`update` returns ``"start"`` when a new stroke appears, ``"move"`` when
    the last stroke gained points, ``"stop"`` when it stopped growing (or the
    drawing changed in another way), ``None`` otherwise.
    """

    def __init__(self):
        self.key = None
        self.strokes = 0
        self.points = 0
        self.active = False
        self.last_growth = 0.0

    def update(self, key, strokes, points, now):
        previous = (self.key, self.strokes, self.points)
        self.key, self.strokes, self.points = key, strokes, points
        if previous[0] != key:  # another composition, layer or keyframe: just look
            return self._stop()
        grew = False
        if strokes == previous[1] + 1 and points >= 1:
            event = "start"
            grew = True
        elif strokes == previous[1] and strokes > 0 and points > previous[2]:
            event = "move" if self.active else "start"
            grew = True
        elif strokes != previous[1] or points < previous[2]:
            # undo, eraser, a pasted or deleted stroke: no sound for those
            return self._stop()
        else:
            event = None
        if grew:
            self.active = True
            self.last_growth = now
            return event
        if self.active and now - self.last_growth > SILENCE_AFTER:
            return self._stop()
        return None

    def _stop(self):
        was = self.active
        self.active = False
        return "stop" if was else None


def tip_pitch(z, spec, mode, rows=None):
    """MIDI pitch of the stroke tip at height ``z`` (None outside the board).

    Optical readings give a continuous pitch, the others the row snapped to
    the scale, exactly like :mod:`interpret`. ``rows``: rows of the board.
    """
    row = z / max(spec.row_height, 1e-9)
    if row < 0 or (rows is not None and row >= rows):
        return None
    if mode in OPTICAL_MODES:
        return float(spec.low_note + row - 0.5)
    lookup = music.scale_lookup(spec.scale, spec.root)
    index = int(np.clip(spec.low_note + np.floor(row), 0, 127))
    return int(lookup[index])


def tip_volume(radius, max_radius, mapping):
    """Playback volume from the thickness at the tip (thickness = volume)."""
    if mapping.thickness not in ("VOLUME", "VOLUME_VIBRATO") or max_radius <= 0:
        return 0.8
    return float(np.clip(radius / max_radius, 0.15, 1.0)) * 0.8


# --- Blender side ----------------------------------------------------------------

class _Live:
    tracker = Tracker()
    handle = None
    pitch = None  # pitch being heard (quantized) or base pitch of the handle (optical)
    optical = False
    instrument = None
    max_radius = 0.0
    started = 0.0


def _silence():
    from . import keyboard
    if _Live.handle is not None:
        keyboard.note_off(_Live.handle)
    _Live.handle = None
    _Live.pitch = None


def _composition(context):
    obj = getattr(context, "active_object", None)
    if obj is None or obj.type != "GREASEPENCIL" or obj.mode != "PAINT_GREASE_PENCIL":
        return None
    return obj if obj.gp2m.is_composition else None


def _tip(obj, scene):
    """(key, strokes, points of last stroke, tip z, tip radius, material, layer) or None."""
    from . import board, reader
    gp = obj.data
    layer = gp.layers.active
    if layer is None or layer.hide or board.is_board_layer(layer):
        return None
    drawing = reader.drawing_at(layer, scene.frame_current)
    if drawing is None:
        return None
    key = (obj.name, layer.name, drawing.as_pointer())
    strokes = len(drawing.strokes)
    if strokes == 0:
        return key, 0, 0, None, None, None, layer
    offsets = drawing.curve_offsets
    end = int(offsets[strokes].value)
    start = int(offsets[strokes - 1].value)
    if end <= start:
        return key, strokes, 0, None, None, None, layer
    position = drawing.attributes.get("position")
    radius = drawing.attributes.get("radius")
    material = drawing.attributes.get("material_index")
    z = float(position.data[end - 1].vector[2]) if position is not None else None
    r = float(radius.data[end - 1].value) if radius is not None else 0.01
    m = int(material.data[strokes - 1].value) if material is not None else 0
    return key, strokes, end - start, z, r, m, layer


def _play(obj, tip, event):
    from . import engine, keyboard, prefs, props, reader, synth
    _key, _strokes, _points, z, radius, material_index, layer = tip
    if z is None:
        return
    s = obj.gp2m
    slots = obj.material_slots
    material = (slots[material_index].material
                if 0 <= material_index < len(slots) else None)
    if reader.material_muted(material):
        _silence()
        return
    settings = props.find_layer_settings(obj.data, layer.name)
    mode = settings.mode if settings is not None else "QUANTIZED"
    pitch = tip_pitch(z, engine.board_spec(s), mode, s.octaves * 12)
    if event == "start":
        _silence()
        _Live.instrument = reader.material_instrument(material)
        _Live.max_radius = 0.0
        _Live.optical = mode in OPTICAL_MODES
        _Live.started = time.monotonic()
    _Live.max_radius = max(_Live.max_radius, radius)
    volume = (tip_volume(radius, _Live.max_radius, prefs.get_mapping())
              * reader.material_gain(material) * max(layer.opacity, 0.0))
    rate = int(s.sample_rate)
    if synth.get_instrument(_Live.instrument).percussive:
        if event == "start" and pitch is not None:
            keyboard.note_on(_Live.instrument, round(pitch), rate, volume)  # decays alone
        return
    if pitch is None:  # the tip left the board
        _silence()
        return
    if _Live.optical:
        handle = _Live.handle
        alive = handle is not None and bool(getattr(handle, "status", 0))
        if not alive:
            _Live.pitch = round(pitch)
            _Live.handle = keyboard.note_on(_Live.instrument, _Live.pitch, rate, 1.0)
            handle = _Live.handle
        if handle is not None:
            try:
                handle.pitch = float(2.0 ** ((pitch - _Live.pitch) / 12.0))
                handle.volume = float(volume)
            except Exception:
                pass
        return
    if pitch == _Live.pitch and _Live.handle is not None:
        try:
            _Live.handle.volume = float(volume)
        except Exception:
            pass
        return
    _silence()  # a new row: a new note
    _Live.pitch = pitch
    _Live.handle = keyboard.note_on(_Live.instrument, pitch, rate, volume)


def step(obj, scene, now=None):
    """One check of the active drawing of ``obj``; returns the tracker event."""
    now = time.monotonic() if now is None else now
    tip = _tip(obj, scene) if obj is not None and scene is not None else None
    if tip is None:
        event = _Live.tracker.update(None, 0, 0, now)
    else:
        event = _Live.tracker.update(tip[0], tip[1], tip[2], now)
    if event == "stop":
        _silence()
    elif event in ("start", "move"):
        _play(obj, tip, event)
    return event


def _tick():
    import bpy
    from . import prefs
    try:
        context = bpy.context
        if not getattr(prefs.get_prefs(), "draw_sound", True):
            step(None, None)
            return IDLE_INTERVAL
        obj = _composition(context)
        step(obj, context.scene)
        if obj is None:
            return IDLE_INTERVAL
    except Exception:  # never let the timer die (file loading, data being freed)
        _silence()
    return DRAW_INTERVAL if _Live.tracker.active else DRAW_INTERVAL * 2


def register():
    import bpy
    if not bpy.app.background and not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=IDLE_INTERVAL, persistent=True)


def unregister():
    import bpy
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    _silence()
    _Live.tracker = Tracker()
