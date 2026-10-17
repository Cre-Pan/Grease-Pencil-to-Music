# SPDX-License-Identifier: GPL-3.0-or-later
"""Doodle Music.

Draw on a musical board with Grease Pencil and hear it: X is time, Z is pitch,
the material is the instrument; thickness, opacity and vertex color shape the
sound. Inspired by the drawn sound of Norman McLaren and Daphne Oram.
"""

import bpy

from . import (handlers, keyboard, midi_import, midi_input,  # noqa: F401
               operators, prefs, props, timeline, ui)

_classes = (props.classes + prefs.classes + operators.classes + midi_import.classes
            + keyboard.classes + timeline.classes + ui.classes)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    props.register_properties()
    ui.register()
    midi_import.register()
    handlers.register()
    timeline.register()


def unregister():
    timeline.unregister()
    handlers.unregister()
    midi_import.unregister()
    ui.unregister()
    props.unregister_properties()
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
