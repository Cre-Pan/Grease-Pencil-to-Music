# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests of the bpy-independent modules (music, interpret, synth,
effects, mixer, midi)."""

import json
import struct
from dataclasses import replace

import numpy as np
import pytest

from grease_pencil_to_music import effects, interpret, midi, mixer, music, synth, web_project

# The recorded instruments and rooms are read with Blender's audio module (aud), as in the
# add-on (samples.register does this when the add-on is enabled).
from grease_pencil_to_music import samples  # noqa: E402

synth.SAMPLE_LOADER = samples.load_recorded
effects.ROOM_LOADER = samples.load_room

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


def test_zigzag_in_time_sounds_every_part():
    # 0 -> 1 -> 0.5 -> 2: like an optical reader, each part under the playhead sounds.
    x = np.concatenate((np.linspace(0, 1, 50), np.linspace(1, 0.5, 20), np.linspace(0.5, 2, 50)))
    z = np.full(len(x), (C4_ROW + 0.5) * H)
    s = interpret.StrokeData(x, z, np.full(len(x), 0.02), np.ones(len(x)))
    res = interpret.interpret_stroke(s, free_spec(), interpret.Mapping())
    spans = sorted((round(n.start, 2), round(n.end, 2)) for n in res.notes)
    assert spans == [(0.0, 1.0), (0.5, 1.0), (0.5, 2.0)]


def semicircle(n=200):
    """Like the drawing: from top-left, round on the right, back to bottom-left."""
    angle = np.linspace(np.pi / 2, -np.pi / 2, n)
    x = 0.5 + 2.0 * np.cos(angle)
    z = (C4_ROW + 0.5) * H + 0.9 * np.sin(angle)
    return interpret.StrokeData(x, z, np.full(n, 0.02), np.ones(n))


def test_semicircle_plays_two_voices():
    optical = interpret.interpret_stroke(semicircle(), free_spec(), interpret.Mapping(),
                                         mode="OPTICAL")
    assert len(optical.voices) == 2
    upper, lower = sorted(optical.voices, key=lambda v: -float(np.mean(v.pitch)))
    assert np.mean(upper.pitch) > 60 > np.mean(lower.pitch)
    assert upper.start == pytest.approx(lower.start, abs=0.05)  # they sound together
    quantized = interpret.interpret_stroke(semicircle(), free_spec(), interpret.Mapping())
    assert min(n.pitch for n in quantized.notes) < 60 < max(n.pitch for n in quantized.notes)


def test_closed_circle_is_read_all_around():
    angle = np.linspace(0, 2 * np.pi, 240, endpoint=False)
    x = 2.0 + 1.0 * np.cos(angle)
    z = (C4_ROW + 0.5) * H + 0.6 * np.sin(angle)
    circle = interpret.StrokeData(x, z, np.full(240, 0.02), np.ones(240), cyclic=True)
    res = interpret.interpret_stroke(circle, free_spec(), interpret.Mapping(), mode="OPTICAL")
    covered = sorted((v.start, v.start + v.duration) for v in res.voices)
    assert covered[0][0] == pytest.approx(1.0, abs=0.02)
    assert max(end for _s, end in covered) == pytest.approx(3.0, abs=0.02)
    assert len(res.voices) >= 2


def test_split_runs_ignores_hand_jitter():
    x = np.linspace(0, 2, 100) + np.random.default_rng(3).normal(0, 0.002, 100)
    assert interpret.split_runs(x, 0.02) == [(0, 100)]


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


@pytest.mark.parametrize("ident", [i.ident for i in synth.INSTRUMENTS
                                   if i.ident not in ("SAMPLE", "LIBRARY")])
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


# --- 0.0.2 ---------------------------------------------------------------------

from grease_pencil_to_music import glyphs, timeline  # noqa: E402


def test_italian_note_names():
    assert music.note_name(60, "IT") == "Do4"
    assert music.note_name(67, "IT") == "Sol4"
    assert music.note_name(70, "IT") == "La#4"


def test_every_label_character_has_a_glyph():
    for style in ("EN", "IT"):
        for midi in range(12, 120):
            for char in music.note_name(midi, style).replace("-", ""):
                assert char in glyphs.GLYPHS, (style, char)
    for char in "0123456789s":
        assert char in glyphs.GLYPHS


def test_text_alignment():
    right = glyphs.text_polylines("C4", 0.0, 0.0, 1.0, "RIGHT")
    assert max(x for line in right for x, _y in line) == pytest.approx(0.0, abs=1e-9)
    centered = glyphs.text_polylines("8s", 2.0, 0.0, 1.0, "CENTER")
    xs = [x for line in centered for x, _y in line]
    assert (min(xs) + max(xs)) / 2 == pytest.approx(2.0, abs=0.1)


@pytest.mark.parametrize("ident", ["KICK", "SNARE", "HIHAT", "CRASH", "CLAP", "TOM", "COWBELL"])
def test_percussion_is_a_single_hit(ident):
    inst = synth.get_instrument(ident)
    assert inst.percussive and inst.gm_program == -1
    short = voice(ident, 50, duration=0.1)
    long = voice(ident, 50, duration=3.0)
    _o, a = synth.render_voice(short, SR)
    _o, b = synth.render_voice(long, SR)
    assert len(a) == len(b) == int(inst.length * SR)  # the stroke length does not matter
    assert np.max(np.abs(a)) > 0.05 and np.all(np.isfinite(a))


def test_drum_notes_follow_general_midi():
    assert synth.midi_drum_note("KICK", 70) == 36
    assert synth.midi_drum_note("HIHAT", 40) == 42
    assert synth.midi_drum_note("TOM", 36) < synth.midi_drum_note("TOM", 80)
    assert synth.midi_drum_note("DRUM", 55) == 55


def test_swing_delays_offbeats():
    spec = interpret.BoardSpec(time_grid="1_8", bpm=120, swing=0.5)  # 0.25 s grid
    on = interpret.interpret_stroke(stroke((1.0, 1.0), (5, 5)), spec, interpret.Mapping())
    off = interpret.interpret_stroke(stroke((1.25, 1.25), (5, 5)), spec, interpret.Mapping())
    assert on.notes[0].start == pytest.approx(1.0)
    assert off.notes[0].start == pytest.approx(1.25 + 0.125)


def filled(xs, rows_low, rows_high):
    x0, x1 = xs
    z0, z1 = (rows_low + 0.1) * H, (rows_high + 0.9) * H
    x = np.array([x0, x1, x1, x0], dtype=float)
    z = np.array([z0, z0, z1, z1], dtype=float)
    return interpret.StrokeData(x, z, np.full(4, 0.02), np.ones(4), filled=True)


def test_tonal_cluster_plays_the_covered_scale_notes():
    res = interpret.interpret_stroke(filled((1, 2), C4_ROW, C4_ROW + 4),
                                     free_spec(scale="MAJOR"), interpret.Mapping())
    assert sorted(n.pitch for n in res.notes) == [60, 62, 64]  # C D E


def test_noise_cluster_follows_the_shape():
    res = interpret.interpret_stroke(filled((1, 2), C4_ROW, C4_ROW + 12), free_spec(),
                                     interpret.Mapping(), fill_mode="NOISE")
    assert len(res.voices) == 1 and not res.notes
    v = res.voices[0]
    assert v.instrument == interpret.NOISE_BAND
    assert np.median(v.band_low) == pytest.approx(60, abs=0.6)
    assert np.median(v.band_high) == pytest.approx(72, abs=0.6)
    _o, buf = synth.render_voice(v, SR)
    spectrum = np.abs(np.fft.rfft(buf[:, 0]))
    freqs = np.fft.rfftfreq(len(buf), 1 / SR)
    inside = spectrum[(freqs > 280) & (freqs < 500)].mean()
    outside = spectrum[(freqs > 2000) & (freqs < 4000)].mean()
    assert inside > 10 * outside


def test_timeline_wave_sums_sources():
    seg = {"start": 1.0, "peaks": np.full(800, 0.4, dtype=np.float32), "rate": 100,
           "frame_from": 1.0, "frame_to": 193.0}
    frames, amp = timeline.build_wave([seg], 0.0, 200.0, 24.0)
    assert amp[(frames > 10) & (frames < 150)].min() == pytest.approx(0.4, abs=1e-6)
    assert amp[frames > 195].max() == 0.0
    _f, both = timeline.build_wave([seg, dict(seg)], 0.0, 200.0, 24.0)
    assert both.max() == pytest.approx(0.8, abs=1e-6)  # the mix adds up


@pytest.mark.parametrize("style,primitives", [("PEAKS", ["LINES"]), ("FILLED", ["TRIS"]),
                                              ("OUTLINE", ["LINES"]),
                                              ("RMS", ["TRIS", "LINES"]), ("NONE", [])])
def test_timeline_wave_styles(style, primitives):
    x = np.linspace(0, 100, 50)
    amp = np.abs(np.sin(x))
    parts = timeline.wave_geometry(x, amp, 0.0, 40.0, style)
    assert [p[0] for p in parts] == primitives
    for _primitive, vertices, _weight in parts:
        assert vertices[:, 1].min() >= -1e-4 and vertices[:, 1].max() <= 40.0 + 1e-4


def test_timeline_notes_and_optical_curves():
    data = {"notes": [(1.0, 2.0, 60, (1, 0, 0, 1))], "low": 48, "high": 84,
            "curves": [(0.0, np.linspace(60, 64, 20), (0, 0, 1, 1))], "curve_rate": 10.0}
    def to_x(frames):
        return np.asarray(frames) * 10.0
    tris, lines = timeline.note_geometry(data, 0.0, 24.0, to_x, 2000, 0.0, 74.0)
    red = tris[(1, 0, 0)]
    assert red[:, 0].min() == pytest.approx(240.0) and red[:, 0].max() == pytest.approx(480.0)
    blue = lines[(0, 0, 1)]
    assert blue[:, 1].min() < blue[:, 1].max()  # the glide rises
    none_t, none_l = timeline.note_geometry(data, 0.0, 24.0, to_x, 2000, 0.0, 74.0,
                                            show_notes=False, show_curves=False)
    assert not none_t and not none_l



# --- 0.0.4 ---------------------------------------------------------------------

def test_midi_roundtrip():
    notes = [interpret.MidiNote(0.0, 0.5, 60, 100), interpret.MidiNote(0.5, 1.5, 64, 80)]
    drums = [interpret.MidiNote(1.0, 1.1, 36, 120)]
    data = midi.build_midi([{"name": "Melodia", "program": 48, "notes": notes},
                            {"name": "Batteria", "program": -1, "notes": drums}], 90)
    tracks, bpm = midi.parse_midi(data)
    assert bpm == pytest.approx(90.0, abs=0.01)
    melody = next(t for t in tracks if t["name"] == "Melodia")
    assert melody["program"] == 48
    assert [(round(a, 3), round(b, 3), p, v) for a, b, p, v in melody["notes"]] == [
        (0.0, 0.5, 60, 100), (0.5, 1.5, 64, 80)]
    assert next(t for t in tracks if t["name"] == "Batteria")["program"] == -1


def test_midi_parser_rejects_garbage():
    with pytest.raises(midi.MidiError):
        midi.parse_midi(b"not a midi file")


def test_general_midi_mapping():
    assert synth.instrument_for_program(40, recorded=False) == "STRINGS"
    assert synth.instrument_for_program(80, recorded=False) == "SQUARE"
    assert synth.instrument_for_program(-1, 36) == "KICK"
    assert synth.instrument_for_program(-1, 42) == "HIHAT"
    assert synth.instrument_for_program(-1, 81, recorded=False) == "DRUM"


def test_sample_instrument_follows_the_pitch():
    rate = 22050
    tone = np.sin(2 * np.pi * 440 * np.arange(rate) / rate).astype(np.float32)  # A4
    synth.register_sample("test-a4", tone, rate, 69, True)
    up = voice(synth.SAMPLE_PREFIX + "test-a4", 81)  # one octave up
    _o, buf = synth.render_voice(up, SR)
    assert dominant_frequency(buf[: SR // 2, 0]) == pytest.approx(880.0, rel=0.02)
    missing = voice(synth.SAMPLE_PREFIX + "nothing", 69)
    assert not np.any(synth.render_voice(missing, SR)[1])


def test_instrument_effects_change_only_their_strokes():
    spec = interpret.BoardSpec(length=4.0)
    dry = stroke((1.0, 1.2), (5, 5))
    wet = stroke((1.0, 1.2), (5, 5))
    wet.fx = (0.0, 0.75, 0.35, 0.8, 0.9, 0.0)  # big reverb
    a = mixer.render([mixer.LayerInput("L", [dry])], spec, interpret.Mapping(), SR)
    b = mixer.render([mixer.LayerInput("L", [wet])], spec, interpret.Mapping(), SR)
    assert a.key != b.key
    tail = slice(int(2.0 * SR), int(3.0 * SR))
    assert np.abs(b.audio[tail]).max() > 10 * max(np.abs(a.audio[tail]).max(), 1e-6)


def test_legato_is_one_voice_that_slides_between_scale_notes():
    rising = stroke((0.0, 2.0), (C4_ROW, C4_ROW + 4))
    res = interpret.interpret_stroke(rising, free_spec(scale="MAJOR"), interpret.Mapping(),
                                     mode="LEGATO", glide=0.2)
    assert len(res.voices) == 1  # no new attack between notes
    pitch = res.voices[0].pitch
    assert pitch[0] == pytest.approx(60, abs=0.01) and pitch[-1] == pytest.approx(64, abs=0.01)
    assert np.all(np.diff(pitch) >= -1e-9)  # it only slides upwards
    assert np.any(np.abs(pitch - np.round(pitch)) > 0.2)  # glides between the notes
    assert [n.pitch for n in res.notes] == [60, 62, 64]  # but the notes are the scale's
    quick = interpret.interpret_stroke(rising, free_spec(scale="MAJOR"), interpret.Mapping(),
                                       mode="LEGATO", glide=0.01)
    held = lambda v: np.mean(np.abs(v.pitch - np.round(v.pitch)) < 0.05)
    assert held(quick.voices[0]) > held(res.voices[0])  # shorter glide = longer held notes


# --- 0.0.5: instrument libraries -------------------------------------------------------

import sf2_fixture  # noqa: E402
from grease_pencil_to_music import libraries  # noqa: E402


def test_sf2_presets_and_zones(tmp_path):
    path = tmp_path / "test.sf2"
    sf2_fixture.write_sf2(path)
    font = libraries.read_sf2(path)
    assert font.preset_list() == [(0, 0, 5, "Sine Test")]
    zones = font.zones(0)
    assert len(zones) == 1
    zone = zones[0]
    assert (zone.lo, zone.hi, zone.root, zone.loop) == (0, 127, 69.0, True)
    assert 0 < zone.loop_start < zone.loop_end <= len(zone.data)


def test_sf2_instrument_plays_in_tune_and_loops(tmp_path):
    path = tmp_path / "test.sf2"
    sf2_fixture.write_sf2(path)
    synth.register_zones("test-sf2", libraries.read_sf2(path).zones(0))
    long_note = voice(synth.LIBRARY_PREFIX + "test-sf2", 81, duration=3.0)
    _o, buf = synth.render_voice(long_note, SR)
    assert dominant_frequency(buf[: SR // 2, 0]) == pytest.approx(880.0, rel=0.02)
    # The sample lasts < 1 s at this pitch: the loop keeps the note sounding.
    assert np.abs(buf[int(2.5 * SR):int(2.8 * SR)]).max() > 0.1


def test_sf2_rejects_other_files(tmp_path):
    path = tmp_path / "bad.sf2"
    path.write_bytes(b"RIFF\0\0\0\0WAVE")
    with pytest.raises(libraries.LibraryError):
        libraries.read_sf2(path)
    # A SoundFont missing one of its tables: a clear error, not a KeyError.
    good = tmp_path / "good.sf2"
    sf2_fixture.write_sf2(good)
    path.write_bytes(good.read_bytes().replace(b"igen", b"junk"))
    with pytest.raises(libraries.LibraryError):
        libraries.read_sf2(path)


def test_sfz_regions_inheritance_and_note_names(tmp_path):
    assert libraries.sfz_key("c4") == 60 and libraries.sfz_key("a#3") == 58
    assert libraries.sfz_key("db4") == 61 and libraries.sfz_key("72") == 72
    regions = libraries.parse_sfz("<group> loop_mode=no_loop <region> sample=x y.wav key=60")
    assert regions == [{"loop_mode": "no_loop", "sample": "x y.wav", "key": "60"}]
    zones = libraries.sfz_zones(str(sf2_fixture.write_sfz(tmp_path)), sf2_fixture.read_wav)
    assert [(z.lo, z.hi, z.root) for z in zones] == [(36, 59, 57.0), (60, 127, 69.0)]
    synth.register_zones("test-sfz", zones)
    _o, low = synth.render_voice(voice(synth.LIBRARY_PREFIX + "test-sfz", 57), SR)
    _o, high = synth.render_voice(voice(synth.LIBRARY_PREFIX + "test-sfz", 76), SR)
    assert dominant_frequency(low[: SR // 2, 0]) == pytest.approx(220.0, rel=0.02)
    assert dominant_frequency(high[: SR // 2, 0]) == pytest.approx(659.3, rel=0.02)


def test_midi_input_decoding():
    from grease_pencil_to_music import midi_input
    assert midi_input.decode([0x90, 60, 100]) == ("on", 60, 100)
    assert midi_input.decode([0x93, 61, 1]) == ("on", 61, 1)  # any channel
    assert midi_input.decode([0x90, 60, 0]) == ("off", 60, 0)  # note on, velocity 0
    assert midi_input.decode([0x80, 60, 64]) == ("off", 60, 0)
    assert midi_input.decode([0xB0, 64, 127]) == ("sustain", 0, 127)
    assert midi_input.decode([0xB0, 7, 127]) is None  # other controllers ignored
    assert midi_input.decode([0xF8]) is None  # clock
    assert midi_input.decode(None) is None


def test_sections_repeat_each_loop_until_the_next_one():
    def part(pitch):
        return mixer.render([mixer.LayerInput("L", [stroke((0.5, 1.0), (pitch, pitch))])],
                            free_spec(length=2.0), interpret.Mapping(), SR, loop=False)

    first, second = part(C4_ROW), part(C4_ROW + 4)
    joined = mixer.sequence([(0.0, 5.0, first), (5.0, 7.0, second)], 2.0, SR)
    assert joined.duration == 7.0 and joined.sections == (0.0, 5.0)
    assert len(joined.audio) == 7 * SR
    assert [(n.pitch, n.start) for n in joined.notes] == [
        (60, 0.5), (60, 2.5), (60, 4.5), (64, 5.5)]
    rms = [float(np.sqrt(np.mean(joined.audio[int(t * SR):int((t + 0.3) * SR)] ** 2)))
           for t in (0.6, 1.6, 2.6, 4.6, 5.1, 5.6)]
    assert rms[0] > 0.01 and rms[2] > 0.01 and rms[3] > 0.01 and rms[5] > 0.01
    assert rms[1] < rms[0] * 0.2 and rms[4] < rms[0] * 0.2
    # A section shorter than a loop cuts its repetition (fading) and its notes.
    short = mixer.sequence([(0.0, 0.75, first), (0.75, 2.75, second)], 2.0, SR)
    assert [(n.pitch, n.start, n.end) for n in short.notes][0] == (60, 0.5, 0.75)
    assert mixer.sequence([(0.0, 5.0, first)], 2.0, SR).key != joined.key


def test_canon_repeats_the_layer_in_later_transposed_voices():
    line = stroke((0.5, 1.0), (C4_ROW, C4_ROW))
    spec, mapping = free_spec(length=2.0), interpret.Mapping()
    plain = mixer.render([mixer.LayerInput("L", [line])], spec, mapping, SR)
    canon = mixer.render([mixer.LayerInput("L", [line], canon_voices=3, canon_delay=1.0,
                                           canon_transpose=12)], spec, mapping, SR)
    # Third voice enters at 2.5 s: in a 2 s loop it wraps to 0.5 s.
    assert sorted((n.pitch, n.start) for n in canon.notes) == [(60, 0.5), (72, 1.5),
                                                               (84, 0.5)]
    assert canon.key != plain.key and canon.voice_count == 3 * plain.voice_count
    window = slice(int(1.6 * SR), int(1.9 * SR))
    assert np.abs(plain.audio[window]).max() < 0.01 < np.abs(canon.audio[window]).max()
    flat = mixer.render([mixer.LayerInput("L", [line], canon_voices=2, canon_delay=1.0)],
                        spec, mapping, SR, loop=False)
    assert [(n.pitch, n.start) for n in flat.notes] == [(60, 0.5), (60, 1.5)]


def test_gesture_mode_follows_the_drawing_speed():
    # A vertical stroke (C4 up to G4) drawn in one second: a rising scale run.
    n = 100
    rising = interpret.StrokeData(
        x=np.full(n, 1.0), z=(np.linspace(C4_ROW, C4_ROW + 7, n) + 0.5) * H,
        radius=np.full(n, 0.02), opacity=np.ones(n), instrument="SINE", layer="L1",
        times=np.linspace(0.0, 1.0, n))
    spec, mapping = interpret.BoardSpec(time_grid="1_16", min_note=0.05), interpret.Mapping()
    result = interpret.interpret_stroke(rising, spec, mapping, "GESTURE")
    assert [n.pitch for n in result.notes] == list(range(60, 68))
    assert result.notes[0].start == pytest.approx(1.0, abs=0.01)
    assert result.notes[-1].end == pytest.approx(2.0, abs=0.02)
    # The same horizontal stroke drawn slowly lasts longer than drawn fast.
    flat = stroke((1.0, 1.5), (C4_ROW, C4_ROW), n=n)
    flat.times = np.linspace(0.0, 2.0, n)
    note = interpret.interpret_stroke(flat, spec, mapping, "GESTURE").notes[0]
    assert (note.start, round(note.end, 2)) == (1.0, 3.0)
    # Without drawing time (script, MIDI import): read as "Quantizzata".
    flat.times = np.zeros(n)
    assert interpret.interpret_stroke(flat, spec, mapping, "GESTURE").notes == \
        interpret.interpret_stroke(flat, spec, mapping, "QUANTIZED").notes


# --- 0.0.6: five readings, legato across strokes, robust rendering ---------------------

def test_optical_legato_reads_each_stroke_like_optical():
    line = stroke((1.0, 2.0), (C4_ROW, C4_ROW + 3))
    optical = interpret.interpret_stroke(line, free_spec(), interpret.Mapping(), "OPTICAL")
    joined = interpret.interpret_stroke(line, free_spec(), interpret.Mapping(), "OPTICAL_LEGATO")
    assert len(joined.voices) == 1 and joined.voices[0].glide
    assert np.allclose(joined.voices[0].pitch, optical.voices[0].pitch)


def test_legato_join_glides_through_the_gap():
    spec, mapping = free_spec(), interpret.Mapping()
    first = interpret.interpret_stroke(stroke((1.0, 1.5), (C4_ROW, C4_ROW)), spec, mapping,
                                       "OPTICAL").voices[0]
    second = interpret.interpret_stroke(stroke((1.8, 2.3), (C4_ROW + 4, C4_ROW + 4)), spec,
                                        mapping, "OPTICAL").voices[0]
    far = interpret.interpret_stroke(stroke((5.0, 5.5), (C4_ROW, C4_ROW)), spec, mapping,
                                     "OPTICAL").voices[0]
    joined = interpret.legato_join([second, far, first], gap=0.5)
    assert [sorted(m) for m, _v in joined] == [[0, 2], [1]]  # the far one stays alone
    voice = joined[0][1]
    assert voice.start == pytest.approx(1.0) and voice.duration == pytest.approx(1.3, abs=0.01)
    times = voice.start + np.arange(len(voice.pitch)) / interpret.CONTROL_RATE
    gap = (times > 1.55) & (times < 1.75)
    assert voice.pitch[0] == pytest.approx(60, abs=0.05)
    assert voice.pitch[-1] == pytest.approx(64, abs=0.05)
    assert np.all(np.diff(voice.pitch[gap]) > 0)  # slides up through the pause
    assert np.all(voice.amp[gap] > 0)  # and keeps sounding
    # Different instruments and percussion never join.
    drum = replace(second, instrument="KICK")
    melodic = lambda v: not synth.get_instrument(v.instrument).percussive  # noqa: E731
    assert len(interpret.legato_join([first, drum], 1.0, melodic)) == 2
    assert len(interpret.legato_join([first, replace(second, instrument="SAW")], 1.0)) == 2


def test_legato_layers_join_strokes_in_the_mix():
    spec = free_spec(length=4.0, bpm=120.0)
    strokes = [stroke((0.5, 1.0), (C4_ROW, C4_ROW)), stroke((1.2, 1.7), (C4_ROW + 2, C4_ROW + 2))]
    loose = mixer.render([mixer.LayerInput("L", strokes, mode="OPTICAL")], spec,
                         interpret.Mapping(), SR)
    joined = mixer.render([mixer.LayerInput("L", strokes, mode="OPTICAL_LEGATO")], spec,
                          interpret.Mapping(), SR)
    apart = mixer.render([mixer.LayerInput("L", strokes, mode="OPTICAL_LEGATO",
                                           legato_gap=0.2)], spec, interpret.Mapping(), SR)
    assert loose.voice_count == 2 and joined.voice_count == 1 and apart.voice_count == 2
    assert len(joined.notes) == len(loose.notes)  # MIDI keeps every note
    pause = slice(int(1.08 * SR), int(1.12 * SR))  # between the strokes (after the release)
    assert np.abs(joined.audio[pause]).max() > 5 * max(np.abs(loose.audio[pause]).max(), 1e-4)
    assert joined.key != loose.key != apart.key
    quantized = mixer.render([mixer.LayerInput("L", strokes, mode="LEGATO")], spec,
                             interpret.Mapping(), SR)
    assert quantized.voice_count == 1


def test_plucked_sounds_hold_the_optical_glide():
    rising = stroke((0.0, 2.0), (C4_ROW, C4_ROW + 12))
    res = interpret.interpret_stroke(rising, free_spec(), interpret.Mapping(), "OPTICAL")
    voice = replace(res.voices[0], instrument="PLUCK")
    _o, held = synth.render_voice(voice, SR)
    _o, plain = synth.render_voice(replace(voice, glide=False), SR)
    late = slice(int(1.6 * SR), int(1.9 * SR))
    assert np.abs(held[late]).max() > 3 * np.abs(plain[late]).max()
    # The held tone follows the line: an octave higher at the end than at the start.
    early = held[int(0.2 * SR):int(0.45 * SR), 0]
    end = held[int(1.6 * SR):int(1.85 * SR), 0]
    assert dominant_frequency(end) > 1.6 * dominant_frequency(early)


def test_one_broken_voice_does_not_silence_the_mix(monkeypatch):
    mixer.clear_cache()
    spec = free_spec(length=4.0)
    good = stroke((0.5, 1.0), (C4_ROW, C4_ROW))
    bad = stroke((2.0, 2.5), (C4_ROW, C4_ROW), instrument="SAW")
    real = synth.render_voice

    def flaky(voice, *args):
        if voice.instrument == "SAW":
            raise ValueError("broken")
        return real(voice, *args)

    monkeypatch.setattr(synth, "render_voice", flaky)
    result = mixer.render([mixer.LayerInput("L", [good, bad])], spec, interpret.Mapping(), SR)
    assert result.errors == 1 and result.voice_count == 1
    assert np.abs(result.audio[int(0.6 * SR):int(0.9 * SR)]).max() > 0.01
    monkeypatch.setattr(synth, "render_voice", real)  # fixed: rendered again, not cached
    again = mixer.render([mixer.LayerInput("L", [good, bad])], spec, interpret.Mapping(), SR)
    assert again.errors == 0 and again.voice_count == 2


def test_cache_is_limited_in_memory():
    cache = mixer._LRU(100, max_bytes=1000)
    for i in range(5):
        cache.put(i, np.zeros(100, dtype=np.float32))  # 400 bytes each
    assert len(cache.data) == 2 and cache.bytes == 800
    assert cache.get(4) is not None and cache.get(0) is None
    cache.put(4, np.zeros(10, dtype=np.float32))
    assert cache.bytes == 440


# --- sound while drawing (draw_sound, pure part) -----------------------------------

def test_draw_sound_tracker_follows_the_growing_stroke():
    from grease_pencil_to_music import draw_sound
    t = draw_sound.Tracker()
    k = ("comp", "L1", 1)
    assert t.update(k, 3, 10, 0.0) is None  # first look: nothing is heard
    assert t.update(k, 4, 1, 0.01) == "start"  # the pen touches the board
    assert t.update(k, 4, 5, 0.02) == "move"
    assert t.update(k, 4, 5, 0.1) is None  # held still for a moment
    assert t.update(k, 4, 9, 0.2) == "move"
    assert t.update(k, 4, 9, 0.2 + draw_sound.SILENCE_AFTER + 0.01) == "stop"
    assert t.update(k, 4, 9, 2.0) is None
    # undo or eraser: silence, never a note
    assert t.update(k, 5, 2, 3.0) == "start"
    assert t.update(k, 4, 9, 3.01) == "stop"
    assert t.update(k, 2, 9, 3.02) is None
    # another drawing: only look
    assert t.update(("comp", "L2", 2), 3, 4, 3.03) is None
    assert t.update(("comp", "L2", 2), 3, 6, 3.04) == "start"
    assert t.update(None, 0, 0, 3.05) == "stop"


def test_draw_sound_tip_pitch_follows_rows_scale_and_reading():
    from grease_pencil_to_music import draw_sound
    spec = interpret.BoardSpec(low_note=48, row_height=H, scale="MAJOR", root=0)
    rows = 36
    assert draw_sound.tip_pitch((12 + 0.5) * H, spec, "QUANTIZED", rows) == 60
    # C#4 snaps to the C major scale (ties go down)
    assert draw_sound.tip_pitch((13 + 0.5) * H, spec, "QUANTIZED", rows) == 60
    assert draw_sound.tip_pitch((14 + 0.5) * H, spec, "GESTURE", rows) == 62
    # optical: continuous, centred on the row
    assert draw_sound.tip_pitch((13 + 0.75) * H, spec, "OPTICAL", rows) == pytest.approx(61.25)
    assert draw_sound.tip_pitch(-0.01, spec, "QUANTIZED", rows) is None
    assert draw_sound.tip_pitch((rows + 0.5) * H, spec, "OPTICAL", rows) is None


def test_draw_sound_tip_volume_uses_thickness_only_when_mapped():
    from grease_pencil_to_music import draw_sound
    loud = draw_sound.tip_volume(0.04, 0.04, interpret.Mapping(thickness="VOLUME"))
    soft = draw_sound.tip_volume(0.01, 0.04, interpret.Mapping(thickness="VOLUME"))
    assert loud > soft > 0
    assert draw_sound.tip_volume(0.0, 0.04, interpret.Mapping(thickness="VOLUME")) > 0
    assert draw_sound.tip_volume(0.01, 0.04, interpret.Mapping(thickness="NONE")) == loud


# --- New instruments, harmony and master bus -----------------------------------------

@pytest.mark.parametrize("ident", ["EPIANO", "MARIMBA", "PAD", "BASS", "OPENHAT", "RIM",
                                   "SHAKER"])
def test_new_instruments_render(ident):
    interp = interpret.interpret_stroke(stroke((1.0, 2.0), (C4_ROW, C4_ROW), instrument=ident),
                                        free_spec(), interpret.Mapping())
    offset, buf = synth.render_voice(interp.voices[0], SR)
    assert buf.shape[1] == 2 and np.all(np.isfinite(buf))
    assert 0.05 < float(np.max(np.abs(buf))) < 2.0


def test_new_instruments_in_midi_import():
    assert synth.instrument_for_program(0, recorded=False) == "EPIANO"
    assert synth.instrument_for_program(12, recorded=False) == "MARIMBA"
    assert synth.instrument_for_program(33, recorded=False) == "BASS"
    assert synth.instrument_for_program(89, recorded=False) == "PAD"
    assert synth.instrument_for_program(-1, 46) == "OPENHAT"
    assert synth.midi_drum_note("SHAKER", 60) == 70


def test_diatonic_shift_stays_in_scale():
    # C major: a third above C is E, above B is D, a sixth below E is G.
    assert music.diatonic_shift([60, 71], 2, "MAJOR", 0).tolist() == [64, 74]
    assert music.diatonic_shift([64], -5, "MAJOR", 0).tolist() == [55]
    # The fractional part (a glide) is kept.
    assert music.diatonic_shift([60.3], 2, "MAJOR", 0)[0] == pytest.approx(64.3)
    # A minor pentatonic: one step above A is C.
    assert music.diatonic_shift([57], 1, "PENTA_MINOR", 9).tolist() == [60]
    # The chromatic scale harmonizes in major.
    assert music.diatonic_shift([62], 2, "CHROMATIC", 0).tolist() == [65]


def test_harmony_adds_voices_and_notes():
    spec = free_spec(scale="MAJOR")
    layer = mixer.LayerInput("L1", [stroke((1.0, 2.0), (C4_ROW, C4_ROW))], harmony="TRIAD")
    result = mixer.render([layer], spec, interpret.Mapping(), SR)
    assert sorted(n.pitch for n in result.notes) == [60, 64, 67]
    assert result.voice_count == 3
    drums = mixer.LayerInput("L1", [stroke((1.0, 1.1), (C4_ROW, C4_ROW), instrument="KICK")],
                             harmony="TRIAD")
    assert len(mixer.render([drums], spec, interpret.Mapping(), SR).notes) == 1


def test_harmony_in_legato_keeps_voices_apart():
    spec = free_spec(scale="MAJOR")
    layer = mixer.LayerInput("L1", [stroke((1.0, 2.0), (C4_ROW, C4_ROW + 2))],
                             mode="LEGATO", harmony="THIRD")
    result = mixer.render([layer], spec, interpret.Mapping(), SR)
    assert result.voice_count == 2


def test_master_never_clips_and_loops_seamlessly():
    rng = np.random.default_rng(1)
    loud = (rng.uniform(-3.0, 3.0, (SR * 2, 2))).astype(np.float32)
    out = effects.master(loud, SR, ambience=0.3, loop=True)
    assert out.shape == loud.shape and np.all(np.isfinite(out))
    assert float(np.max(np.abs(out))) <= 10 ** (-1.0 / 20) + 1e-6
    # Quiet material passes almost untouched (no pumping below the threshold).
    t = np.arange(SR) / SR
    quiet = np.stack([0.05 * np.sin(2 * np.pi * 440 * t)] * 2, axis=1).astype(np.float32)
    calm = effects.master(quiet, SR, ambience=0.0, loop=True)
    assert np.max(np.abs(calm)) == pytest.approx(0.05 * effects.MASTER_MAKEUP, rel=0.1)


def test_master_on_render_and_key():
    spec = free_spec()
    strokes = [stroke((0.5 + 0.1 * k, 3.0), (C4_ROW + k, C4_ROW + k), radius=0.2)
               for k in range(12)]
    layer = mixer.LayerInput("L1", strokes)
    raw = mixer.render([layer], spec, interpret.Mapping(), SR, master_volume=2.0)
    done = mixer.render([layer], spec, interpret.Mapping(), SR, master_volume=2.0,
                        master_fx=mixer.MasterFx())
    assert raw.key != done.key
    assert float(np.max(np.abs(done.audio))) <= 0.9
    assert len(done.audio) == len(raw.audio)


# --- Web app project (.json) ----------------------------------------------------------------

def _web(**state):
    import json
    base = {"name": "T", "bpm": 120, "bars": 1, "low": 48, "octaves": 3, "scale": "MAJOR",
            "root": 0, "grid": 0.25, "strokes": [],
            "layers": [{"id": "a", "name": "A", "mode": "QUANTIZED"}]}
    base.update(state)
    return json.dumps({"app": web_project.APP_ID, "version": 3, "state": base})


def test_web_beat_follows_swing_and_the_ab_chain():
    tracks = {"KICK": {"p": [2] + [0] * 31, "pB": [0] * 32},
              "SNARE": {"p": [0] * 32, "pB": [0, 1] + [0] * 30}}
    beat = {"on": True, "steps": 16, "swing": 0.5, "ab": True,
            "chain": ["A", "B", "-"] + ["A"] * 29, "tracks": tracks}
    hits = web_project.beat_hits(beat, bars=4)
    # Bar 1 = A (kick), bar 2 = B (snare on the swung second 16th), bar 3 rests, bar 4 = A.
    assert hits == [(0.0, "KICK", 1.0), (4.25 + 0.0625, "SNARE", 0.7), (12.0, "KICK", 1.0)]
    assert web_project.beat_hits({**beat, "on": False}, bars=4) == []


def test_web_instruments_fall_back_when_the_addon_lacks_them():
    available = set(synth.INSTRUMENT_BY_ID)
    assert web_project.addon_instrument("GUITAR", available) == "PLUCK"
    assert web_project.addon_instrument("HAT", available) == "HIHAT"
    assert web_project.addon_instrument("PAD", {"STRINGS"}) == "STRINGS"
    assert web_project.addon_instrument("WAV:x", available) is None
    project = web_project.parse(_web(strokes=[
        {"id": "s", "layer": "a", "inst": "WAV:x", "pts": [[0, 60.5, 0.5, 0]]}]), available)
    assert project.skipped == ["WAV:x"] and len(project.layers[0].strokes) == 1


def test_new_web_instruments_round_trip_to_addon_sounds():
    available = set(synth.INSTRUMENT_BY_ID)
    for web_id in ("ORGAN", "BRASS", "CHOIR", "VIBES", "OCARINA", "CRASH", "COWBELL", "CONGA",
                   "PIANO", "TRUMPET", "TROMBONE", "HORN", "SAX", "CLARINET", "OBOE",
                   "BASSOON", "TUBA", "VIOLIN", "CELLO", "HARP", "GLOCK", "STRINGS_PIZZ",
                   "VIOLIN_STAC", "CELLO_PIZZ", "GONG", "TEMPLE", "GUIRO", "GLASS",
                   "GRAND", "HARPSI", "PIPEORGAN", "XYLO", "TUBULAR", "KALIMBA", "RECORDER",
                   "HARMONICA", "DARBUKA", "CAJON"):
        assert web_project.addon_instrument(web_id, available) in available
    assert web_project.ADDON_TO_WEB["TRIANGLE"] == "OCARINA"
    assert web_project.ADDON_TO_WEB["CRASH"] == "CRASH"
    assert web_project.ADDON_TO_WEB["COWBELL"] == "COWBELL"


def test_web_grid_and_scale_mapping():
    assert web_project.grid_ident(0.25) == "1_16" and web_project.grid_ident(1 / 3) == "1_8T"
    assert web_project.grid_beats("1_8") == 0.5
    project = web_project.parse(_web(scale="PENTA", root=14, grid=0), set())
    assert (project.scale, project.root, project.grid) == ("PENTA_MAJOR", 2, "OFF")


def test_web_project_round_trip_keeps_the_drawing():
    available = set(synth.INSTRUMENT_BY_ID)
    text = _web(bpm=90, bars=2, layers=[
        {"id": "a", "name": "Melodia", "mode": "OPTICAL", "volume": 0.5, "reverb": 0.3}],
        strokes=[{"id": "s", "layer": "a", "inst": "STRINGS", "op": 0.8, "brush": "air",
                  "pts": [[0.5, 64.5, 0.4, 0], [2.5, 67.5, 0.6, 900]]}])
    project = web_project.parse(text, available, row_height=0.2, seconds_width=2.0)
    st = project.layers[0].strokes[0]
    assert st.x.tolist() == pytest.approx([0.5 * 2 / 3 * 2, 2.5 * 2 / 3 * 2])  # beats → s → x
    assert st.z.tolist() == pytest.approx([16.5 * 0.2, 19.5 * 0.2])
    assert st.times.tolist() == pytest.approx([0.0, 0.9]) and st.softness == 0.8
    again = web_project.parse(web_project.dump(project), available, 0.2, 2.0)
    st2 = again.layers[0].strokes[0]
    assert st2.x.tolist() == pytest.approx(st.x.tolist(), abs=1e-3)
    assert st2.z.tolist() == pytest.approx(st.z.tolist(), abs=1e-3)
    assert st2.radius.tolist() == pytest.approx(st.radius.tolist(), abs=1e-3)
    assert st2.instrument == "S_STRINGS" and st2.softness == 0.8 and st2.opacity == 0.8
    layer = again.layers[0]
    assert (layer.mode, layer.volume, layer.reverb) == ("OPTICAL", 0.5, 0.3)
    assert again.board.bpm == 90 and again.board.length == pytest.approx(2 * 4 * 60 / 90)


def test_web_project_rejects_other_json():
    with pytest.raises(web_project.ProjectError):
        web_project.parse('{"layers": []}', set())
    with pytest.raises(web_project.ProjectError):
        web_project.parse("not json", set())


# --- 0.0.10: robustness and speed --------------------------------------------------

@pytest.mark.parametrize("height", [0, 1, 5, 11])
def test_timeline_collapsed_to_a_bar_draws_nothing(height):
    assert timeline.wave_band(height, 0.6) is None


@pytest.mark.parametrize("height", [12, 20, 40, 79, 80, 300, 1200])
@pytest.mark.parametrize("fraction", [0.05, 0.6, 1.0])
def test_timeline_wave_stays_inside_the_region(height, fraction):
    y0, y1 = timeline.wave_band(height, fraction)
    assert 0.0 <= y0 < y1 <= height


def _exact_low_cut(buffer, rate, cutoff=30.0):
    spectrum = np.fft.rfft(buffer, axis=0)
    f = np.maximum(np.fft.rfftfreq(len(buffer), 1.0 / rate), 1e-3)
    spectrum *= ((f / cutoff) ** 4 / (1.0 + (f / cutoff) ** 4))[:, None]
    return np.fft.irfft(spectrum, n=len(buffer), axis=0)


@pytest.mark.parametrize("n", [3000, 44100 * 3 + 1, 48000 * 4 + 3, 44100 * 8])
def test_low_cut_matches_the_exact_circular_filter(n):
    """Long loops use the short-kernel convolution: same result as one FFT as
    long as the loop (any length, prime factors included), DC removed."""
    rng = np.random.default_rng(3)
    buffer = rng.standard_normal((n, 2)) * 0.3 + 0.2
    out = effects.low_cut(buffer, 48000)
    assert out.shape == buffer.shape
    assert np.max(np.abs(out - _exact_low_cut(buffer, 48000))) < 1e-9
    assert np.max(np.abs(out.mean(axis=0))) < 1e-9


def test_reverb_impulse_is_computed_once():
    ir, key = effects.reverb_ir(SR, 0.55)
    again, key_again = effects.reverb_ir(SR, 0.55)
    assert again is ir and key == key_again and not ir.flags.writeable
    assert ir.shape == (int((0.3 + 0.55 * 2.7) * SR), 2)
    assert np.sum(ir[:, 0] ** 2) == pytest.approx(1.0)


# --- the web app's instruments (0.0.11) -------------------------------------------------

def test_every_web_instrument_has_its_own_addon_instrument():
    from grease_pencil_to_music import web_instruments
    available = set(synth.INSTRUMENT_BY_ID)
    assert len(web_instruments.INSTRUMENTS) == 89
    for row in web_instruments.INSTRUMENTS:
        ident = web_project.addon_instrument(row["id"], available)
        if row["zones"]:  # recorded: the same recordings, not a synth stand-in
            assert ident == "S_" + row["id"]
            assert synth.INSTRUMENT_BY_ID[ident].label == row["name"]
        assert web_project.ADDON_TO_WEB[ident] == row["id"]  # and back to the same one
    assert {"ORGAN", "CHOIR", "BRASS"} <= available
    # Without the recordings (an older add-on) the synth stand-ins are still there.
    assert web_project.addon_instrument("CELLO", available - {"S_CELLO"}) == "STRINGS"


def test_recorded_zones_are_the_bundled_files():
    synth.SAMPLES.pop("S_CELLO", None)
    zones = synth.recorded_zones("S_CELLO")
    assert [z.root for z in zones] == list(synth.RECORDINGS["S_CELLO"].zones)
    assert all(z.data is None for z in zones)  # read when they first play
    assert all(z.rate == 44100 and len(synth.zone_ready(z).data) > z.offset for z in zones)
    assert len(synth.recorded_zones("S_GONG")) == 1


def test_unreadable_recordings_are_not_kept_silent(monkeypatch):
    """A recording that cannot be read (a file locked for a moment) is skipped as an
    error, so neither the instrument nor the render caches keep it silent."""
    loader = synth.SAMPLE_LOADER
    calls = []

    def broken(ident):
        calls.append(ident)
        raise OSError("locked")

    synth.SAMPLES.pop("S_FLUTE", None)
    mixer.clear_cache()
    monkeypatch.setattr(synth, "SAMPLE_LOADER", broken)
    with pytest.raises(OSError):
        synth.render_voice(voice("S_FLUTE", 69, 0.5), SR)
    assert "S_FLUTE" not in synth.SAMPLES
    zone = synth.Zone(None, 44100.0, 69.0, source=lambda: (_ for _ in ()).throw(OSError("x")))
    with pytest.raises(OSError):
        synth.zone_ready(zone)
    assert zone.source is not None  # read again next time
    monkeypatch.setattr(synth, "SAMPLE_LOADER", loader)
    _offset, buf = synth.render_voice(voice("S_FLUTE", 69, 0.5), SR)
    assert float(np.max(np.abs(buf))) > 0.01 and calls == ["S_FLUTE"]


@pytest.mark.parametrize("ident,note", [("S_FLUTE", 69), ("S_PIANO", 69), ("S_CELLO", 57),
                                        ("S_TRUMPET", 70)])
def test_recorded_instruments_play_the_right_pitch(ident, note):
    _offset, buf = synth.render_voice(voice(ident, note, 1.5), SR)
    f0 = float(music.midi_to_freq(note))
    found = dominant_frequency(buf[SR // 10: SR, 0])
    # The strongest partial: the fundamental or one of the first harmonics.
    assert min(abs(found / (k * f0) - 1) for k in (1, 2, 3)) < 0.03


def test_sustained_recordings_loop_past_their_end():
    _offset, buf = synth.render_voice(voice("S_CELLO", 48, 12.0), SR)
    rms = [float(np.sqrt(np.mean(buf[k * SR:(k + 1) * SR, 0] ** 2))) for k in range(12)]
    assert min(rms[1:]) > 0.4 * rms[0]  # still playing after the recording (about 4 s)
    _offset, short = synth.render_voice(voice("S_VIOLIN_PIZZ", 60, 12.0), SR)
    assert float(np.max(np.abs(short[8 * SR:]))) < 0.01  # a pizzicato dies away


def test_recorded_hits_and_held_scrapes():
    gong = synth.INSTRUMENT_BY_ID["S_GONG"]
    assert gong.percussive and gong.drum_note == 52 and gong.length > 3
    _offset, buf = synth.render_voice(voice("S_TAIKO", 60, 0.2), SR)
    assert len(buf) == int(synth.INSTRUMENT_BY_ID["S_TAIKO"].length * SR)
    assert np.max(np.abs(buf)) > 0.2
    short = synth.render_voice(voice("S_GUIRO", 60, 0.3), SR)[1]
    long_ = synth.render_voice(voice("S_GUIRO", 60, 1.2), SR)[1]
    assert len(short) == int((0.3 + synth.HOLD_FADE) * SR) and len(long_) > len(short)
    assert synth.midi_drum_note("S_CONGA", 60) == 63


def test_new_synths_sound_and_hold_their_pitch():
    for ident in ("ORGAN", "CHOIR", "BRASS"):
        _offset, buf = synth.render_voice(voice(ident, 57, 1.0), SR)
        assert np.all(np.isfinite(buf)) and np.max(np.abs(buf)) > 0.1
        found = dominant_frequency(buf[SR // 4: SR, 0])
        f0 = float(music.midi_to_freq(57))
        assert min(abs(found / (k * f0) - 1) for k in (0.5, 1, 2, 3, 4)) < 0.03, ident


def test_midi_programs_pick_the_recorded_instrument():
    assert synth.instrument_for_program(42) == "S_CELLO"
    assert synth.instrument_for_program(0) == "S_PIANO"
    assert synth.instrument_for_program(38) == "BASS"  # nothing recorded: the synth
    assert synth.instrument_for_program(-1, 36) == "KICK"
    assert synth.instrument_for_program(-1, 63) == "S_CONGA"


def test_recorded_rooms():
    impulse = np.zeros((SR // 2, 2), dtype=np.float32)
    impulse[0] = 1.0
    tails = {room: effects.reverb(impulse, SR, 1.0, 0.5, room=room) for room in effects.ROOMS}
    assert len(tails["CHURCH"]) > len(tails["CONCERT"]) > len(tails["ROOM"])
    ir, _key = effects.room_ir("CHURCH", SR)
    assert np.sum(ir ** 2, axis=0) == pytest.approx([1.0, 1.0])
    assert effects.room_ir("HALL", SR) is None
    assert effects.room_ir("CONCERT", 48000)[0].shape[1] == 2
    project = web_project.parse(_web(room="church"), set())
    assert project.room == "CHURCH"
    assert json.loads(web_project.dump(project))["state"]["room"] == "church"
    project.room = "HALL"
    assert "room" not in json.loads(web_project.dump(project))["state"]


# --- Absolute thickness, stems --------------------------------------------------------

def test_thickness_is_an_absolute_volume():
    ref = interpret.full_radius(0.12)
    assert interpret.thickness_level(ref, ref) == pytest.approx(1.0)
    assert interpret.thickness_level(ref * 3, ref) == pytest.approx(1.0)
    assert 0.06 <= interpret.thickness_level(ref / 100, ref) < 0.1
    spec = interpret.BoardSpec(length=4.0)
    thin = mixer.LayerInput("A", [stroke((0.2, 1.5), (5, 5), radius=0.01)])
    thick = mixer.LayerInput("B", [stroke((2.0, 3.5), (9, 9), radius=0.3)])
    alone = mixer.render([thin], spec, interpret.Mapping(), SR)
    both = mixer.render([thin, thick], spec, interpret.Mapping(), SR, stems=True)
    window = slice(int(0.5 * SR), int(1.2 * SR))
    assert np.abs(both.stems[0][1][window]).max() == pytest.approx(
        np.abs(alone.audio[window]).max(), rel=1e-4)


def test_stems_add_up_to_the_mix_through_the_master_bus():
    spec = interpret.BoardSpec(length=2.0)
    layers = [mixer.LayerInput("A", [stroke((0.1, 1.0), (5, 5), radius=0.05)]),
              mixer.LayerInput("B", [stroke((0.5, 1.8), (9, 9), radius=0.3)],
                               fx=mixer.LayerFx(reverb_mix=0.4))]
    for fx in (None, mixer.MasterFx()):
        result = mixer.render(layers, spec, interpret.Mapping(), SR, master_fx=fx, stems=True)
        assert [name for name, _a in result.stems] == ["A", "B"]
        total = sum(audio for _name, audio in result.stems)
        assert np.abs(total - result.audio).max() < 1e-4
        plain = mixer.render(layers, spec, interpret.Mapping(), SR, master_fx=fx)
        assert np.abs(plain.audio - result.audio).max() < 1e-5
        assert plain.key == result.key


def test_one_layer_mixed_again_with_the_others_sound():
    spec, mapping = interpret.BoardSpec(length=2.0), interpret.Mapping()
    a = mixer.LayerInput("A", [stroke((0.1, 1.0), (5, 5))])
    b = mixer.LayerInput("B", [stroke((0.5, 1.8), (9, 9))])
    b2 = mixer.LayerInput("B", [stroke((0.5, 1.8), (12, 12))])
    first = mixer.render_layers([a, b], spec, mapping, SR)
    fresh = mixer.render_layers([b2], spec, mapping, SR)
    partial = mixer.mix_layers([first[0], fresh[0]], spec, mapping, SR,
                               master_fx=mixer.MasterFx(), stems=True)
    full = mixer.render([a, b2], spec, mapping, SR, master_fx=mixer.MasterFx(), stems=True)
    assert partial.key == full.key
    assert np.abs(partial.audio - full.audio).max() < 1e-6


def test_sections_keep_one_stem_per_layer():
    spec = interpret.BoardSpec(length=2.0)
    a = mixer.LayerInput("A", [stroke((0.1, 1.0), (5, 5))])
    b = mixer.LayerInput("B", [stroke((0.5, 1.8), (9, 9))])
    parts = [(0.0, 4.0, mixer.render([a, b], spec, interpret.Mapping(), SR, loop=False,
                                     stems=True)),
             (4.0, 6.0, mixer.render([a], spec, interpret.Mapping(), SR, loop=False,
                                     stems=True))]
    joined = mixer.sequence(parts, 2.0, SR, master_fx=mixer.MasterFx(), stems=True)
    assert sorted(name for name, _a in joined.stems) == ["A", "B"]
    total = sum(audio for _name, audio in joined.stems)
    assert np.abs(total - joined.audio).max() < 1e-4


# --- layer modifiers (0.0.15) -----------------------------------------------------------

from grease_pencil_to_music import layer_mods  # noqa: E402

MB = layer_mods.Board(low_note=48, row_height=H, seconds_width=1.0, length=8.0, bpm=120.0,
                      rows=37, scale="MAJOR", root=0)


def test_mods_off_keep_the_strokes():
    s = stroke((1.0, 2.0), (C4_ROW, C4_ROW))
    out = layer_mods.apply([s], layer_mods.Stack(), MB)
    assert out == [s] and not layer_mods.Stack()


def test_array_repeats_every_beats_and_climbs_the_scale():
    s = stroke((0.0, 0.4), (C4_ROW, C4_ROW))  # C4 = degree 0 of C major
    stack = layer_mods.Stack(array=layer_mods.Array(count=3, beats=2.0, pitch=1, decay=0.5))
    out = layer_mods.apply([s], stack, MB)
    assert len(out) == 3
    beat = 0.5  # 120 BPM, one second per board unit
    assert np.allclose([o.x[0] for o in out], [0.0, 2 * beat, 4 * beat])
    notes = [round(48 + o.z[0] / H - 0.5) for o in out]
    assert notes == [60, 62, 64]  # C, D, E
    assert np.allclose([o.radius[0] for o in out], [0.02, 0.01, 0.005])
    fill = layer_mods.Stack(array=layer_mods.Array(fill=True, beats=4.0))  # 2 s apart, 8 s loop
    assert len(layer_mods.apply([s], fill, MB)) == 4
    assert s.x[0] == 0.0  # the input is untouched


def test_mirror_in_time_and_pitch():
    s = stroke((1.0, 2.0), (C4_ROW, C4_ROW + 4))
    stack = layer_mods.Stack(mirror=layer_mods.Mirror(time=True, pitch=True, keep=False))
    out = layer_mods.apply([s], stack, MB)
    assert len(out) == 3  # time, pitch, both
    t = out[0]
    assert np.all(np.diff(t.x) >= 0)  # still runs forward in time
    assert np.isclose(t.x[0], 8.0 - 2.0) and np.isclose(t.z[0], s.z[-1])
    centre = 0.5 * 37 * H
    assert np.allclose(out[1].z, 2 * centre - s.z)


def test_transpose_fade_and_noise():
    s = stroke((0.0, 2.0), (C4_ROW, C4_ROW))
    semis = layer_mods.Stack(transpose=layer_mods.Transpose(steps=-3, unit="SEMITONES"))
    assert np.allclose(layer_mods.apply([s], semis, MB)[0].z, s.z - 3 * H)
    fade = layer_mods.Stack(fade=layer_mods.Fade(direction="BOTH", length=0.5, minimum=0.0))
    r = layer_mods.apply([s], fade, MB)[0].radius
    assert r[0] == 0 and r[-1] == 0 and np.isclose(r[len(r) // 2], 0.02, rtol=1e-3)
    song = layer_mods.Stack(fade=layer_mods.Fade(direction="OUT", scope="SONG", length=1.0))
    late = layer_mods.apply([stroke((6.0, 7.0), (C4_ROW, C4_ROW))], song, MB)[0]
    assert late.radius.max() < 0.02 * 0.3
    noisy = layer_mods.Stack(noise=layer_mods.Noise(pitch=0.5, width=0.5, time=0.1))
    a = layer_mods.apply([s], noisy, MB)[0]
    b = layer_mods.apply([stroke((5.0, 6.0), (2, 2)), s], noisy, MB)[1]
    assert not np.allclose(a.z, s.z) and np.allclose(a.z, b.z)  # same stroke, same noise


def test_layer_modifiers_change_the_sound():
    spec = free_spec()
    mapping = interpret.Mapping()
    s = stroke((0.5, 1.0), (C4_ROW, C4_ROW))
    plain = mixer.render_layers([mixer.LayerInput("L1", [s])], spec, mapping, SR)[0]
    array = mixer.LayerInput("L1", [s], mods=layer_mods.Stack(
        array=layer_mods.Array(count=3, beats=2.0)))
    copied = mixer.render_layers([array], spec, mapping, SR)[0]
    assert len(copied.notes) == 3 * len(plain.notes)
    assert copied.key != plain.key


def test_web_modifiers_round_trip():
    web = [{"type": "array", "on": True, "count": 3, "beats": 2, "pitch": 1, "unit": "semi"},
           {"type": "jitter", "on": False, "pitch": 0.3},
           {"type": "fade", "dir": "both", "scope": "song", "len": 0.3, "min": 0.1},
           {"type": "array", "count": 9}]  # only one Array in the add-on
    values = web_project.mods_to_settings(web)
    assert values["use_array"] and values["array_count"] == 3
    assert values["array_unit"] == "SEMITONES" and values["use_noise"] is False
    assert values["fade_direction"] == "BOTH" and values["fade_scope"] == "SONG"
    back = web_project.settings_to_mods(values)
    assert [m["type"] for m in back] == ["array", "fade"]
    assert back[0]["unit"] == "semi" and back[1]["dir"] == "both"


def test_every_instrument_is_in_one_family_with_an_icon():
    import collections
    import pathlib

    from grease_pencil_to_music import families
    listed = [i for f in families.ALL for i in families.idents(f)]
    assert [i for i, n in collections.Counter(listed).items() if n > 1] == []
    assert sorted(listed) == sorted(i.ident for i in synth.INSTRUMENTS)
    folder = pathlib.Path(families.__file__).parent / "icons"
    for name in families.icon_names():
        assert (folder / f"inst_{name}.png").is_file(), name
    for ident in listed:
        assert families.icon_name(ident) or ident in families.BUILTIN_ICONS, ident
    # The recorded instrument comes before the synth of the same kind.
    flutes = families.idents(families.family_of("SINE"))
    assert flutes.index("S_FLUTE") < flutes.index("SINE")


# --- 0.0.28: faster master bus, same sound ---------------------------------------------

def _master_linear_reference(buffer, rate, ambience, room="HALL"):
    """The linear part of the master bus as it was computed before 0.0.28 (room
    convolution folded onto the loop, then the low cut)."""
    out = np.asarray(buffer, dtype=np.float64)
    n = len(out)
    if ambience > 0:
        dry = out
        wet = effects.reverb(out.astype(np.float32), rate, 1.0, effects.MASTER_ROOM_SIZE,
                             room=room).astype(np.float64)
        wet[:n] -= dry
        wet *= 0.35 * ambience
        out = dry + effects._fold(wet, n)
    return effects.low_cut(out, rate)


@pytest.mark.parametrize("room", ["HALL", "ROOM"])
@pytest.mark.parametrize("ambience", [0.0, 0.25, 1.0])
def test_master_linear_in_one_product_is_the_same_filter(ambience, room):
    n = SR * 4  # a fast FFT length: the one-product path
    assert effects._fast_fft_length(n)
    x = np.random.default_rng(3).normal(0.0, 0.2, (n, 2)).astype(np.float32)
    fast = effects.master_linear(x, SR, ambience, True, room)
    reference = _master_linear_reference(x, SR, ambience, room)
    assert fast.shape == reference.shape
    # Far below one step of a 16-bit file (3e-5).
    assert np.max(np.abs(fast - reference)) < 1e-6


def test_master_linear_odd_lengths_and_short_loops_keep_the_old_path():
    rng = np.random.default_rng(4)
    for n in (SR * 4 + 1, SR // 2):  # large prime factors; shorter than the room
        x = rng.normal(0.0, 0.2, (n, 2)).astype(np.float32)
        out = effects.master_linear(x, SR, 0.25, True)
        assert np.array_equal(out, _master_linear_reference(x, SR, 0.25))


def test_block_gain_interpolation_is_np_interp():
    rng = np.random.default_rng(5)
    for count, n in ((1, 10), (2, 64), (2, 100), (37, 37 * 64), (37, 37 * 64 - 5), (5, 1000)):
        gain = rng.uniform(0.2, 1.0, count)
        centers = (np.arange(count) + 0.5) * effects.MASTER_BLOCK
        expected = np.interp(np.arange(n), centers, gain)
        assert np.allclose(effects._block_gain_to_samples(gain, n), expected, rtol=0,
                           atol=1e-15)


def test_volume_changes_reuse_the_room_of_the_master_bus(monkeypatch):
    """Layer volume and master volume scale the cached room of a layer instead of
    computing it again; the sound is the one of a fresh render."""
    spec = free_spec(length=2.0)
    mapping = interpret.Mapping()
    fx = mixer.MasterFx(ambience=0.4)

    def layers(gain):
        return [mixer.LayerInput("A", [stroke((0.1, 0.9), (12, 12))], gain=gain),
                mixer.LayerInput("B", [stroke((0.5, 1.5), (16, 19), instrument="SAW")])]
    mixer.clear_cache()
    mixer.render(layers(1.0), spec, mapping, SR, master_volume=0.8, master_fx=fx, stems=True)
    calls = []
    original = effects.master_linear
    monkeypatch.setattr(effects, "master_linear",
                        lambda *a, **k: calls.append(1) or original(*a, **k))
    for gain, volume in ((0.5, 0.8), (0.5, 0.6), (0.9, 0.3)):
        cached = mixer.render(layers(gain), spec, mapping, SR, master_volume=volume,
                              master_fx=fx, stems=True)
        assert not calls  # no room computed again
        mixer.clear_cache()
        fresh = mixer.render(layers(gain), spec, mapping, SR, master_volume=volume,
                             master_fx=fx, stems=True)
        calls.clear()
        assert np.max(np.abs(cached.audio - fresh.audio)) < 1e-5
        for (_n1, a), (_n2, b) in zip(cached.stems, fresh.stems):
            assert np.max(np.abs(a - b)) < 1e-5
        mixer.clear_cache()
        mixer.render(layers(1.0), spec, mapping, SR, master_volume=0.8, master_fx=fx,
                     stems=True)
        calls.clear()


def test_sections_use_the_room_of_the_composition():
    """Keyframe sections render the layer reverbs in the composition's room too."""
    spec = free_spec(length=1.0)
    mapping = interpret.Mapping()
    layer = mixer.LayerInput("A", [stroke((0.1, 0.5), (12, 12))],
                             fx=mixer.LayerFx(reverb_mix=0.6))
    hall = mixer.render([layer], spec, mapping, SR, loop=False, room="HALL")
    church = mixer.render([layer], spec, mapping, SR, loop=False, room="CHURCH")
    count = min(len(hall.audio), len(church.audio))
    assert len(hall.audio) != len(church.audio) or not np.allclose(
        hall.audio[:count], church.audio[:count])


@pytest.mark.parametrize("mode", ["QUANTIZED", "LEGATO"])
@pytest.mark.parametrize("instrument", ["SAW", "S_PIANO", "PLUCK"])
def test_instrument_volume_scales_the_voices_without_synthesis(monkeypatch, mode, instrument):
    """Changing an instrument's volume reuses the voices rendered at volume 1: same
    sound (and MIDI velocities) as synthesizing them again, no synthesis."""
    spec = free_spec(length=2.0)
    mapping = interpret.Mapping()

    def layer(gain):
        strokes = [replace(stroke((0.1, 0.6), (12, 14), instrument=instrument), gain=gain),
                   replace(stroke((0.7, 1.2), (16, 16), instrument=instrument), gain=gain),
                   replace(filled((1.3, 1.8), 10, 14), instrument=instrument, gain=gain)]
        return [mixer.LayerInput("A", strokes, mode=mode, fx=mixer.LayerFx(reverb_mix=0.3))]
    mixer.clear_cache()
    mixer.render(layer(1.0), spec, mapping, SR, master_fx=mixer.MasterFx())
    calls = []
    original = mixer._render_voices
    monkeypatch.setattr(mixer, "_render_voices",
                        lambda *a, **k: calls.append(1) or original(*a, **k))
    for gain in (0.4, 1.7, 0.9):
        cached = mixer.render(layer(gain), spec, mapping, SR, master_fx=mixer.MasterFx())
        assert not calls
        monkeypatch.setattr(mixer, "_unit_gain", lambda *a: None)  # synthesized again
        mixer.clear_cache()
        fresh = mixer.render(layer(gain), spec, mapping, SR, master_fx=mixer.MasterFx())
        monkeypatch.undo()
        monkeypatch.setattr(mixer, "_render_voices",
                            lambda *a, **k: calls.append(1) or original(*a, **k))
        assert np.max(np.abs(cached.audio - fresh.audio)) < 1e-5
        assert [(n.pitch, n.velocity) for n in cached.notes] == \
            [(n.pitch, n.velocity) for n in fresh.notes]
        mixer.clear_cache()
        mixer.render(layer(1.0), spec, mapping, SR, master_fx=mixer.MasterFx())
        calls.clear()


def test_loud_strokes_are_synthesized_again_at_the_ceiling():
    """Where the volume would push a voice past the amplitude ceiling (interpret clips
    it), the stroke is synthesized at its own volume, as before."""
    spec = free_spec(length=1.0)
    mapping = interpret.Mapping()
    loud = replace(stroke((0.1, 0.8), (12, 12), radius=0.2), gain=2.0)
    args = (spec, mapping, "QUANTIZED", "TONAL", interpret.full_radius(H), (), 0.12, 0,
            None, "OFF")
    unit = mixer._unit_gain(loud, args)
    peak = max(float(np.max(v.amp)) for v in mixer._interpret_stroke(
        replace(loud, gain=1.0), *args)[1].voices)
    assert (unit is None) == (peak * 2.0 >= mixer.AMP_CEILING)


# --- Composizione Bit ----------------------------------------------------------------

def test_bit_reads_each_stroke_on_its_lane_drum():
    from types import SimpleNamespace

    from grease_pencil_to_music import beat
    from grease_pencil_to_music.interpret import StrokeData
    lanes = [SimpleNamespace(drum=d) for d in ("KICK", "SNARE", "TOM")]
    s = SimpleNamespace(kind="BEAT", lanes=3, lane_drums=lanes, row_height=0.1)
    h = beat.lane_height(s)
    assert h == pytest.approx(0.45)
    assert beat.lane_at(s, 0.0) == 0 and beat.lane_at(s, 3 * h - 1e-6) == 2
    assert beat.lane_at(s, -0.01) is None and beat.lane_at(s, 3 * h) is None

    def stroke(z0, z1):
        return StrokeData(x=np.array([0.0, 1.0]), z=np.array([z0, z1]),
                          radius=np.full(2, 0.02), opacity=np.ones(2), instrument="PIANO")
    low, high, slanted, tom, above = beat.read_strokes(s, [
        stroke(0.05, 0.06), stroke(0.4, 0.41), stroke(0.46, 0.85),
        stroke(1.0, 1.1), stroke(5.0, 5.0)])
    assert low.instrument == high.instrument == "KICK"
    assert np.allclose(low.z, high.z) and np.ptp(low.z) == 0  # flat, same height
    assert slanted.instrument == "SNARE" and np.ptp(slanted.z) == 0
    assert tom.instrument == "TOM" and above.instrument == "TOM"  # clamped to the board
    assert round(tom.z[0] / 0.1 - 0.5) == beat.LANE_PITCH["TOM"]
    assert all(beat.default_drum(0, used=beat.DEFAULT_DRUMS[:i]) == beat.DEFAULT_DRUMS[i]
               for i in range(len(beat.DEFAULT_DRUMS)))


# --- Layer modifiers on the strokes (stroke_mods: the formulas of the nodes) ---------------

from grease_pencil_to_music import stroke_mods  # noqa: E402


def _node_shift(pitch, steps, scale, root):
    """The diatonic shift as the node group computes it, from the tables."""
    degrees, intervals, n = stroke_mods.degree_tables(scale, root)
    base = np.round(pitch)
    rel = base - root
    pc = np.mod(rel, 12)
    octave = (rel - pc) / 12
    d = np.array([degrees[int(c)] for c in pc]) + steps
    q = np.floor(d / n)
    r = (d - q * n).astype(int)
    note = root + 12 * (octave + q) + np.array([intervals[i] for i in r])
    return pitch + (note - base)


@pytest.mark.parametrize("scale", [ident for ident, _l, _i in music.SCALES])
def test_stroke_mods_tables_match_the_diatonic_shift(scale):
    pitch = np.arange(30.0, 90.0, 0.25)
    for root in range(12):
        for steps in (-9, -3, -1, 1, 2, 5, 11):
            expected = music.diatonic_shift(pitch, steps, scale, root)
            assert np.allclose(_node_shift(pitch, steps, scale, root), expected), \
                (scale, root, steps)


def test_stroke_mods_inputs_of_a_stack():
    off = stroke_mods.node_inputs(layer_mods.Stack(), MB)
    assert off["Array Count"] == 1 and off["Mirror Count"] == 1 and off["Mirror 0"] == 0
    assert off["Transpose"] == 0 and not off["Fade"] and not off["Noise"]
    stack = layer_mods.Stack(
        array=layer_mods.Array(count=3, beats=2.0, decay=0.2),
        mirror=layer_mods.Mirror(time=True, pitch=True, keep=False),
        fade=layer_mods.Fade(direction="OUT"))
    values = stroke_mods.node_inputs(stack, MB)
    assert values["Array Count"] == 3 and values["Array Step"] == pytest.approx(2 * MB.beat)
    assert values["Array Decay"] == pytest.approx(0.8)
    assert values["Mirror Count"] == 3
    assert [values[f"Mirror {i}"] for i in range(3)] == [1, 2, 3]
    assert values["Fade"] and values["Fade Out"] and not values["Fade In"]
    names = {name for name, _kind in stroke_mods.INPUTS}
    assert set(values) == names


def test_array_and_transpose_keep_the_shape_of_a_glide():
    """0.0.36: in the scale a stroke moves whole (its first point by degrees, the rest
    by as many semitones): a glide stays a glide, no zigzags."""
    x = np.linspace(0.5, 2.0, 80)
    z = (61.0 - MB.low_note + 0.5) * H + np.linspace(0, 7 * H, 80)  # C#4 up to G#4
    glide = interpret.StrokeData(x=x, z=z, radius=np.full(80, 0.03), opacity=np.ones(80))
    board = replace(MB, scale="MAJOR", root=0)
    for stack in (layer_mods.Stack(array=layer_mods.Array(count=4, pitch=2)),
                  layer_mods.Stack(transpose=layer_mods.Transpose(steps=3))):
        for out in layer_mods.apply([glide], stack, board):
            moved = out.z - glide.z
            assert np.allclose(moved, moved[0])  # one shift for the whole stroke
            semis = moved[0] / H
            assert semis == pytest.approx(round(semis))
    # The first point lands on the degree: C#4 is read as C4, two degrees up is E4.
    copy = layer_mods.apply([glide], layer_mods.Stack(array=layer_mods.Array(count=2, pitch=2)),
                            board)[1]
    assert (copy.z[0] - glide.z[0]) / H == pytest.approx(3.0)  # C#4 -> E4 + its 0 cents
