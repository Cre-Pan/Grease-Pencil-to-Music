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


def add_stroke(obj, layer_index, points, radius=0.02, material_index=0):
    """``points``: (x, z) pairs in board coordinates."""
    layer = obj.data.layers[layer_index]
    drawing = layer.frames[0].drawing
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


def test_add_composition_builds_the_board(comp):
    s = comp.gp2m
    assert s.is_composition and comp.name.startswith("Composizione Musicale")
    assert [layer.name for layer in comp.data.layers] == ["Livello 1", "Livello 2", "Livello 3"]
    instruments = [slot.material.gp2m_instrument for slot in comp.material_slots]
    assert len(instruments) == 8 and "PLUCK" in instruments
    roles = sorted(child.get("gp2m_role") for child in comp.children)
    assert roles.count("board") == 1 and roles.count("playhead") == 1
    labels = sorted(c.data.body for c in comp.children if c.get("gp2m_role") == "label")
    assert {"C3", "C4", "C5", "C6", "0s", "8s"} <= set(labels)
    # Empty composition: a silent strip already exists and the scene loops 8 s.
    scene = bpy.context.scene
    strip = sub("engine").find_strip(scene, comp)
    assert strip is not None and os.path.exists(bpy.path.abspath(strip.sound.filepath))
    fps = scene.render.fps / scene.render.fps_base
    assert scene.frame_end - scene.frame_start + 1 == round(8 * fps)


def test_playhead_follows_time(comp):
    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    scene.frame_set(scene.frame_start + int(fps))  # one second later
    assert comp.gp2m.playhead.location.x == pytest.approx(comp.gp2m.seconds_width, abs=1e-4)
    scene.frame_set(scene.frame_start)


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
    comp.data.layers[0].hide = True
    assert [n.pitch for n in engine.regenerate(comp).notes] == [64]


def test_modifiers_are_ignored_and_reported(comp):
    engine, reader = sub("engine"), sub("reader")
    add_stroke(comp, 0, line(comp, 1.0, 2.0, 60))
    before = engine.regenerate(comp).key
    comp.modifiers.new("Noise", "GREASE_PENCIL_NOISE")
    assert reader.has_unsupported_stack(comp)
    assert engine.regenerate(comp).key == before


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
    comp.gp2m.length = 4.0
    comp.gp2m.octaves = 2
    board._rebuild_pending()  # normally run by a timer
    labels = sorted(c.data.body for c in comp.children if c.get("gp2m_role") == "label")
    assert "4s" in labels and "5s" not in labels
    assert "C5" in labels and "C6" not in labels
    assert sub("engine").regenerate(comp).audio.shape[0] == 4 * 44100


class MockLayout:
    """Stand-in for ``bpy.types.UILayout`` that validates what panels draw."""

    def __init__(self, log):
        self.log = log

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)

    def _child(self, *_args, **_kwargs):
        return MockLayout(self.log)

    row = column = box = split = grid_flow = _child

    def label(self, **_kwargs):
        pass

    def separator(self, **_kwargs):
        pass

    def menu(self, menu_id, **_kwargs):
        assert hasattr(bpy.types, menu_id), menu_id
        self.log.append(("menu", menu_id))

    def prop(self, data, attr, **_kwargs):
        target = getattr(data, "_target", data)
        assert attr in target.bl_rna.properties, f"{type(target).__name__}.{attr}"
        self.log.append(("prop", attr))

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
        if issubclass(panel, bpy.types.Panel):
            assert panel.poll(bpy.context) if hasattr(panel, "poll") else True
            panel.draw(_Drawer(log), bpy.context)
    ui.VIEW3D_MT_gp2m_add.draw(_Drawer(log), bpy.context)
    ui.draw_add_menu(_Drawer(log), bpy.context)
    preferences = bpy.context.preferences.addons[MODULE].preferences
    type(preferences).draw(_Drawer(log, preferences), bpy.context)
    drawn = {entry[1] for entry in log}
    assert {"gp2m_instrument", "mode", "reverb_mix", "map_thickness",
            "gp2m.export", "VIEW3D_MT_gp2m_add"} <= drawn


def test_deleting_a_composition_removes_its_sound(addon):
    engine = sub("engine")
    assert bpy.ops.gp2m.add_composition() == {"FINISHED"}
    obj = bpy.context.view_layer.objects.active
    name = obj.name
    scene = bpy.context.scene
    assert engine.find_strip(scene, obj) is not None
    children = [child.name for child in obj.children]
    bpy.data.objects.remove(obj, do_unlink=True)
    engine.cleanup_orphans()
    assert scene.sequence_editor.strips.get(engine.STRIP_PREFIX + name) is None
    assert not any(bpy.data.objects.get(child) for child in children)
