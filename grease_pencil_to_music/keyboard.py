# SPDX-License-Identifier: GPL-3.0-or-later
"""Play the active instrument with the computer keyboard (or a MIDI keyboard), and record it.

Layout (like a piano on a QWERTY keyboard)::

     W E   T Y U   O P
    A S D F G H J K L ;      Z / X = octave down / up, R = record, Esc = exit

While recording and while the scene plays, every held key becomes a stroke on
the active layer, at the row of its note, from press to release.

A connected MIDI keyboard plays too (velocity = volume, sustain pedal held notes);
see :mod:`midi_input`.
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
    try:
        _offset, buffer = synth.render_voice(voice, sample_rate)
    except Exception as error:  # noqa: BLE001 - e.g. a recording that cannot be read
        print(f"[Doodle Music] nota non suonata: {error!r}")
        return np.zeros((1, 2), dtype=np.float32)  # not cached: tried again next time
    _sounds[key] = buffer
    while len(_sounds) > 128:
        _sounds.popitem(last=False)
    return buffer


def note_on(instrument, pitch, sample_rate=44100, volume=1.0):
    out = device()
    if out is None:
        return None
    import aud
    sound = aud.Sound.buffer(note_buffer(instrument, pitch, sample_rate), float(sample_rate))
    if volume != 1.0:
        sound = sound.volume(float(volume))
    return out.play(sound)


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


PREVIEW_PITCH = 60  # middle C
PREVIEW_SECONDS = 0.9
_preview = {"handle": None, "ident": None, "time": -10.0}


def preview(ident, sample_rate=44100):
    """A short note of an instrument: played when the mouse rests on it in the instrument
    menus (Blender asks for its tooltip; there is no hover event for menu entries)."""
    import time
    if ident in ("SAMPLE", "LIBRARY") or ident not in synth.INSTRUMENT_BY_ID:
        return
    now = time.monotonic()
    if ident == _preview["ident"] and now - _preview["time"] < PREVIEW_SECONDS:
        return
    note_off(_preview["handle"])
    handle = note_on(ident, PREVIEW_PITCH, sample_rate, 0.7)
    _preview.update(handle=handle, ident=ident, time=now)
    if handle is not None:
        def stop():
            if _preview["handle"] is handle:
                note_off(handle)
                _preview["handle"] = None
            return None
        bpy.app.timers.register(stop, first_interval=PREVIEW_SECONDS)


def velocity_volume(velocity):
    """MIDI velocity (1-127) to playback volume, with a gentle curve."""
    return 0.15 + 0.85 * (max(min(velocity, 127), 1) / 127.0) ** 1.5


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
    """Add a recorded note as a stroke on the active layer. Returns the stroke count.

    ``t0``/``t1`` are composition seconds; with keyframe sections the note goes
    into the drawing of the section being played, at its place inside the loop.
    """
    s = comp.gp2m
    section, local = engine.locate(comp, max(t0, 0.0))
    span = s.length if t1 < t0 else t1 - t0  # wrapped around the end of the scene
    t0, t1 = local, min(local + span, s.length)
    if t1 - t0 < 0.02:
        t1 = min(t0 + 0.08, s.length)
    if not s.low_note <= pitch <= s.low_note + board.span(s) or t1 <= t0:
        return 0
    gp = comp.data
    layer = gp.layers.active
    if layer is None or board.is_board_layer(layer):
        layers = board.user_layers(gp)
        if not layers:
            return 0
        layer = layers[-1]
    fps = scene.render.fps / scene.render.fps_base
    frame = scene.frame_start + int(round(section * fps))
    drawing = reader.drawing_at(layer, frame)
    if drawing is None:
        drawing = layer.frames.new(frame).drawing
    from . import prefs
    count = max(2, int((t1 - t0) * 20) + 1)
    x = np.linspace(t0 * s.seconds_width, t1 * s.seconds_width, count)
    z = np.full(count, (pitch - s.low_note + 0.5) * s.row_height)
    radius = np.full(count, s.row_height * prefs.get_prefs().record_thickness)
    board.add_strokes_bulk(drawing, [(x, z, radius, material_index)])
    return 1


class GP2M_OT_play_keyboard(bpy.types.Operator):
    """Suona lo strumento attivo con la tastiera del PC o una tastiera MIDI (R registra)"""

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
        midi = f" · MIDI: {self.midi.name}" if self.midi is not None else ""
        text = (f"Tastiera: A W S E D F T G Y H U J K = {music.note_name(self.base, style)}… "
                f"· Z/X ottava · {state} · Spazio = play · Esc = esci{midi}")
        area = self._area(context)
        if area is not None:
            area.header_text_set(text)
        elif context.workspace is not None:  # started without an editor: the status bar
            context.workspace.status_text_set(text)

    def _area(self, context):
        """The editor the operator started in, still open (None if it was closed).

        During a modal operator ``context.area`` may be another editor, or None
        when the operator was started from a collapsed one."""
        screen = context.screen
        pointer = getattr(self, "area_pointer", 0)
        if screen is None or not pointer:
            return None
        return next((a for a in screen.areas if a.as_pointer() == pointer), None)

    def _open_midi(self):
        from . import midi_input, prefs
        p = prefs.get_prefs()
        if not p.use_midi_input or midi_input.rtmidi() is None:
            return None
        try:
            return midi_input.Input(p.midi_port)
        except midi_input.MidiInputError as error:
            if p.midi_port.strip():  # only complain when a port was asked for
                self.report({"WARNING"}, str(error))
            return None

    def invoke(self, context, _event):
        comp = active_composition(context)
        self.comp_name = comp.name
        self.area_pointer = context.area.as_pointer() if context.area is not None else 0
        self.base = min(max((comp.gp2m.low_note // 12 + 1) * 12, 12), 108)
        self.recording = False
        self.sustain = False
        self.held = {}  # key -> (handle, pitch, start seconds)
        self.sustained = {}  # MIDI keys released while the pedal is down
        self.midi = self._open_midi()
        self.timer = None
        if self.midi is not None:
            self.timer = context.window_manager.event_timer_add(0.01, window=context.window)
        context.window_manager.modal_handler_add(self)
        self._header(context)
        return {"RUNNING_MODAL"}

    def _finish(self, context):
        for handle, _pitch, _start in list(self.held.values()) + list(self.sustained.values()):
            note_off(handle)
        self.held.clear()
        self.sustained.clear()
        if self.timer is not None:
            context.window_manager.event_timer_remove(self.timer)
            self.timer = None
        if self.midi is not None:
            self.midi.close()
            self.midi = None
        area = self._area(context)
        if area is not None:
            area.header_text_set(None)
        if context.workspace is not None:
            context.workspace.status_text_set(None)

    def cancel(self, context):
        """Blender stops the operator (file loaded, window closed): free port and timer."""
        self._finish(context)

    def _press(self, context, comp, key, pitch, volume=1.0):
        if key in self.held:
            self._release(context, comp, key)
        if key in self.sustained:
            self._end_note(context, comp, *self.sustained.pop(key))
        scene = context.scene
        instrument, _index = instrument_of(comp)
        handle = note_on(instrument, pitch, int(comp.gp2m.sample_rate), volume)
        start = composition_seconds(comp, scene, scene.frame_current)
        self.held[key] = (handle, pitch, start)

    def _release(self, context, comp, key):
        note = self.held.pop(key, None)
        if note is None:
            return
        if self.sustain and isinstance(key, int):
            self.sustained[key] = note
            return
        self._end_note(context, comp, *note)

    def _end_note(self, context, comp, handle, pitch, start):
        note_off(handle)
        scene = context.scene
        playing = context.screen is not None and context.screen.is_animation_playing
        if self.recording and playing:
            _instrument, index = instrument_of(comp)
            end = composition_seconds(comp, scene, scene.frame_current)
            record_stroke(comp, scene, pitch, start, end, index)

    def _poll_midi(self, context, comp):
        for kind, note, value in self.midi.events():
            if kind == "on":
                self._press(context, comp, note, note, velocity_volume(value))
            elif kind == "off":
                self._release(context, comp, note)
            elif kind == "sustain":
                self.sustain = value >= 64
                if not self.sustain:
                    for key in list(self.sustained):
                        self._end_note(context, comp, *self.sustained.pop(key))

    def modal(self, context, event):
        comp = bpy.data.objects.get(self.comp_name)
        if comp is None or event.type == "ESC":
            self._finish(context)
            return {"FINISHED"}
        if event.type == "TIMER":
            if self.midi is not None:
                self._poll_midi(context, comp)
            return {"PASS_THROUGH"}
        if event.type in KEYMAP:
            if event.value == "PRESS" and not event.is_repeat and event.type not in self.held:
                self._press(context, comp, event.type, self.base + KEYMAP[event.type])
            elif event.value == "RELEASE":
                self._release(context, comp, event.type)
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
