# SPDX-License-Identifier: GPL-3.0-or-later
"""Integration tests inside Blender (bpy module).

The extension zip is built, installed and enabled exactly like a user would do
with "Install from Disk", then the whole workflow is exercised in background
mode: add a composition, draw strokes, edit them, mute materials and layers,
export WAV/MP3/MIDI.
"""

import os
import pathlib
import sys
import wave

import numpy as np
import pytest

bpy = pytest.importorskip("bpy")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import build_zip  # noqa: E402

MODULE = "bl_ext.user_default.grease_pencil_to_music"
PLATFORM = {"linux": "linux-x64", "win32": "windows-x64", "darwin": "macos-arm64"}[sys.platform]


@pytest.fixture(scope="module")
def addon(tmp_path_factory):
    bpy.ops.wm.read_factory_settings(use_empty=False)
    zip_path = build_zip.build(tmp_path_factory.mktemp("dist"), PLATFORM)
    result = bpy.ops.extensions.package_install_files(
        filepath=str(zip_path), repo="user_default", enable_on_install=True)
    assert result == {"FINISHED"}
    assert MODULE in bpy.context.preferences.addons
    preferences = bpy.context.preferences.addons[MODULE].preferences
    # Most tests want a richer starting point than the default (1 layer, 1 instrument).
    preferences.new_layers = 3
    preferences.new_instruments = "ALL"
    package = sys.modules[MODULE]
    yield package
    bpy.ops.preferences.addon_disable(module=MODULE)


def sub(name):
    return sys.modules[f"{MODULE}.{name}"]


@pytest.fixture
def comp(addon):
    assert bpy.ops.gp2m.add_composition() == {"FINISHED"}
    obj = bpy.context.view_layer.objects.active
    yield obj
    sub("engine")._state.pop(obj.name, None)


def add_stroke(obj, layer_index, points, radius=0.02, material_index=0, frame=None):
    """``points``: (x, z) pairs in board coordinates; ``layer_index`` counts the
    user layers only (0 = "Livello 1"); ``frame``: keyframe number (new if missing)."""
    layer = sub("board").user_layers(obj.data)[layer_index]
    if frame is None:
        drawing = layer.frames[0].drawing
    else:
        key = next((f for f in layer.frames if f.frame_number == frame), None)
        drawing = (key or layer.frames.new(frame)).drawing
    drawing.add_strokes([len(points)])
    stroke = drawing.strokes[len(drawing.strokes) - 1]
    stroke.material_index = material_index
    for point, (x, z) in zip(stroke.points, points):
        point.position = (x, 0.0, z)
        point.radius = radius
        point.opacity = 1.0
    drawing.tag_positions_changed()
    return stroke


def row_z(obj, midi):
    s = obj.gp2m
    return (midi - s.low_note + 0.5) * s.row_height


def line(obj, x0, x1, midi, n=40):
    return [(x, row_z(obj, midi)) for x in np.linspace(x0, x1, n)]


def read_wav(path):
    with wave.open(path) as handle:
        frames = handle.readframes(handle.getnframes())
        return handle.getframerate(), np.frombuffer(frames, dtype="<i2").reshape(-1, 2)


def test_menu_and_panels_are_registered(addon):
    assert hasattr(bpy.types, "VIEW3D_MT_gp2m_add")
    assert hasattr(bpy.types, "GP2M_PT_main")
    assert hasattr(bpy.ops.gp2m, "add_composition")


def test_add_composition_is_one_object(comp):
    board = sub("board")
    s = comp.gp2m
    assert s.is_composition and comp.name.startswith("Composizione Musicale")
    assert len(comp.children) == 0  # no parent lines: everything is inside
    names = [layer.name for layer in comp.data.layers]
    assert [l.name for l in board.user_layers(comp.data)] == ["Livello 1", "Livello 2",
                                                              "Livello 3"]
    # Board at the bottom, playhead on top, user layers in between.
    assert board.is_board_layer(comp.data.layers[0]) and names[-1] == board.HEAD_LAYER
    assert all(layer.lock for layer in comp.data.layers if board.is_board_layer(layer))
    assert comp.data.layers.active.name == "Livello 1"
    instruments = [slot.material.gp2m_instrument for slot in comp.material_slots
                   if not board.is_board_material(slot.material)]
    assert len(instruments) == 15 and {"PLUCK", "KICK", "SNARE", "HIHAT"} <= set(instruments)
    labels = comp.data.layers.get("GP2M Etichette").frames[0].drawing
    assert len(labels.strokes) > 10
    # Empty composition: a silent strip already exists and the scene loops 8 s.
    scene = bpy.context.scene
    strip = sub("engine").find_strip(scene, comp)
    assert strip is not None and os.path.exists(bpy.path.abspath(strip.sound.filepath))
    fps = scene.render.fps / scene.render.fps_base
    assert scene.frame_end - scene.frame_start + 1 == round(8 * fps)


def test_playhead_follows_time(comp):
    board = sub("board")
    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    scene.frame_set(scene.frame_start + int(fps))  # one second later
    evaluated = comp.evaluated_get(bpy.context.evaluated_depsgraph_get())
    head = evaluated.data.layers[board.HEAD_LAYER]
    assert head.translation[0] == pytest.approx(comp.gp2m.seconds_width, abs=1e-4)
    scene.frame_set(scene.frame_start)


def test_key_labels_options(comp):
    board = sub("board")
    def label_strokes():
        return len(comp.data.layers.get("GP2M Etichette").frames[0].drawing.strokes)
    counts = {}
    for mode in ("NONE", "C", "WHITE", "ALL"):
        comp.gp2m.key_labels = mode
        board._rebuild_pending()
        counts[mode] = label_strokes()
    assert counts["NONE"] < counts["C"] < counts["WHITE"] < counts["ALL"]
    # Rebuilding keeps the drawing and the active layer.
    assert comp.data.layers.active.name == "Livello 1"


def test_drawing_produces_sound(comp):
    engine = sub("engine")
    add_stroke(comp, 0, line(comp, 1.0, 3.0, 60))  # C4 for two seconds
    add_stroke(comp, 0, line(comp, 4.0, 5.0, 67), material_index=5)  # G4, guitar
    result = engine.regenerate(comp)
    assert sorted(n.pitch for n in result.notes) == [60, 67]
    rate, samples = read_wav(engine.find_strip(bpy.context.scene, comp).sound.filepath)
    assert rate == 44100
    assert np.abs(samples[int(1.5 * rate)]).max() > 500  # sound during the first note
    assert np.abs(samples[int(0.5 * rate)]).max() == 0  # silence before it


def test_edit_mode_changes_update_the_sound(comp):
    engine = sub("engine")
    stroke = add_stroke(comp, 0, line(comp, 1.0, 2.0, 60))
    first = engine.regenerate(comp)
    # Like moving the stroke up one row in Edit Mode.
    for point in stroke.points:
        x, y, z = point.position
        point.position = (x, y, z + comp.gp2m.row_height)
    second = engine.regenerate(comp)
    assert second.key != first.key
    assert [n.pitch for n in second.notes] == [61]
    # Like the Thickness tool in Sculpt Mode: only volume changes, key too.
    for point in stroke.points:
        point.radius *= 0.3
    assert engine.regenerate(comp).key != second.key


def test_depsgraph_handler_marks_composition_dirty(comp):
    handlers = sub("handlers")
    handlers._dirty.clear()
    add_stroke(comp, 0, line(comp, 0.5, 1.5, 62))
    bpy.context.view_layer.update()
    assert comp.name in handlers._dirty
    handlers.flush()
    stats = sub("engine").state(comp)["stats"]
    assert stats["notes"] == 1


def test_hidden_material_and_layer_are_muted(comp):
    engine = sub("engine")
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60), material_index=0)
    add_stroke(comp, 1, line(comp, 3.0, 4.0, 64), material_index=3)
    assert len(engine.regenerate(comp).notes) == 2
    comp.material_slots[3].material.grease_pencil.hide = True
    try:
        assert [n.pitch for n in engine.regenerate(comp).notes] == [60]
    finally:
        comp.material_slots[3].material.grease_pencil.hide = False
    sub("board").user_layers(comp.data)[0].hide = True
    assert [n.pitch for n in engine.regenerate(comp).notes] == [64]


def test_modifiers_are_ignored_unless_requested(comp):
    engine, reader = sub("engine"), sub("reader")
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60))
    before = engine.regenerate(comp)
    comp.modifiers.new("Noise", "GREASE_PENCIL_NOISE")
    assert reader.has_unsupported_stack(comp)
    assert engine.regenerate(comp).key == before.key
    # "Usa modificatori": an Array modifier makes the stroke play twice.
    comp.modifiers.clear()
    array = comp.modifiers.new("Array", "GREASE_PENCIL_ARRAY")
    array.count = 2
    array.use_relative_offset = False
    array.use_constant_offset = True
    array.constant_offset = (2.0, 0.0, 0.0)
    comp.gp2m.use_modifiers = True
    bpy.context.view_layer.update()
    starts = sorted(round(n.start, 2) for n in engine.regenerate(comp).notes)
    assert len(starts) == 2 and starts[1] - starts[0] == pytest.approx(2.0, abs=0.05)


def test_layer_modes_and_effects(comp):
    engine, props = sub("engine"), sub("props")
    add_stroke(comp, 0, [(x, row_z(comp, 60) + (x - 1.0) * 0.3) for x in np.linspace(1, 2, 60)])
    quantized = engine.regenerate(comp)
    settings = props.find_layer_settings(comp.data, "Livello 1")
    settings.mode = "OPTICAL"
    settings.reverb_mix = 0.4
    optical = engine.regenerate(comp)
    assert optical.key != quantized.key
    assert optical.voice_count == 1 and quantized.voice_count > 1


def test_export_wav_mp3_midi(comp, tmp_path):
    add_stroke(comp, 0, line(comp, 0.5, 1.5, 60))
    add_stroke(comp, 1, line(comp, 2.0, 2.2, 40), material_index=7)  # drums
    add_stroke(comp, 1, line(comp, 3.0, 3.2, 50), material_index=8)  # kick
    for fmt, ext in (("WAV", ".wav"), ("MP3", ".mp3"), ("MIDI", ".mid")):
        path = tmp_path / f"out{ext}"
        assert bpy.ops.gp2m.export(format=fmt, filepath=str(path)) == {"FINISHED"}
        data = path.read_bytes()
        assert len(data) > 100
    assert (tmp_path / "out.wav").read_bytes()[:4] == b"RIFF"
    mp3 = (tmp_path / "out.mp3").read_bytes()
    assert mp3[:3] == b"ID3" or (mp3[0] == 0xFF and mp3[1] & 0xE0 == 0xE0)
    assert (tmp_path / "out.mid").read_bytes()[:4] == b"MThd"


def test_board_rebuild_follows_settings(comp):
    board = sub("board")
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60))
    keys_before = len(comp.data.layers.get("GP2M Tasti").frames[0].drawing.strokes)
    comp.gp2m.length = 4.0
    comp.gp2m.octaves = 2
    board._rebuild_pending()  # normally run by a timer
    keys_after = len(comp.data.layers.get("GP2M Tasti").frames[0].drawing.strokes)
    assert keys_after < keys_before
    # The user's drawing survives the rebuild.
    assert len(board.user_layers(comp.data)[0].frames[0].drawing.strokes) == 1
    assert sub("engine").regenerate(comp).audio.shape[0] == 4 * 44100


class MockLayout:
    """Stand-in for ``bpy.types.UILayout`` that validates what panels draw."""

    def __init__(self, log):
        self.log = log

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)

    def _child(self, *_args, **_kwargs):
        return MockLayout(self.log)

    def column(self, *_args, **_kwargs):
        return MockLayout(self.log)

    row = box = split = grid_flow = _child

    def label(self, **_kwargs):
        pass

    def separator(self, **_kwargs):
        pass

    def menu(self, menu_id, **_kwargs):
        if menu_id == "GP2M_MT_add_instrument":
            self.log.append(("menu", menu_id))
            return
        assert hasattr(bpy.types, menu_id), menu_id
        self.log.append(("menu", menu_id))

    def prop(self, data, attr, **_kwargs):
        target = getattr(data, "_target", data)
        assert attr in target.bl_rna.properties, f"{type(target).__name__}.{attr}"
        self.log.append(("prop", attr))

    def template_list(self, list_id, _list_name, data, propname, active_data, active_prop,
                      **_kwargs):
        ui_list = getattr(bpy.types, list_id)
        assert propname in data.bl_rna.properties, propname
        assert active_prop in active_data.bl_rna.properties, active_prop
        items = list(getattr(data, propname))
        fake = type("FakeList", (), {"bitflag_filter_item": 1 << 30})()
        flags, order = ui_list.filter_items(fake, bpy.context, data, propname)
        assert len(flags) == len(items) and (not order or sorted(order) == list(range(len(items))))
        for item, flag in zip(items, flags):
            if flag:
                ui_list.draw_item(fake, bpy.context, MockLayout(self.log), data, item, 0,
                                  active_data, active_prop)
        self.log.append(("list", list_id))

    def template_ID(self, data, prop, **_kwargs):
        assert prop in data.bl_rna.properties, prop
        self.log.append(("prop", prop))

    def context_pointer_set(self, name, data):
        self.log.append(("context", name))

    def popover(self, panel, **_kwargs):
        assert hasattr(bpy.types, panel), panel
        self.log.append(("popover", panel))

    def operator_menu_enum(self, idname, prop, **_kwargs):
        self.operator(idname)
        module, name = idname.split(".")
        rna = getattr(getattr(bpy.ops, module), name).get_rna_type()
        assert prop in rna.properties, prop

    def operator(self, idname, **_kwargs):
        module, name = idname.split(".")
        assert hasattr(getattr(bpy.ops, module), name), idname
        self.log.append(("operator", idname))
        return type("OperatorProps", (), {})()


class _Drawer:
    def __init__(self, log, target=None):
        self.layout = MockLayout(log)
        self._target = target

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_target"), name)


def test_panels_menus_and_preferences_draw(comp):
    ui = sub("ui")
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60))
    sub("engine").regenerate(comp)
    log = []
    for panel in ui.classes:
        if issubclass(panel, bpy.types.Panel) and panel is not ui.GP2M_PT_material:
            assert panel.poll(bpy.context) if hasattr(panel, "poll") else True
            panel.draw(_Drawer(log), bpy.context)
    # The Material panel needs context.material (Properties editor only).
    material = comp.material_slots[0].material
    for ident in ("SAMPLE", "LIBRARY"):
        material.gp2m_instrument = ident
        ui.draw_instrument_details(MockLayout(log), material)
    material.gp2m_instrument = "SINE"
    settings = sub("props").find_layer_settings(comp.data, "Livello 1")
    settings.show_fx = True
    ui.draw_layers_and_instruments(MockLayout(log), comp)
    settings.show_fx = False
    menu = _Drawer(log)
    ui.GP2M_MT_add_instrument.draw(menu, bpy.context)
    ui.VIEW3D_MT_gp2m_add.draw(_Drawer(log), bpy.context)
    ui.draw_export_menu(_Drawer(log), bpy.context)
    ui.draw_add_menu(_Drawer(log), bpy.context)
    preferences = bpy.context.preferences.addons[MODULE].preferences
    type(preferences).draw(_Drawer(log, preferences), bpy.context)
    drawn = {entry[1] for entry in log}
    assert {"gp2m_instrument", "gp2m_volume", "mode", "fill_mode", "reverb_mix",
            "map_thickness", "note_naming", "gp2m.export", "gp2m.add_instrument",
            "VIEW3D_MT_gp2m_add", "GP2M_MT_add_instrument", "gp2m.use_instrument",
            "gp2m.add_layer", "gp2m.remove_layer", "hide", "gp2m_library_path",
            "gp2m_sample", "gp2m_sample_root", "gp2m.load_sample", "gp2m.play_keyboard",
            "channel", "new_bpm", "volume_feedback", "gp2m.import_midi"} <= drawn


def test_deleting_a_composition_removes_its_sound(addon):
    engine = sub("engine")
    assert bpy.ops.gp2m.add_composition() == {"FINISHED"}
    obj = bpy.context.view_layer.objects.active
    name = obj.name
    scene = bpy.context.scene
    assert engine.find_strip(scene, obj) is not None
    bpy.data.objects.remove(obj, do_unlink=True)
    engine.cleanup_orphans()
    assert scene.sequence_editor.strips.get(engine.STRIP_PREFIX + name) is None


def test_duplicate_is_a_new_work_plane(comp):
    engine, handlers = sub("engine"), sub("handlers")
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60))
    engine.regenerate(comp)
    copy = comp.copy()
    copy.data = comp.data.copy()
    bpy.context.collection.objects.link(copy)
    copy.location.z += 10
    handlers._cleanup_needed[0] = True
    handlers._last_change[0] = 0.0
    handlers._tick()
    scene = bpy.context.scene
    first, second = engine.find_strip(scene, comp), engine.find_strip(scene, copy)
    assert first is not None and second is not None and first.channel != second.channel
    assert [n.pitch for n in engine.regenerate(copy).notes] == [60]


def test_same_length_regeneration_keeps_the_strip(comp):
    engine = sub("engine")
    engine.regenerate(comp)
    strip = engine.find_strip(bpy.context.scene, comp)
    name, channel = strip.name, strip.channel
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60))
    engine.regenerate(comp)
    again = engine.find_strip(bpy.context.scene, comp)
    assert again.as_pointer() == strip.as_pointer() and again.channel == channel
    assert again.sound.use_memory_cache


def test_mute_and_instrument_volume(comp):
    engine = sub("engine")
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60))
    loud = engine.regenerate(comp)
    comp.material_slots[0].material.gp2m_volume = 0.25
    try:
        quiet = engine.regenerate(comp)
        assert quiet.notes[0].velocity < loud.notes[0].velocity
    finally:
        comp.material_slots[0].material.gp2m_volume = 1.0
    comp.gp2m.mute = True
    engine.regenerate(comp)
    assert engine.find_strip(bpy.context.scene, comp).mute


def test_filled_shape_is_a_cluster(comp):
    engine, props = sub("engine"), sub("props")
    h = comp.gp2m.row_height
    z0, z1 = row_z(comp, 60) - 0.4 * h, row_z(comp, 64) + 0.4 * h  # C4..E4
    stroke = add_stroke(comp, 0, [(1.0, z0), (2.0, z0), (2.0, z1), (1.0, z1)])
    stroke.cyclic = True
    stroke.fill_id = 1
    tonal = engine.regenerate(comp)
    assert sorted(n.pitch for n in tonal.notes) == [60, 61, 62, 63, 64]
    props.find_layer_settings(comp.data, "Livello 1").fill_mode = "NOISE"
    noise = engine.regenerate(comp)
    assert noise.voice_count == 1 and np.abs(noise.audio).max() > 0.01


def test_instrument_and_layer_list_operators(comp):
    board = sub("board")
    before = len(comp.material_slots)
    bpy.ops.gp2m.remove_instrument()
    assert len(comp.material_slots) == before - 1
    assert bpy.ops.gp2m.add_instrument(instrument="SINE") == {"FINISHED"}
    assert comp.material_slots[comp.active_material_index].material.gp2m_instrument == "SINE"
    # Instruments stay before the board materials.
    flags = [board.is_board_material(slot.material) for slot in comp.material_slots]
    assert flags == sorted(flags)
    assert bpy.ops.gp2m.add_layer() == {"FINISHED"}
    assert comp.data.layers[-1].name == board.HEAD_LAYER  # playhead stays on top
    assert comp.data.layers.active.name == "Livello 4"
    assert bpy.ops.gp2m.move_layer(direction="UP") == {"CANCELLED"}  # never above the head
    assert bpy.ops.gp2m.move_layer(direction="DOWN") == {"FINISHED"}
    assert bpy.ops.gp2m.remove_layer() == {"FINISHED"}
    assert [l.name for l in board.user_layers(comp.data)] == ["Livello 1", "Livello 2",
                                                              "Livello 3"]


def _fresh(addon):
    assert bpy.ops.gp2m.add_composition() == {"FINISHED"}
    return bpy.context.view_layer.objects.active


def test_compositions_have_their_own_instruments(comp):
    board = sub("board")
    other = _fresh(None)
    mine = {slot.material.name for slot in comp.material_slots}
    theirs = {slot.material.name for slot in other.material_slots
              if not board.is_board_material(slot.material)}
    assert not (mine & theirs)  # muting/volume in one never touches the other
    assert board.material_label(other.material_slots[0].material) == "Flauto"


def test_duplicates_become_independent(comp):
    board = sub("board")
    linked = comp.copy()  # like Alt+D: same data and materials
    bpy.context.collection.objects.link(linked)
    assert linked.data == comp.data
    changed = board.make_independent([comp, linked])
    assert linked in changed and linked.data != comp.data
    mats = lambda o: {s.material.name for s in o.material_slots
                      if not board.is_board_material(s.material)}
    assert not (mats(comp) & mats(linked))


def test_play_modes(comp):
    engine = sub("engine")
    scene = bpy.context.scene
    for obj in engine.scene_compositions(scene):
        if obj != comp:
            bpy.data.objects.remove(obj, do_unlink=True)
    engine.cleanup_orphans()
    second = _fresh(None)
    second.gp2m.length = 4.0
    engine.regenerate(second)
    fps = scene.render.fps / scene.render.fps_base
    play = scene.gp2m_play
    first = engine.scene_compositions(scene)[0]
    other = engine.scene_compositions(scene)[1]

    play.mode = "TOGETHER"
    engine.arrange(scene)
    strips = [engine.find_strip(scene, o) for o in (first, other)]
    assert all(s.content_start == scene.frame_start and not s.mute for s in strips)
    assert scene.frame_end - scene.frame_start + 1 == round(8 * fps)

    play.mode = "SEQUENCE"
    engine.arrange(scene)
    lengths = [round(o.gp2m.length * fps) for o in (first, other)]
    assert engine.find_strip(scene, other).content_start == scene.frame_start + lengths[0]
    assert scene.frame_end - scene.frame_start + 1 == sum(lengths)
    curve = other.data.animation_data.drivers.find(
        f'layers["{sub("board").HEAD_LAYER}"].translation', index=0)
    assert f"- {lengths[0]})" in curve.driver.expression

    play.mode = "SOLO"
    bpy.context.view_layer.objects.active = other
    engine.arrange(scene)
    assert engine.find_strip(scene, first).mute and not engine.find_strip(scene, other).mute
    assert scene.frame_end - scene.frame_start + 1 == round(other.gp2m.length * fps)
    play.mode = "TOGETHER"
    engine.arrange(scene)


def test_object_scale_changes_length_and_octaves(comp):
    handlers, board = sub("handlers"), sub("board")
    stroke = add_stroke(comp, 0, line(comp, 1.0, 2.0, 60))
    before = [tuple(p.position) for p in stroke.points]
    comp.scale = (2.0, 1.0, 5.0 / 3.0)
    assert handlers.apply_scale(comp)
    assert tuple(comp.scale) == (1.0, 1.0, 1.0)
    assert comp.gp2m.length == pytest.approx(16.0) and comp.gp2m.octaves == 5
    after = [tuple(p.position) for p in board.user_layers(comp.data)[0].frames[0].drawing.strokes[0].points]
    assert after == before  # the strokes are not stretched


def test_timeline_sources(comp):
    engine, timeline = sub("engine"), sub("timeline")
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60))
    engine.regenerate(comp)
    settings = bpy.context.scene.gp2m_timeline
    for source in ("ACTIVE", "ALL", "VSE_MIX", "VSE_CHANNEL"):
        settings.source = source
        settings.channel = engine.find_strip(bpy.context.scene, comp).channel
        segments, items = timeline.collect(bpy.context, settings)
        assert segments, source
        assert any(len(s["peaks"]) and s["peaks"].max() > 0 for s in segments)
        assert bool(items) == (source in ("ACTIVE", "ALL"))
    settings.source = "SPEAKERS"
    assert timeline.collect(bpy.context, settings) == ([], [])
    settings.source = "ACTIVE"


def test_timeline_header_and_popover_draw(comp):
    timeline = sub("timeline")
    log = []
    timeline.GP2M_PT_timeline.draw(_Drawer(log), bpy.context)
    timeline.draw_header_button(_Drawer(log), bpy.context)
    drawn = {entry[1] for entry in log}
    assert {"source", "wave_style", "show_notes", "show_optical", "enabled"} <= drawn



def test_array_modifier_leaves_the_board_alone(comp):
    board, handlers = sub("board"), sub("handlers")
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60))
    keys = len(comp.data.layers.get("GP2M Tasti").frames[0].drawing.strokes)
    array = comp.modifiers.new("Array", "GREASE_PENCIL_ARRAY")
    array.count = 3
    handlers._dirty.add(comp.name)
    handlers.flush()  # what the timer does after a modifier is added
    assert array.use_layer_pass_filter and array.invert_layer_pass_filter
    evaluated = comp.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    assert len(evaluated.layers["GP2M Tasti"].current_frame().drawing.strokes) == keys
    user = board.user_layers(evaluated)[0]
    assert len(user.current_frame().drawing.strokes) == 3


def test_sequencer_channels_auto_and_manual(comp):
    engine = sub("engine")
    scene = bpy.context.scene
    other = _fresh(None)
    assert comp.gp2m.channel > 0 and other.gp2m.channel > 0
    assert comp.gp2m.channel != other.gp2m.channel
    other.gp2m.channel = 40
    engine.arrange(scene)
    assert engine.find_strip(scene, other).channel == 40
    copy = other.copy()  # Shift+D copies the channel too
    copy.data = other.data.copy()
    bpy.context.collection.objects.link(copy)
    engine.resolve_channels(scene)
    assert copy.gp2m.channel != other.gp2m.channel


def test_new_compositions_use_the_preferences(addon):
    preferences = bpy.context.preferences.addons[MODULE].preferences
    preferences.new_bpm = 90.0
    preferences.new_octaves = 2
    preferences.new_layers = 2
    preferences.new_instruments = "ESSENTIAL"
    try:
        obj = _fresh(None)
        board = sub("board")
        assert obj.gp2m.bpm == 90.0 and obj.gp2m.octaves == 2
        assert len(board.user_layers(obj.data)) == 2
        idents = [s.material.gp2m_instrument for s in obj.material_slots
                  if not board.is_board_material(s.material)]
        assert idents == ["SINE", "SQUARE", "SAW", "STRINGS", "PLUCK", "KICK", "SNARE", "HIHAT"]
    finally:
        preferences.new_bpm = 120.0
        preferences.new_octaves = 3
        preferences.new_layers = 3
        preferences.new_instruments = "ALL"


def test_scale_is_never_compounded(comp):
    handlers = sub("handlers")
    handlers._scale_base[comp.name] = (8.0, 3)
    comp.scale = (2.0, 1.0, 1.0)
    assert handlers.apply_scale(comp)
    assert comp.gp2m.length == pytest.approx(16.0)
    # A second, late update of the same gesture must not double it again.
    handlers._scale_base[comp.name] = (8.0, 3)
    comp.scale = (2.0, 1.0, 1.0)
    handlers.apply_scale(comp)
    assert comp.gp2m.length == pytest.approx(16.0)


def test_scale_waits_until_the_gesture_settles(comp):
    handlers = sub("handlers")
    comp.scale = (1.5, 1.0, 1.0)
    handlers._scaled.add(comp.name)
    assert handlers._scale_pending() is not None  # first sight: wait
    assert handlers._scale_pending() is not None  # still within the settle time
    handlers._scale_seen[comp.name] = (handlers._scale_of(comp), 0.0)  # long ago
    assert handlers._scale_pending() is None
    assert tuple(comp.scale) == (1.0, 1.0, 1.0) and comp.gp2m.length == pytest.approx(12.0)


def test_volume_feedback_thickness(comp):
    feedback, engine = sub("feedback"), sub("engine")
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60))
    comp.gp2m.use_modifiers = True
    full = engine.regenerate(comp).notes[0].velocity
    material = comp.material_slots[0].material
    material.gp2m_volume = 0.5  # update callback adds the Thickness modifier
    modifier = comp.modifiers.get(feedback.MODIFIER_PREFIX + material.name)
    assert modifier is not None and modifier.thickness_factor == pytest.approx(0.5)
    bpy.context.view_layer.update()
    half = engine.regenerate(comp).notes[0].velocity
    # The modifier is only visual: volume is counted once, not twice.
    assert half == pytest.approx(full * 0.5, abs=2)
    material.gp2m_volume = 1.0
    assert comp.modifiers.get(feedback.MODIFIER_PREFIX + material.name) is None
    assert not sub("reader").has_unsupported_stack(comp)


def test_midi_import_creates_layers_and_instruments(addon, tmp_path):
    midi = sub("midi")
    notes = [sub("interpret").MidiNote(0.5 * i, 0.5 * i + 0.4, 60 + i, 100) for i in range(8)]
    kicks = [sub("interpret").MidiNote(float(i), float(i) + 0.1, 36, 110) for i in range(4)]
    path = tmp_path / "song.mid"
    midi.write_midi(str(path), [{"name": "Archi", "program": 48, "notes": notes},
                                {"name": "Batteria", "program": -1, "notes": kicks}], 100)
    comp, count = sub("midi_import").import_midi(bpy.context, str(path))
    board = sub("board")
    assert count == 12
    assert [l.name for l in board.user_layers(comp.data)] == ["Archi", "Batteria"]
    assert comp.gp2m.bpm == pytest.approx(100.0, abs=0.01) and comp.gp2m.length == 4.0
    result = sub("engine").regenerate(comp)
    assert sorted(n.pitch for n in result.notes if n.instrument == "STRINGS") == list(range(60, 68))
    assert sum(1 for n in result.notes if n.instrument == "KICK") == 4


def test_keyboard_recording_and_notes(comp):
    keyboard, engine = sub("keyboard"), sub("engine")
    scene = bpy.context.scene
    assert keyboard.record_stroke(comp, scene, 64, 1.0, 1.5, 0) == 1
    result = engine.regenerate(comp)
    assert [(n.pitch, round(n.start, 2)) for n in result.notes] == [(64, 1.0)]
    assert keyboard.KEYMAP["A"] == 0 and keyboard.KEYMAP["K"] == 12
    buffer = keyboard.note_buffer("SINE", 69)
    assert buffer.shape[1] == 2 and np.abs(buffer).max() > 0.1
    assert keyboard.composition_seconds(comp, scene, scene.frame_start) == 0.0


def test_keyframe_sections(comp):
    """Every keyframe starts a section that loops its drawing until the next one."""
    engine, board, keyboard = sub("engine"), sub("board"), sub("keyboard")
    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    start = scene.frame_start
    comp.gp2m.length = 2.0
    add_stroke(comp, 0, line(comp, 0.5, 1.0, 60))
    add_stroke(comp, 0, line(comp, 0.5, 1.0, 64), frame=start + round(5 * fps))
    result = engine.regenerate(comp)
    assert [n.pitch for n in result.notes] == [60]  # off: only the first keyframe
    assert engine.state(comp)["stats"]["multi_keyframes"] == ["Livello 1"]

    comp.gp2m.use_sections = True
    result = engine.regenerate(comp)
    assert result.sections == (0.0, 5.0) and result.duration == pytest.approx(7.0)
    assert [(n.pitch, round(n.start, 2)) for n in result.notes] == [
        (60, 0.5), (60, 2.5), (60, 4.5), (64, 5.5)]
    assert len(result.audio) == round(7.0 * result.sample_rate)
    strip = engine.find_strip(scene, comp)
    assert strip.duration == round(7.0 * fps)  # the strip covers the song
    assert engine.duration(comp) == pytest.approx(7.0)

    def head_at(seconds):
        scene.frame_set(start + round(seconds * fps))
        evaluated = comp.evaluated_get(bpy.context.evaluated_depsgraph_get())
        return evaluated.data.layers[board.HEAD_LAYER].translation[0] / comp.gp2m.seconds_width

    assert head_at(1.0) == pytest.approx(1.0, abs=0.05)
    assert head_at(3.0) == pytest.approx(1.0, abs=0.05)  # second loop of section 1
    assert head_at(5.5) == pytest.approx(0.5, abs=0.05)  # section 2 restarts the loop
    scene.frame_set(start)

    # A note played at 6 s is recorded into the drawing of the second section.
    assert keyboard.record_stroke(comp, scene, 67, 6.0, 6.5, 0) == 1
    result = engine.regenerate(comp)
    assert (67, 6.0) in [(n.pitch, round(n.start, 2)) for n in result.notes]
    assert (67, 2.0) not in [(n.pitch, round(n.start, 2)) for n in result.notes]
    comp.gp2m.use_sections = False
    engine.regenerate(comp)
    assert engine.find_strip(scene, comp).duration == round(2.0 * fps)


def test_gesture_mode_reads_drawing_time(comp):
    engine, props = sub("engine"), sub("props")
    add_stroke(comp, 0, line(comp, 1.0, 1.25, 60, n=50))
    drawing = sub("board").user_layers(comp.data)[0].frames[0].drawing
    assert drawing.attributes.get("delta_time") is None
    settings = props.find_layer_settings(comp.data, "Livello 1")
    settings.mode = "GESTURE"
    result = engine.regenerate(comp)  # no drawing time: read like "Quantizzata"
    assert [(n.start, round(n.end, 2)) for n in result.notes] == [(1.0, 1.25)]
    attr = drawing.attributes.new("delta_time", "FLOAT", "POINT")
    attr.data.foreach_set("value", np.linspace(0.0, 1.5, 50, dtype=np.float32))
    drawing.tag_positions_changed()
    result = engine.regenerate(comp)  # drawn in 1.5 s: the note lasts 1.5 s
    assert [(n.start, round(n.end, 2)) for n in result.notes] == [(1.0, 2.5)]


def test_midi_keyboard_plays_and_records(comp):
    """MIDI notes (velocity, sustain pedal) go through the same path as PC keys."""
    from types import SimpleNamespace
    keyboard, midi_input, engine = sub("keyboard"), sub("midi_input"), sub("engine")
    assert midi_input.rtmidi() is not None, "the bundled rtmidi2 wheel is installed"
    assert isinstance(midi_input.port_names(), list)  # no MIDI backend here: empty
    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base

    class Port:
        def __init__(self):
            self.queue = []

        def events(self):
            out, self.queue = self.queue, []
            return out

    methods = keyboard.GP2M_OT_play_keyboard.__dict__
    Fake = type("Fake", (), {k: methods[k] for k in
                             ("_press", "_release", "_end_note", "_poll_midi")})
    op = Fake()
    op.held, op.sustained, op.sustain, op.recording, op.midi = {}, {}, False, True, Port()
    context = SimpleNamespace(scene=scene, screen=SimpleNamespace(is_animation_playing=True))

    def at(seconds, *events):
        scene.frame_current = scene.frame_start + round(seconds * fps)
        op.midi.queue = [midi_input.decode(e) for e in events]
        op._poll_midi(context, comp)

    at(1.0, [0x90, 60, 100])
    at(1.5, [0x80, 60, 0])
    at(2.0, [0x90, 64, 90], [0xB0, 64, 127])
    at(2.5, [0x90, 64, 0])  # released while the pedal is down: keeps sounding
    assert 64 in op.sustained
    at(3.0, [0xB0, 64, 0])
    assert not op.held and not op.sustained
    result = engine.regenerate(comp)
    notes = sorted((n.pitch, round(n.start, 2), round(n.end, 1))
                   for n in result.notes)
    assert notes == [(60, 1.0, 1.5), (64, 2.0, 3.0)]
    assert keyboard.velocity_volume(127) == pytest.approx(1.0)
    assert 0.15 < keyboard.velocity_volume(1) < keyboard.velocity_volume(64) < 1.0


@pytest.mark.parametrize("rate", ["44100", "48000"])
def test_sound_is_written_at_any_rate_and_length(comp, tmp_path, rate):
    """Blender's FFmpeg WAV writer fails at 48 kHz on some lengths: WAV must not use it."""
    engine = sub("engine")
    comp.gp2m.sample_rate = rate
    comp.gp2m.length = 8.0
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60))
    assert engine.regenerate(comp, force=True) is not None
    for fmt, ext in (("WAV", ".wav"), ("MP3", ".mp3")):
        path = tmp_path / f"out{rate}{ext}"
        engine.export(comp, bpy.context.scene, str(path), fmt)
        assert path.stat().st_size > 1000


def test_new_composition_stays_in_object_mode(addon):
    _fresh(None)
    assert bpy.context.mode == "OBJECT"


def test_legato_layer_mode(comp):
    engine, props = sub("engine"), sub("props")
    add_stroke(comp, 0, [(x, row_z(comp, 60) + (x - 1.0) * 0.4) for x in np.linspace(1, 2, 60)])
    props.find_layer_settings(comp.data, "Livello 1").mode = "LEGATO"
    result = engine.regenerate(comp)
    assert result.voice_count == 1 and len(result.notes) > 1



def test_new_composition_starts_empty(addon):
    preferences = bpy.context.preferences.addons[MODULE].preferences
    preferences.new_layers, preferences.new_instruments = 1, "ONE"
    try:
        obj = _fresh(None)
        board = sub("board")
        assert [l.name for l in board.user_layers(obj.data)] == ["Livello 1"]
        own = board.layer_instruments(obj, "Livello 1")
        assert [m.gp2m_instrument for _i, m in own] == ["SINE"]
        assert not any(len(l.frames[0].drawing.strokes) for l in board.user_layers(obj.data))
    finally:
        preferences.new_layers, preferences.new_instruments = 3, "ALL"


def test_instruments_live_inside_layers(comp):
    board = sub("board")
    assert bpy.ops.gp2m.add_layer() == {"FINISHED"}
    new = comp.data.layers.active.name
    assert board.layer_instruments(comp, new) == []
    assert bpy.ops.gp2m.add_instrument(instrument="PLUCK", layer=new) == {"FINISHED"}
    own = board.layer_instruments(comp, new)
    assert [m.gp2m_instrument for _i, m in own] == ["PLUCK"]
    assert comp.active_material_index == own[0][0]  # ready to draw with it
    # Choosing a layer picks its first instrument.
    assert bpy.ops.gp2m.use_instrument(layer="Livello 1", index=-1) == {"FINISHED"}
    assert comp.data.layers.active.name == "Livello 1"
    assert comp.material_slots[comp.active_material_index].material.gp2m_layer == "Livello 1"
    # Deleting a layer removes its unused instruments.
    slots = len(comp.material_slots)
    assert bpy.ops.gp2m.remove_layer(name=new) == {"FINISHED"}
    assert len(comp.material_slots) == slots - 1


def test_renamed_layer_keeps_its_instruments(comp):
    board, props = sub("board"), sub("props")
    count = len(board.layer_instruments(comp, "Livello 1"))
    comp.data.layers["Livello 1"].name = "Melodia"
    props.ensure_layer_settings(comp.data)
    assert len(board.layer_instruments(comp, "Melodia")) == count


def test_library_instrument_from_soundfont(comp, tmp_path):
    import sf2_fixture
    engine = sub("engine")
    path = tmp_path / "test.sf2"
    sf2_fixture.write_sf2(path)
    assert bpy.ops.gp2m.add_instrument(instrument="LIBRARY", layer="Livello 1") == {"FINISHED"}
    material = comp.material_slots[comp.active_material_index].material
    material.gp2m_library_path = str(path)
    items = sub("samples").preset_items(material, bpy.context)
    assert items[0][1].endswith("Sine Test")
    material.gp2m_library_preset = items[0][0]
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 69), material_index=comp.active_material_index)
    result = engine.regenerate(comp)
    assert [n.pitch for n in result.notes] == [69]
    assert np.abs(result.audio[int(1.4 * 44100):int(1.6 * 44100)]).max() > 0.05


def test_mapping_presets(addon):
    prefs = sub("prefs")
    p = prefs.get_prefs()
    try:
        assert bpy.ops.gp2m.mapping_preset(preset="MCLAREN") == {"FINISHED"}
        assert (p.map_thickness, p.map_opacity, p.map_vertex_color) == (
            "VOLUME", "VOLUME", "BRIGHTNESS")
        assert prefs.applied_preset() == "MCLAREN"
        p.map_softness = "ATTACK"
        assert prefs.applied_preset() is None
        assert prefs.get_mapping().opacity == "VOLUME"
    finally:
        bpy.ops.gp2m.mapping_preset(preset="CLASSIC")
    assert prefs.applied_preset() == "CLASSIC"
    assert p.map_thickness == "VOLUME" and p.map_opacity == "BRIGHTNESS"
