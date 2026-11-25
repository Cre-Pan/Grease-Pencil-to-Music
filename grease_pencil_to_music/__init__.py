# SPDX-License-Identifier: GPL-3.0-or-later
"""Doodle Music.

Draw on a musical board with Grease Pencil and hear it: X is time, Z is pitch,
the material is the instrument; thickness, opacity and vertex color shape the
sound. Inspired by the drawn sound of Norman McLaren and Daphne Oram.
"""

import bpy

from . import (draw_sound, handlers, help, icons, keyboard, midi_import, midi_input,  # noqa: F401
               operators, prefs, props, rig, samples, table, theme, timeline, ui, web_io)

_classes = (props.classes + prefs.classes + help.classes + operators.classes + midi_import.classes
            + keyboard.classes + timeline.classes + rig.classes + table.classes + ui.classes
            + web_io.classes)


def register():
    icons.load()  # first: the instrument lists show them
    props.build_instrument_items()
    for cls in _classes:
        bpy.utils.register_class(cls)
    samples.register()
    props.register_properties()
    ui.register()
    table.register()
    midi_import.register()
    web_io.register()
    handlers.register()
    timeline.register()
    draw_sound.register()
    theme.register()
    rig.register_keymap()


def unregister():
    rig.unregister_keymap()
    theme.unregister()
    draw_sound.unregister()
    timeline.unregister()
    handlers.unregister()
    web_io.unregister()
    midi_import.unregister()
    table.unregister()
    ui.unregister()
    props.unregister_properties()
    samples.unregister()
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
    icons.free()
