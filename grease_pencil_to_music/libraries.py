# SPDX-License-Identifier: GPL-3.0-or-later
"""Sampled instrument libraries: SoundFont 2 (.sf2) and SFZ (.sfz).

Both become a list of :class:`synth.Zone` (one sample per key range, with its
root key and loop points), played by the "Libreria" instrument.

Free libraries that work well: GeneralUser GS and FluidR3 (SF2), the CC0
Versilian Community Sample Library (SFZ).

Pure Python + NumPy: no ``bpy`` import (SFZ sample files are read through a
``read_audio(path) -> (mono float array, rate)`` callback).
"""

import os
import re
import struct

import numpy as np

from .synth import Zone


class LibraryError(ValueError):
    pass


# --- SoundFont 2 ----------------------------------------------------------------------

GEN_START_OFFSET, GEN_END_OFFSET = 0, 1
GEN_LOOP_START_OFFSET, GEN_LOOP_END_OFFSET = 2, 3
GEN_START_COARSE, GEN_END_COARSE = 4, 12
GEN_INSTRUMENT, GEN_KEY_RANGE, GEN_VEL_RANGE = 41, 43, 44
GEN_LOOP_START_COARSE, GEN_ATTENUATION, GEN_LOOP_END_COARSE = 45, 48, 50
GEN_COARSE_TUNE, GEN_FINE_TUNE, GEN_SAMPLE_ID, GEN_SAMPLE_MODES = 51, 52, 53, 54
GEN_ROOT_KEY = 58
RANGE_GENERATORS = (GEN_KEY_RANGE, GEN_VEL_RANGE)


def _chunks(data, start, end):
    """Yield (id, payload_start, payload_end) of RIFF sub-chunks."""
    pos = start
    while pos + 8 <= end:
        cid = data[pos:pos + 4]
        size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
        yield cid, pos + 8, pos + 8 + size
        pos += 8 + size + (size & 1)


class SoundFont:
    """Parsed SF2 file: presets and the generators needed to build zones."""

    def __init__(self, data):
        if data[:4] != b"RIFF" or data[8:12] != b"sfbk":
            raise LibraryError("non è un SoundFont 2 (.sf2)")
        self.samples = None
        self.records = {}
        for cid, a, b in _chunks(data, 12, len(data)):
            if cid != b"LIST":
                continue
            kind = data[a:a + 4]
            for sub, sa, sb in _chunks(data, a + 4, b):
                if kind == b"sdta" and sub == b"smpl":
                    self.samples = np.frombuffer(data[sa:sb], dtype="<i2")
                elif kind == b"pdta":
                    self.records[sub.decode("ascii", "replace")] = data[sa:sb]
        if self.samples is None or "phdr" not in self.records:
            raise LibraryError("SoundFont incompleto")
        self.presets = self._read("phdr", "<20sHHHIII")
        self.pbags = self._read("pbag", "<HH")
        self.pgens = self.records["pgen"]
        self.instruments = self._read("inst", "<20sH")
        self.ibags = self._read("ibag", "<HH")
        self.igens = self.records["igen"]
        self.headers = self._read("shdr", "<20sIIIIIBbHH")

    def _read(self, name, fmt):
        size = struct.calcsize(fmt)
        raw = self.records.get(name, b"")
        return [struct.unpack(fmt, raw[i:i + size]) for i in range(0, len(raw) - size + 1, size)]

    @staticmethod
    def _gens(raw, first, last):
        gens = {}
        for i in range(first, last):
            oper = struct.unpack("<H", raw[i * 4:i * 4 + 2])[0]
            if oper in RANGE_GENERATORS:
                gens[oper] = (raw[i * 4 + 2], raw[i * 4 + 3])
            else:
                gens[oper] = struct.unpack("<h", raw[i * 4 + 2:i * 4 + 4])[0]
        return gens

    def preset_list(self):
        """``[(index, bank, program, name)]`` without the terminal record."""
        out = []
        for index, (name, program, bank, *_rest) in enumerate(self.presets[:-1]):
            out.append((index, bank, program, name.split(b"\0")[0].decode("latin-1").strip()))
        return sorted(out, key=lambda p: (p[1], p[2]))

    def _zones(self, bags, raw_gens, first_bag, last_bag, key):
        """Generator dicts of the zones of a preset/instrument, global zone merged in."""
        zones, global_gens = [], {}
        for bag in range(first_bag, last_bag):
            gens = self._gens(raw_gens, bags[bag][0], bags[bag + 1][0])
            if key not in gens:
                if bag == first_bag:
                    global_gens = gens
                continue
            zones.append({**global_gens, **gens})
        return zones

    def zones(self, preset_index):
        """Zones of a preset: one per key range, the velocity layer for ~100 preferred."""
        if not 0 <= preset_index < len(self.presets) - 1:
            raise LibraryError("preset inesistente")
        first, last = self.presets[preset_index][3], self.presets[preset_index + 1][3]
        result, seen = [], set()
        for pzone in self._zones(self.pbags, self.pgens, first, last, GEN_INSTRUMENT):
            plo, phi = pzone.get(GEN_KEY_RANGE, (0, 127))
            inst = pzone[GEN_INSTRUMENT]
            if not 0 <= inst < len(self.instruments) - 1:
                continue
            ifirst, ilast = self.instruments[inst][1], self.instruments[inst + 1][1]
            candidates = self._zones(self.ibags, self.igens, ifirst, ilast, GEN_SAMPLE_ID)
            candidates.sort(key=lambda z: 0 if z.get(GEN_VEL_RANGE, (0, 127))[0] <= 100
                            <= z.get(GEN_VEL_RANGE, (0, 127))[1] else 1)
            for izone in candidates:
                lo, hi = izone.get(GEN_KEY_RANGE, (0, 127))
                lo, hi = max(lo, plo), min(hi, phi)
                if lo > hi or (lo, hi) in seen:
                    continue
                zone = self._zone(izone, pzone, lo, hi)
                if zone is not None:
                    seen.add((lo, hi))
                    result.append(zone)
        return result

    def _zone(self, gens, pgens, lo, hi):
        sid = gens[GEN_SAMPLE_ID]
        if not 0 <= sid < len(self.headers) - 1:
            return None
        _name, start, end, loop_start, loop_end, rate, original, correction, _l, kind = \
            self.headers[sid]
        if kind & 0x8000:  # ROM sample
            return None
        start += gens.get(GEN_START_OFFSET, 0) + 32768 * gens.get(GEN_START_COARSE, 0)
        end += gens.get(GEN_END_OFFSET, 0) + 32768 * gens.get(GEN_END_COARSE, 0)
        loop_start += gens.get(GEN_LOOP_START_OFFSET, 0) + 32768 * gens.get(
            GEN_LOOP_START_COARSE, 0)
        loop_end += gens.get(GEN_LOOP_END_OFFSET, 0) + 32768 * gens.get(GEN_LOOP_END_COARSE, 0)
        start, end = max(start, 0), min(end, len(self.samples))
        if end - start < 8:
            return None
        root = gens.get(GEN_ROOT_KEY, -1)
        root = original if root < 0 else root
        tune = (gens.get(GEN_COARSE_TUNE, 0) + pgens.get(GEN_COARSE_TUNE, 0)
                + (gens.get(GEN_FINE_TUNE, 0) + pgens.get(GEN_FINE_TUNE, 0)
                   + correction) / 100.0)
        attenuation = (gens.get(GEN_ATTENUATION, 0) + pgens.get(GEN_ATTENUATION, 0)) / 10.0
        data = self.samples[start:end].astype(np.float32) / 32768.0
        loop = gens.get(GEN_SAMPLE_MODES, 0) in (1, 3) and start < loop_start < loop_end <= end
        return Zone(data=data, rate=float(rate), root=float(root) - tune, lo=lo, hi=hi,
                    loop=bool(loop), loop_start=loop_start - start if loop else 0,
                    loop_end=loop_end - start if loop else len(data),
                    gain=float(10 ** (-attenuation / 20.0)))


def read_sf2(path):
    with open(path, "rb") as handle:
        return SoundFont(handle.read())


# --- SFZ -----------------------------------------------------------------------------

_NOTE_OFFSETS = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}


def sfz_key(value):
    """SFZ key: a MIDI number or a note name (c4 = 60, c#4, db4)."""
    value = value.strip().lower()
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    match = re.fullmatch(r"([a-g])([#b]?)(-?\d+)", value)
    if not match:
        raise LibraryError(f"nota SFZ non valida: {value}")
    letter, accidental, octave = match.groups()
    shift = 1 if accidental == "#" else -1 if accidental == "b" else 0
    return (int(octave) + 1) * 12 + _NOTE_OFFSETS[letter] + shift


def parse_sfz(text):
    """Regions of an SFZ file as opcode dicts (inheritance already applied)."""
    text = re.sub(r"//[^\n]*", "", text)
    levels = {"control": {}, "global": {}, "master": {}, "group": {}}
    order = ("control", "global", "master", "group")
    regions, current, target = [], None, None
    for token in re.split(r"(<\w+>)", text):
        header = re.fullmatch(r"<(\w+)>", token.strip())
        if header:
            name = header.group(1)
            if current is not None:
                regions.append(current)
                current = None
            if name in levels:
                for level in order[order.index(name):]:
                    levels[level] = {} if level != name else {}
                target = name
            elif name == "region":
                current = {}
                target = "region"
            else:
                target = None
            continue
        if target is None:
            continue
        for key, value in re.findall(r"(\w+)=(.*?)(?=\s+\w+=|$)", token.strip(), re.S):
            value = value.strip()
            if target == "region":
                current[key] = value
            else:
                levels[target][key] = value
        if target == "region":
            merged = {}
            for level in order:
                merged.update(levels[level])
            merged.update(current)
            current = merged
    if current is not None:
        regions.append(current)
    return regions


def sfz_zones(path, read_audio):
    """Zones of an SFZ instrument; ``read_audio(path) -> (mono float array, rate)``."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        regions = parse_sfz(handle.read())
    base = os.path.dirname(path)
    zones, seen, cache = [], set(), {}
    regions.sort(key=lambda r: 0 if int(r.get("lovel", 1)) <= 100 <= int(r.get("hivel", 127))
                 else 1)
    for region in regions:
        sample = region.get("sample")
        if not sample:
            continue
        if "key" in region:
            lo = hi = root = sfz_key(region["key"])
        else:
            lo = sfz_key(region.get("lokey", "0"))
            hi = sfz_key(region.get("hikey", "127"))
            root = sfz_key(region.get("pitch_keycenter", str(lo if lo == hi else 60)))
        if (lo, hi) in seen:
            continue
        file = os.path.join(base, region.get("default_path", ""),
                            sample.replace("\\", os.sep))
        if file not in cache:
            try:
                cache[file] = read_audio(file)
            except Exception:
                cache[file] = None
        if cache[file] is None:
            continue
        data, rate = cache[file]
        offset = int(region.get("offset", 0))
        end = int(region.get("end", len(data) - 1)) + 1
        data = np.asarray(data[offset:end], dtype=np.float32)
        mode = region.get("loop_mode", "no_loop")
        loop = mode in ("loop_continuous", "loop_sustain") and "loop_end" in region
        tune = float(region.get("tune", 0)) / 100.0 + float(region.get("transpose", 0))
        zones.append(Zone(
            data=data, rate=float(rate), root=float(root) - tune, lo=lo, hi=hi, loop=loop,
            loop_start=max(int(region.get("loop_start", 0)) - offset, 0) if loop else 0,
            loop_end=min(int(region.get("loop_end", len(data))) - offset + 1, len(data))
            if loop else len(data),
            gain=float(10 ** (float(region.get("volume", 0)) / 20.0))))
        seen.add((lo, hi))
    if not zones:
        raise LibraryError("nessuna regione SFZ leggibile")
    return zones
