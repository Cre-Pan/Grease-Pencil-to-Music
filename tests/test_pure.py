# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests of the bpy-independent modules (music, interpret, synth,
effects, mixer, midi)."""

import struct
from dataclasses import replace

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
    assert synth.instrument_for_program(40) == "STRINGS"
    assert synth.instrument_for_program(80) == "SQUARE"
    assert synth.instrument_for_program(-1, 36) == "KICK"
    assert synth.instrument_for_program(-1, 42) == "HIHAT"
    assert synth.instrument_for_program(-1, 81) == "DRUM"


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
