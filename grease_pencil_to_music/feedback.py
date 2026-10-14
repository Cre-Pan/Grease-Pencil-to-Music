# SPDX-License-Identifier: GPL-3.0-or-later
"""Show the volume of each instrument on its strokes (visual only).

* THICKNESS: a Thickness modifier per instrument ("GP2M Volume <material>")
  multiplies the stroke radius by the volume; the strokes themselves are not
  changed, and the reader divides the factor back out when it reads modifiers.
* OPACITY: the material color alpha follows the volume.
"""


from . import board, prefs

MODIFIER_PREFIX = "GP2M Volume "


def is_feedback_modifier(modifier):
    return modifier.name.startswith(MODIFIER_PREFIX)


def user_modifiers(obj):
    return [m for m in obj.modifiers if not is_feedback_modifier(m)]


def radius_divisors(obj):
    """{material slot index: factor} of the active volume modifiers."""
    result = {}
    names = [m.name if m else "" for m in obj.data.materials]
    for modifier in obj.modifiers:
        if not is_feedback_modifier(modifier) or not modifier.show_viewport:
            continue
        material = modifier.material_filter
        if material is not None and material.name in names:
            result[names.index(material.name)] = max(modifier.thickness_factor, 1e-3)
    return result


def _set_alpha(color, alpha):
    if abs(color[3] - alpha) > 1e-4:
        color[3] = alpha
        return True
    return False


def sync(obj):
    """Bring modifiers and material alphas in line with the volumes (writes only changes)."""
    mode = prefs.feedback_mode()
    wanted = {}
    for material in obj.data.materials:
        if material is None or board.is_board_material(material) or material.grease_pencil is None:
            continue
        volume = float(material.gp2m_volume)
        style = material.grease_pencil
        alpha = min(max(volume, 0.08), 1.0) if mode == "OPACITY" else 1.0
        _set_alpha(style.color, alpha)
        _set_alpha(style.fill_color, 0.45 * alpha)
        if mode == "THICKNESS" and abs(volume - 1.0) > 1e-3:
            wanted[MODIFIER_PREFIX + material.name] = (material, max(volume, 0.05))

    for modifier in [m for m in obj.modifiers if is_feedback_modifier(m)]:
        if modifier.name not in wanted:
            obj.modifiers.remove(modifier)
    for name, (material, factor) in wanted.items():
        modifier = obj.modifiers.get(name)
        if modifier is None:
            modifier = obj.modifiers.new(name, "GREASE_PENCIL_THICKNESS")
            modifier.material_filter = material
            modifier.show_expanded = False
        if abs(modifier.thickness_factor - factor) > 1e-4:
            modifier.thickness_factor = factor
    board.protect_board(obj)


def sync_material(material):
    from . import handlers
    for obj in handlers.compositions():
        if any(slot.material == material for slot in obj.material_slots):
            sync(obj)
