# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthesized instruments, rendered with NumPy.

Every instrument receives a :class:`interpret.Voice` (pitch, volume, vibrato,
brightness and pan curves) and returns a stereo float32 buffer.

Pure Python + NumPy: no ``bpy`` import.
"""

from dataclasses import dataclass

import numpy as np

from . import music
from .interpret import CONTROL_RATE


@dataclass(frozen=True)
class Instrument:
    ident: str
    label: str
    description: str
    color: tuple  # RGBA used for the Grease Pencil material
    gm_program: int  # General MIDI program (0-based); -1 = drum channel
    release: float  # seconds of fade after the stroke ends
    gain: float


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
               (0.85, 0.85, 0.85, 1.0), -1, 0.0, 0.7),
)
INSTRUMENT_BY_ID = {inst.ident: inst for inst in INSTRUMENTS}
DEFAULT_INSTRUMENT = "SINE"


def get_instrument(ident):
    return INSTRUMENT_BY_ID.get(ident, INSTRUMENT_BY_ID[DEFAULT_INSTRUMENT])


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


# --- Voice rendering ---------------------------------------------------------

def voice_length(voice, sample_rate):
    inst = get_instrument(voice.instrument)
    if inst.ident == "DRUM":
        return int(0.5 * sample_rate)
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
    else:  # DRUM
        signal = _drum(n, sample_rate, float(voice.pitch[0]), rng)

    if inst.ident not in ("DRUM", "BELL", "SINE"):
        dull = _lowpass(signal, sample_rate, 2.5 * f0)
        signal = brightness * signal + (1.0 - brightness) * dull

    attack = max(voice.attack, 0.12 if inst.ident == "STRINGS" else 0.0)
    envelope = ctrl(voice.amp) * np.clip(ts / max(attack, 1e-4), 0.0, 1.0)
    if inst.ident != "DRUM":
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
