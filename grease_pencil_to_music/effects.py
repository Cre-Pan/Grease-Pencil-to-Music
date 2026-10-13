# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-layer audio effects on stereo float buffers of shape (n, 2).

Effects may return a longer buffer (echo and reverb tails).

Pure Python + NumPy: no ``bpy`` import.
"""

import numpy as np


def _fft_convolve(signal, kernel):
    n = len(signal) + len(kernel) - 1
    size = 1 << int(np.ceil(np.log2(max(n, 1))))
    out = np.fft.irfft(np.fft.rfft(signal, size) * np.fft.rfft(kernel, size), size)
    return out[:n]


def delay(buffer, sample_rate, time_seconds, feedback, mix, ping_pong=True, max_tail=4.0):
    """Echo repeats; with ``ping_pong`` they bounce between left and right."""
    step = int(round(time_seconds * sample_rate))
    if mix <= 0.0 or step <= 0 or len(buffer) == 0:
        return buffer
    feedback = float(np.clip(feedback, 0.0, 0.95))
    repeats = 1
    while (repeats < 16 and feedback ** repeats >= 0.01
           and (repeats + 1) * step <= max_tail * sample_rate):
        repeats += 1
    out = np.zeros((len(buffer) + repeats * step, 2), dtype=np.float32)
    out[:len(buffer)] += buffer
    for k in range(1, repeats + 1):
        echo = buffer[:, ::-1] if (ping_pong and k % 2 == 1) else buffer
        out[k * step:k * step + len(buffer)] += echo * (mix * feedback ** (k - 1))
    return out


def reverb(buffer, sample_rate, mix, size=0.5, seed=7):
    """Convolution with a synthetic, exponentially decaying noise tail."""
    if mix <= 0.0 or len(buffer) == 0:
        return buffer
    decay = 0.3 + float(np.clip(size, 0.0, 1.0)) * 2.7  # ~RT60 in seconds
    length = int(decay * sample_rate)
    t = np.arange(length) / sample_rate
    rng = np.random.default_rng(seed)
    envelope = np.exp(-t * 6.9 / decay)
    predelay = int(0.015 * sample_rate)
    out = np.zeros((len(buffer) + length + predelay - 1, 2), dtype=np.float32)
    out[:len(buffer)] += buffer
    for ch in range(2):
        ir = rng.uniform(-1.0, 1.0, length) * envelope
        ir /= max(np.sqrt(np.sum(ir ** 2)), 1e-9)
        wet = _fft_convolve(buffer[:, ch].astype(np.float64), ir)
        out[predelay:predelay + len(wet), ch] += (wet * mix).astype(np.float32)
    return out


def lofi(buffer, sample_rate, amount, seed=11):
    """Sample-rate and bit-depth reduction, tape wobble and a little hiss."""
    amount = float(np.clip(amount, 0.0, 1.0))
    if amount <= 0.0 or len(buffer) == 0:
        return buffer
    n = len(buffer)
    idx = np.arange(n, dtype=np.float64)
    # Wow: slow pitch wobble as a time warp.
    wobble = amount * 0.003 * sample_rate * np.sin(2 * np.pi * 0.5 * idx / sample_rate)
    warped = np.stack([np.interp(idx + wobble, idx, buffer[:, ch]) for ch in range(2)], axis=1)
    hold = 1 + int(amount * 7)
    held = warped[(np.arange(n) // hold) * hold]
    levels = 2.0 ** (15.0 - amount * 11.0)
    crushed = np.round(held * levels) / levels
    rng = np.random.default_rng(seed)
    hiss = rng.normal(0.0, 0.004 * amount, (n, 2))
    return (crushed + hiss).astype(np.float32)


def apply_chain(buffer, sample_rate, settings, bpm):
    """``settings``: object with delay_mix, delay_beats, delay_feedback,
    reverb_mix, reverb_size and lofi attributes."""
    out = lofi(buffer, sample_rate, settings.lofi)
    beat = 60.0 / bpm if bpm > 0 else 0.5
    out = delay(out, sample_rate, settings.delay_beats * beat, settings.delay_feedback,
                settings.delay_mix)
    out = reverb(out, sample_rate, settings.reverb_mix, settings.reverb_size)
    return out
