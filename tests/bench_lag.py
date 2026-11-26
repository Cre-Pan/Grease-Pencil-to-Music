# SPDX-License-Identifier: GPL-3.0-or-later
"""Micro-lag benchmark (not part of the test suite).

    python -m pytest tests/bench_lag.py -s -q

Times what runs on every depsgraph update while you draw, edit or sculpt (the
handler and the timers it starts), and what a change of volume, pan or opacity
costs once the pause is over. Prints one table; ``GP2M_PROFILE=1`` also prints
the top functions of each case.
"""

import cProfile
import io
import os
import pstats
import statistics
import time

import bpy
import pytest

from test_blender import add_stroke, line, sub
from test_blender import addon, comp  # noqa: F401  (fixtures)

RESULTS = []
PROFILE = bool(os.environ.get("GP2M_PROFILE"))


def _run_timers():
    handlers = sub("handlers")
    for timer in (handlers._layer_sync_tick, handlers._shade_tick):
        if bpy.app.timers.is_registered(timer):
            bpy.app.timers.unregister(timer)
            timer()


def _measure(label, fn, repeat=30):
    times = []
    profiler = cProfile.Profile() if PROFILE else None
    for _ in range(repeat):
        began = time.perf_counter()
        if profiler:
            profiler.enable()
        fn()
        if profiler:
            profiler.disable()
        times.append(time.perf_counter() - began)
    RESULTS.append((label, statistics.median(times) * 1000.0, max(times) * 1000.0))
    if profiler:
        out = io.StringIO()
        pstats.Stats(profiler, stream=out).sort_stats("cumulative").print_stats(18)
        print(f"\n=== {label}\n{out.getvalue()}")


@pytest.fixture
def busy(comp):
    """A composition with 3 layers, 30 strokes."""
    for layer in range(3):
        for k in range(10):
            add_stroke(comp, layer, line(comp, 0.2 + 0.35 * k, 0.5 + 0.35 * k, 48 + 3 * k + layer),
                       material_index=layer % 3)
    sub("engine").regenerate(comp, force=True)
    bpy.context.view_layer.update()
    _run_timers()
    handlers = sub("handlers")
    handlers._dirty.clear()
    handlers._full.clear()
    return comp


def _nudge(comp, layer_index=0):
    layer = sub("board").user_layers(comp.data)[layer_index]
    drawing = layer.frames[0].drawing
    stroke = drawing.strokes[0]
    point = stroke.points[0]
    x, y, z = point.position
    point.position = (x, y, z + 1e-4)
    drawing.tag_positions_changed()


def test_lag(busy):
    comp = busy
    handlers = sub("handlers")
    engine = sub("engine")

    def stroke_update():  # one depsgraph update of a sculpt / edit step
        _nudge(comp)
        bpy.context.view_layer.update()
        _run_timers()
    _measure("aggiornamento depsgraph (tratto)", stroke_update, 60)

    seqsync = sub("seqsync")
    _measure("sync del Sequencer (ogni update della scena)",
             lambda: seqsync.sync_scene(bpy.context.scene), 30)
    seen = []

    def spy(_scene, depsgraph):
        seen.extend(type(u.id.original).__name__ for u in depsgraph.updates)
    bpy.app.handlers.depsgraph_update_post.append(spy)
    stroke_update()
    bpy.app.handlers.depsgraph_update_post.remove(spy)
    print("\nID aggiornati da un tratto:", sorted(set(seen)))

    def frame_change():
        scene = bpy.context.scene
        scene.frame_set(scene.frame_current + 1)
        _run_timers()
    _measure("cambio fotogramma", frame_change, 30)

    def regen_same():  # e.g. a selection in Edit Mode: nothing to hear changed
        handlers.mark_dirty(comp, strokes_only=True)
        handlers.flush()
    regen_same()
    _measure("rigenera senza cambi (selezione)", regen_same, 20)

    def regen_active():
        _nudge(comp)
        handlers.mark_dirty(comp, strokes_only=True)
        handlers.flush()
    comp.gp2m.auto_active_layer = True
    handlers._dirty.clear()
    handlers._full.clear()
    _measure("rigenera dopo tratto (solo attivo)", regen_active, 10)
    comp.gp2m.auto_active_layer = False

    main_thread = []

    def regen_split():  # the background render: only prepare and apply hold Blender
        _nudge(comp)
        began = time.perf_counter()
        job = engine.prepare(comp)
        middle = time.perf_counter()
        engine.run(job)
        after = time.perf_counter()
        engine.apply(job)
        main_thread.append((middle - began) + (time.perf_counter() - after))
    _measure("rigenera in sottofondo (totale)", regen_split, 10)
    RESULTS.append(("  di cui nel thread di Blender", statistics.median(main_thread) * 1000,
                    max(main_thread) * 1000))

    def regen_full():
        _nudge(comp)
        handlers.mark_dirty(comp, strokes_only=True)
        handlers.flush()
    _measure("rigenera dopo tratto (tutto)", regen_full, 10)

    items = [item for item in comp.data.gp2m_layers if not item.is_group]
    step = [0]

    def change(setter):
        """A slider dragged: a new value every time (nothing found in the caches)."""
        def run():
            step[0] += 1
            setter(step[0])
            bpy.context.view_layer.update()
            _run_timers()
            handlers.flush()
        return run

    _measure("volume clip", change(lambda i: setattr(items[0], "clip_volume",
                                                     0.5 + 0.01 * (i % 50))), 10)
    _measure("pan clip", change(lambda i: setattr(items[0], "clip_pan",
                                                  -0.5 + 0.01 * (i % 50))), 10)
    layer = sub("board").user_layers(comp.data)[0]
    _measure("opacità livello", change(lambda i: setattr(layer, "opacity",
                                                         0.4 + 0.01 * (i % 50))), 10)
    material = comp.material_slots[0].material
    _measure("volume strumento", change(lambda i: setattr(material, "gp2m_volume",
                                                          0.4 + 0.01 * (i % 50))), 10)
    _measure("volume master", change(lambda i: setattr(comp.gp2m, "master_volume",
                                                       0.4 + 0.01 * (i % 50))), 10)
    _measure("muto livello", change(lambda i: setattr(items[1], "mute", bool(i % 2))), 10)
    _measure("colore materiale", change(lambda i: setattr(
        material.grease_pencil, "color", (0.01 * (i % 50), 0.2, 0.3, 1.0))), 10)
    print("\n{:<40} {:>10} {:>10}".format("caso", "mediana ms", "max ms"))
    for label, median, worst in RESULTS:
        print(f"{label:<40} {median:>10.2f} {worst:>10.2f}")
