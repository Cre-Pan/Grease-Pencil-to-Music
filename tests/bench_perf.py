# SPDX-License-Identifier: GPL-3.0-or-later
"""Performance benchmark (not part of the test suite).

    python -m pytest tests/bench_perf.py -s -q

Builds a composition with 3 layers and 45 strokes (synth and recorded instruments,
layer effects, master bus) and times what the user waits for: the first render, an
Auto update while drawing on the active layer, a full update, the depsgraph handler,
the panels' draw and the loading of the recorded instruments. Prints one table.
"""

import gc
import os
import statistics
import sys
import time
import tracemalloc

import bpy
import numpy as np
import pytest

from test_blender import MODULE, add_stroke, line, sub  # noqa: F401  (fixtures below)
from test_blender import addon, comp  # noqa: F401

RESULTS = {}
RECORDED = ("S_PIANO", "S_CELLO", "S_FLUTE", "S_TAIKO")


def _timed(fn, repeat=1):
    times = []
    for _ in range(repeat):
        gc.collect()
        began = time.perf_counter()
        fn()
        times.append(time.perf_counter() - began)
    return statistics.median(times)


def _clear_caches():
    mixer, synth, effects = sub("mixer"), sub("synth"), sub("effects")
    mixer.clear_cache()
    for ident in list(synth.SAMPLES):
        if ident in synth.RECORDINGS:
            del synth.SAMPLES[ident]
    for name in ("_SPECTRA", "_ROOMS", "_IR_CACHE"):
        if isinstance(getattr(effects, name, None), dict):
            getattr(effects, name).clear()


def _populate(obj):
    rng = np.random.default_rng(7)
    slots = [slot.material for slot in obj.material_slots
             if not sub("board").is_board_material(slot.material)]
    for material, ident in zip(slots[-len(RECORDED):], RECORDED):
        material.gp2m_instrument = ident
    for layer in range(3):
        for k in range(15):
            x0 = float(rng.uniform(0.0, 7.0))
            midi = int(rng.integers(52, 80))
            add_stroke(obj, layer, line(obj, x0, x0 + float(rng.uniform(0.2, 1.2)), midi, 30),
                       radius=float(rng.uniform(0.01, 0.04)),
                       material_index=obj.material_slots.find(slots[(layer * 7 + k) % len(slots)].name))
    settings = sub("props").find_layer_settings(obj.data, "Livello 1")
    settings.use_reverb, settings.use_echo = True, True


def _dump_or_compare(engine, obj, scene):
    """GP2M_DUMP=file saves the rendered audio; GP2M_COMPARE=file checks it is the same."""
    dump, compare = os.environ.get("GP2M_DUMP"), os.environ.get("GP2M_COMPARE")
    if not (dump or compare):
        return
    arrays = {}
    for loop in (True, False):
        obj.gp2m.loop = loop
        result, _reads = engine.render_composition(obj, scene, stems=True)
        arrays[f"mix_{loop}"] = result.audio
        for name, audio in result.stems:
            arrays[f"stem_{loop}_{name}"] = audio
    obj.gp2m.loop = True
    if dump:
        np.savez(dump, **arrays)
        return
    reference = np.load(compare)
    assert sorted(reference.files) == sorted(arrays)
    for key in reference.files:
        diff = float(np.max(np.abs(reference[key] - arrays[key])))
        RESULTS[f"Differenza max {key}"] = diff
    print({k: v for k, v in RESULTS.items() if k.startswith("Differenza")})
    assert max(v for k, v in RESULTS.items() if k.startswith("Differenza")) < 1e-5


class _Layout:
    def __getattr__(self, _name):
        return self._any

    def _any(self, *_args, **_kwargs):
        return self

    def template_list(self, list_id, _name, data, propname, active_data, active_prop, **_kw):
        ui_list = getattr(bpy.types, list_id)
        fake = type("FakeList", (), {"bitflag_filter_item": 1 << 30, "filter_name": "",
                                     "use_filter_invert": False})()
        flags, _order = ui_list.filter_items(fake, bpy.context, data, propname)
        for item, flag in zip(getattr(data, propname), flags):
            if flag:
                ui_list.draw_item(fake, bpy.context, _Layout(), data, item, 0, active_data,
                                  active_prop)


class _Panel:
    def __init__(self):
        self.layout = _Layout()


def _draw_panels():
    ui = sub("ui")
    for panel in ui.classes:
        if issubclass(panel, bpy.types.Panel) and getattr(panel, "bl_context", "") != "material":
            if hasattr(panel, "poll") and not panel.poll(bpy.context):
                continue
            panel.draw(_Panel(), bpy.context)
            if hasattr(panel, "draw_header"):
                panel.draw_header(_Panel(), bpy.context)


class _Update:
    def __init__(self, id_, geometry=False):
        self.id = id_
        self.is_updated_geometry = geometry
        self.is_updated_shading = False
        self.is_updated_transform = False


class _Depsgraph:
    def __init__(self, updates):
        self.updates = updates


def test_benchmark(comp):
    handlers, engine, synth = sub("handlers"), sub("engine"), sub("synth")
    scene = bpy.context.scene
    comp.gp2m.auto_update = False  # the benchmark drives every update itself
    _populate(comp)
    comp.gp2m.auto_update = True

    _clear_caches()
    _dump_or_compare(engine, comp, scene)
    _clear_caches()
    RESULTS["Primo calcolo (cache vuote) s"] = _timed(lambda: engine.regenerate(comp, scene))
    RESULTS["Rigenera forzato (cache piene) s"] = _timed(
        lambda: engine.regenerate(comp, scene, force=True), 5)

    counter = iter(range(1000))

    def draw_one_stroke():
        k = next(counter)
        add_stroke(comp, 0, line(comp, 0.1 * (k % 60), 0.1 * (k % 60) + 0.5, 60 + k % 12, 30))
        handlers.mark_dirty(comp, strokes_only=True)
        handlers.flush()

    comp.gp2m.auto_active_layer = True
    RESULTS["Auto, un tratto (solo livello attivo) s"] = _timed(draw_one_stroke, 7)
    comp.gp2m.auto_active_layer = False
    RESULTS["Auto, un tratto (tutti i livelli) s"] = _timed(draw_one_stroke, 7)
    comp.gp2m.auto_active_layer = True

    def no_change():
        handlers.mark_dirty(comp)
        handlers.flush()
    RESULTS["Auto senza cambiamenti s"] = _timed(no_change, 7)

    gp_updates = _Depsgraph([_Update(comp.data), _Update(comp, geometry=True)])
    scene_updates = _Depsgraph([_Update(scene)])

    def depsgraph_burst():
        for _ in range(200):
            handlers.on_depsgraph_update(scene, gp_updates)
            handlers.on_depsgraph_update(scene, scene_updates)
            handlers._layer_sync_tick()
    RESULTS["Handler depsgraph, 200 aggiornamenti ms"] = 1000 * _timed(depsgraph_burst, 3)
    handlers._dirty.clear()
    handlers._full.clear()

    RESULTS["Disegno pannelli, 20 volte ms"] = 1000 * _timed(
        lambda: [_draw_panels() for _ in range(20)], 3)

    def load_recorded():
        for ident in RECORDED:
            synth.SAMPLES.pop(ident, None)
        mixer = sub("mixer")
        mixer.clear_cache()
        engine.regenerate(comp, scene, force=True)
    RESULTS["Rigenera con strumenti registrati da leggere s"] = _timed(load_recorded, 3)

    def one_note_each():
        for ident in synth.RECORDINGS:
            synth.SAMPLES.pop(ident, None)
        sub("mixer").clear_cache()
        voice_pitch = 60.0
        for ident in synth.RECORDINGS:
            zones = synth.recorded_zones(ident)
            zone = synth.pick_zone(zones, voice_pitch)
            getattr(synth, "zone_ready", lambda z: z)(zone)  # 0.0.15: read with the zones
    RESULTS["Prima nota di ogni strumento registrato s"] = _timed(one_note_each, 1)
    tracemalloc.start()
    one_note_each()
    RESULTS["Memoria dopo una nota di ognuno MB"] = tracemalloc.get_traced_memory()[0] / 2**20
    tracemalloc.stop()

    if os.environ.get("GP2M_PROFILE"):
        import cProfile, pstats
        for label, fn in (("cold", lambda: (_clear_caches(), engine.regenerate(comp, scene, force=True))),
                          ("active", draw_one_stroke), ("nochange", no_change),
                          ("force", lambda: engine.regenerate(comp, scene, force=True)),
                          ("depsgraph", depsgraph_burst), ("ui", _draw_panels)):
            comp.gp2m.auto_active_layer = True
            prof = cProfile.Profile()
            prof.enable()
            for _ in range(3):
                fn()
            prof.disable()
            print("=====", label)
            pstats.Stats(prof).sort_stats(os.environ.get("GP2M_SORT", "cumulative")).print_stats(35)
    print()
    for name, value in RESULTS.items():
        print(f"{name:55s} {value:10.3f}")
    print(f"python {sys.version.split()[0]}, blender {bpy.app.version_string}")
