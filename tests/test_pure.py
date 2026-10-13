# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests of the bpy-independent modules (music, interpret, synth,
effects, mixer, midi)."""

import struct

import numpy as np
import pytest

from grease_pencil_to_music import effects, interpret, midi, mixer, music, synth

SR = 44100
H = 0.12  # row height of the default board
C4_ROW = 12  # low note C3 (48) + 12 = C4 (60)


def stroke(xs, rows, radius=0.02, opacity=1.0, instrument="SINE", color=None, n=200):
    """A straight-ish stroke from (x0, row0) to (x1, row1); rows are row centres."""
    x = np.linspace(xs[0], xs[1], n)
    z = (np.linspace(rows[0], rows[1], n) + 0.5) * H
    r = np.full(n, radius) if np.isscalar(radius) else np.asarray(radius)
    o = np.full(n, opacity)
    c = None if color is None else np.tile(np.asarray(color, float), (n, 1))
    return interpret.StrokeData(x, z, r, o, color=c, instrument=instrument, layer="L1")


def free_spec(**kw):
    return interpret.BoardSpec(time_grid="OFF", **kw)


# --- music ---------------------------------------------------------------------

def test_note_names_and_frequencies():
    assert music.note_name(60) == "C4"
    assert music.note_name(48) == "C3"
    assert music.note_name(61) == "C#4"
    assert music.is_black(61) and not music.is_black(60)
    assert music.midi_to_freq(69) == pytest.approx(440.0)
    assert music.midi_to_freq(81) == pytest.approx(880.0)


def test_scale_snapping_resolves_ties_downwards():
    assert music.snap_to_scale(61, "MAJOR", 0) == 60  # C# -> C
    assert music.snap_to_scale(66, "MAJOR", 0) == 65  # F# -> F
    assert music.snap_to_scale(64, "MAJOR", 0) == 64
    assert music.snap_to_scale(61, "CHROMATIC", 0) == 61
    # D major: C (60) is not in the scale, C# (61) is.
    assert music.snap_to_scale(60, "MAJOR", 2) == 59


def test_grid_step():
    assert music.grid_step_seconds(120, "1_16") == pytest.approx(0.125)
    assert music.grid_step_seconds(120, "1_4") == pytest.approx(0.5)
    assert music.grid_step_seconds(120, "OFF") == 0.0


# --- interpret -----------------------------------------------------------------

def test_horizontal_line_is_one_note():
    res = interpret.interpret_stroke(stroke((1.0, 2.0), (C4_ROW, C4_ROW)), free_spec(),
                                     interpret.Mapping())
    assert len(res.notes) == 1
    note = res.notes[0]
    assert note.pitch == 60
    assert note.start == pytest.approx(1.0, abs=0.01)
    assert note.end == pytest.approx(2.0, abs=0.01)


def test_rising_line_plays_ascending_notes():
    res = interpret.interpret_stroke(stroke((0.0, 2.0), (C4_ROW, C4_ROW + 4)), free_spec(),
                                     interpret.Mapping())
    pitches = [n.pitch for n in res.notes]
    assert pitches == sorted(pitches)
    assert pitches[0] == 60 and pitches[-1] == 64


def test_direction_does_not_matter():
    spec, mapping = free_spec(), interpret.Mapping()
    forward = interpret.interpret_stroke(stroke((0.5, 1.5), (C4_ROW, C4_ROW + 2)), spec, mapping)
    backward = interpret.interpret_stroke(stroke((1.5, 0.5), (C4_ROW + 2, C4_ROW)), spec, mapping)
    assert [n.pitch for n in forward.notes] == [n.pitch for n in backward.notes]


def test_scribbles_back_in_time_are_ignored():
    x = np.concatenate((np.linspace(0, 1, 50), np.linspace(1, 0.5, 20), np.linspace(0.5, 2, 50)))
    z = np.full(len(x), (C4_ROW + 0.5) * H)
    s = interpret.StrokeData(x, z, np.full(len(x), 0.02), np.ones(len(x)))
    res = interpret.interpret_stroke(s, free_spec(), interpret.Mapping())
    assert len(res.notes) == 1
    assert res.notes[0].end == pytest.approx(2.0, abs=0.01)


def test_dot_is_a_short_note():
    s = interpret.StrokeData(np.array([3.0]), np.array([(C4_ROW + 0.5) * H]),
                             np.array([0.02]), np.array([1.0]))
    res = interpret.interpret_stroke(s, free_spec(), interpret.Mapping())
    assert len(res.notes) == 1 and res.notes[0].pitch == 60
    assert res.notes[0].end - res.notes[0].start == pytest.approx(interpret.SHORT_NOTE)


def test_time_grid_quantizes_note_edges():
    spec = interpret.BoardSpec(time_grid="1_4", bpm=120)  # 0.5 s grid
    res = interpret.interpret_stroke(stroke((1.1, 2.4), (C4_ROW, C4_ROW)), spec,
                                     interpret.Mapping())
    assert [(n.start, n.end) for n in res.notes] == [(1.0, 2.5)]


def test_scale_snapping_in_quantized_mode():
    spec = free_spec(scale="MAJOR")
    res = interpret.interpret_stroke(stroke((0, 1), (C4_ROW + 1, C4_ROW + 1)), spec,
                                     interpret.Mapping())
    assert res.notes[0].pitch == 60  # C#4 row snaps to C4


def test_optical_mode_follows_the_line_continuously():
    res = interpret.interpret_stroke(stroke((0, 2), (C4_ROW, C4_ROW + 4)), free_spec(),
                                     interpret.Mapping(), mode="OPTICAL")
    assert len(res.voices) == 1
    pitch = res.voices[0].pitch
    assert pitch[0] == pytest.approx(60, abs=0.05) and pitch[-1] == pytest.approx(64, abs=0.05)
    assert np.any(np.abs(pitch - np.round(pitch)) > 0.2)  # glides between notes


def test_strokes_outside_the_loop_are_silent():
    spec = free_spec(length=4.0)
    assert not interpret.interpret_stroke(stroke((-2, -1), (5, 5)), spec,
                                          interpret.Mapping()).notes
    assert not interpret.interpret_stroke(stroke((5, 6), (5, 5)), spec,
                                          interpret.Mapping()).notes


def test_thickness_is_volume():
    spec, mapping = free_spec(), interpret.Mapping(thickness="VOLUME")
    thin = interpret.interpret_stroke(stroke((0, 1), (5, 5), radius=0.005), spec, mapping, radius_ref=0.02)
    thick = interpret.interpret_stroke(stroke((0, 1), (5, 5), radius=0.02), spec, mapping, radius_ref=0.02)
    assert thin.notes[0].velocity < thick.notes[0].velocity


def test_thickness_jitter_becomes_vibrato():
    rng = np.random.default_rng(1)
    jittery = 0.02 * (1 + 0.4 * rng.uniform(-1, 1, 200))
    mapping = interpret.Mapping(thickness="VOLUME_VIBRATO")
    wobbly = interpret.interpret_stroke(stroke((0, 1), (5, 5), radius=jittery), free_spec(), mapping)
    clean = interpret.interpret_stroke(stroke((0, 1), (5, 5), radius=0.02), free_spec(), mapping)
    assert np.mean(wobbly.voices[0].vibrato) > 0.1
    assert np.max(clean.voices[0].vibrato) == 0.0


def test_vertex_color_pan():
    mapping = interpret.Mapping(vertex_color="PAN")
    red = interpret.interpret_stroke(stroke((0, 1), (5, 5), color=(1, 0, 0, 1)), free_spec(), mapping)
    blue = interpret.interpret_stroke(stroke((0, 1), (5, 5), color=(0, 0, 1, 1)), free_spec(), mapping)
    assert np.mean(red.voices[0].pan) < -0.5 < 0.5 < np.mean(blue.voices[0].pan)


# --- synth ---------------------------------------------------------------------

def dominant_frequency(mono):
    spectrum = np.abs(np.fft.rfft(mono * np.hanning(len(mono))))
    return np.fft.rfftfreq(len(mono), 1 / SR)[np.argmax(spectrum)]


def voice(instrument, midi_pitch=69, duration=1.0):
    n = int(duration * interpret.CONTROL_RATE) + 1
    return interpret.Voice(0.0, duration, np.full(n, float(midi_pitch)), np.ones(n),
                           np.zeros(n), np.full(n, 0.7), np.zeros(n), instrument=instrument)


@pytest.mark.parametrize("ident", [i.ident for i in synth.INSTRUMENTS])
def test_every_instrument_renders(ident):
    offset, buf = synth.render_voice(voice(ident), SR)
    assert offset == 0 and buf.shape[1] == 2
    assert np.all(np.isfinite(buf))
    assert np.max(np.abs(buf)) > 0.05


@pytest.mark.parametrize("ident", ["SINE", "TRIANGLE", "SQUARE", "SAW", "PLUCK"])
def test_instruments_play_the_right_pitch(ident):
    _offset, buf = synth.render_voice(voice(ident, 69), SR)
    assert dominant_frequency(buf[: SR // 2, 0]) == pytest.approx(440.0, rel=0.02)


# --- effects -------------------------------------------------------------------

def test_effects_shapes():
    buf = np.zeros((SR, 2), dtype=np.float32)
    buf[0] = 1.0
    echoed = effects.delay(buf, SR, 0.25, 0.5, 0.5)
    assert len(echoed) > len(buf)
    assert echoed[int(0.25 * SR), 0] != 0 or echoed[int(0.25 * SR), 1] != 0
    assert len(effects.reverb(buf, SR, 0.5, 0.5)) > len(buf)
    assert effects.lofi(buf, SR, 0.5).shape == buf.shape
    assert effects.delay(buf, SR, 0.25, 0.5, 0.0) is buf


# --- mixer ---------------------------------------------------------------------

def test_mix_has_exact_loop_length_and_is_cached():
    spec = interpret.BoardSpec(length=4.0)
    layer = mixer.LayerInput("L1", [stroke((3.5, 4.0), (5, 5), instrument="BELL")],
                             fx=mixer.LayerFx(reverb_mix=0.5))
    first = mixer.render([layer], spec, interpret.Mapping(), SR)
    assert first.audio.shape == (4 * SR, 2)
    # The bell rings past the loop end and wraps to the beginning.
    assert np.max(np.abs(first.audio[: SR // 4])) > 0.001
    again = mixer.render([layer], spec, interpret.Mapping(), SR)
    assert again.key == first.key
    moved = mixer.LayerInput("L1", [stroke((3.0, 3.5), (5, 5), instrument="BELL")],
                             fx=layer.fx)
    assert mixer.render([moved], spec, interpret.Mapping(), SR).key != first.key


def test_empty_composition_is_silence():
    out = mixer.render([mixer.LayerInput("L1", [])], interpret.BoardSpec(length=2.0),
                       interpret.Mapping(), SR)
    assert out.audio.shape == (2 * SR, 2) and not np.any(out.audio)


# --- midi ----------------------------------------------------------------------

def parse_midi(data):
    assert data[:4] == b"MThd"
    _fmt, ntracks, ppq = struct.unpack(">HHH", data[8:14])
    pos, note_ons = 14, 0
    for _ in range(ntracks):
        assert data[pos:pos + 4] == b"MTrk"
        length = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        track = data[pos + 8:pos + 8 + length]
        note_ons += sum(1 for i in range(len(track) - 2)
                        if track[i] & 0xF0 == 0x90 and track[i + 2] > 0)
        assert track[-3:] == b"\xff\x2f\x00"
        pos += 8 + length
    return ntracks, ppq, note_ons


def test_midi_file_structure():
    notes = [interpret.MidiNote(0.0, 0.5, 60, 100), interpret.MidiNote(0.5, 1.0, 64, 90)]
    data = midi.build_midi([{"name": "L1", "program": 0, "notes": notes},
                            {"name": "Drums", "program": -1, "notes": notes[:1]}], 120)
    ntracks, ppq, note_ons = parse_midi(data)
    assert (ntracks, ppq, note_ons) == (3, midi.PPQ, 3)
