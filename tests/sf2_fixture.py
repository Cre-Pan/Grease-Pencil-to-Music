# SPDX-License-Identifier: GPL-3.0-or-later
"""Tiny valid SoundFont 2 and SFZ files for the tests."""

import struct
import wave

import numpy as np


def _chunk(cid, payload):
    pad = b"\0" if len(payload) & 1 else b""
    return cid + struct.pack("<I", len(payload)) + payload + pad


def _list(kind, *chunks):
    return _chunk(b"LIST", kind + b"".join(chunks))


def write_sf2(path, rate=22050, freq=440.0, root=69):
    period = rate / freq
    length = int(round(period * 200))
    smpl = (np.sin(2 * np.pi * np.arange(length) / period) * 20000).astype("<i2").tobytes()
    smpl += b"\0" * 92  # 46 zero samples after each sample, as the spec asks
    loop_start, loop_end = int(round(period * 20)), int(round(period * 180))
    phdr = (struct.pack("<20sHHHIII", b"Sine Test", 5, 0, 0, 0, 0, 0)
            + struct.pack("<20sHHHIII", b"EOP", 0, 0, 1, 0, 0, 0))
    pbag = struct.pack("<HH", 0, 0) + struct.pack("<HH", 1, 0)
    pmod = b"\0" * 10
    pgen = struct.pack("<Hh", 41, 0) + struct.pack("<Hh", 0, 0)
    inst = struct.pack("<20sH", b"Sine", 0) + struct.pack("<20sH", b"EOI", 1)
    ibag = struct.pack("<HH", 0, 0) + struct.pack("<HH", 4, 0)
    imod = b"\0" * 10
    igen = (struct.pack("<HBB", 43, 0, 127) + struct.pack("<Hh", 54, 1)
            + struct.pack("<Hh", 58, root) + struct.pack("<Hh", 53, 0)
            + struct.pack("<Hh", 0, 0))
    shdr = (struct.pack("<20sIIIIIBbHH", b"A4", 0, length, loop_start, loop_end, rate, root, 0,
                        0, 1)
            + struct.pack("<20sIIIIIBbHH", b"EOS", 0, 0, 0, 0, 0, 0, 0, 0, 0))
    body = (b"sfbk"
            + _list(b"INFO", _chunk(b"ifil", struct.pack("<HH", 2, 1)),
                    _chunk(b"INAM", b"Test\0\0"))
            + _list(b"sdta", _chunk(b"smpl", smpl))
            + _list(b"pdta", _chunk(b"phdr", phdr), _chunk(b"pbag", pbag), _chunk(b"pmod", pmod),
                    _chunk(b"pgen", pgen), _chunk(b"inst", inst), _chunk(b"ibag", ibag),
                    _chunk(b"imod", imod), _chunk(b"igen", igen), _chunk(b"shdr", shdr)))
    with open(path, "wb") as handle:
        handle.write(b"RIFF" + struct.pack("<I", len(body)) + body)


def write_wav(path, freq, rate=22050, seconds=1.0):
    data = (np.sin(2 * np.pi * freq * np.arange(int(rate * seconds)) / rate) * 20000)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(data.astype("<i2").tobytes())


def read_wav(path):
    with wave.open(str(path)) as handle:
        rate = handle.getframerate()
        data = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2")
    return data.astype(np.float32) / 32768.0, float(rate)


def write_sfz(folder):
    """Two regions: A3 for the low keys, A4 for the high keys."""
    write_wav(folder / "a3.wav", 220.0)
    write_wav(folder / "a4.wav", 440.0)
    (folder / "test.sfz").write_text(
        "// test instrument\n<control> default_path=\n<group> loop_mode=no_loop volume=0\n"
        "<region> sample=a3.wav lokey=c2 hikey=b3 pitch_keycenter=a3\n"
        "<region> sample=a4.wav lokey=c4 hikey=127 pitch_keycenter=69\n", encoding="utf-8")
    return folder / "test.sfz"
