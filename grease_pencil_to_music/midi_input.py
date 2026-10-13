# SPDX-License-Identifier: GPL-3.0-or-later
"""MIDI keyboards (input) through the bundled ``rtmidi2`` wheel.

The port is polled from the main thread (a window timer in the keyboard
operator): no callback thread ever touches Blender data.
"""

NOTE_OFF, NOTE_ON, CONTROL = 0x80, 0x90, 0xB0
SUSTAIN = 64

_module = [None]


class MidiInputError(RuntimeError):
    pass


def rtmidi():
    """The ``rtmidi2`` module, or None when the wheel is not installed."""
    if _module[0] is None:
        try:
            import rtmidi2
            _module[0] = rtmidi2
        except Exception:
            _module[0] = False
    return _module[0] or None


def port_names():
    module = rtmidi()
    if module is None:
        return []
    try:
        return [str(name) for name in module.get_in_ports()]
    except Exception:  # no MIDI backend (e.g. no ALSA sequencer)
        return []


def decode(message):
    """``("on", note, velocity)``, ``("off", note, 0)``, ``("sustain", 0, value)`` or None."""
    if not message or len(message) < 3:
        return None
    kind, data1, data2 = message[0] & 0xF0, int(message[1]), int(message[2])
    if kind == NOTE_ON and data2 > 0:
        return ("on", data1, data2)
    if kind == NOTE_OFF or kind == NOTE_ON:
        return ("off", data1, 0)
    if kind == CONTROL and data1 == SUSTAIN:
        return ("sustain", 0, data2)
    return None


class Input:
    """An open MIDI input port."""

    def __init__(self, pattern=""):
        module = rtmidi()
        if module is None:
            raise MidiInputError("modulo rtmidi2 non disponibile")
        try:
            self.midi = module.MidiIn()
        except Exception as error:
            raise MidiInputError(f"MIDI non disponibile: {error}") from error
        ports = [str(name) for name in self.midi.ports]
        if not ports:
            raise MidiInputError("nessuna tastiera MIDI collegata")
        try:
            self.midi.open_port(pattern.strip() or 0)
        except Exception as error:
            raise MidiInputError(f"porta MIDI «{pattern}» non trovata") from error
        matches = [p for p in ports if pattern.strip() and p.startswith(pattern.strip())]
        self.name = matches[0] if matches else ports[0] if not pattern.strip() else pattern

    def events(self, limit=256):
        """Decoded events waiting in the queue (non-blocking)."""
        out = []
        for _ in range(limit):
            try:
                message = self.midi.get_message()
            except Exception:
                break
            if message is None:
                break
            event = decode(message)
            if event is not None:
                out.append(event)
        return out

    def close(self):
        try:
            self.midi.close_port()
        except Exception:
            pass
