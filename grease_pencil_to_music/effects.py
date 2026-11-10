# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-layer audio effects on stereo float buffers of shape (n, 2).

Effects may return a longer buffer (echo and reverb tails).

Pure Python + NumPy: no ``bpy`` import.
"""

import numpy as np


def _fft_convolve(signal, kernel):
    """Overlap-add FFT convolution: memory stays bounded for long loops."""
    n = len(signal) + len(kernel) - 1
    size = 1 << int(np.ceil(np.log2(max(2 * len(kernel), 1024))))
    block = size - len(kernel) + 1
    kernel_spectrum = np.fft.rfft(kernel, size)
    out = np.zeros(n + size)
    for start in range(0, len(signal), block):
        chunk = signal[start:start + block]
        out[start:start + size] += np.fft.irfft(np.fft.rfft(chunk, size) * kernel_spectrum,
                                                size)
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


# --- Master bus: the "finished sound" -----------------------------------------------
#
# The same chain as the web app (masterChain): a hall send, a gentle "glue"
# compressor, a soft saturator and a brickwall limiter, plus a low cut that
# removes rumble and DC. Whatever is drawn, the mix stays full, round and never
# clips. Gains are computed on short blocks and smoothed with attack/release, so
# only the block loop runs in Python.

MASTER_BLOCK = 64  # samples per gain step of the dynamics
MASTER_MAKEUP = 1.25  # gain after the glue compressor (the limiter catches the peaks)


def _db(x):
    return 20.0 * np.log10(np.maximum(x, 1e-9))


def _smooth(target, rate, attack, release):
    """Attack/release smoothing of a per-block gain (lower gain = attack)."""
    a = np.exp(-MASTER_BLOCK / (max(attack, 1e-5) * rate))
    r = np.exp(-MASTER_BLOCK / (max(release, 1e-5) * rate))
    out = np.empty_like(target)
    g = 1.0
    for i, t in enumerate(target.tolist()):
        coef = a if t < g else r
        g = t + coef * (g - t)
        out[i] = g
    return out


def _block_gain_to_samples(gain, n):
    centers = (np.arange(len(gain)) + 0.5) * MASTER_BLOCK
    return np.interp(np.arange(n), centers, gain)


def _blocks(buffer, stat):
    n = len(buffer)
    count = -(-n // MASTER_BLOCK)
    padded = np.zeros((count * MASTER_BLOCK, 2), dtype=np.float64)
    padded[:n] = buffer
    frames = padded.reshape(count, MASTER_BLOCK, 2)
    return stat(frames)


def compress(buffer, rate, threshold_db=-16.0, ratio=2.5, knee_db=8.0, attack=0.012,
             release=0.25):
    """Soft-knee RMS compressor, both channels linked."""
    if len(buffer) == 0:
        return buffer
    level = _db(_blocks(buffer, lambda f: np.sqrt(np.mean(f ** 2, axis=(1, 2)) * 2.0)))
    over = level - threshold_db
    slope = 1.0 - 1.0 / ratio
    reduction = np.where(over <= -knee_db / 2, 0.0,
                         np.where(over >= knee_db / 2, slope * over,
                                  slope * (over + knee_db / 2) ** 2 / (2 * knee_db)))
    gain = _smooth(10.0 ** (-reduction / 20.0), rate, attack, release)
    return buffer * _block_gain_to_samples(gain, len(buffer))[:, None]


SOFT_CLIP_KNEE = 0.6


def soft_clip(buffer, knee=SOFT_CLIP_KNEE):
    """Linear below ``knee``, then a tanh shoulder that never reaches 1 (web: softClip)."""
    a = np.abs(buffer)
    shoulder = knee + (1.0 - knee) * np.tanh((a - knee) / (1.0 - knee))
    return np.sign(buffer) * np.where(a < knee, a, shoulder)


def limit(buffer, rate, ceiling_db=-1.0, lookahead=0.004, release=0.08):
    """Brickwall limiter with lookahead: peaks above the ceiling are turned down
    smoothly before they arrive."""
    if len(buffer) == 0:
        return buffer
    ceiling = 10.0 ** (ceiling_db / 20.0)
    peak = _blocks(buffer, lambda f: np.max(np.abs(f), axis=(1, 2)))
    need = np.minimum(1.0, ceiling / np.maximum(peak, 1e-9))
    ahead = max(1, int(np.ceil(lookahead * rate / MASTER_BLOCK)))
    for k in range(1, ahead + 1):  # start turning down a few blocks early
        need[:-k] = np.minimum(need[:-k], need[k:])
    need = np.minimum(need, np.concatenate((need[1:], need[-1:])))
    gain = _smooth(need, rate, 1e-5, release)
    gain = np.minimum(gain, np.concatenate((gain[1:], gain[-1:])))  # interpolation safety
    out = buffer * _block_gain_to_samples(gain, len(buffer))[:, None]
    return np.clip(out, -ceiling, ceiling)


def low_cut(buffer, rate, cutoff=30.0):
    """Removes rumble and DC offset (circular: a loop stays seamless)."""
    if len(buffer) < 4:
        return buffer
    spectrum = np.fft.rfft(buffer, axis=0)
    f = np.maximum(np.fft.rfftfreq(len(buffer), 1.0 / rate), 1e-3)
    spectrum *= ((f / cutoff) ** 4 / (1.0 + (f / cutoff) ** 4))[:, None]
    return np.fft.irfft(spectrum, n=len(buffer), axis=0)


def _fold(buffer, length):
    out = np.array(buffer[:length], dtype=np.float64)
    for begin in range(length, len(buffer), length):
        chunk = buffer[begin:begin + length]
        out[:len(chunk)] += chunk
    return out


def master(buffer, rate, ambience=0.25, loop=True, wrap=2.0):
    """The finished sound of a whole mix: room, glue, saturation, limiter.

    With ``loop`` the buffer is one loop: reverb tails fold back onto the start
    and the dynamics see the end of the loop before its start, so the joint
    stays seamless.
    """
    n = len(buffer)
    if n == 0:
        return buffer
    out = np.asarray(buffer, dtype=np.float64)
    if ambience > 0:
        dry = out
        wet = reverb(out.astype(np.float32), rate, 1.0, 0.55).astype(np.float64)
        wet[:n] -= dry  # reverb() returns dry + wet
        wet *= 0.35 * float(np.clip(ambience, 0.0, 1.0))
        if loop:
            out = dry + _fold(wet, n)
        else:
            out = np.concatenate((dry, np.zeros((len(wet) - n, 2)))) + wet
            n = len(out)
    out = low_cut(out, rate)
    pre = min(int(wrap * rate), n) if loop else 0
    if pre:
        out = np.concatenate((out[-pre:], out))
    out = compress(out, rate)
    out = soft_clip(out * MASTER_MAKEUP)
    out = limit(out, rate)
    if pre:
        out = out[pre:]
    return out.astype(np.float32)
