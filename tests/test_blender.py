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
    preferences.new_scale = "CHROMATIC"  # the tests read every semitone
    # Each composition keeps its own length (test_follow_scene_* switch it on).
    preferences.new_follow_scene = False
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


def _grid(comp):
    """Grease Pencil data of the composition's grid object."""
    return sub("board").grid_object(comp).data


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


def test_add_composition_has_its_grid_apart(comp):
    board = sub("board")
    s = comp.gp2m
    assert s.is_composition and comp.name.startswith("Composizione Musicale")
    # The grid is its own Grease Pencil object, a child of the composition.
    grid = board.grid_object(comp)
    assert set(comp.children) == {grid} and grid.name == comp.name + board.GRID_SUFFIX
    assert board.is_grid(grid) and not grid.gp2m.is_composition
    assert all(grid.lock_location) and all(grid.lock_scale)
    assert comp.show_in_front and not grid.show_in_front
    assert tuple(grid.matrix_world.translation)[1] > tuple(comp.matrix_world.translation)[1]
    names = [layer.name for layer in comp.data.layers]
    assert [l.name for l in board.user_layers(comp.data)] == ["Livello 1", "Livello 2",
                                                              "Livello 3"]
    # The drawing has only the user layers and the playhead on top.
    assert names[-1] == board.HEAD_LAYER and names[:-1] == ["Livello 1", "Livello 2",
                                                           "Livello 3"]
    assert comp.data.layer_groups.get(board.BOARD_GROUP) is None
    assert all(board.is_board_layer(layer) and layer.lock for layer in grid.data.layers)
    assert comp.data.layers.active.name == "Livello 1"
    board_materials = [m.name for m in comp.data.materials if board.is_board_material(m)]
    assert board_materials == ["GP2M Testina"]
    instruments = [slot.material.gp2m_instrument for slot in comp.material_slots
                   if not board.is_board_material(slot.material)]
    assert len(instruments) == 25 and {"PLUCK", "KICK", "SNARE", "HIHAT"} <= set(instruments)
    labels = board.grid_object(comp).data.layers.get("GP2M Etichette").frames[0].drawing
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
        return len(_grid(comp).layers.get("GP2M Etichette").frames[0].drawing.strokes)
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


def test_five_readings_and_legato_across_strokes(comp):
    engine, props = sub("engine"), sub("props")
    items = props.GP2M_LayerSettings.bl_rna.properties["mode"].enum_items
    assert [i.identifier for i in items] == ["QUANTIZED", "LEGATO", "OPTICAL",
                                             "OPTICAL_LEGATO", "GESTURE"]
    # Saved numbers are those of 0.0.5 (older files keep their reading).
    assert {i.identifier: i.value for i in items} == {
        "QUANTIZED": 0, "OPTICAL": 1, "LEGATO": 2, "GESTURE": 3, "OPTICAL_LEGATO": 4}
    assert [i.name.split(" · ")[0] for i in items] == ["Q", "QL", "O", "OL", "G"]
    add_stroke(comp, 0, line(comp, 1.0, 1.5, 60))
    add_stroke(comp, 0, line(comp, 1.7, 2.2, 64))
    settings = props.find_layer_settings(comp.data, "Livello 1")
    settings.mode = "OPTICAL"
    assert engine.regenerate(comp).voice_count == 2
    settings.mode = "OPTICAL_LEGATO"
    joined = engine.regenerate(comp)
    assert joined.voice_count == 1 and len(joined.notes) == 2
    settings.legato_gap = 0.0
    assert engine.regenerate(comp).voice_count == 2


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
    keys_before = len(_grid(comp).layers.get("GP2M Tasti").frames[0].drawing.strokes)
    comp.gp2m.length = 4.0
    comp.gp2m.octaves = 2
    board._rebuild_pending()  # normally run by a timer
    keys_after = len(_grid(comp).layers.get("GP2M Tasti").frames[0].drawing.strokes)
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

    def label_multiline(self, **kwargs):  # Blender 5.3
        assert "label_multiline" in bpy.types.UILayout.bl_rna.functions
        self.log.append(("multiline", kwargs.get("text", "")))

    def label_markdown(self, text, **_kwargs):  # Blender 5.3
        assert "label_markdown" in bpy.types.UILayout.bl_rna.functions
        self.log.append(("markdown", text))

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
        if attr.startswith('["') and attr.endswith('"]'):  # a custom property
            assert attr[2:-2] in target, f"{type(target).__name__}{attr}"
        else:
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
    settings = sub("props").find_layer_settings(comp.data, comp.data.layers.active.name)
    for toggle in ("use_array", "use_mirror", "use_transpose", "use_fade", "use_noise",
                   "use_echo", "use_reverb", "use_lofi", "use_canon"):
        setattr(settings, toggle, True)  # the "N attivi" summaries
    for panel in ui.classes:
        is_material = getattr(panel, "bl_context", "") == "material"
        if panel is ui.GP2M_PT_sequencer_group:
            continue  # below, with a group active in the Sequencer
        if issubclass(panel, bpy.types.Panel) and not is_material:
            assert panel.poll(bpy.context) if hasattr(panel, "poll") else True, panel
            panel.draw(_Drawer(log), bpy.context)
            if hasattr(panel, "draw_header"):
                panel.draw_header(_Drawer(log), bpy.context)
        if hasattr(panel, "draw_header_preset") and not is_material:
            panel.draw_header_preset(_Drawer(log), bpy.context)
    # The group panel of the Sequencer: a group of compositions, then of layers.
    engine, seqsync = sub("engine"), sub("seqsync")
    editor = bpy.context.scene.sequence_editor
    meta = engine.meta_strip(bpy.context.scene, comp)
    group = editor.strips.new_meta("MetaStrip", engine._block_from(
        1, 1, {s.channel for s in editor.strips}), int(meta.left_handle))
    seqsync.make_group(group)
    layer_group = meta.strips.new_meta("MetaStrip", 9, int(meta.left_handle))
    layer_group[engine.OWNER_KEY] = comp.name
    layer_group[engine.LAYER_GROUP_KEY] = comp.data.layers.active.name
    for strip in (group, layer_group):
        editor.active_strip = strip
        assert ui.GP2M_PT_sequencer_group.poll(bpy.context)
        ui.GP2M_PT_sequencer_group.draw(_Drawer(log), bpy.context)
    for strip in (layer_group, group):
        engine._remove_strip(editor, strip)
    ui.GP2M_PT_material_fx.draw(_Drawer(log), type("C", (), {
        "material": comp.material_slots[0].material})())
    ui.GP2M_PT_material.draw_header_preset(_Drawer(log), bpy.context)
    ui.GP2M_MT_layer_specials.draw(_Drawer(log), bpy.context)
    table = sub("table").GP2M_PT_compositions
    table.draw(_Drawer(log), bpy.context)
    table.draw_header_preset(_Drawer(log), bpy.context)
    for panel in sub("help").classes:
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
    ui.GP2M_MT_change_instrument.draw(_Drawer(log), bpy.context)
    for family in ui.ADD_FAMILY_MENUS + ui.CHANGE_FAMILY_MENUS:  # one submenu per family
        family.draw(_Drawer(log), bpy.context)
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
            "channel", "new_bpm", "volume_feedback", "gp2m.import_midi", "gp2m.export_web",
            "GP2M_PT_help_main", "GP2M_PT_help_reading", "GP2M_PT_help_instrument",
            "GP2M_PT_help_export", "GP2M_UL_layers", "GP2M_MT_change_instrument",
            "gp2m.set_instrument", ui.CHANGE_FAMILY_MENUS[0].bl_idname,
            "solo", "mute", "lock", "use_array", "array_count", "mirror_time",
            "transpose_steps", "fade_direction", "noise_pitch", "use_echo", "delay_mix",
            "use_reverb", "use_lofi", "canon_voices", "use_master", "ambience",
            "gp2m.copy_layer_settings", "gp2m.paste_layer_settings",
            "GP2M_PT_help_modifiers", "GP2M_PT_help_table", "GP2M_UL_compositions",
            "gp2m.composition_move", "gp2m.composition_toggle", "gp2m.table_stack",
            "gp2m.board_octaves"} <= drawn
    assert sum(1 for entry in log if entry[0] == "markdown") == len(sub("help").classes)


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
    first, second = engine.top_strip(scene, comp), engine.top_strip(scene, copy)
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
    assert engine.top_strip(bpy.context.scene, comp).mute


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


def test_harmony_and_finished_sound(comp):
    engine, props = sub("engine"), sub("props")
    comp.gp2m.scale = "MAJOR"
    add_stroke(comp, 0, [(1.0, row_z(comp, 60)), (2.0, row_z(comp, 60))], radius=0.3)
    plain = engine.regenerate(comp)
    assert [n.pitch for n in plain.notes] == [60]
    props.find_layer_settings(comp.data, "Livello 1").harmony = "TRIAD"
    chord = engine.regenerate(comp)
    assert sorted(n.pitch for n in chord.notes) == [60, 64, 67]
    assert comp.gp2m.use_master and np.abs(chord.audio).max() <= 0.9
    comp.gp2m.use_master = False
    assert engine.regenerate(comp).key != chord.key


def test_removing_an_instrument_keeps_the_others_on_their_strokes(comp):
    """Blender already shifts the strokes of the following slots when a slot goes."""
    operators = sub("operators")
    mats = comp.data.materials
    later = add_stroke(comp, 0, line(comp, 0.5, 1.0, 60), material_index=3)
    removed = add_stroke(comp, 0, line(comp, 1.5, 2.0, 60), material_index=1)
    instrument = mats[3].gp2m_instrument
    operators.remove_material_slot(comp, 1)
    drawing = sub("board").user_layers(comp.data)[0].frames[0].drawing
    strokes = list(drawing.strokes)
    assert mats[strokes[-2].material_index].gp2m_instrument == instrument
    assert strokes[-1].material_index == 0
    del later, removed


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


def test_change_instrument_keeps_strokes(comp):
    engine, board = sub("engine"), sub("board")
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60), material_index=0)
    material = comp.material_slots[0].material
    before = material.gp2m_instrument
    target = "BELL" if before != "BELL" else "PLUCK"
    first = engine.regenerate(comp)
    assert bpy.ops.gp2m.set_instrument(instrument=target, index=0) == {"FINISHED"}
    assert material.gp2m_instrument == target
    inst = sub("synth").INSTRUMENT_BY_ID[target]
    assert board.material_label(material) == inst.label
    assert tuple(round(c, 3) for c in material.grease_pencil.color[:3]) == \
        tuple(round(c, 3) for c in inst.color[:3])
    second = engine.regenerate(comp)
    assert [n.pitch for n in second.notes] == [n.pitch for n in first.notes] == [60]
    assert second.key != first.key
    # A colour chosen by hand stays.
    material.grease_pencil.color = (0.1, 0.9, 0.1, 1.0)
    bpy.ops.gp2m.set_instrument(instrument="SINE", index=0)
    assert material.gp2m_instrument == "SINE"
    assert round(material.grease_pencil.color[1], 3) == 0.9
    assert sub("ui").layer_instrument_slot(comp, "Livello 1") == 0


def test_layer_list_mute_and_solo(comp):
    engine, props, board = sub("engine"), sub("props"), sub("board")
    gp = comp.data
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60), material_index=0)
    add_stroke(comp, 1, line(comp, 3.0, 4.0, 64), material_index=3)
    assert len(engine.regenerate(comp).notes) == 2
    one, two = (props.find_layer_settings(gp, n) for n in ("Livello 1", "Livello 2"))
    layers = {l.name: l for l in board.user_layers(gp)}
    # Mute: visible, silent.
    one.mute = True
    assert [n.pitch for n in engine.regenerate(comp).notes] == [64]
    assert not layers["Livello 1"].hide
    one.mute = False
    # Solo: the others are silent and dimmed to 10%, then restored.
    layers["Livello 1"].opacity = 0.8
    two.solo = True
    assert [n.pitch for n in engine.regenerate(comp).notes] == [64]
    assert abs(layers["Livello 1"].opacity - props.SOLO_OPACITY) < 1e-6
    assert abs(layers["Livello 2"].opacity - 1.0) < 1e-6
    assert abs(props.layer_volume(gp, layers["Livello 1"]) - 0.8) < 1e-6
    two.solo = False
    assert abs(layers["Livello 1"].opacity - 0.8) < 1e-6
    assert len(engine.regenerate(comp).notes) == 2
    # The list's active index follows the active layer, both ways.
    index = [item.name for item in gp.gp2m_layers].index("Livello 2")
    gp.gp2m_layer_index = index
    assert gp.layers.active.name == "Livello 2"
    assert gp.gp2m_layer_index == index
    # Top layer first, like Blender's list.
    flags, order = sub("ui").GP2M_UL_layers.filter_items(
        type("L", (), {"bitflag_filter_item": 1})(), bpy.context, gp, "gp2m_layers")
    shown = sorted((o, item.name) for o, item, f in zip(order, gp.gp2m_layers, flags) if f)
    assert [name for _o, name in shown] == [l.name for l in reversed(board.user_layers(gp))]


def test_preview_range_darkens_the_grid_only(comp):
    engine, board = sub("engine"), sub("board")
    scene = bpy.context.scene
    add_stroke(comp, 0, line(comp, 0.5, 3.5, 60))
    sound = engine.regenerate(comp).key
    shade = _grid(comp).layers.get(board.SHADE_LAYER)
    assert shade is not None and board.is_board_layer(shade)
    assert len(shade.frames[0].drawing.strokes) == 0
    fps = scene.render.fps / scene.render.fps_base
    s = comp.gp2m
    scene.use_preview_range = True
    scene.frame_preview_start = scene.frame_start + int(round(1.0 * fps))
    scene.frame_preview_end = scene.frame_start + int(round(2.0 * fps)) - 1
    try:
        assert board.update_preview_shade(comp, scene)
        drawing = shade.frames[0].drawing
        assert len(drawing.strokes) == 2
        xs = sorted(round(p.position.x / s.seconds_width, 2)
                    for stroke in drawing.strokes for p in stroke.points)
        assert xs[0] == 0.0 and xs[-1] == round(s.length, 2)
        assert 1.0 in xs and 2.0 in xs
        assert not board.update_preview_shade(comp, scene)  # nothing changed
        assert engine.regenerate(comp).key == sound  # the music is the same
        # A rebuilt board keeps the shading.
        board.rebuild(comp, scene)
        shade = _grid(comp).layers.get(board.SHADE_LAYER)
        assert len(shade.frames[0].drawing.strokes) == 2
        assert board.board_materials_ok(comp)
    finally:
        scene.use_preview_range = False
    assert board.update_preview_shade(comp, scene)
    assert len(_grid(comp).layers.get(board.SHADE_LAYER).frames[0].drawing.strokes) == 0


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
    assert board.material_label(other.material_slots[0].material) == "Flauto (synth)"


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
    assert engine.top_strip(scene, first).mute and not engine.top_strip(scene, other).mute
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
    assert settings.source == "EVERYTHING"  # the default
    for source in ("EVERYTHING", "ACTIVE", "ALL", "VSE_MIX", "VSE_CHANNEL"):
        settings.source = source
        settings.channel = engine.top_strip(bpy.context.scene, comp).channel
        audio, composed, items = timeline.collect(bpy.context, settings)
        segments = audio + composed
        assert segments, source
        assert any(len(s["peaks"]) and s["peaks"].max() > 0 for s in segments)
        assert bool(items) == (source in ("EVERYTHING", "ACTIVE", "ALL"))
        # The composition's own strip is not counted twice next to its notes.
        assert not audio if source in ("EVERYTHING", "ACTIVE", "ALL") else not composed
    settings.source = "SPEAKERS"
    assert timeline.collect(bpy.context, settings) == ([], [], [])
    settings.source = "EVERYTHING"


def _tone_file(path, seconds=2.0, rate=22050):
    t = np.arange(int(seconds * rate)) / rate
    data = (np.sin(2 * np.pi * 330 * t) * 0.5 * 32767).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(data.tobytes())
    return path


def test_timeline_shows_plain_audio_with_the_compositions(comp, tmp_path):
    """Any sound strip (channel 1 included, not a composition) is drawn next to
    the compositions, even when it is packed in the .blend file."""
    engine, timeline = sub("engine"), sub("timeline")
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60))
    engine.regenerate(comp)
    scene = bpy.context.scene
    path = _tone_file(tmp_path / "voice.wav")
    strip = scene.sequence_editor.strips.new_sound("Voce", str(path), 1, scene.frame_start)
    try:
        assert strip.channel == 1
        settings = scene.gp2m_timeline
        settings.source = "EVERYTHING"
        audio, composed, items = timeline.collect(bpy.context, settings)
        assert len(audio) == 1 and audio[0]["peaks"].max() > 0.4
        assert composed and items
        settings.source = "VSE_CHANNEL"
        settings.channel = 1
        on_one = timeline.collect(bpy.context, settings)[0]
        assert any(abs(seg["peaks"].max() - 0.5) < 0.01 for seg in on_one)
        strip.sound.pack()
        os.remove(path)
        settings.source = "EVERYTHING"
        audio, _composed, _items = timeline.collect(bpy.context, settings)
        assert len(audio) == 1 and audio[0]["peaks"].max() > 0.4
        strip.mute = True
        assert timeline.collect(bpy.context, settings)[0] == []
    finally:
        sound = strip.sound
        scene.sequence_editor.strips.remove(strip)
        bpy.data.sounds.remove(sound)
        scene.gp2m_timeline.source = "EVERYTHING"


def test_timeline_header_and_popover_draw(comp):
    timeline = sub("timeline")
    log = []
    timeline.GP2M_PT_timeline.draw(_Drawer(log), bpy.context)
    timeline.draw_header_button(_Drawer(log), bpy.context)
    drawn = {entry[1] for entry in log}
    assert {"source", "wave_style", "show_notes", "show_optical", "enabled",
            "audio_color", "wave_color"} <= drawn



class _FakeView2D:
    def __init__(self, frames_per_pixel=0.5):
        self.fpp = frames_per_pixel

    def view_to_region(self, x, _y, clip=True):
        return (x / self.fpp, 0)

    def region_to_view(self, x, _y):
        return (x * self.fpp, 0.0)


class _FakeRegion:
    type = "WINDOW"

    def __init__(self, width, height):
        self.width, self.height = width, height
        self.view2d = _FakeView2D()

    def as_pointer(self):
        return id(self)


class _FakeContext:
    def __init__(self, region):
        self.scene = bpy.context.scene
        self.region = region
        self.active_object = bpy.context.view_layer.objects.active


@pytest.mark.parametrize("region", [None, _FakeRegion(800, 0), _FakeRegion(800, 6),
                                    _FakeRegion(0, 200), _FakeRegion(4, 200)])
def test_timeline_overlay_without_room_does_no_work(comp, monkeypatch, region):
    """No Timeline region, or a Timeline collapsed to a thin bar (or squeezed
    sideways): the overlay returns at once, without collecting any sound."""
    timeline = sub("timeline")
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60))
    sub("engine").regenerate(comp)
    calls = []
    monkeypatch.setattr(timeline, "collect", lambda *a: calls.append(a) or ([], [], []))
    assert timeline.draw_overlay(_FakeContext(region)) is None
    assert not calls
    timeline._draw()  # the real handler, in background (no region): no error


def test_timeline_overlay_collects_once_until_something_changes(comp, monkeypatch):
    timeline = sub("timeline")
    calls = []
    monkeypatch.setattr(timeline, "collect", lambda *a: calls.append(a) or ([], [], []))
    timeline.invalidate()
    region = _FakeRegion(800, 120)
    for _ in range(5):  # every frame of the playback
        assert timeline.draw_overlay(_FakeContext(region)) == 0
    assert len(calls) == 1
    timeline.tag_redraw()  # a new sound (regenerate, arrange, settings)
    timeline.draw_overlay(_FakeContext(region))
    assert len(calls) == 2
    bpy.context.view_layer.update()
    comp.location.x += 1.0
    bpy.context.view_layer.update()  # any depsgraph change (strips, sounds...)
    timeline.draw_overlay(_FakeContext(region))
    assert len(calls) == 3


def test_resume_playback_and_popups_without_windows(comp):
    """Background mode has no window, screen or Timeline: nothing breaks."""
    handlers, operators = sub("handlers"), sub("operators")
    assert handlers._resume_playback() is None
    handlers._popup_queue.append(comp.name)
    handlers._show_popups()
    assert not handlers._popup_queue
    operators.frame_view(bpy.context, comp)  # no screen: nothing to frame
    assert sub("engine").scene_of(comp) == bpy.context.scene
    sub("timeline").tag_redraw()


def test_keyboard_header_without_an_editor(comp):
    """Started with no editor (or from one that was closed meanwhile), the
    keyboard player neither fails nor writes in another editor's header."""
    keyboard = sub("keyboard")

    class Op:
        recording = False
        midi = None
        base = 60
        area_pointer = 0
        _area = keyboard.GP2M_OT_play_keyboard._area

    op = Op()
    assert op._area(bpy.context) is None
    keyboard.GP2M_OT_play_keyboard._header(op, bpy.context)
    op.area_pointer = 12345  # an editor that no longer exists
    assert op._area(bpy.context) is None


def test_array_modifier_leaves_the_board_alone(comp):
    board, handlers = sub("board"), sub("handlers")
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60))
    keys = len(_grid(comp).layers.get("GP2M Tasti").frames[0].drawing.strokes)
    array = comp.modifiers.new("Array", "GREASE_PENCIL_ARRAY")
    array.count = 3
    handlers._dirty.add(comp.name)
    handlers.flush()  # what the timer does after a modifier is added
    assert array.use_layer_pass_filter and array.invert_layer_pass_filter
    evaluated = comp.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    assert len(evaluated.layers[board.HEAD_LAYER].current_frame().drawing.strokes) == 1
    assert len(_grid(comp).layers["GP2M Tasti"].frames[0].drawing.strokes) == keys
    user = board.user_layers(evaluated)[0]
    assert len(user.current_frame().drawing.strokes) == 3


def test_sequencer_channels_auto_and_manual(comp):
    engine = sub("engine")
    scene = bpy.context.scene
    other = _fresh(None)
    assert comp.gp2m.channel > 0 and other.gp2m.channel > 0
    assert comp.gp2m.channel != other.gp2m.channel
    used = {strip.channel for strip in scene.sequence_editor.strips_all
            if strip not in engine.composition_strips(scene, other)}
    free = engine._block_from(1, engine._channel_count(scene, other), used)
    other.gp2m.channel = free  # a free block chosen by hand is kept
    engine.arrange(scene)
    assert engine.top_strip(scene, other).channel == free
    copy = other.copy()  # Shift+D copies the channel too
    copy.data = other.data.copy()
    bpy.context.collection.objects.link(copy)
    engine.resolve_channels(scene)
    assert copy.gp2m.channel != other.gp2m.channel


def test_new_composition_goes_above_clips_and_compositions(comp):
    """A new composition is a new level of the timeline: above every composition,
    skipping channels with clips; a clip added later on its channel pushes it up."""
    engine = sub("engine")
    scene = bpy.context.scene
    editor = scene.sequence_editor
    channel = 1  # the other tests leave compositions all over the channels
    for obj in engine.scene_compositions(scene):
        obj.gp2m.channel = channel
        channel += engine._channel_count(scene, obj)
    engine.arrange(scene)
    top = max(o.gp2m.channel + engine._channel_count(scene, o) - 1
              for o in engine.scene_compositions(scene) if o.gp2m.channel)
    clip = editor.strips.new_effect("Clip video", "COLOR", top + 1, frame_start=1,
                                    length=10)
    try:
        other = _fresh(None)
        base = other.gp2m.channel
        assert base == top + 2
        assert engine.top_strip(scene, other).channel == base
        assert clip.channel == top + 1 and clip.channel != base
        # A clip added later on its channel (after the sound, so Blender lets it
        # there): the composition moves up, the clip stays.
        later = editor.strips.new_effect("Clip dopo", "COLOR", base, frame_start=5000,
                                         length=10)
        engine.arrange(scene)
        assert later.channel == base and other.gp2m.channel > base
        channel = engine.top_strip(scene, other).channel
        assert channel == other.gp2m.channel and channel not in (later.channel, clip.channel)
        editor.strips.remove(later)
    finally:
        editor.strips.remove(clip)


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
    # GM 48 (string ensemble): the recorded strings of the web app.
    assert sorted(n.pitch for n in result.notes if n.instrument == "S_STRINGS") == list(
        range(60, 68))
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


def test_blank_keyframe_is_a_silent_section(comp):
    """Blender 5.3 has no frame durations: a pause is a blank keyframe (empty drawing)."""
    engine = sub("engine")
    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    start = scene.frame_start
    comp.gp2m.length = 2.0
    add_stroke(comp, 0, line(comp, 0.5, 1.0, 60))
    layer = sub("board").user_layers(comp.data)[0]
    layer.frames.new(start + round(4 * fps))  # what "Insert Blank Frame" makes
    add_stroke(comp, 0, line(comp, 0.5, 1.0, 67), frame=start + round(6 * fps))
    comp.gp2m.use_sections = True
    result = engine.regenerate(comp)
    assert result.sections == (0.0, 4.0, 6.0)
    assert [(n.pitch, round(n.start, 2)) for n in result.notes] == [
        (60, 0.5), (60, 2.5), (67, 6.5)]  # nothing between 4 and 6 s


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


def test_scene_start_and_frame_rate_changes_follow(comp):
    """Moving the scene start or changing fps re-places strips and keyframe sections."""
    handlers, engine = sub("handlers"), sub("engine")
    scene = bpy.context.scene
    old_start, old_fps = scene.frame_start, scene.render.fps
    comp.gp2m.length = 2.0
    add_stroke(comp, 0, line(comp, 0.5, 1.0, 60))
    add_stroke(comp, 0, line(comp, 0.5, 1.0, 64), frame=old_start + 48)
    comp.gp2m.use_sections = True
    engine.regenerate(comp)
    handlers._scene_timing.clear()
    bpy.context.view_layer.update()  # remembers the current timing
    try:
        scene.frame_start = old_start + 10
        scene.render.fps = 25
        bpy.context.view_layer.update()
        assert comp.name in handlers._dirty and handlers._cleanup_needed[0]
        handlers._last_change[0] = 0.0
        handlers._tick()
        strip = engine.find_strip(scene, comp)
        assert strip.content_start == scene.frame_start
        result = engine.regenerate(comp)
        # Keyframe at old_start + 48 = 38 frames after the new start, at 25 fps.
        assert result.sections == (0.0, pytest.approx(38 / 25))
    finally:
        scene.frame_start, scene.render.fps = old_start, old_fps
        bpy.context.view_layer.update()
        handlers._last_change[0] = 0.0
        handlers._tick()


def test_undo_in_draw_mode_keeps_the_board_colours(comp):
    """Draw-mode Ctrl+Z restores the drawings but not the material slots: board
    strokes must not stay on the wrong (black) materials."""
    board = sub("board")
    gp = comp.data
    board_layers = [layer for layer in gp.layers if board.is_board_layer(layer)]

    def indices():
        return [[stroke.material_index for stroke in layer.frames[0].drawing.strokes]
                for layer in board_layers]

    before = indices()
    assert board.board_materials_ok(comp)
    assert bpy.ops.gp2m.add_instrument(instrument="SINE") == {"FINISHED"}
    assert board.board_materials_ok(comp)  # adding shifts board slots and strokes
    # What paint-mode undo leaves: old drawings, new material slots.
    for layer, old in zip(board_layers, before):
        for stroke, index in zip(layer.frames[0].drawing.strokes, old):
            stroke.material_index = index
    assert not board.board_materials_ok(comp)
    board._pending.clear()
    sub("handlers").on_undo_redo()
    assert comp.name in board._pending
    board._rebuild_pending()  # normally run by a timer
    assert board.board_materials_ok(comp)


def test_sound_while_drawing_follows_the_stroke_being_drawn(comp, monkeypatch):
    draw_sound, keyboard, props = sub("draw_sound"), sub("keyboard"), sub("props")
    played = []

    class Handle:
        status = 1
        pitch = 1.0
        volume = 1.0

        def stop(self):
            self.status = 0

    def note_on(instrument, pitch, rate=44100, volume=1.0):
        played.append((instrument, pitch))
        return Handle()

    monkeypatch.setattr(keyboard, "note_on", note_on)
    monkeypatch.setattr(keyboard, "note_off", lambda handle: None)
    scene = bpy.context.scene
    layer = sub("board").user_layers(comp.data)[0]
    comp.data.layers.active = layer
    draw_sound._Live.tracker = draw_sound.Tracker()
    assert draw_sound.step(comp, scene, 0.0) is None  # first look
    # The pen goes down on E4 and moves up to G4: one note per row.
    stroke = add_stroke(comp, 0, [(0.5, row_z(comp, 64))])
    assert draw_sound.step(comp, scene, 0.01) == "start"
    drawing = layer.frames[0].drawing
    index = len(drawing.strokes) - 1
    for i, midi in enumerate((64, 65, 67), start=2):
        drawing.resize_strokes([i], indices=[index])
        stroke = drawing.strokes[index]
        stroke.points[i - 1].position = (0.5 + 0.1 * i, 0.0, row_z(comp, midi))
        stroke.points[i - 1].radius = 0.02
        assert draw_sound.step(comp, scene, 0.01 * (i + 1)) == "move"
    instrument = keyboard.instrument_of(comp)[0]
    assert [p for _i, p in played] == [64, 65, 67]  # the same row is one note
    assert {i for i, _p in played} == {instrument}
    assert draw_sound.step(comp, scene, 5.0) == "stop"
    # Optical reading: one held sound whose pitch follows the tip.
    props.find_layer_settings(comp.data, layer.name).mode = "OPTICAL"
    played.clear()
    add_stroke(comp, 0, [(2.0, row_z(comp, 60))])
    assert draw_sound.step(comp, scene, 6.0) == "start"
    index = len(drawing.strokes) - 1
    drawing.resize_strokes([2], indices=[index])
    drawing.strokes[index].points[1].position = (2.2, 0.0, row_z(comp, 62))
    assert draw_sound.step(comp, scene, 6.01) == "move"
    assert played == [(instrument, 60)]
    assert draw_sound._Live.handle.pitch == pytest.approx(2 ** (2 / 12))
    draw_sound.step(None, None, 7.0)
    assert draw_sound._tick() > 0  # the timer itself never fails (no Draw Mode here)


# --- Web app project (.json) ----------------------------------------------------------------

def _web_project_json():
    """A small project as the web app saves it (version 3)."""
    import base64
    import json
    tone = (np.sin(np.arange(4410) * 2 * np.pi * 440 / 44100) * 0.5 * 32767).astype("<i2")
    stroke = lambda sid, layer, inst, pts, **kw: {"id": sid, "layer": layer, "inst": inst,  # noqa: E731
                                                  "op": 1, "pts": pts, **kw}
    melody = [[b / 10, 72.5, 0.6, int(b * 60)] for b in range(0, 21)]  # 2 beats on C5
    state = {
        "name": "Dall'iPad", "bpm": 120, "bars": 2, "low": 48, "octaves": 3, "scale": "MINOR",
        "root": 2, "grid": 0.5,
        "layers": [
            {"id": "la", "name": "Melodia", "mode": "OPTICAL_LEGATO", "visible": True,
             "muted": False, "volume": 0.6, "pan": 0, "reverb": 0.4},
            {"id": "lb", "name": "Voce", "mode": "GESTURE", "visible": False, "muted": True,
             "volume": 0.9, "pan": 0, "reverb": 0},
        ],
        "strokes": [
            stroke("s1", "la", "EPIANO", melody),
            stroke("s2", "la", "GUITAR", [[4, 60.5, 0.5, 0], [5, 64.5, 0.5, 400]], brush="air"),
            stroke("s3", "la", "PAD", [[0, 55, 0.3, 0], [2, 55, 0.3, 50], [2, 58, 0.3, 90],
                                       [0, 58, 0.3, 130]], brush="fill"),
            stroke("s4", "lb", "SMP:xyz", [[1, 67.5, 0.5, 0], [3, 67.5, 0.5, 500]]),
            stroke("s5", "lb", "WAV:w1", [[6, 62.5, 0.5, 0], [7, 62.5, 0.5, 300]]),
        ],
        "beat": {"on": True, "steps": 16, "swing": 0, "volume": 0.7, "ab": False,
                 "tracks": {"KICK": {"mute": False, "p": [2, 0, 0, 0] * 8, "pB": [0] * 32},
                            "HAT": {"mute": False, "p": [0, 0, 1, 0] * 8, "pB": [0] * 32}}},
        "samples": [{"id": "SMP:xyz", "name": "La mia voce", "root": 69}],
        "waves": [{"id": "WAV:w1", "name": "Onda 1", "strokes": []}],
    }
    return json.dumps({"app": "grease-pencil-to-music-web", "version": 3, "state": state,
                       "sounds": {"SMP:xyz": base64.b64encode(tone.tobytes()).decode()}})


def test_web_project_opens_as_composition(addon, tmp_path):
    board, engine = sub("board"), sub("engine")
    path = tmp_path / "progetto.json"
    path.write_text(_web_project_json(), encoding="utf-8")
    assert bpy.ops.gp2m.import_web(filepath=str(path)) == {"FINISHED"}
    comp = bpy.context.view_layer.objects.active
    try:
        s = comp.gp2m
        assert comp.name.startswith("Dall'iPad")
        assert s.bpm == 120 and s.length == pytest.approx(4.0)  # 2 bars of 4/4 at 120
        assert (s.scale, s.root, s.time_grid) == ("MINOR", "D", "1_8")
        gp = comp.data
        names = [layer.name for layer in board.user_layers(gp)]
        assert names == ["Melodia", "Voce", "Beat"]  # the empty default layers are gone
        melodia, voce, beat = (gp.layers[n] for n in names)
        assert melodia.opacity == pytest.approx(0.6) and not melodia.hide
        assert voce.hide  # muted in the web app = hidden (not heard) in Blender
        settings = sub("props").find_layer_settings
        assert settings(gp, "Melodia").mode == "OPTICAL_LEGATO"
        assert settings(gp, "Melodia").reverb_mix == pytest.approx(0.4)
        assert settings(gp, "Voce").mode == "GESTURE"
        drawing = melodia.frames[0].drawing
        assert len(drawing.strokes) == 3
        first = drawing.strokes[0]
        # Beat 0..2 at 120 BPM = 0..1 s; pitch 72.5 = the middle of the C5 row.
        xs = [p.position.x for p in first.points]
        assert xs[0] == pytest.approx(0.0) and xs[-1] == pytest.approx(1.0 * s.seconds_width)
        assert first.points[0].position.z == pytest.approx(row_z(comp, 72))
        assert first.points[0].radius == pytest.approx(0.3 * s.row_height)
        assert drawing.attributes["delta_time"].data[20].value == pytest.approx(1.2)
        mats = gp.materials
        assert mats[first.material_index].gp2m_instrument in ("EPIANO", "BELL")
        assert mats[drawing.strokes[1].material_index].gp2m_instrument == "PLUCK"
        assert drawing.strokes[1].softness == pytest.approx(0.8)  # airbrush: slow attack
        fill = drawing.strokes[2]
        assert fill.fill_id != 0 and fill.cyclic
        sample_mat = mats[voce.frames[0].drawing.strokes[0].material_index]
        assert sample_mat.gp2m_instrument == "SAMPLE"
        assert sample_mat.gp2m_sample is not None and sample_mat.gp2m_sample_root == 69
        assert sample_mat.gp2m_sample.packed_file is not None
        assert all(mats[st.material_index].gp2m_layer == "Beat"
                   for st in beat.frames[0].drawing.strokes)
        assert len(beat.frames[0].drawing.strokes) == 8 + 8  # kicks and hats on every beat, 2 bars
        assert settings(gp, "Beat").mode == "OPTICAL"
        result = engine.regenerate(comp, force=True)
        assert len(result.notes) > 20
    finally:
        engine._state.pop(comp.name, None)


def test_composition_saves_for_the_web_app(addon, tmp_path):
    import json
    web_project = sub("web_project")
    source = tmp_path / "in.json"
    source.write_text(_web_project_json(), encoding="utf-8")
    bpy.ops.gp2m.import_web(filepath=str(source))
    comp = bpy.context.view_layer.objects.active
    out = tmp_path / "out.json"
    try:
        assert bpy.ops.gp2m.export_web(filepath=str(out)) == {"FINISHED"}
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["app"] == web_project.APP_ID and data["version"] == 3
        state = data["state"]
        assert (state["bpm"], state["bars"], state["scale"], state["root"], state["grid"]) \
            == (120, 2, "MINOR", 2, 0.5)
        assert [layer["name"] for layer in state["layers"]] == ["Melodia", "Voce", "Beat"]
        assert state["layers"][0]["mode"] == "OPTICAL_LEGATO"
        assert state["layers"][1]["muted"] is True
        melody = next(st for st in state["strokes"] if st["layer"] == state["layers"][0]["id"])
        assert melody["inst"] in ("EPIANO", "BELL")
        assert melody["pts"][0][:3] == pytest.approx([0.0, 72.5, 0.6], abs=1e-3)
        assert melody["pts"][-1][0] == pytest.approx(2.0, abs=1e-3)
        assert melody["pts"][-1][3] == 1200
        brushes = {st["brush"] for st in state["strokes"]}
        assert {"fill", "air", "smooth"} <= brushes
        # The recorded sound goes back into the file.
        assert len(state["samples"]) == 1 and state["samples"][0]["root"] == 69
        sid = state["samples"][0]["id"]
        assert sid in data["sounds"] and any(st["inst"] == sid for st in state["strokes"])
        # And the file opens again.
        project = web_project.parse(out.read_text(encoding="utf-8"),
                                    set(sub("synth").INSTRUMENT_BY_ID))
        assert len(project.layers) == 3 and len(project.sounds) == 1
    finally:
        sub("engine")._state.pop(comp.name, None)


def test_web_project_rejects_other_files(addon, tmp_path):
    path = tmp_path / "altro.json"
    path.write_text('{"hello": 1}', encoding="utf-8")
    with pytest.raises(RuntimeError):
        bpy.ops.gp2m.import_web(filepath=str(path))


def test_installed_addon_plays_the_web_app_recordings(comp):
    """The zip carries the recordings and the rooms; old .blend values keep their instrument."""
    import os
    samples, synth, props, engine = sub("samples"), sub("synth"), sub("props"), sub("engine")
    sounds = samples.sounds_dir()
    assert sounds.endswith("sounds") and os.path.isfile(os.path.join(sounds, "rooms", "church.mp3"))
    assert len([d for d in os.listdir(os.path.join(sounds, "samples"))
                if os.path.isdir(os.path.join(sounds, "samples", d))]) == 69
    # Recordings shared by two instruments are in the zip once (sounds/samples/aliases.txt),
    # and every note is decoded only when it first plays.
    assert not os.path.exists(os.path.join(sounds, "samples", "STRINGS", "53.mp3"))
    synth.SAMPLES.pop("S_STRINGS", None)
    zones = synth.recorded_zones("S_STRINGS")
    assert len(zones) == len(synth.RECORDINGS["S_STRINGS"].zones)
    assert all(zone.data is None for zone in zones)
    assert all(len(synth.zone_ready(zone).data) > 1000 for zone in zones)
    items = bpy.types.Material.bl_rna.properties["gp2m_instrument"].enum_items
    values = {item.identifier: item.value for item in items}
    old = ("SINE", "TRIANGLE", "SQUARE", "SAW", "STRINGS", "PLUCK", "BELL", "EPIANO", "MARIMBA",
           "PAD", "BASS", "DRUM", "KICK", "SNARE", "HIHAT", "OPENHAT", "CRASH", "CLAP", "TOM",
           "COWBELL", "RIM", "SHAKER", "SAMPLE", "LIBRARY")  # the 0.0.10 list, in its order
    assert [values[ident] for ident in old] == list(range(len(old)))
    assert len(values) == len(synth.INSTRUMENTS) == 96
    material = sub("board").instrument_material(synth.get_instrument("S_HARP"))
    assert material.gp2m_instrument == "S_HARP" and material.name.startswith("Arpa")
    sub("operators").append_instrument(comp, material)
    material.gp2m_layer = "Livello 1"
    index = list(comp.data.materials).index(material)
    add_stroke(comp, 0, line(comp, 0.5, 1.5, 62), material_index=index)
    comp.gp2m.room = "CHURCH"
    result = engine.regenerate(comp)
    assert any(n.instrument == "S_HARP" for n in result.notes)
    assert np.max(np.abs(result.audio)) > 0.05


def test_auto_update_waits_for_a_running_transform(comp, monkeypatch):
    """Regenerating while G/R/S or Alt+S is still dragging crashed Blender 5.3
    (the transform holds pointers into the drawings): the timer waits for it."""
    engine, handlers = sub("engine"), sub("handlers")
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60))
    engine.state(comp).pop("key", None)
    handlers.mark_dirty(comp)
    handlers._last_change[0] = 0.0
    monkeypatch.setattr(handlers, "transform_running", lambda: True)
    assert handlers._tick() == handlers.TRANSFORM_POLL
    assert comp.name in handlers._dirty  # still pending
    assert engine.state(comp).get("key") is None  # nothing regenerated yet
    monkeypatch.setattr(handlers, "transform_running", lambda: False)
    assert handlers._tick() is None
    assert engine.state(comp).get("key") is not None  # regenerated once it ended


def _list_order(gp):
    """(flags, order) of the layer list, checked like Blender does."""
    fake = type("FakeList", (), {"bitflag_filter_item": 1 << 30})()
    flags, order = sub("ui").GP2M_UL_layers.filter_items(fake, bpy.context, gp, "gp2m_layers")
    assert sorted(order) == list(range(len(gp.gp2m_layers)))  # a gap crashes Blender
    return flags, order


def _shown(gp):
    flags, order = _list_order(gp)
    return [name for _o, name in sorted((o, item.name) for o, item, f
                                         in zip(order, gp.gp2m_layers, flags) if f)]


def test_layer_list_order_stays_valid_while_settings_lag(comp):
    gp = comp.data
    gp.layers.active = gp.layers["Livello 2"]
    # Blender's own Duplicate: the new layer has no settings yet when the list redraws.
    with bpy.context.temp_override(active_object=comp, object=comp):
        assert bpy.ops.grease_pencil.layer_duplicate(empty_keyframes=False) == {"FINISHED"}
    assert sub("props").find_layer_settings(gp, "Livello 2.001") is None
    _list_order(gp)
    # And a layer deleted in Blender's list leaves settings without a layer.
    gp.layers.remove(gp.layers["Livello 3"])
    _list_order(gp)
    ui_log = []
    sub("ui").draw_layers_and_instruments(MockLayout(ui_log), comp)
    # The automatic sync gives the duplicate its settings, even with Auto off.
    comp.gp2m.auto_update = False
    sub("handlers").request_layer_sync(gp)
    sub("handlers")._layer_sync_tick()
    assert sub("props").find_layer_settings(gp, "Livello 2.001") is not None
    assert "Livello 2.001" in _shown(gp)


def test_duplicated_layer_gets_its_own_settings_and_instruments(comp):
    engine, props, board = sub("engine"), sub("props"), sub("board")
    gp = comp.data
    source = props.find_layer_settings(gp, "Livello 1")
    source.mode = "LEGATO"
    source.reverb_mix = 0.4
    own = board.layer_instruments(comp, "Livello 1")
    index, material = own[0]
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60), material_index=index)
    before = len(engine.regenerate(comp).notes)
    gp.layers.active = gp.layers["Livello 1"]
    assert bpy.ops.gp2m.duplicate_layer() == {"FINISHED"}
    copy = gp.layers.active
    assert copy.name == "Livello 1.001"
    settings = props.find_layer_settings(gp, copy.name)
    assert settings.mode == "LEGATO" and abs(settings.reverb_mix - 0.4) < 1e-6
    # Its instruments are copies: changing one does not change the original.
    copies = board.layer_instruments(comp, copy.name)
    assert [m.gp2m_instrument for _i, m in copies] == [m.gp2m_instrument for _i, m in own]
    assert all(m != material for _i, m in copies)
    stroke = copy.frames[0].drawing.strokes[0]
    assert stroke.material_index == copies[0][0]
    copies[0][1].gp2m_instrument = "PLUCK"
    assert material.gp2m_instrument != "PLUCK"
    assert len(engine.regenerate(comp).notes) == 2 * before
    # The playhead stays on top.
    assert list(gp.root_nodes)[-1].name == board.HEAD_GROUP


def test_layer_groups(comp):
    engine, props, board = sub("engine"), sub("props"), sub("board")
    gp = comp.data
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60), material_index=0)
    add_stroke(comp, 1, line(comp, 3.0, 4.0, 64), material_index=0)
    add_stroke(comp, 2, line(comp, 5.0, 6.0, 67), material_index=0)
    pitches = lambda: sorted(n.pitch for n in engine.regenerate(comp).notes)  # noqa: E731
    assert pitches() == [60, 64, 67]
    # New group around "Livello 2", in its place.
    gp.layers.active = gp.layers["Livello 2"]
    assert bpy.ops.gp2m.add_group() == {"FINISHED"}
    group = gp.layers["Livello 2"].parent_group
    assert group is not None and group.name == "Gruppo 1"
    assert gp.layers.active.name == "Livello 2"
    assert _shown(gp) == ["Livello 3", "Gruppo 1", "Livello 2", "Livello 1"]
    settings = props.find_layer_settings(gp, "Gruppo 1")
    assert settings is not None and settings.is_group
    # Moving into and out of the group.
    gp.layers.active = gp.layers["Livello 1"]
    assert bpy.ops.gp2m.move_layer(direction="UP") == {"FINISHED"}
    assert gp.layers["Livello 1"].parent_group.name == "Gruppo 1"
    assert _shown(gp) == ["Livello 3", "Gruppo 1", "Livello 2", "Livello 1"]
    assert bpy.ops.gp2m.move_layer(direction="DOWN") == {"FINISHED"}
    assert gp.layers["Livello 1"].parent_group is None
    assert bpy.ops.gp2m.move_layer(direction="DOWN") == {"CANCELLED"}  # the board is below
    assert bpy.ops.gp2m.move_to_group(group="Gruppo 1") == {"FINISHED"}
    assert [c.name for c in group.children] == ["Livello 2", "Livello 1"]
    # Mute, Solo and hide of the whole group.
    settings = props.find_layer_settings(gp, "Gruppo 1")
    settings.mute = True
    assert pitches() == [67]
    settings.mute = False
    settings.solo = True
    assert pitches() == [60, 64]
    assert abs(gp.layers["Livello 3"].opacity - props.SOLO_OPACITY) < 1e-6
    settings.solo = False
    assert abs(gp.layers["Livello 3"].opacity - 1.0) < 1e-6
    group.hide = True
    assert pitches() == [67]
    group.hide = False
    # A closed group hides its layers in the list.
    group.is_expanded = False
    assert _shown(gp) == ["Livello 3", "Gruppo 1"]
    group.is_expanded = True
    # Clicking the group row picks its top layer.
    gp.gp2m_layer_index = [i.name for i in gp.gp2m_layers].index("Gruppo 1")
    assert gp.layers.active.name == "Livello 1"
    # The panel draws groups too.
    log = []
    sub("ui").draw_layers_and_instruments(MockLayout(log), comp)
    sub("ui").GP2M_MT_layer_specials.draw(_Drawer(log), bpy.context)
    sub("ui").GP2M_MT_move_to_group.draw(_Drawer(log), bpy.context)
    drawn = {entry[1] for entry in log}
    assert {"is_expanded", "gp2m.duplicate_layer", "gp2m.add_group", "gp2m.move_to_group",
            "gp2m.ungroup", "GP2M_MT_layer_specials"} <= drawn
    # Ungroup: the layers stay, the playhead stays on top.
    assert bpy.ops.gp2m.ungroup() == {"FINISHED"}
    assert gp.layer_groups.get("Gruppo 1") is None
    assert props.find_layer_settings(gp, "Gruppo 1") is None
    assert _shown(gp) == ["Livello 3", "Livello 1", "Livello 2"]
    assert list(gp.root_nodes)[-1].name == board.HEAD_GROUP
    assert pitches() == [60, 64, 67]


def test_group_made_in_blenders_list_keeps_the_playhead_on_top(comp):
    board, props = sub("board"), sub("props")
    gp = comp.data
    group = gp.layer_groups.new("Archi")  # Blender's own "+ group": on top of everything
    gp.layers.move_to_layer_group(gp.layers["Livello 3"], group)
    board.ensure_order(gp)
    props.ensure_layer_settings(gp)
    roots = [n.name for n in gp.root_nodes]
    assert roots[-1] == board.HEAD_GROUP and board.BOARD_GROUP not in roots
    assert props.find_layer_settings(gp, "Archi").is_group
    group.is_expanded = True
    assert _shown(gp)[:2] == ["Archi", "Livello 3"]
    group.is_expanded = False  # a closed group shows only its own row
    assert _shown(gp)[:2] == ["Archi", "Livello 2"]


def test_layer_specials_like_blender(comp):
    board, props, engine = sub("board"), sub("props"), sub("engine")
    gp = comp.data
    gp.layers.active = gp.layers["Livello 2"]
    # Hide others / show all / lock: never the board.
    assert bpy.ops.gp2m.layers_hide_others() == {"FINISHED"}
    assert [l.hide for l in board.user_layers(gp)] == [True, False, True]
    assert not any(l.hide for l in gp.layers if board.is_board_layer(l)
                   and l.name != board.SHADE_LAYER)
    assert bpy.ops.gp2m.layers_reveal() == {"FINISHED"}
    assert not any(l.hide for l in board.user_layers(gp))
    assert bpy.ops.gp2m.layers_lock(lock=True) == {"FINISHED"}
    assert all(l.lock for l in board.user_layers(gp))
    assert bpy.ops.gp2m.layers_lock(lock=False) == {"FINISHED"}
    assert not any(l.lock for l in board.user_layers(gp))
    assert all(l.lock for l in gp.layers if board.is_board_layer(l))
    # Merge down: the instruments of the merged layer move to the one that stays.
    add_stroke(comp, 1, line(comp, 1.0, 2.0, 64), material_index=0)
    count = len(board.layer_instruments(comp, "Livello 1"))
    moved = len(board.layer_instruments(comp, "Livello 2"))
    assert bpy.ops.gp2m.merge_layer(mode="ACTIVE") == {"FINISHED"}
    assert gp.layers.get("Livello 2") is None and gp.layers.active.name == "Livello 1"
    assert len(board.layer_instruments(comp, "Livello 1")) == count + moved
    assert props.find_layer_settings(gp, "Livello 2") is None
    assert list(gp.root_nodes)[-1].name == board.HEAD_GROUP
    assert [n.pitch for n in engine.regenerate(comp).notes] == [64]
    # Merging the bottom layer would cross the board.
    gp.layers.active = board.user_layers(gp)[0]
    assert not bpy.ops.gp2m.merge_layer.poll()
    # Duplicate with empty keyframes.
    assert bpy.ops.gp2m.duplicate_layer(empty_keyframes=True) == {"FINISHED"}
    assert len(gp.layers.active.frames[0].drawing.strokes) == 0


def test_grid_inside_the_composition_moves_out(comp):
    """Files up to 0.0.20 had the grid inside the composition (group renamed in 0.0.12)."""
    board, operators = sub("board"), sub("operators")
    gp = comp.data
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60), material_index=1)
    instrument = gp.materials[1].name
    # Rebuild what an old file looks like: board group and materials inside.
    old_grid = board.grid_object(comp)
    bpy.data.objects.remove(old_grid, do_unlink=True)
    group = gp.layer_groups.new(board.LEGACY_BOARD_GROUP)
    gp.layer_groups.move_bottom(group)
    index = board._ensure_materials(gp)
    keys = gp.layers.new("GP2M Tasti", set_active=False, layer_group=group)
    board._add_strokes(keys.frames.new(1).drawing,
                       [([(0, 0), (1, 0)], 0.01, index["GP2M Tasto nero"], "line")])
    operators.append_instrument(comp, board.instrument_materials(["SINE"])[0])
    assert not board.has_board(comp)
    board.rebuild(comp)
    assert board.has_board(comp)
    assert gp.layer_groups.get(board.LEGACY_BOARD_GROUP) is None
    assert gp.layer_groups.get(board.BOARD_GROUP) is None
    assert [m.name for m in gp.materials if board.is_board_material(m)] == ["GP2M Testina"]
    stroke = board.user_layers(gp)[0].frames[0].drawing.strokes[0]
    assert gp.materials[stroke.material_index].name == instrument  # same instrument
    assert board.board_materials_ok(comp)
    assert len(_grid(comp).layers["GP2M Tasti"].frames[0].drawing.strokes) > 10


def test_clicking_the_grid_selects_the_composition(comp):
    board, handlers = sub("board"), sub("handlers")
    view_layer = bpy.context.view_layer
    grid = board.grid_object(comp)
    comp.select_set(False)
    grid.select_set(True)
    view_layer.objects.active = grid
    assert handlers.select_composition_of_grid(view_layer) == comp
    assert view_layer.objects.active == comp and comp.select_get()
    assert not grid.select_get()


def test_duplicate_and_delete_take_care_of_the_grid(comp):
    board, engine, handlers = sub("board"), sub("engine"), sub("handlers")
    copy = comp.copy()
    bpy.context.scene.collection.objects.link(copy)
    assert copy.gp2m.grid == comp.gp2m.grid and board.grid_object(copy) is None
    assert not board.has_board(copy)
    board.make_independent(handlers.compositions())
    board.rebuild(copy)
    assert board.grid_object(copy) not in (None, board.grid_object(comp))
    grid_name = board.grid_object(copy).name
    bpy.data.objects.remove(copy, do_unlink=True)
    engine.cleanup_orphans()
    assert bpy.data.objects.get(grid_name) is None
    assert board.grid_object(comp) is not None


# --- One channel per layer, absolute volumes, Auto on the active layer only -----------

def _two_layers(comp):
    """Strokes on the first two layers of a new composition (it has three)."""
    names = [layer.name for layer in sub("board").user_layers(comp.data)]
    assert len(names) >= 2
    add_stroke(comp, 0, line(comp, 0.5, 2.5, 60), radius=0.02)
    add_stroke(comp, 1, line(comp, 3.0, 5.0, 67), radius=0.3)
    return names


def test_one_strip_per_layer_adds_up_to_the_mix(comp):
    engine = sub("engine")
    scene = bpy.context.scene
    names = _two_layers(comp)
    assert comp.gp2m.layer_channels
    result = engine.regenerate(comp)
    strips = engine.layer_strips(scene, comp)
    assert set(strips) == set(names)
    # One meta-clip on the composition's channel, the layers inside from channel 1.
    meta = engine.meta_strip(scene, comp)
    assert meta is not None and meta.channel == comp.gp2m.channel
    assert all(strip.parent_meta() == meta for strip in strips.values())
    channels = sorted(strip.channel for strip in strips.values())
    assert channels == list(range(1, 1 + len(names)))
    assert meta.left_handle <= min(s.left_handle for s in strips.values())
    assert meta.right_handle >= max(s.right_handle for s in strips.values())
    order = [strips[name].channel for name in names]
    assert order == sorted(order)  # the layers' order, bottom layer lowest
    total = None
    for name, strip in strips.items():
        rate, samples = read_wav(strip.sound.filepath)
        total = samples.astype(np.int64) if total is None else total + samples
    mix = np.clip(result.audio, -1, 1) * 32767
    assert np.abs(total - mix).max() < 8  # rounding of the 16-bit files only
    # The first layer is heard only in its own strip.
    _rate, first = read_wav(strips[names[0]].sound.filepath)
    _rate, second = read_wav(strips[names[1]].sound.filepath)
    assert np.abs(first[int(1.5 * rate)]).max() > 300
    assert np.abs(second[int(1.5 * rate)]).max() < 30


def test_mix_strip_when_layer_channels_are_off(comp):
    engine = sub("engine")
    scene = bpy.context.scene
    _two_layers(comp)
    engine.regenerate(comp)
    comp.gp2m.layer_channels = False
    engine.regenerate(comp)
    assert not engine.layer_strips(scene, comp)
    assert len(engine.composition_strips(scene, comp)) == 1
    comp.gp2m.layer_channels = True
    engine.regenerate(comp)
    layers = len(sub("board").user_layers(comp.data))
    assert len(engine.layer_strips(scene, comp)) == layers
    assert len(engine.composition_strips(scene, comp)) == layers


def test_sequencer_volume_of_a_layer_strip_is_kept(comp):
    engine = sub("engine")
    scene = bpy.context.scene
    names = _two_layers(comp)
    engine.regenerate(comp)
    engine.layer_strips(scene, comp)[names[0]].volume = 0.3
    sub("seqsync").sync_scene(scene)  # what the depsgraph handler does after the change
    assert sub("props").find_layer_settings(comp.data, names[0]).clip_volume == \
        pytest.approx(0.3)
    add_stroke(comp, 0, line(comp, 6.0, 7.5, 64))  # longer sound: strips may be recreated
    engine.regenerate(comp)
    assert engine.layer_strips(scene, comp)[names[0]].volume == pytest.approx(0.3)


def test_a_thick_stroke_does_not_turn_the_others_down(comp):
    engine = sub("engine")
    add_stroke(comp, 0, line(comp, 0.5, 2.5, 60), radius=0.02)
    alone = engine.regenerate(comp)
    add_stroke(comp, 0, line(comp, 4.0, 6.0, 72), radius=0.5)  # very thick, elsewhere
    both = engine.regenerate(comp)
    rate = alone.sample_rate
    window = slice(int(1.0 * rate), int(2.0 * rate))
    a = float(np.abs(alone.audio[window]).max())
    b = float(np.abs(both.audio[window]).max())
    assert b == pytest.approx(a, rel=0.25)  # the glue compressor may move it a little


def test_auto_on_the_active_layer_only(comp):
    engine = sub("engine")
    scene = bpy.context.scene
    names = _two_layers(comp)
    engine.regenerate(comp)
    comp.gp2m.auto_active_layer = True
    comp.data.layers.active = comp.data.layers[names[1]]
    add_stroke(comp, 1, line(comp, 6.0, 7.0, 69))
    result = engine.regenerate(comp, only_active=True)
    assert engine.state(comp)["stats"]["only_active"]
    assert sorted(n.pitch for n in result.notes) == [60, 67, 69]
    full = engine.regenerate(comp, force=True)
    assert full.key == result.key  # same sound as rendering everything
    # A layer muted meanwhile cannot keep its old sound: everything is rendered.
    sub("props").find_layer_settings(comp.data, names[0]).mute = True
    result = engine.regenerate(comp, only_active=True)
    assert not engine.state(comp)["stats"]["only_active"]
    strips = engine.layer_strips(scene, comp)  # the muted layer keeps its clip, muted
    assert {name for name, strip in strips.items() if not strip.mute} == set(names[1:])
    assert strips[names[0]].mute


def test_layer_modifiers_effects_and_copy_paste(comp):
    """0.0.15: modifiers and effects per layer with their checkbox, copy and paste."""
    props, engine = sub("props"), sub("engine")
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60))
    notes = lambda: engine.render_composition(comp, bpy.context.scene)[0].notes  # noqa: E731
    plain = len(notes())
    assert plain > 0
    first = sub("board").user_layers(comp.data)[0].name
    settings = props.find_layer_settings(comp.data, first)
    settings.use_array = True
    settings.array_count = 3
    assert len(notes()) == 3 * plain
    settings.use_array = False
    assert len(notes()) == plain

    # Effects are off until their checkbox is on; switching on gives an audible amount.
    assert engine._layer_fx(settings).reverb_mix == 0
    settings.use_reverb = True
    assert settings.reverb_mix > 0 and engine._layer_fx(settings).reverb_mix > 0
    settings.use_canon = True
    assert settings.canon_voices == 2
    assert len(notes()) == 2 * plain

    # Files saved before 0.0.15: an effect in use keeps sounding.
    old = props.find_layer_settings(comp.data, sub("board").user_layers(comp.data)[1].name)
    old.delay_mix = 0.4
    old.settings_version = 0
    props.migrate_layer_settings(old)
    assert old.use_echo and not old.use_reverb and old.settings_version == 1

    # Copy and paste to every layer.
    settings.use_fade = True
    settings.fade_direction = "BOTH"
    settings.mode = "OPTICAL"
    comp.data.layers.active = comp.data.layers[first]
    assert bpy.ops.gp2m.copy_layer_settings() == {"FINISHED"}
    assert bpy.ops.gp2m.paste_layer_settings(every=True) == {"FINISHED"}
    for layer in sub("board").user_layers(comp.data):
        item = props.find_layer_settings(comp.data, layer.name)
        assert item.use_fade and item.fade_direction == "BOTH" and item.mode == "OPTICAL"
        assert item.use_canon and item.name == layer.name


def test_instrument_icons_are_loaded(addon):
    icons, families = sub("icons"), sub("families")
    for name in families.icon_names():  # (icon ids stay 0 without a GPU, as here)
        assert "inst_" + name in icons._previews, name
    assert icons.instrument_icon("SAMPLE") == ("FILE_SOUND", 0)
    assert icons.instrument_icon("S_VIOLIN") in (("", icons.icon("inst_violin")), ("DOT", 0))
    # The instrument list keeps the old numbers (saved files) and is in family order.
    items = bpy.types.Material.bl_rna.properties["gp2m_instrument"].enum_items
    numbers = {i.identifier: i.value for i in items}
    synth = sub("synth")
    assert numbers == {inst.ident: n for n, inst in enumerate(synth.INSTRUMENTS)}
    order = [i.identifier for i in items]
    assert order.index("S_FLUTE") < order.index("SINE") < order.index("S_TRUMPET")


def test_auto_active_layer_hears_edits_of_the_other_layers(comp):
    """Edit and Sculpt Mode change the strokes of every layer: a partial render of the
    active layer must not keep the old sound of a layer that was edited."""
    engine = sub("engine")
    scene = bpy.context.scene
    comp.gp2m.layer_channels = True
    comp.gp2m.auto_active_layer = True
    add_stroke(comp, 0, line(comp, 0.5, 2.0, 60))
    other = add_stroke(comp, 1, line(comp, 3.0, 4.0, 64))
    comp.data.layers.active = comp.data.layers["Livello 1"]
    before = {name: audio.copy() for name, audio in engine.regenerate(comp, scene, force=True).stems}
    # Nothing changed: only the active layer is rendered again.
    engine.regenerate(comp, scene, only_active=True)
    assert engine.state(comp)["stats"]["only_active"]
    for point in other.points:
        x, y, z = point.position
        point.position = (x, y, z + comp.gp2m.row_height * 5)
    sub("board").user_layers(comp.data)[1].frames[0].drawing.tag_positions_changed()
    after = dict(engine.regenerate(comp, scene, only_active=True).stems)
    assert not engine.state(comp)["stats"]["only_active"]
    assert not np.array_equal(before["Livello 2"], after["Livello 2"])


def test_removing_the_layer_in_solo_lights_up_the_others(comp):
    props = sub("props")
    gp = comp.data
    props.find_layer_settings(gp, "Livello 2").solo = True
    assert gp.layers["Livello 1"].opacity == pytest.approx(props.SOLO_OPACITY)
    gp.layers.active = gp.layers["Livello 2"]
    assert bpy.ops.gp2m.remove_layer() == {"FINISHED"}
    assert all(layer.opacity == pytest.approx(1.0) for layer in sub("board").user_layers(gp))
    # Also when deleted with Blender's own layer list.
    props.find_layer_settings(gp, "Livello 3").solo = True
    assert gp.layers["Livello 1"].opacity == pytest.approx(props.SOLO_OPACITY)
    gp.layers.remove(gp.layers["Livello 3"])
    props.ensure_layer_settings(gp)
    assert all(layer.opacity == pytest.approx(1.0) for layer in sub("board").user_layers(gp))


@pytest.mark.parametrize("per_layer", [False, True])
def test_strips_given_back_an_older_file_are_written_again(comp, tmp_path, per_layer):
    """Undo gives the strips back the files of an earlier sound (deleted, or still on
    disk on Windows): the sound is written again, also with automatic updates off."""
    engine, handlers = sub("engine"), sub("handlers")
    scene = bpy.context.scene
    comp.gp2m.layer_channels = per_layer
    add_stroke(comp, 0, line(comp, 0.5, 2.0, 60))
    engine.regenerate(comp, scene, force=True)
    assert engine.sound_files_ok(comp, scene)
    stale = str(tmp_path / "older.wav")
    engine.write_audio(stale, np.zeros((100, 2), np.float32), 44100)
    strip = engine.find_strip(scene, comp)
    strip.sound.filepath = stale  # what undo does
    assert not engine.sound_files_ok(comp, scene)
    comp.gp2m.auto_update = False
    handlers.on_undo_redo()
    handlers._last_change[0] = 0.0
    handlers._tick()
    assert engine.sound_files_ok(comp, scene)
    assert bpy.path.abspath(engine.find_strip(scene, comp).sound.filepath) != stale
    comp.gp2m.auto_update = True


def _only(comp):
    engine = sub("engine")
    for obj in engine.scene_compositions(bpy.context.scene):
        if obj != comp:
            bpy.data.objects.remove(obj, do_unlink=True)
    engine.cleanup_orphans()


def test_follow_scene_in_and_out(comp):
    """The composition lasts from the scene Start to its End, both ways."""
    engine = sub("engine")
    _only(comp)
    scene = bpy.context.scene
    scene.gp2m_play.mode = "TOGETHER"
    fps = scene.render.fps / scene.render.fps_base
    comp.gp2m.length = 8.0
    scene.frame_end = scene.frame_start + 400
    comp.gp2m.follow_scene = True  # the only one: the scene takes its length
    assert scene.frame_end - scene.frame_start + 1 == round(8 * fps)
    assert comp.gp2m.length == pytest.approx(8.0)

    scene.frame_end = scene.frame_start + round(10 * fps) - 1  # new Out
    engine.arrange(scene)
    assert comp.gp2m.length == pytest.approx(10.0)
    engine.regenerate(comp)
    assert engine.find_strip(scene, comp).duration == round(10 * fps)

    comp.gp2m.length = 6.0  # Durata (or scaling the board) moves the Out
    engine.arrange(scene)
    assert scene.frame_end - scene.frame_start + 1 == round(6 * fps)

    other = _fresh(None)  # a second composition follows the scene
    other.gp2m.follow_scene = True
    engine.arrange(scene)
    assert other.gp2m.length == pytest.approx(6.0)
    assert scene.frame_end - scene.frame_start + 1 == round(6 * fps)

    scene.frame_start += 24  # new In: the strips move, the length stays
    engine.arrange(scene)
    assert engine.find_strip(scene, comp).frame_final_start == scene.frame_start
    scene.frame_start -= 24
    comp.gp2m.follow_scene = other.gp2m.follow_scene = False
    bpy.data.objects.remove(other, do_unlink=True)


def test_follow_scene_with_sections(comp):
    """With keyframe sections the loop keeps its length and the last one reaches Out."""
    engine = sub("engine")
    _only(comp)
    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    start = scene.frame_start
    comp.gp2m.length = 2.0
    add_stroke(comp, 0, line(comp, 0.5, 1.0, 60))
    add_stroke(comp, 0, line(comp, 0.5, 1.0, 64), frame=start + round(4 * fps))
    comp.gp2m.use_sections = True
    comp.gp2m.follow_scene = True
    scene.frame_end = start + round(9 * fps) - 1
    engine.arrange(scene)
    result = engine.regenerate(comp)
    assert comp.gp2m.length == pytest.approx(2.0)
    assert result.sections == (0.0, 4.0) and result.duration == pytest.approx(9.0)
    scene.frame_end = start + round(3 * fps) - 1  # the second section is after Out
    result = engine.regenerate(comp)
    assert {n.pitch for n in result.notes} == {60}
    assert result.duration == pytest.approx(3.0)
    comp.gp2m.follow_scene = False
    comp.gp2m.use_sections = False


def test_layers_have_their_own_colors_on_strips(comp):
    engine, props = sub("engine"), sub("props")
    scene = bpy.context.scene
    comp.gp2m.layer_channels = True
    for index in range(3):
        add_stroke(comp, index, line(comp, 0.5, 1.0, 60 + index))
    engine.regenerate(comp, force=True)
    items = [props.find_layer_settings(comp.data, layer.name)
             for layer in sub("board").user_layers(comp.data)]
    colors = [item.color for item in items]
    assert "NONE" not in colors and len(set(colors)) == len(colors)
    strips = engine.layer_strips(scene, comp)
    assert all(strips[item.name].color_tag == item.color for item in items)
    items[0].color = "COLOR_09"  # by hand: the strip follows at once
    assert strips[items[0].name].color_tag == "COLOR_09"
    comp.data.layers.new("Nuovo")
    props.ensure_layer_settings(comp.data)
    fresh = props.find_layer_settings(comp.data, "Nuovo")
    assert fresh.color not in ("NONE", "COLOR_09")


# --- Compositions as layers on the table ------------------------------------------------

def test_new_composition_is_stacked_on_the_table(comp):
    table = sub("table")
    board = sub("board")
    other = _fresh(None)
    below = max((o for o in table.compositions(bpy.context.scene) if o != other),
                key=lambda o: table._top_point(o).z)
    z0, _z1 = board.vertical_extent(other.gp2m)
    bottom = (other.matrix_world @ __import__("mathutils").Vector((0, 0, z0))).z
    assert bottom >= table._top_point(below).z - 1e-4
    assert abs(other.matrix_world.translation.x - below.matrix_world.translation.x) < 1e-4


def test_composition_list_follows_the_channels(comp):
    table = sub("table")
    engine = sub("engine")
    scene = bpy.context.scene
    other = _fresh(None)
    ordered = table.by_channel(scene)
    assert ordered[-1] == other  # the newest is the highest level
    # The list shows the highest channel on top.
    flags, order = sub("table").GP2M_UL_compositions.filter_items(
        type("L", (), {"bitflag_filter_item": 1})(), bpy.context, scene, "objects")
    shown = sorted((order[i], obj) for i, obj in enumerate(scene.objects) if flags[i])
    assert [obj for _rank, obj in shown][0] == other
    # Moving it down swaps the channel blocks with the one below.
    below = ordered[-2]
    before = (below.gp2m.channel, other.gp2m.channel)
    bpy.context.view_layer.objects.active = other
    assert bpy.ops.gp2m.composition_move(direction="DOWN") == {"FINISHED"}
    assert other.gp2m.channel == before[0] and below.gp2m.channel > other.gp2m.channel
    assert table.by_channel(scene).index(other) == len(ordered) - 2
    for obj in (other, below):
        first, last = table.channel_span(scene, obj)
        assert first == last == engine.top_strip(scene, obj).channel
    # Picking a row selects the composition.
    index = list(scene.objects).index(below)
    scene.gp2m_composition_index = index
    assert bpy.context.view_layer.objects.active == below


def test_hide_lock_duplicate_remove_and_stack(comp):
    table = sub("table")
    board = sub("board")
    engine = sub("engine")
    scene = bpy.context.scene
    grid = board.grid_object(comp)
    assert bpy.ops.gp2m.composition_toggle(name=comp.name, what="HIDE") == {"FINISHED"}
    assert comp.hide_get() and grid.hide_get()
    bpy.ops.gp2m.composition_toggle(name=comp.name, what="HIDE")
    assert not comp.hide_get() and not grid.hide_get()
    bpy.ops.gp2m.composition_toggle(name=comp.name, what="LOCK")
    assert comp.hide_select and grid.hide_select
    bpy.ops.gp2m.composition_toggle(name=comp.name, what="LOCK")
    assert not comp.hide_select
    table.select_only(bpy.context, comp)
    assert bpy.ops.gp2m.composition_duplicate() == {"FINISHED"}
    copy = bpy.context.view_layer.objects.active
    assert copy != comp and copy.gp2m.is_composition and board.has_board(copy)
    assert board.grid_object(copy) not in (None, grid)
    assert table.by_channel(scene)[-1] == copy
    assert bpy.ops.gp2m.table_stack() == {"FINISHED"}
    ordered = table.by_channel(scene)
    for low, high in zip(ordered, ordered[1:]):
        assert high.matrix_world.translation.z > low.matrix_world.translation.z
    name = copy.name
    grid_name = board.grid_object(copy).name
    assert bpy.ops.gp2m.composition_remove() == {"FINISHED"}
    assert bpy.data.objects.get(name) is None and bpy.data.objects.get(grid_name) is None
    assert not [s for s in scene.sequence_editor.strips_all if s.get(engine.OWNER_KEY) == name]


def test_octaves_below_and_above_keep_the_drawing(comp):
    board = sub("board")
    engine = sub("engine")
    from mathutils import Vector
    s = comp.gp2m
    s.low_note, s.octaves = 48, 2
    board.rebuild(comp)
    add_stroke(comp, 0, line(comp, 0.5, 2.0, 60))
    layer = board.user_layers(comp.data)[0]
    world = lambda: [tuple(comp.matrix_world @ Vector(p.position))
                     for p in layer.frames[0].drawing.strokes[-1].points]
    before = world()
    notes = sorted({round(n.pitch) for n in engine.regenerate(comp).notes})
    assert bpy.ops.gp2m.board_octaves(edge="BOTTOM", delta=1, name=comp.name) == {"FINISHED"}
    assert (s.low_note, s.octaves) == (36, 3)
    assert np.allclose(world(), before, atol=1e-4)  # the drawing has not moved
    board.rebuild(comp)
    assert sorted({round(n.pitch) for n in engine.regenerate(comp).notes}) == notes
    assert bpy.ops.gp2m.board_octaves(edge="TOP", delta=1, name=comp.name) == {"FINISHED"}
    assert (s.low_note, s.octaves) == (36, 4)
    assert bpy.ops.gp2m.board_octaves(edge="BOTTOM", delta=-1, name=comp.name) == {"FINISHED"}
    assert (s.low_note, s.octaves) == (48, 3)
    assert np.allclose(world(), before, atol=1e-4)
    s.low_note = 12
    assert board.octave_steps(s, "BOTTOM", 1) == 0  # no room below C0


# --- Rig (Object Mode handles, gizmos) -------------------------------------------------

def test_rig_handles_are_gizmos_with_theme_colors(comp):
    rig = sub("rig")
    assert rig.rig_object(comp) is None  # no object: the handles are gizmos
    assert "bl_rna" in rig.GP2M_GGT_rig.__dict__
    assert "bl_rna" in rig.GP2M_GT_handle.__dict__
    for handle in rig.HANDLE_NAMES:
        body, rim, glyphs = rig.handle_geometry(handle)
        assert len(body) % 3 == 0 and len(rim) % 3 == 0 and len(glyphs) % 3 == 0
        # Drawn outside the board, beside the anchor (pixels).
        xs = [p[0] for p in rim]
        zs = [p[2] for p in rim]
        if handle == rig.LENGTH:
            assert min(xs) > 0
        elif handle in (rig.OCT_TOP, rig.HEAD):
            assert min(zs) >= -3.0
        else:
            assert max(zs) < 0
    colors = sub("theme").handle_colors(bpy.context)
    active = tuple(bpy.context.preferences.themes[0].view_3d.object_active)
    assert np.allclose(colors["active"], active)
    playhead = tuple(bpy.context.preferences.themes[0].common.anim.playhead)[:3]
    assert np.allclose(colors["playhead"], playhead)


def test_rig_of_0_0_22_is_removed(comp):
    rig = sub("rig")
    data = bpy.data.grease_pencils.new(comp.name + rig.RIG_SUFFIX)
    old = bpy.data.objects.new(data.name, data)
    old[rig.RIG_ROLE] = True
    bpy.context.scene.collection.objects.link(old)
    old.parent = comp
    name = old.name
    assert not sub("board").has_board(comp)
    sub("board").rebuild(comp)
    assert rig.rig_object(comp) is None and bpy.data.objects.get(name) is None
    assert sub("board").has_board(comp)


def test_board_and_playhead_follow_the_theme(comp):
    theme = sub("theme")
    t = bpy.context.preferences.themes[0]
    head = bpy.data.materials["GP2M Testina"].grease_pencil
    assert np.allclose(tuple(head.color)[:3], theme.to_linear(t.common.anim.playhead), atol=1e-4)
    back = bpy.data.materials["GP2M Sfondo"].grease_pencil
    assert np.allclose(tuple(back.fill_color)[:3],
                       theme.to_linear(t.dopesheet_editor.space.back), atol=1e-4)
    old = tuple(t.common.anim.playhead)
    try:
        t.common.anim.playhead = (0.9, 0.1, 0.5, 1.0)
        assert theme.apply_to_materials()
        assert np.allclose(tuple(head.color)[:3], theme.to_linear(t.common.anim.playhead),
                           atol=1e-4)
        assert head.color[0] > 0.6 > head.color[1]
        assert not theme.apply_to_materials()  # nothing changed since
    finally:
        t.common.anim.playhead = old
        theme.apply_to_materials()


def test_rig_handles_change_length_playhead_and_octaves(comp):
    rig = sub("rig")
    s = comp.gp2m
    s.bpm, s.show_beats = 120.0, True
    assert rig.length_value(s, 6.21, 24) == round(149 / 24, 4)  # free, to the frame
    assert rig.length_value(s, 6.2, 24, bars=True) == 6.0  # Ctrl: bars of 2 s at 120 BPM
    assert rig.length_value(s, 0.1, 24) == 1.0
    assert rig.apply(comp, rig.LENGTH, 6.0) and s.length == 6.0
    assert not rig.apply(comp, rig.LENGTH, 6.0)
    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    frame = rig.frame_at(scene, comp, 2.0 * s.seconds_width)
    assert frame == round(scene.frame_start + sub("engine").state(comp).get(
        "offset_frames", 0) + 2.0 * fps)
    s.low_note, s.octaves = 48, 2
    assert rig.apply(comp, rig.OCT_BOTTOM, 12) and (s.low_note, s.octaves) == (36, 3)
    assert rig.apply(comp, rig.OCT_TOP, 12) and s.octaves == 4
    # One key at a time: the lowest note goes down a semitone, the top gains one key.
    assert rig.apply(comp, rig.OCT_BOTTOM, 1) and s.low_note == 35
    assert rig.apply(comp, rig.OCT_TOP, 2) and (s.octaves, s.extra_keys) == (4, 3)
    assert sub("board").dimensions(s)[0] == 4 * 12 + 3 + 1
    assert rig.apply(comp, rig.OCT_TOP, -3) and (s.octaves, s.extra_keys) == (4, 0)
    # The handles sit outside the board: right edge, above the keys, below the keys.
    rows, width, top = sub("board").dimensions(s)
    assert rig.handle_point(comp, rig.LENGTH)[0] == width
    assert rig.handle_point(comp, rig.OCT_TOP)[1] == top
    assert rig.handle_point(comp, rig.OCT_BOTTOM)[1] == 0
    assert rig.handle_point(comp, rig.HEAD, 1.5) == (1.5, top + rig.HEAD_LIFT)


def test_rig_gizmos_only_in_object_mode(comp):
    rig = sub("rig")
    assert rig.GP2M_GGT_rig.poll(bpy.context)
    bpy.context.view_layer.objects.active = comp
    bpy.ops.object.mode_set(mode="PAINT_GREASE_PENCIL")
    try:
        assert not rig.GP2M_GGT_rig.poll(bpy.context)
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    # A deleted composition leaves no handles behind (old rigs included).
    other = _fresh(None)
    bpy.data.objects.remove(other, do_unlink=True)
    sub("engine").cleanup_orphans()
    assert not any(rig.is_rig(obj) for obj in bpy.data.objects)


def test_layers_live_in_one_meta_clip(comp):
    """A composition is one clip in the Sequencer: a meta-clip with a strip per layer
    inside. Muting the composition mutes the meta; strips of 0.0.21 (one channel per
    layer at the top) move inside, keeping their volume."""
    engine = sub("engine")
    scene = bpy.context.scene
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60))
    engine.regenerate(comp)
    meta = engine.meta_strip(scene, comp)
    assert meta.type == "META" and engine.top_strip(scene, comp) == meta
    assert [s for s in scene.sequence_editor.strips if engine._owned(s, comp)] == [meta]
    # A 0.0.21 file: the layer strip sits at the top, with its own volume.
    strip = engine.layer_strips(scene, comp)["Livello 1"]
    path = strip.sound.filepath
    engine._remove_strip(scene.sequence_editor, meta)
    legacy = scene.sequence_editor.strips.new_sound(
        engine.strip_name(comp, "Livello 1"), path, 30, scene.frame_start)
    legacy[engine.OWNER_KEY], legacy[engine.LAYER_KEY] = comp.name, "Livello 1"
    legacy.volume = 0.4
    engine.regenerate(comp, force=True)
    meta = engine.meta_strip(scene, comp)
    inside = engine.layer_strips(scene, comp)["Livello 1"]
    assert inside.parent_meta() == meta and abs(inside.volume - 0.4) < 1e-6
    assert [s for s in scene.sequence_editor.strips if engine._owned(s, comp)] == [meta]
    comp.gp2m.mute = True
    engine.arrange(scene)
    assert meta.mute and not inside.mute
    comp.gp2m.mute = False
    engine.arrange(scene)
    assert not meta.mute
    # Back to one mix strip: the meta-clip goes away.
    comp.gp2m.layer_channels = False
    engine.regenerate(comp, force=True)
    assert engine.meta_strip(scene, comp) is None
    assert engine.top_strip(scene, comp).type == "SOUND"
    comp.gp2m.layer_channels = True


def test_rig_handle_selection_and_g(comp):
    rig = sub("rig")
    assert rig.selected() is None
    rig.select(comp.name, rig.LENGTH)
    assert rig.selected() == (comp.name, rig.LENGTH)
    assert "bl_rna" in rig.GP2M_OT_rig_grab.__dict__
    # G is bound in Object Mode (before Blender's Move), so with no handle it moves objects.
    items = [item for km, item in rig._keymaps if item.idname == "gp2m.rig_grab"]
    assert items and items[0].type == "G"
    # Idle handles are muted, not the full white of a hovered one.
    colors = sub("theme").handle_colors(bpy.context)
    assert sum(colors["idle"]) < sum(colors["hover"]) and colors["rim_idle"][3] < colors["rim"][3]
    rig.select(None, None)
    assert rig.selected() is None


# --- The Sequencer as a view of the layers ------------------------------------------------

def test_layer_mute_and_clip_mute_follow_each_other(comp):
    engine, seqsync, props = sub("engine"), sub("seqsync"), sub("props")
    scene = bpy.context.scene
    names = _two_layers(comp)
    engine.regenerate(comp)
    first = props.find_layer_settings(comp.data, names[0])
    # Muting the layer mutes its clip at once, and the clip stays after the new sound.
    first.mute = True
    assert engine.layer_strips(scene, comp)[names[0]].mute
    engine.regenerate(comp)
    strips = engine.layer_strips(scene, comp)
    assert names[0] in strips and strips[names[0]].mute and not strips[names[1]].mute
    assert not engine.regenerate(comp) is None
    # Unmuting the clip in the Sequencer unmutes the layer.
    strips[names[0]].mute = False
    assert seqsync.sync_scene(scene)
    assert not first.mute
    engine.regenerate(comp)
    assert not engine.layer_strips(scene, comp)[names[0]].mute
    # Muting the clip in the Sequencer mutes the layer.
    engine.layer_strips(scene, comp)[names[1]].mute = True
    seqsync.sync_scene(scene)
    assert props.find_layer_settings(comp.data, names[1]).mute
    props.find_layer_settings(comp.data, names[1]).mute = False


def test_moving_clips_reorders_layers_and_compositions(comp):
    engine, seqsync, board = sub("engine"), sub("seqsync"), sub("board")
    scene = bpy.context.scene
    names = _two_layers(comp)
    engine.regenerate(comp)
    strips = engine.layer_strips(scene, comp)
    low, high = strips[names[0]], strips[names[1]]
    assert low.channel < high.channel
    # Swap the two clips inside the meta-clip (park one on a free channel first).
    a, b = low.channel, high.channel
    low.channel = 20
    high.channel = a
    low.channel = b
    assert seqsync.sync_scene(scene)
    order = [layer.name for layer in board.user_layers(comp.data)]
    assert order.index(names[1]) < order.index(names[0])
    assert comp.data.layers[-1].name == board.HEAD_LAYER  # the playhead stays on top
    strips = engine.layer_strips(scene, comp)
    assert strips[names[1]].channel < strips[names[0]].channel
    assert not seqsync.sync_scene(scene)  # nothing more to do
    # The meta-clip moved to another channel: the composition takes it.
    meta = engine.meta_strip(scene, comp)
    used = {s.channel for s in scene.sequence_editor.strips}
    free = engine._block_from(1, 1, used)
    meta.channel = free
    seqsync.sync_scene(scene)
    assert comp.gp2m.channel == free and meta.channel == free


def test_clip_volume_pan_color_and_time_follow_the_sequencer(comp, tmp_path):
    engine, seqsync, props = sub("engine"), sub("seqsync"), sub("props")
    scene = bpy.context.scene
    names = _two_layers(comp)
    engine.regenerate(comp)
    item = props.find_layer_settings(comp.data, names[0])
    strip = engine.layer_strips(scene, comp)[names[0]]
    # From the layer to the clip, at once.
    item.clip_volume, item.clip_pan = 0.5, -0.4
    assert abs(strip.volume - 0.5) < 1e-5 and abs(strip.pan + 0.4) < 1e-5
    # From the clip (changed in the Sequencer) to the layer.
    strip.volume, strip.pan, strip.color_tag = 0.8, 0.3, "COLOR_07"
    assert seqsync.sync_scene(scene)
    assert abs(item.clip_volume - 0.8) < 1e-5 and abs(item.clip_pan - 0.3) < 1e-5
    assert item.color == "COLOR_07"
    # The export plays the layers as the Sequencer does.
    path = str(tmp_path / "mix.wav")
    item.clip_volume, item.clip_pan = 0.0, 0.0
    engine.export(comp, scene, path, "WAV")
    _rate, quiet = read_wav(path)
    item.clip_volume = 1.0
    engine.export(comp, scene, path, "WAV")
    _rate, loud = read_wav(path)
    assert np.abs(loud.astype(np.int64)).sum() > np.abs(quiet.astype(np.int64)).sum() > 0
    # Moving the meta-clip later: the composition starts later.
    engine.arrange(scene)
    meta = engine.meta_strip(scene, comp)
    fps = scene.render.fps / scene.render.fps_base
    meta.content_start = meta.content_start + round(2 * fps)
    assert seqsync.sync_scene(scene)
    assert abs(comp.gp2m.start_delay - 2.0) < 0.05
    inner = engine.layer_strips(scene, comp)[names[0]]
    assert inner.content_start == scene.frame_start + engine.state(comp)["offset_frames"]
    comp.gp2m.start_delay = 0.0
    assert min(s.content_start for s in engine.layer_strips(scene, comp).values()) \
        == scene.frame_start + engine.state(comp)["offset_frames"]


def test_grid_opacity_and_layer_pan(comp):
    board = sub("board")
    s = comp.gp2m
    s.grid_opacity = 0.4
    grid = board.grid_object(comp)
    assert all(abs(layer.opacity - 0.4) < 1e-6 for layer in grid.data.layers)
    board.rebuild(comp)
    assert all(abs(layer.opacity - 0.4) < 1e-6 for layer in board.grid_object(comp).data.layers)
    # The drawing is not touched.
    assert all(layer.opacity == 1.0 for layer in board.user_layers(comp.data))
    item = sub("props").find_layer_settings(comp.data, "Livello 1")
    item.pan_percent = 0.0
    assert abs(item.clip_pan + 1.0) < 1e-6
    item.pan_percent = 100.0
    assert abs(item.clip_pan - 1.0) < 1e-6
    item.pan_percent = 50.0
    assert abs(item.clip_pan) < 1e-6


def test_meta_clip_end_changes_the_length(comp):
    engine, seqsync = sub("engine"), sub("seqsync")
    scene = bpy.context.scene
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60))
    engine.regenerate(comp)
    meta = engine.meta_strip(scene, comp)
    assert meta is not None and engine.state(comp).get("meta_span")
    fps = scene.render.fps / scene.render.fps_base
    before = comp.gp2m.length
    meta.right_handle = meta.right_handle + int(2 * fps)
    assert seqsync.sync_scene(scene)
    assert abs(comp.gp2m.length - (before + 2.0)) < 1e-3


# --- Cases in the Sequencer (cut, duplicate, rename, delete, trim, move) -------------------

def _meta_ready(comp):
    engine = sub("engine")
    names = _two_layers(comp)
    engine.regenerate(comp)
    engine.arrange(bpy.context.scene)
    return names, engine.meta_strip(bpy.context.scene, comp)


def test_cutting_a_composition_clip_is_undone(comp):
    engine, seqsync = sub("engine"), sub("seqsync")
    scene = bpy.context.scene
    names, meta = _meta_ready(comp)
    span = (meta.left_handle, meta.right_handle)
    meta.split(frame=int(meta.left_handle + 48), split_method="SOFT")
    seqsync.sync_scene(scene)
    metas = [s for s in scene.sequence_editor.strips if engine._owned(s, comp)]
    assert len(metas) == 1 and metas[0].type == "META"
    assert (metas[0].left_handle, metas[0].right_handle) == span
    assert sorted(engine.layer_strips(scene, comp)) == sorted(
        n for n in names if n in engine.layer_strips(scene, comp))
    inner = [s for s in metas[0].strips if s.type == "SOUND"]
    assert len({s[engine.LAYER_KEY] for s in inner}) == len(inner)
    assert "non si tagliano" in seqsync.MESSAGES[-1]


def test_duplicating_a_composition_clip_makes_a_new_composition(comp):
    engine, seqsync, table = sub("engine"), sub("seqsync"), sub("table")
    scene = bpy.context.scene
    names, meta = _meta_ready(comp)
    before = set(table.compositions(scene))
    # What Shift+D leaves in the Sequencer: a copy of the meta-clip, elsewhere.
    editor = scene.sequence_editor
    used = {s.channel for s in editor.strips}
    channel = engine._block_from(meta.channel + 1, 1, used)
    copy = editor.strips.new_meta(meta.name + ".001", channel, int(meta.content_start))
    copy[engine.OWNER_KEY] = comp.name
    seqsync.sync_scene(scene)
    new = set(table.compositions(scene)) - before
    assert len(new) == 1
    twin = new.pop()
    assert twin.gp2m.channel == channel and engine.top_strip(scene, twin).channel == channel
    assert [s for s in editor.strips if engine._owned(s, comp)] == [meta]
    assert len(board_layers := sub("board").user_layers(twin.data)) == len(
        sub("board").user_layers(comp.data)) and board_layers


def test_renaming_the_clip_renames_the_composition(comp):
    engine, seqsync = sub("engine"), sub("seqsync")
    scene = bpy.context.scene
    _names, meta = _meta_ready(comp)
    meta.name = "Melodia del mare"
    seqsync.sync_scene(scene)
    assert comp.name == "Melodia del mare"
    assert meta.name == engine.strip_name(comp) and meta[engine.OWNER_KEY] == comp.name
    assert all(s[engine.OWNER_KEY] == comp.name for s in engine.layer_strips(scene, comp).values())
    owned = [s for s in scene.sequence_editor.strips if engine._owned(s, comp)]
    assert owned == [meta]  # no second clip, no double sound
    engine.regenerate(comp)
    assert [s for s in scene.sequence_editor.strips if engine._owned(s, comp)] == [meta]


def test_deleting_the_clip_mutes_the_composition(comp):
    engine, seqsync = sub("engine"), sub("seqsync")
    scene = bpy.context.scene
    _names, meta = _meta_ready(comp)
    engine._remove_strip(scene.sequence_editor, meta)
    seqsync.sync_scene(scene)
    assert comp.gp2m.mute
    assert engine.regenerate(comp) is None or engine.meta_strip(scene, comp) is not None
    comp.gp2m.mute = False
    engine.regenerate(comp)
    assert engine.meta_strip(scene, comp) is not None


def test_muted_layer_and_composition_are_not_rendered(comp):
    engine, props = sub("engine"), sub("props")
    scene = bpy.context.scene
    names, _meta = _meta_ready(comp)
    sub("handlers")._dirty.clear()
    props.find_layer_settings(comp.data, names[0]).mute = True
    assert comp.name not in sub("handlers")._dirty  # nothing to render again
    assert engine.layer_strips(scene, comp)[names[0]].mute
    props.find_layer_settings(comp.data, names[0]).mute = False
    comp.gp2m.mute = True
    assert engine.regenerate(comp) is None and engine.meta_strip(scene, comp).mute
    comp.gp2m.mute = False
    assert engine.regenerate(comp) is not None


def test_trimming_the_clip(comp):
    engine, seqsync = sub("engine"), sub("seqsync")
    scene = bpy.context.scene
    _names, meta = _meta_ready(comp)
    # The start cannot be trimmed.
    left = meta.left_handle
    meta.left_handle = left + 24
    seqsync.sync_scene(scene)
    assert meta.left_handle == left
    # Following the scene, the end moves the scene's End.
    comp.gp2m.follow_scene = True
    engine.arrange(scene)
    end = scene.frame_end
    meta.right_handle = meta.right_handle - 24
    seqsync.sync_scene(scene)
    assert scene.frame_end == end - 24
    comp.gp2m.follow_scene = False


def test_moving_a_layer_clip_in_time_moves_its_strokes(comp):
    engine, seqsync, board = sub("engine"), sub("seqsync"), sub("board")
    scene = bpy.context.scene
    names, _meta = _meta_ready(comp)
    layer = comp.data.layers[names[1]]
    xs = lambda: [p.position[0] for p in layer.frames[0].drawing.strokes[0].points]  # noqa
    before = xs()
    strip = engine.layer_strips(scene, comp)[names[1]]
    fps = scene.render.fps / scene.render.fps_base
    strip.content_start = strip.content_start + round(fps)  # one second later
    assert seqsync.sync_scene(scene)
    assert np.allclose(np.array(xs()) - np.array(before), comp.gp2m.seconds_width, atol=1e-3)
    other = engine.layer_strips(scene, comp)[names[0]]
    assert strip.content_start == other.content_start  # the clip is back in line
    assert board.user_layers(comp.data)  # still there


def test_a_layer_clip_pasted_in_another_composition_moves_the_layer(comp):
    engine, seqsync, board = sub("engine"), sub("seqsync"), sub("board")
    scene = bpy.context.scene
    names, _meta = _meta_ready(comp)
    other = _fresh(None)
    add_stroke(other, 0, line(other, 1.0, 2.0, 62))
    engine.regenerate(other)
    engine.arrange(scene)
    strokes = len(comp.data.layers[names[1]].frames[0].drawing.strokes)
    theirs = {l.name for l in board.user_layers(other.data)}
    source = engine.layer_strips(scene, comp)[names[1]]
    target = engine.meta_strip(scene, other)
    pasted = target.strips.new_sound(source.name + ".001", source.sound.filepath, 5,
                                     int(source.content_start))
    pasted[engine.OWNER_KEY], pasted[engine.LAYER_KEY] = comp.name, names[1]
    seqsync.sync_scene(scene)
    assert comp.data.layers.get(names[1]) is None
    moved = [l for l in board.user_layers(other.data) if l.name not in theirs]
    assert len(moved) == 1 and len(moved[0].frames[0].drawing.strokes) == strokes
    assert pasted.name not in [s.name for s in target.strips]
    result = engine.regenerate(other)
    assert 67 in {round(n.pitch) for n in result.notes}  # it still plays its note


def test_a_locked_clip_is_left_alone(comp):
    engine, seqsync = sub("engine"), sub("seqsync")
    scene = bpy.context.scene
    _names, meta = _meta_ready(comp)
    meta.lock = True
    channel = meta.channel
    comp.gp2m.start_delay = 1.0
    engine.arrange(scene)
    assert meta.channel == channel
    meta.name = "Bloccata"
    assert not seqsync.sync_scene(scene)
    assert comp.name != "Bloccata"
    meta.lock = False
    meta.name = engine.strip_name(comp)
    comp.gp2m.start_delay = 0.0


def test_undo_brings_back_clip_and_layer_together(addon):
    engine, seqsync, props = sub("engine"), sub("seqsync"), sub("props")
    scene = bpy.context.scene
    comp = _fresh(None)
    name = comp.name
    names, _meta = _meta_ready(comp)
    bpy.ops.ed.undo_push(message="prima")
    engine.layer_strips(scene, comp)[names[0]].volume = 0.5
    seqsync.sync_scene(scene)
    assert props.find_layer_settings(comp.data, names[0]).clip_volume == pytest.approx(0.5)
    bpy.ops.ed.undo_push(message="volume nel Sequencer")
    assert bpy.ops.ed.undo() == {"FINISHED"}
    scene = bpy.context.scene
    comp = bpy.data.objects[name]
    strip = engine.layer_strips(scene, comp)[names[0]]
    item = props.find_layer_settings(comp.data, names[0])
    assert strip.volume == pytest.approx(1.0) and item.clip_volume == pytest.approx(1.0)
    seqsync.sync_scene(scene)
    assert item.clip_volume == pytest.approx(1.0)


def _grouped(comp):
    """Two compositions with their meta-clips grouped as Ctrl+G does."""
    engine, seqsync = sub("engine"), sub("seqsync")
    scene = bpy.context.scene
    _names, meta = _meta_ready(comp)
    other = _fresh(None)
    add_stroke(other, 0, line(other, 0.5, 2.0, 64), radius=0.05)
    engine.regenerate(other)
    engine.arrange(scene)
    editor = scene.sequence_editor
    used = {s.channel for s in editor.strips}
    group = editor.strips.new_meta("MetaStrip", engine._block_from(1, 1, used),
                                   int(meta.left_handle))
    meta.move_to_meta(group)
    engine.meta_strip(scene, other).move_to_meta(group)
    seqsync.sync_scene(scene)
    return other, group


def test_grouping_compositions_in_the_sequencer(comp):
    engine, board = sub("engine"), sub("board")
    scene = bpy.context.scene
    other, group = _grouped(comp)
    assert engine.is_group_meta(group) and group.name.startswith("Gruppo")
    key = group[engine.GROUP_KEY]
    assert comp[engine.GROUP_KEY] == key and other[engine.GROUP_KEY] == key
    # Apart on the table: two compositions with their own layers.
    assert comp.data != other.data and board.user_layers(comp.data)
    # A new sound stays in the group, the group spans its clips.
    engine.regenerate(comp, force=True)
    engine.regenerate(other, force=True)
    metas = [engine.meta_strip(scene, comp), engine.meta_strip(scene, other)]
    assert all(m.parent_meta() == group for m in metas)
    assert group.left_handle <= min(m.left_handle for m in metas)
    assert group.right_handle >= max(m.right_handle for m in metas)
    assert not [s for s in scene.sequence_editor.strips if engine._owned(s, comp)]


def test_a_group_is_a_bus(comp):
    engine, seqsync, props = sub("engine"), sub("seqsync"), sub("props")
    scene = bpy.context.scene
    other, group = _grouped(comp)
    group[engine.BUS_VOLUME] = 0.5
    group[engine.BUS_PAN] = 0.4
    seqsync.sync_scene(scene)
    for obj in (comp, other):
        for name, strip in engine.layer_strips(scene, obj).items():
            item = props.find_layer_settings(obj.data, name)
            assert item.clip_volume == pytest.approx(1.0)  # the layer keeps its own
            assert strip.volume == pytest.approx(0.5)
            assert strip.pan == pytest.approx(min(1.0, item.clip_pan + 0.4))
    # The volume set on the meta-clip itself becomes the group's.
    group.volume = 0.5
    seqsync.sync_scene(scene)
    assert group.volume == 1.0 and group[engine.BUS_VOLUME] == pytest.approx(0.25)
    strip = next(iter(engine.layer_strips(scene, comp).values()))
    assert strip.volume == pytest.approx(0.25)
    # Exports too.
    result, _reads = engine.render_composition(comp, scene, stems=True)
    loud = np.abs(engine._clip_mix(comp, result)).max()
    quiet = np.abs(engine._clip_mix(comp, result, scene)).max()
    assert quiet < loud * 0.5
    # A muted group: its compositions are not rendered until it is heard again.
    group.mute = True
    assert engine.regenerate(comp) is None and engine.state(comp).get("muted_stale")
    group.mute = False
    seqsync.sync_scene(scene)
    assert not engine.state(comp).get("muted_stale")


def test_separating_groups(comp):
    engine, seqsync = sub("engine"), sub("seqsync")
    scene = bpy.context.scene
    other, group = _grouped(comp)
    editor = scene.sequence_editor
    # A group in a group; Alt+G on the inner one takes its compositions out.
    used = {s.channel for s in editor.strips}
    outer = editor.strips.new_meta("MetaStrip", engine._block_from(1, 1, used),
                                   int(group.left_handle))
    group.move_to_meta(outer)
    seqsync.sync_scene(scene)
    assert engine.is_group_meta(outer)
    for obj in (comp, other):
        engine.meta_strip(scene, obj).move_to_meta(outer)
    outer.strips.remove(group)
    seqsync.sync_scene(scene)
    assert comp[engine.GROUP_KEY] == outer[engine.GROUP_KEY] == other[engine.GROUP_KEY]
    # Alt+G on a composition's own clip is undone: its layers stay inside it.
    meta = engine.meta_strip(scene, comp)
    for strip in list(meta.strips):
        strip.move_to_meta(outer)
    outer.strips.remove(meta)
    seqsync.sync_scene(scene)
    meta = engine.meta_strip(scene, comp)
    assert meta is not None and meta.parent_meta() == outer
    assert all(s.parent_meta() == meta for s in engine.layer_strips(scene, comp).values())
    assert "non si separa" in seqsync.MESSAGES[-1]


def _layer_group(comp):
    """Ctrl+G on the clips of the first two layers, inside the composition's clip."""
    engine, seqsync = sub("engine"), sub("seqsync")
    scene = bpy.context.scene
    names, meta = _meta_ready(comp)
    strips = engine.layer_strips(scene, comp)
    group_meta = meta.strips.new_meta("MetaStrip", 9, int(meta.left_handle))
    for name in names[:2]:
        strips[name].move_to_meta(group_meta)
    seqsync.sync_scene(scene)
    return names, meta, group_meta


def test_grouping_layer_clips_makes_a_group_of_layers(comp):
    engine, board = sub("engine"), sub("board")
    scene = bpy.context.scene
    names, meta, group_meta = _layer_group(comp)
    gp = comp.data
    name = group_meta[engine.LAYER_GROUP_KEY]
    group = gp.layer_groups.get(name)
    assert group is not None and not board.is_board_group(group)
    assert sorted(child.name for child in group.children) == sorted(names[:2])
    assert engine.meta_strip(scene, comp) == meta  # still one composition
    strips = engine.layer_strips(scene, comp)
    assert all(strips[n].parent_meta().name == group_meta.name for n in names[:2])
    assert group_meta.parent_meta().name == meta.name
    # A new sound keeps the group's clip, with its layers inside.
    engine.regenerate(comp, force=True)
    metas = engine.layer_group_metas(engine.meta_strip(scene, comp))
    assert list(metas) == [name]
    strips = engine.layer_strips(scene, comp)
    assert all(strips[n].parent_meta().name == metas[name].name for n in names[:2])
    # A group made on the board is a meta-clip too.
    assert len(engine.meta_sounds(engine.meta_strip(scene, comp))) == len(strips)


def test_a_group_of_layers_is_a_bus(comp):
    engine, seqsync, props = sub("engine"), sub("seqsync"), sub("props")
    scene = bpy.context.scene
    names, meta, group_meta = _layer_group(comp)
    engine.arrange(scene)
    name = group_meta[engine.LAYER_GROUP_KEY]
    item = props.find_layer_settings(comp.data, name)
    item.clip_volume = 0.5
    strips = engine.layer_strips(scene, comp)
    for n in names[:2]:
        own = props.find_layer_settings(comp.data, n).clip_volume
        assert strips[n].volume == pytest.approx(own * 0.5)
    seqsync.sync_scene(scene)  # not read back as a change of the layers
    assert props.find_layer_settings(comp.data, names[0]).clip_volume == pytest.approx(1.0)
    # The volume set on the group's clip becomes the group's.
    group_meta = engine.layer_group_metas(engine.meta_strip(scene, comp))[name]
    group_meta.volume = 0.5
    seqsync.sync_scene(scene)
    assert item.clip_volume == pytest.approx(0.25) and group_meta.volume == 1.0
    # Muting the group's clip mutes the group (and the other way round).
    group_meta.mute = True
    seqsync.sync_scene(scene)
    assert item.mute
    item.mute = False
    group_meta = engine.layer_group_metas(engine.meta_strip(scene, comp))[name]
    assert not group_meta.mute


def test_separating_a_group_of_layers(comp):
    engine, seqsync = sub("engine"), sub("seqsync")
    scene = bpy.context.scene
    names, meta, group_meta = _layer_group(comp)
    engine.arrange(scene)
    name = group_meta[engine.LAYER_GROUP_KEY]
    meta = engine.meta_strip(scene, comp)
    group_meta = engine.layer_group_metas(meta)[name]
    # Alt+G: the layers' clips come out, the group's clip is gone.
    for strip in list(group_meta.strips):
        strip.move_to_meta(meta)
    meta.strips.remove(group_meta)
    seqsync.sync_scene(scene)
    gp = comp.data
    assert gp.layer_groups.get(name) is None
    assert all(gp.layers[n].parent_group is None for n in names[:2])
    assert "sciolto" in seqsync.MESSAGES[-1]


def test_deleting_a_group_clip_mutes_the_group(comp):
    engine, seqsync, props = sub("engine"), sub("seqsync"), sub("props")
    scene = bpy.context.scene
    names, meta, group_meta = _layer_group(comp)
    engine.arrange(scene)
    name = group_meta[engine.LAYER_GROUP_KEY]
    meta = engine.meta_strip(scene, comp)
    engine._remove_strip(scene.sequence_editor, engine.layer_group_metas(meta)[name])
    seqsync.sync_scene(scene)
    item = props.find_layer_settings(comp.data, name)
    assert item.mute and comp.data.layer_groups.get(name) is not None
    item.mute = False
    engine.regenerate(comp)
    assert name in engine.layer_group_metas(engine.meta_strip(scene, comp))


def test_reordering_clips_inside_a_group_of_layers(comp):
    engine, seqsync = sub("engine"), sub("seqsync")
    scene = bpy.context.scene
    names, meta, group_meta = _layer_group(comp)
    engine.arrange(scene)
    name = group_meta[engine.LAYER_GROUP_KEY]
    group = comp.data.layer_groups[name]
    before = [child.name for child in group.children]
    strips = engine.layer_strips(scene, comp)
    low, high = strips[before[0]], strips[before[1]]
    low.channel, high.channel = 5, 6
    high.channel = 1
    low.channel = 2
    seqsync.sync_scene(scene)
    assert [child.name for child in group.children] == before[::-1]


def test_undo_brings_back_a_group(addon):
    engine, seqsync = sub("engine"), sub("seqsync")
    scene = bpy.context.scene
    comp = _fresh(addon)
    bpy.ops.ed.undo_push(message="before")
    other, group = _grouped(comp)
    key = group[engine.GROUP_KEY]
    name = comp.name
    bpy.ops.ed.undo_push(message="grouped")
    bpy.ops.ed.undo()
    comp = bpy.data.objects[name]
    scene = bpy.context.scene
    assert comp.get(engine.GROUP_KEY) is None
    assert engine.find_group(scene.sequence_editor, key) is None
    bpy.ops.ed.redo()
    comp = bpy.data.objects[name]
    scene = bpy.context.scene
    seqsync.sync_scene(scene)
    assert comp.get(engine.GROUP_KEY) == key
    assert engine.meta_strip(scene, comp).parent_meta()[engine.GROUP_KEY] == key
