# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthesized instruments, rendered with NumPy.

Every instrument receives a :class:`interpret.Voice` (pitch, volume, vibrato,
brightness and pan curves) and returns a stereo float32 buffer.

Pure Python + NumPy: no ``bpy`` import.
"""

from dataclasses import dataclass

import numpy as np

from . import music
from .interpret import CONTROL_RATE, NOISE_BAND


@dataclass(frozen=True)
class Instrument:
    ident: str
    label: str
    description: str
    color: tuple  # RGBA used for the Grease Pencil material
    gm_program: int  # General MIDI program (0-based); -1 = drum channel
    release: float  # seconds of fade after the stroke ends
    gain: float
    percussive: bool = False  # one hit with its own decay, whatever the stroke length
    length: float = 0.0  # seconds of a percussive hit
    drum_note: int = 0  # General MIDI drum note; 0 = the row pitch


INSTRUMENTS = (
    Instrument("SINE", "Flauto", "Sinusoide morbida con un filo di armoniche",
               (0.45, 0.78, 1.0, 1.0), 73, 0.06, 0.55),
    Instrument("TRIANGLE", "Ocarina", "Onda triangolare, dolce e rotonda",
               (0.35, 1.0, 0.8, 1.0), 79, 0.06, 0.55),
    Instrument("SQUARE", "8-bit", "Onda quadra da console anni '80",
               (0.4, 1.0, 0.3, 1.0), 80, 0.03, 0.22),
    Instrument("SAW", "Synth", "Dente di sega brillante",
               (1.0, 0.55, 0.15, 1.0), 81, 0.08, 0.3),
    Instrument("STRINGS", "Archi", "Tre seghe leggermente stonate, attacco lento e vibrato",
               (1.0, 0.3, 0.4, 1.0), 48, 0.2, 0.32),
    Instrument("PLUCK", "Chitarra", "Corda pizzicata (Karplus-Strong)",
               (1.0, 0.85, 0.25, 1.0), 24, 0.25, 0.8),
    Instrument("BELL", "Campana", "Sintesi FM inarmonica",
               (0.72, 0.5, 1.0, 1.0), 14, 1.2, 0.45),
    Instrument("DRUM", "Percussioni", "Rumore filtrato: grave = cassa, acuto = charleston",
               (0.85, 0.85, 0.85, 1.0), -1, 0.0, 0.7, True, 0.5),
    Instrument("KICK", "Cassa", "Cassa: colpo grave con discesa di altezza",
               (0.62, 0.38, 0.32, 1.0), -1, 0.0, 0.9, True, 0.5, 36),
    Instrument("SNARE", "Rullante", "Rullante: corpo + cordiera di rumore",
               (0.95, 0.93, 0.78, 1.0), -1, 0.0, 0.6, True, 0.35, 38),
    Instrument("HIHAT", "Charleston", "Charleston chiuso: rumore acuto e corto",
               (0.92, 0.86, 0.5, 1.0), -1, 0.0, 0.35, True, 0.15, 42),
    Instrument("CRASH", "Piatto", "Piatto crash: rumore brillante che si spegne lentamente",
               (1.0, 0.96, 0.45, 1.0), -1, 0.0, 0.3, True, 1.6, 49),
    Instrument("CLAP", "Battimani", "Battimani: tre schiocchi ravvicinati",
               (1.0, 0.6, 0.75, 1.0), -1, 0.0, 0.55, True, 0.35, 39),
    Instrument("TOM", "Tom", "Tom intonato sulla riga (più in alto = più acuto)",
               (0.78, 0.52, 0.35, 1.0), -1, 0.0, 0.8, True, 0.6, -1),
    Instrument("COWBELL", "Campanaccio", "Campanaccio metallico",
               (0.86, 0.7, 0.22, 1.0), -1, 0.0, 0.35, True, 0.4, 56),
    Instrument("SAMPLE", "Campione", "Un suono di Blender (importato o del Sequencer), "
               "intonato sulle righe", (0.55, 0.9, 0.95, 1.0), 0, 0.08, 0.8),
    Instrument("LIBRARY", "Libreria", "Strumento campionato da un SoundFont (.sf2) o .sfz: "
               "pianoforti, archi, chitarre…", (0.95, 0.75, 0.55, 1.0), 0, 0.15, 0.9),
)
INSTRUMENT_BY_ID = {inst.ident: inst for inst in INSTRUMENTS}
DEFAULT_INSTRUMENT = "SINE"
NOISE_INSTRUMENT = Instrument(NOISE_BAND, "Banda di rumore", "Cluster di rumore",
                              (0.8, 0.8, 0.8, 1.0), -1, 0.06, 0.5)
TOM_NOTES = (41, 43, 45, 47, 48, 50)


SAMPLE_PREFIX = "SAMPLE:"
LIBRARY_PREFIX = "LIBRARY:"
SAMPLES = {}  # key -> list of Zone


@dataclass
class Zone:
    """One sample of a (multi)sampled instrument."""

    data: np.ndarray  # mono float32
    rate: float
    root: float  # MIDI pitch at which the sample plays unchanged
    lo: int = 0  # key range
    hi: int = 127
    loop: bool = False
    loop_start: int = 0  # samples, inside data
    loop_end: int = 0
    gain: float = 1.0


def register_sample(key, data, rate, root, loop):
    """A single sound over the whole keyboard (the "Campione" instrument)."""
    data = np.asarray(data, dtype=np.float32)
    SAMPLES[key] = [Zone(data, float(rate), float(root), 0, 127, bool(loop), 0, len(data))]


def register_zones(key, zones):
    """A multisampled instrument (the "Libreria" instrument: SF2 / SFZ)."""
    SAMPLES[key] = list(zones)


def pick_zone(zones, pitch):
    inside = [z for z in zones if z.lo <= pitch <= z.hi]
    pool = inside or zones
    return min(pool, key=lambda z: abs(z.root - pitch))


def get_instrument(ident):
    if ident == NOISE_BAND:
        return NOISE_INSTRUMENT
    if ident.startswith(SAMPLE_PREFIX):
        return INSTRUMENT_BY_ID["SAMPLE"]
    if ident.startswith(LIBRARY_PREFIX):
        return INSTRUMENT_BY_ID["LIBRARY"]
    return INSTRUMENT_BY_ID.get(ident, INSTRUMENT_BY_ID[DEFAULT_INSTRUMENT])


def midi_drum_note(ident, pitch):
    """General MIDI note for a percussion hit (row pitch for generic drums)."""
    inst = get_instrument(ident)
    if inst.drum_note > 0:
        return inst.drum_note
    if inst.drum_note < 0:  # toms: low rows = floor tom, high rows = high tom
        return TOM_NOTES[int(min(max((pitch - 36) // 8, 0), len(TOM_NOTES) - 1))]
    return int(pitch)


# --- Building blocks ---------------------------------------------------------

def _rng(voice):
    seed = int(abs(voice.start) * 1000.0) * 131 + int(abs(float(voice.pitch[0])) * 97)
    return np.random.default_rng(seed)


def _lowpass(signal, sample_rate, cutoff):
    """Gentle (4th order magnitude) lowpass in the frequency domain."""
    if cutoff >= sample_rate / 2:
        return signal
    spectrum = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(len(signal), 1.0 / sample_rate)
    spectrum *= 1.0 / (1.0 + (freqs / max(cutoff, 1.0)) ** 4)
    return np.fft.irfft(spectrum, n=len(signal))


def _poly_blep(t, dt):
    """Band-limited step correction for naive sawtooth/square waves."""
    out = np.zeros_like(t)
    low = t < dt
    x = t[low] / dt[low]
    out[low] = x + x - x * x - 1.0
    high = t > 1.0 - dt
    x = (t[high] - 1.0) / dt[high]
    out[high] = x * x + x + x + 1.0
    return out


def _saw(phase, freq, sample_rate):
    t = (phase / (2 * np.pi)) % 1.0
    dt = np.clip(freq / sample_rate, 1e-6, 0.5)
    return 2.0 * t - 1.0 - _poly_blep(t, dt)


def _karplus_strong(n, sample_rate, freq, brightness, rng):
    period = max(2, int(round(sample_rate / max(freq, 20.0))))
    noise = rng.uniform(-1.0, 1.0, period)
    soft = np.convolve(noise, np.ones(4) / 4, mode="same")
    noise = brightness * noise + (1.0 - brightness) * soft
    # A triangular "pluck" shape keeps the fundamental strong; noise adds the attack.
    shape = 1.0 - 2.0 * np.abs(2.0 * np.arange(period) / period - 1.0)
    excitation = 0.8 * shape + 0.5 * noise
    out = np.zeros(n)
    out[:min(period, n)] = excitation[:min(period, n)]
    decay = 0.996
    # y[i] = decay * (y[i-P] + y[i-P-1]) / 2, computed one period at a time:
    # every sample of a block only depends on samples of earlier blocks.
    for k in range(period, n, period):
        m = min(period, n - k)
        a = out[k - period:k - period + m]
        start_b = k - period - 1
        if start_b < 0:
            b = np.concatenate(([0.0], out[0:m - 1]))
        else:
            b = out[start_b:start_b + m]
        out[k:k + m] = decay * 0.5 * (a + b)
    return out


def _drum(n, sample_rate, pitch, rng):
    t = np.arange(n) / sample_rate
    center = float(music.midi_to_freq(pitch)) * 2.0
    noise = rng.uniform(-1.0, 1.0, n)
    spectrum = np.fft.rfft(noise)
    freqs = np.maximum(np.fft.rfftfreq(n, 1.0 / sample_rate), 1.0)
    spectrum *= np.exp(-(np.log2(freqs / center) ** 2) / 2.0)
    shaped = np.fft.irfft(spectrum, n=n)
    shaped /= max(np.max(np.abs(shaped)), 1e-9)
    tau = 0.04 + 0.16 * np.clip((84 - pitch) / 48.0, 0.0, 1.0)
    body = shaped * np.exp(-t / tau)
    # Low notes get a pitched "kick" thump.
    kick_weight = float(np.clip((60 - pitch) / 24.0, 0.0, 1.0))
    if kick_weight > 0:
        f0 = float(music.midi_to_freq(pitch))
        kick_freq = f0 * (1.0 + 2.0 * np.exp(-t / 0.03))
        kick = np.sin(2 * np.pi * np.cumsum(kick_freq) / sample_rate) * np.exp(-t / 0.18)
        body = body * (1.0 - 0.5 * kick_weight) + kick * kick_weight
    return body


def _shape(signal, sample_rate, gain_fn):
    """Multiply the spectrum by ``gain_fn(frequencies)``."""
    spectrum = np.fft.rfft(signal)
    freqs = np.maximum(np.fft.rfftfreq(len(signal), 1.0 / sample_rate), 1.0)
    return np.fft.irfft(spectrum * gain_fn(freqs), n=len(signal))


def _highpass(signal, sample_rate, cutoff):
    return _shape(signal, sample_rate, lambda f: (f / cutoff) ** 4 / (1.0 + (f / cutoff) ** 4))


def _bandpass(signal, sample_rate, center, octaves=1.0):
    return _shape(signal, sample_rate,
                  lambda f: np.exp(-(np.log2(f / center) ** 2) / (2.0 * octaves ** 2)))


def _normalize(signal):
    return signal / max(float(np.max(np.abs(signal))), 1e-9)


def _percussion(ident, n, sample_rate, pitch, rng):
    t = np.arange(n) / sample_rate
    tune = 2.0 ** ((pitch - 60.0) / 24.0)  # higher rows = slightly higher drums
    noise = rng.uniform(-1.0, 1.0, n)
    if ident == "KICK":
        freq = 55.0 * tune * (1.0 + 2.5 * np.exp(-t / 0.04))
        body = np.sin(2 * np.pi * np.cumsum(freq) / sample_rate) * np.exp(-t / 0.28)
        return _normalize(body + 0.3 * noise * np.exp(-t / 0.003))
    if ident == "SNARE":
        tone = np.sin(2 * np.pi * 190.0 * tune * t) * np.exp(-t / 0.07)
        rattle = _normalize(_highpass(noise, sample_rate, 1500.0)) * np.exp(-t / 0.12)
        return _normalize(0.6 * tone + rattle)
    if ident == "HIHAT":
        return _normalize(_highpass(noise, sample_rate, 7000.0 * tune)) * np.exp(-t / 0.035)
    if ident == "CRASH":
        bright = _normalize(_highpass(noise, sample_rate, 3500.0 * tune))
        return bright * np.exp(-t / 0.9)
    if ident == "CLAP":
        band = _normalize(_bandpass(noise, sample_rate, 1500.0 * tune))
        envelope = 0.8 * np.exp(-np.maximum(t - 0.03, 0.0) / 0.14) * (t >= 0.03)
        for hit in (0.0, 0.011, 0.022):
            envelope += np.exp(-np.maximum(t - hit, 0.0) / 0.006) * (t >= hit)
        return _normalize(band * envelope)
    if ident == "TOM":
        freq = float(music.midi_to_freq(pitch - 12)) * (1.0 + 0.5 * np.exp(-t / 0.05))
        body = np.sin(2 * np.pi * np.cumsum(freq) / sample_rate) * np.exp(-t / 0.3)
        return _normalize(body + 0.1 * noise * np.exp(-t / 0.01))
    if ident == "COWBELL":
        phase = 2 * np.pi * t
        metal = np.sign(np.sin(phase * 540.0 * tune)) + np.sign(np.sin(phase * 800.0 * tune))
        metal = _bandpass(metal, sample_rate, 800.0 * tune, 0.8)
        envelope = 0.6 * np.exp(-t / 0.25) + 0.4 * np.exp(-t / 0.02)
        return _normalize(metal) * envelope
    return _drum(n, sample_rate, pitch, rng)


def _noise_band(n, sample_rate, low_hz, high_hz, rng, frame=2048, hop=512):
    """Noise whose spectrum is limited, frame by frame, to [low_hz, high_hz]
    (both arrays of length ``n``). Overlap-add of random-phase frames."""
    count = n // hop + 2
    centers = np.minimum(np.arange(count) * hop, n - 1)
    low = low_hz[centers][:, None]
    high = high_hz[centers][:, None]
    freqs = np.fft.rfftfreq(frame, 1.0 / sample_rate)[None, :]
    band = ((freqs >= low) & (freqs <= high)).astype(np.float64)
    bins = np.maximum(band.sum(axis=1, keepdims=True), 1.0)
    spectrum = band / np.sqrt(bins) * np.exp(1j * rng.uniform(0, 2 * np.pi, band.shape))
    frames = np.fft.irfft(spectrum, n=frame, axis=1) * np.hanning(frame)[None, :]
    out = np.zeros(count * hop + frame)
    for k in range(count):
        out[k * hop:k * hop + frame] += frames[k]
    out = out[frame // 2:frame // 2 + n]
    return out / max(float(np.sqrt(np.mean(out ** 2))), 1e-9) * 0.25


def _sample(ident, freq, sample_rate):
    """Play the registered zone closest to the pitch, following ``freq`` (resampling)."""
    key = ident.split(":", 1)[1] if ":" in ident else ident
    zones = SAMPLES.get(key)
    if not zones:
        return np.zeros(len(freq))
    pitch = 69.0 + 12.0 * np.log2(max(float(np.median(freq)), 1e-6) / 440.0)
    zone = pick_zone(zones, pitch)
    data = zone.data
    if len(data) < 2:
        return np.zeros(len(freq))
    ratio = freq / float(music.midi_to_freq(zone.root)) * (zone.rate / sample_rate)
    position = np.concatenate(([0.0], np.cumsum(ratio[:-1])))
    if zone.loop and zone.loop_end - zone.loop_start > 2:
        span = zone.loop_end - zone.loop_start
        past = position >= zone.loop_end
        position = np.where(past, zone.loop_start + (position - zone.loop_start) % span, position)
    inside = position < len(data) - 1
    return np.interp(position, np.arange(len(data)), data) * inside * zone.gain


# --- Voice rendering ---------------------------------------------------------

GLIDE_HOLD = ("PLUCK", "BELL")  # struck / plucked: the sound dies before the line ends
GLIDE_HOLD_MIN = 0.2  # seconds: shorter voices are just notes


def _glide_hold(phase, ts, sample_rate, brightness):
    """A soft sustained tone under a plucked or struck sound read optically (or
    legato): it rises after the attack and carries the glide on, so the pitch
    keeps moving with the line after the pluck has faded."""
    tone = (2.0 / np.pi) * np.arcsin(np.sin(phase)) + 0.25 * np.sin(2.0 * phase)
    tone = _lowpass(tone, sample_rate, 500.0 + brightness * 2600.0)
    return 0.3 * tone * np.clip(ts / 0.14, 0.0, 1.0)


def voice_length(voice, sample_rate):
    inst = get_instrument(voice.instrument)
    if inst.percussive:
        return int(inst.length * sample_rate)
    return max(1, int(round(voice.duration * sample_rate))) + int(inst.release * sample_rate)


def render_voice(voice, sample_rate=44100, vibrato_rate=5.5):
    """Return ``(offset_in_samples, stereo_float32_buffer)``."""
    inst = get_instrument(voice.instrument)
    n = voice_length(voice, sample_rate)
    ts = np.arange(n) / sample_rate
    ctrl_t = np.arange(len(voice.pitch)) / CONTROL_RATE

    def ctrl(curve):
        return np.interp(ts, ctrl_t, curve)

    rng = _rng(voice)
    pitch = ctrl(voice.pitch)
    vibrato = ctrl(voice.vibrato)
    if inst.ident == "STRINGS":
        vibrato = vibrato + 0.12 * np.clip((ts - 0.25) / 0.4, 0.0, 1.0)
    lfo = np.sin(2 * np.pi * vibrato_rate * ts)
    freq = np.clip(music.midi_to_freq(pitch + vibrato * lfo), 20.0, sample_rate * 0.45)
    phase = 2 * np.pi * np.cumsum(freq) / sample_rate
    f0 = float(np.median(freq))
    brightness = ctrl(voice.brightness)

    if inst.ident == "SINE":
        signal = np.sin(phase) + 0.12 * np.sin(2 * phase) + 0.04 * np.sin(3 * phase)
    elif inst.ident == "TRIANGLE":
        signal = (2.0 / np.pi) * np.arcsin(np.sin(phase))
    elif inst.ident == "SQUARE":
        signal = np.where(np.sin(phase) >= 0.0, 1.0, -1.0)
    elif inst.ident == "SAW":
        signal = _saw(phase, freq, sample_rate)
    elif inst.ident == "STRINGS":
        detune = 2.0 ** (7.0 / 1200.0)
        signal = (_saw(phase, freq, sample_rate)
                  + _saw(phase * detune, freq * detune, sample_rate)
                  + _saw(phase / detune, freq / detune, sample_rate)) / 3.0
    elif inst.ident == "PLUCK":
        signal = _karplus_strong(n, sample_rate, float(freq[0]), float(np.mean(brightness)), rng)
    elif inst.ident == "BELL":
        index = 3.0 * np.exp(-ts / 0.6)
        signal = np.sin(phase + index * np.sin(3.5 * phase)) * np.exp(-ts / 1.4)
    elif inst.ident in ("SAMPLE", "LIBRARY"):
        signal = _sample(voice.instrument, freq, sample_rate)
    elif inst.ident == NOISE_BAND:
        low = music.midi_to_freq(ctrl(voice.band_low))
        high = music.midi_to_freq(ctrl(voice.band_high))
        signal = _noise_band(n, sample_rate, low, high, rng)
    else:  # percussion
        signal = _percussion(inst.ident, n, sample_rate, float(voice.pitch[0]), rng)

    if not inst.percussive and inst.ident not in ("BELL", "SINE", "SAMPLE", "LIBRARY",
                                                  NOISE_BAND):
        dull = _lowpass(signal, sample_rate, 2.5 * f0)
        signal = brightness * signal + (1.0 - brightness) * dull

    if voice.glide and inst.ident in GLIDE_HOLD and voice.duration > GLIDE_HOLD_MIN:
        signal = signal + _glide_hold(phase, ts, sample_rate, float(np.mean(brightness)))

    attack = max(voice.attack, 0.12 if inst.ident == "STRINGS" else 0.0)
    envelope = ctrl(voice.amp) * np.clip(ts / max(attack, 1e-4), 0.0, 1.0)
    if not inst.percussive:
        if inst.release > 0:
            envelope *= np.clip(1.0 - (ts - voice.duration) / inst.release, 0.0, 1.0)
        else:
            envelope *= ts <= voice.duration
    mono = signal * envelope * inst.gain
    pan = ctrl(voice.pan)
    angle = (np.clip(pan, -1.0, 1.0) + 1.0) * np.pi / 4.0
    stereo = np.stack((mono * np.cos(angle), mono * np.sin(angle)), axis=1)
    offset = int(round(voice.start * sample_rate))
    return offset, stereo.astype(np.float32)


# --- General MIDI -> instruments (MIDI import) ------------------------------------

_GM_DRUMS = {35: "KICK", 36: "KICK", 37: "SNARE", 38: "SNARE", 40: "SNARE", 39: "CLAP",
             42: "HIHAT", 44: "HIHAT", 46: "HIHAT", 49: "CRASH", 51: "CRASH", 52: "CRASH",
             55: "CRASH", 57: "CRASH", 59: "CRASH", 41: "TOM", 43: "TOM", 45: "TOM",
             47: "TOM", 48: "TOM", 50: "TOM", 56: "COWBELL"}


def instrument_for_program(program, pitch=60):
    """Closest synthesized instrument for a General MIDI program (-1 = drums)."""
    if program < 0:
        return _GM_DRUMS.get(int(pitch), "DRUM")
    family = program // 8
    return {
        0: "PLUCK",      # pianos
        1: "BELL",       # chromatic percussion
        2: "SINE",       # organs
        3: "PLUCK",      # guitars
        4: "PLUCK",      # basses
        5: "STRINGS",    # strings
        6: "STRINGS",    # ensembles
        7: "SAW",        # brass
        8: "SAW",        # reeds
        9: "SINE",       # pipes
        10: "SQUARE" if program == 80 else "SAW",  # synth leads
        11: "STRINGS",   # synth pads
        12: "TRIANGLE",  # synth effects
        13: "PLUCK",     # ethnic
        14: "DRUM",      # percussive
        15: "TRIANGLE",  # sound effects
    }.get(family, "SINE")
