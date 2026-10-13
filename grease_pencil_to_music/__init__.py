# SPDX-License-Identifier: GPL-3.0-or-later
"""Grease Pencil to Music.

Draw on a musical board with Grease Pencil and hear it: X is time, Z is pitch,
the material is the instrument; thickness, opacity and vertex color shape the
sound. Inspired by the drawn sound of Norman McLaren and Daphne Oram.
"""

import bpy

from . import handlers, operators, prefs, props, ui

_classes = props.classes + prefs.classes + operators.classes + ui.classes


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    props.register_properties()
    ui.register()
    handlers.register()


def unregister():
    handlers.unregister()
    ui.unregister()
    props.unregister_properties()
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
