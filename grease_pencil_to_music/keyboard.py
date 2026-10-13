# SPDX-License-Identifier: GPL-3.0-or-later
"""Play the active instrument with the computer keyboard, and record it.

Layout (like a piano on a QWERTY keyboard)::

     W E   T Y U   O P
    A S D F G H J K L ;      Z / X = octave down / up, R = record, Esc = exit

While recording and while the scene plays, every held key becomes a stroke on
the active layer, at the row of its note, from press to release.
"""

from collections import OrderedDict

import bpy
import numpy as np

from . import board, engine, interpret, reader, synth
from .operators import active_composition

KEYMAP = {"A": 0, "W": 1, "S": 2, "E": 3, "D": 4, "F": 5, "T": 6, "G": 7, "Y": 8, "H": 9,
          "U": 10, "J": 11, "K": 12, "O": 13, "L": 14, "P": 15, "SEMI_COLON": 16}
NOTE_SECONDS = 4.0  # held notes longer than this fade out

_device = [None]
_sounds = OrderedDict()


def device():
    if _device[0] is None:
        try:
            import aud
            _device[0] = aud.Device()
        except Exception:
            _device[0] = False  # no audio output (e.g. background mode)
    return _device[0] or None


def note_buffer(instrument, pitch, sample_rate=44100):
    """Stereo float32 buffer of one held note (cached)."""
    key = (instrument, int(pitch), sample_rate)
    if key in _sounds:
        _sounds.move_to_end(key)
        return _sounds[key]
    count = int(NOTE_SECONDS * interpret.CONTROL_RATE) + 1
    voice = interpret.Voice(
        start=0.0, duration=NOTE_SECONDS, pitch=np.full(count, float(pitch)),
        amp=np.full(count, 0.8), vibrato=np.zeros(count),
        brightness=np.full(count, interpret.DEFAULT_BRIGHTNESS), pan=np.zeros(count),
        attack=0.005, instrument=instrument)
    _offset, buffer = synth.render_voice(voice, sample_rate)
    _sounds[key] = buffer
    while len(_sounds) > 128:
        _sounds.popitem(last=False)
    return buffer


def note_on(instrument, pitch, sample_rate=44100):
    out = device()
    if out is None:
        return None
    import aud
    return out.play(aud.Sound.buffer(note_buffer(instrument, pitch, sample_rate),
                                     float(sample_rate)))


def note_off(handle):
    """Short fade instead of a click."""
    if handle is None:
        return
    steps = [0.5, 0.2, 0.0]

    def fade():
        try:
            if not steps:
                handle.stop()
                return None
            handle.volume = steps.pop(0)
            return 0.012
        except Exception:
            return None
    bpy.app.timers.register(fade, first_interval=0.0)


def instrument_of(comp):
    slots = comp.material_slots
    index = comp.active_material_index
    material = slots[index].material if 0 <= index < len(slots) else None
    if material is None or board.is_board_material(material):
        return synth.DEFAULT_INSTRUMENT, 0
    return reader.material_instrument(material), index


def composition_seconds(comp, scene, frame):
    """Time inside the composition for a scene frame (its own start included)."""
    fps = scene.render.fps / scene.render.fps_base
    offset = engine.state(comp).get("offset_frames", 0)
    return (frame - scene.frame_start - offset) / fps


def record_stroke(comp, scene, pitch, t0, t1, material_index):
    """Add a recorded note as a stroke on the active layer. Returns the stroke count."""
    s = comp.gp2m
    t0 = min(max(t0, 0.0), s.length)
    t1 = s.length if t1 < t0 else min(t1, s.length)  # wrapped around the loop end
    if t1 - t0 < 0.02:
        t1 = min(t0 + 0.08, s.length)
    if not s.low_note <= pitch <= s.low_note + s.octaves * 12 or t1 <= t0:
        return 0
    gp = comp.data
    layer = gp.layers.active
    if layer is None or board.is_board_layer(layer):
        layers = board.user_layers(gp)
        if not layers:
            return 0
        layer = layers[-1]
    drawing = reader.drawing_at(layer, scene.frame_start)
    if drawing is None:
        drawing = layer.frames.new(min(1, scene.frame_start)).drawing
    from . import prefs
    count = max(2, int((t1 - t0) * 20) + 1)
    x = np.linspace(t0 * s.seconds_width, t1 * s.seconds_width, count)
    z = np.full(count, (pitch - s.low_note + 0.5) * s.row_height)
    radius = np.full(count, s.row_height * prefs.get_prefs().record_thickness)
    board.add_strokes_bulk(drawing, [(x, z, radius, material_index)])
    return 1


class GP2M_OT_play_keyboard(bpy.types.Operator):
    """Suona lo strumento attivo con la tastiera del computer (R registra mentre la scena è in play)"""

    bl_idname = "gp2m.play_keyboard"
    bl_label = "Suona con la tastiera"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return active_composition(context) is not None

    def _header(self, context):
        from . import music, prefs
        style = prefs.get_prefs().note_naming
        state = "● REGISTRA" if self.recording else "R = registra"
        text = (f"Tastiera: A W S E D F T G Y H U J K = {music.note_name(self.base, style)}… "
                f"· Z/X ottava · {state} · Spazio = play · Esc = esci")
        if context.area is not None:
            context.area.header_text_set(text)

    def invoke(self, context, _event):
        comp = active_composition(context)
        self.comp_name = comp.name
        self.base = min(max((comp.gp2m.low_note // 12 + 1) * 12, 12), 108)
        self.recording = False
        self.held = {}  # key -> (handle, pitch, start seconds)
        context.window_manager.modal_handler_add(self)
        self._header(context)
        return {"RUNNING_MODAL"}

    def _finish(self, context):
        for handle, _pitch, _start in self.held.values():
            note_off(handle)
        self.held.clear()
        if context.area is not None:
            context.area.header_text_set(None)

    def modal(self, context, event):
        comp = bpy.data.objects.get(self.comp_name)
        if comp is None or event.type == "ESC":
            self._finish(context)
            return {"FINISHED"}
        scene = context.scene
        if event.type in KEYMAP:
            pitch = self.base + KEYMAP[event.type]
            if event.value == "PRESS" and not event.is_repeat and event.type not in self.held:
                instrument, _index = instrument_of(comp)
                handle = note_on(instrument, pitch, int(comp.gp2m.sample_rate))
                start = composition_seconds(comp, scene, scene.frame_current)
                self.held[event.type] = (handle, pitch, start)
            elif event.value == "RELEASE" and event.type in self.held:
                handle, pitch, start = self.held.pop(event.type)
                note_off(handle)
                playing = context.screen is not None and context.screen.is_animation_playing
                if self.recording and playing:
                    _instrument, index = instrument_of(comp)
                    end = composition_seconds(comp, scene, scene.frame_current)
                    record_stroke(comp, scene, pitch, start, end, index)
            return {"RUNNING_MODAL"}
        if event.value == "PRESS" and event.type in ("Z", "X"):
            self.base = min(max(self.base + (12 if event.type == "X" else -12), 12), 108)
            self._header(context)
            return {"RUNNING_MODAL"}
        if event.value == "PRESS" and event.type == "R":
            self.recording = not self.recording
            if self.recording and context.screen is not None \
                    and not context.screen.is_animation_playing:
                bpy.ops.screen.animation_play()
            self._header(context)
            return {"RUNNING_MODAL"}
        return {"PASS_THROUGH"}


classes = (GP2M_OT_play_keyboard,)
