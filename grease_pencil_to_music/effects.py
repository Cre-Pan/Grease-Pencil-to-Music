# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-layer audio effects on stereo float buffers of shape (n, 2).

Effects may return a longer buffer (echo and reverb tails).

Pure Python + NumPy: no ``bpy`` import.
"""

import numpy as np


_SPECTRA = {}  # (kernel key, fft size) -> spectrum of the kernel(s), most recent last
_SPECTRA_MAX_BYTES = 96 * 1024 * 1024
SINGLE_FFT_MAX = 1 << 22  # longer convolutions go in blocks (memory stays bounded)


def _fft_size(kernel_length):
    # Blocks four times the kernel: fewer, larger FFTs (the loop runs in Python).
    return 1 << int(np.ceil(np.log2(max(4 * kernel_length, 1024))))


_FAST_STEPS = (8, 9, 10, 12, 14, 15, 16)  # eighths of a power of two: factors 2, 3, 5, 7


def _fast_size(n):
    """A fast FFT length >= ``n``: a power of two times 1, 9/8, 5/4, 3/2, 7/4 or 15/8.

    Few lengths (at most 1/7 longer than needed), so the spectrum of a reverb is
    reused while the length of what it plays changes a little."""
    n = max(int(n), 1)
    if n <= 16:
        return n
    shift = max((n - 1).bit_length() - 4, 0)
    for step in _FAST_STEPS:
        if step << shift >= n:
            return step << shift
    return 16 << shift


def _kernel_spectrum(kernel, size, key):
    cache_key = None if key is None else (key, size)
    spectrum = _SPECTRA.get(cache_key) if cache_key is not None else None
    if spectrum is None:
        spectrum = np.fft.rfft(kernel, size, axis=-1)
        if cache_key is not None:
            _SPECTRA[cache_key] = spectrum
            while len(_SPECTRA) > 1 and sum(v.nbytes for v in _SPECTRA.values()) > \
                    _SPECTRA_MAX_BYTES:
                del _SPECTRA[next(iter(_SPECTRA))]
    else:
        _SPECTRA[cache_key] = _SPECTRA.pop(cache_key)  # most recently used
    return spectrum


def _fft_convolve(signal, kernel, key=None):
    """FFT convolution: one FFT of a fast length, or (very long signals) overlap-add
    blocks, so memory stays bounded.

    ``signal``: (n,) or (n, channels); ``kernel``: (m,) or (m, channels), one
    kernel per channel. ``key`` names a kernel that does not change (the reverb
    impulse responses): its spectrum is computed once and reused."""
    signal = np.asarray(signal, dtype=np.float64)
    kernel = np.asarray(kernel, dtype=np.float64)
    m = len(kernel)
    n = len(signal) + m - 1
    # Channels first: the FFTs run over contiguous rows.
    sig = np.ascontiguousarray(signal.T)
    ker = np.ascontiguousarray(kernel.T)
    if kernel.ndim == 1 and signal.ndim == 2:  # the same kernel on every channel
        ker = ker[None, :]
    if n <= SINGLE_FFT_MAX:
        size = _fast_size(n)
        spectrum = _kernel_spectrum(ker, size, key)
        out = np.fft.irfft(np.fft.rfft(sig, size, axis=-1) * spectrum, size, axis=-1)[..., :n]
        return out.T
    size = _fft_size(m)
    block = size - m + 1
    spectrum = _kernel_spectrum(ker, size, key)
    out = np.zeros(sig.shape[:-1] + (n + size,))
    for start in range(0, sig.shape[-1], block):
        chunk = sig[..., start:start + block]
        out[..., start:start + size] += np.fft.irfft(
            np.fft.rfft(chunk, size, axis=-1) * spectrum, size, axis=-1)
    return out[..., :n].T


_IRS = {}  # (length, decay, seed) -> (length, 2) impulse responses, unit energy


def reverb_ir(sample_rate, size=0.5, seed=7):
    """The synthetic stereo impulse response of :func:`reverb` (cached)."""
    decay = 0.3 + float(np.clip(size, 0.0, 1.0)) * 2.7  # ~RT60 in seconds
    length = int(decay * sample_rate)
    key = (length, round(decay, 9), int(sample_rate), seed)
    found = _IRS.get(key)
    if found is None:
        t = np.arange(length) / sample_rate
        rng = np.random.default_rng(seed)
        envelope = np.exp(-t * 6.9 / decay)
        channels = []
        for _ch in range(2):
            ir = rng.uniform(-1.0, 1.0, length) * envelope
            ir /= max(np.sqrt(np.sum(ir ** 2)), 1e-9)
            channels.append(ir)
        found = np.stack(channels, axis=1)
        found.flags.writeable = False
        if len(_IRS) > 8:
            _IRS.clear()
        _IRS[key] = found
    return found, key


ROOMS = ("HALL", "ROOM", "CONCERT", "CHURCH")  # HALL: the synthetic response above
ROOM_LOADER = None  # (room, rate) -> (n, 2) recorded response (samples.py, needs bpy)


def room_ir(room, sample_rate):
    """The recorded response of ``room`` at unit energy per channel, or None (synthetic
    hall, or the recording cannot be read)."""
    if room in (None, "", "HALL") or ROOM_LOADER is None:
        return None
    key = ("room", room, int(sample_rate))
    found = _IRS.get(key)
    if found is None:
        try:
            found = np.asarray(ROOM_LOADER(room, sample_rate), dtype=np.float64)
        except Exception as error:  # noqa: BLE001 - the synthetic hall plays instead
            print(f"[Doodle Music] ambiente {room} non letto: {error!r}")
            return None
        found = found / np.maximum(np.sqrt(np.sum(found ** 2, axis=0)), 1e-9)
        found.flags.writeable = False
        if len(_IRS) > 8:
            _IRS.clear()
        _IRS[key] = found
    return found, key


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


def reverb(buffer, sample_rate, mix, size=0.5, seed=7, room="HALL"):
    """Convolution with a synthetic, exponentially decaying noise tail, or (``room``) with
    the recorded response of a room: then ``size`` is the room's own."""
    if mix <= 0.0 or len(buffer) == 0:
        return buffer
    recorded = room_ir(room, sample_rate)
    ir, key = recorded if recorded is not None else reverb_ir(sample_rate, size, seed)
    length = len(ir)
    predelay = 0 if recorded is not None else int(0.015 * sample_rate)
    out = np.zeros((len(buffer) + length + predelay - 1, 2), dtype=np.float32)
    out[:len(buffer)] += buffer
    wet = _fft_convolve(np.asarray(buffer[:, :2], dtype=np.float64), ir, key=key)
    out[predelay:predelay + len(wet)] += (wet * mix).astype(np.float32)
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


def apply_chain(buffer, sample_rate, settings, bpm, room="HALL"):
    """``settings``: object with delay_mix, delay_beats, delay_feedback,
    reverb_mix, reverb_size and lofi attributes; ``room``: the composition's room."""
    out = lofi(buffer, sample_rate, settings.lofi)
    beat = 60.0 / bpm if bpm > 0 else 0.5
    out = delay(out, sample_rate, settings.delay_beats * beat, settings.delay_feedback,
                settings.delay_mix)
    out = reverb(out, sample_rate, settings.reverb_mix, settings.reverb_size, room=room)
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


def compress(buffer, rate, **settings):
    """Soft-knee RMS compressor, both channels linked."""
    if len(buffer) == 0:
        return buffer
    return buffer * compress_gain(buffer, rate, **settings)[:, None]


def compress_gain(buffer, rate, threshold_db=-16.0, ratio=2.5, knee_db=8.0, attack=0.012,
                  release=0.25):
    """Per-sample gain of :func:`compress` (both channels linked)."""
    if len(buffer) == 0:
        return np.ones(0)
    level = _db(_blocks(buffer, lambda f: np.sqrt(np.mean(f ** 2, axis=(1, 2)) * 2.0)))
    over = level - threshold_db
    slope = 1.0 - 1.0 / ratio
    reduction = np.where(over <= -knee_db / 2, 0.0,
                         np.where(over >= knee_db / 2, slope * over,
                                  slope * (over + knee_db / 2) ** 2 / (2 * knee_db)))
    gain = _smooth(10.0 ** (-reduction / 20.0), rate, attack, release)
    return _block_gain_to_samples(gain, len(buffer))


SOFT_CLIP_KNEE = 0.6


def soft_clip(buffer, knee=SOFT_CLIP_KNEE):
    """Linear below ``knee``, then a tanh shoulder that never reaches 1 (web: softClip)."""
    buffer = np.asarray(buffer)
    out = buffer.copy() if buffer.dtype.kind == "f" else buffer.astype(np.float64)
    over = np.abs(out) >= knee
    if over.any():  # the shoulder only where it is reached (tanh is slow)
        loud = out[over]
        a = np.abs(loud)
        out[over] = np.sign(loud) * (knee + (1.0 - knee) * np.tanh((a - knee) / (1.0 - knee)))
    return out


LIMIT_CEILING_DB = -1.0


def limit(buffer, rate, ceiling_db=LIMIT_CEILING_DB, lookahead=0.004, release=0.08):
    """Brickwall limiter with lookahead: peaks above the ceiling are turned down
    smoothly before they arrive."""
    if len(buffer) == 0:
        return buffer
    ceiling = 10.0 ** (ceiling_db / 20.0)
    out = buffer * limit_gain(buffer, rate, ceiling_db, lookahead, release)[:, None]
    return np.clip(out, -ceiling, ceiling)


def limit_gain(buffer, rate, ceiling_db=LIMIT_CEILING_DB, lookahead=0.004, release=0.08):
    """Per-sample gain of :func:`limit` (before its final clip)."""
    if len(buffer) == 0:
        return np.ones(0)
    ceiling = 10.0 ** (ceiling_db / 20.0)
    peak = _blocks(buffer, lambda f: np.max(np.abs(f), axis=(1, 2)))
    need = np.minimum(1.0, ceiling / np.maximum(peak, 1e-9))
    ahead = max(1, int(np.ceil(lookahead * rate / MASTER_BLOCK)))
    for k in range(1, ahead + 1):  # start turning down a few blocks early
        need[:-k] = np.minimum(need[:-k], need[k:])
    need = np.minimum(need, np.concatenate((need[1:], need[-1:])))
    gain = _smooth(need, rate, 1e-5, release)
    gain = np.minimum(gain, np.concatenate((gain[1:], gain[-1:])))  # interpolation safety
    return _block_gain_to_samples(gain, len(buffer))


def _lowpass_kernel(rate, cutoff):
    """Sampled impulse response of the zero-phase low pass 1 / (1 + (f/cutoff)^4).

    Its inverse Fourier transform is known in closed form; it decays as
    exp(-b|t|), so it is cut where it is below 1e-13 of its peak."""
    a = 2.0 * np.pi * cutoff
    b = a / np.sqrt(2.0)
    half = int(np.ceil(30.0 / b * rate))
    t = np.arange(-half, half + 1) / rate
    kernel = (a / (2.0 * np.sqrt(2.0)) * np.exp(-b * np.abs(t))
              * (np.cos(b * t) + np.sin(b * np.abs(t)))) / rate
    return kernel, half


def _fast_fft_length(n):
    """True when ``n`` has only small prime factors (a fast FFT length)."""
    for factor in (2, 3, 5, 7, 11):
        while n % factor == 0:
            n //= factor
    return n == 1


def low_cut(buffer, rate, cutoff=30.0):
    """Removes rumble and DC offset (circular: a loop stays seamless).

    The filter is 1 - 1 / (1 + (f/cutoff)^4). A single FFT as long as the loop
    is very slow when that length has large prime factors (most loop lengths
    in samples): those loops subtract the low pass, computed as a circular
    convolution with its short kernel, in power-of-two blocks instead."""
    n = len(buffer)
    if n < 4:
        return buffer
    kernel, half = _lowpass_kernel(rate, cutoff)
    if n < 2 * len(kernel) or _fast_fft_length(n):  # the exact FFT is fast
        # Channels first: the FFTs run over contiguous rows.
        spectrum = np.fft.rfft(np.ascontiguousarray(np.asarray(buffer).T), axis=-1)
        f = np.maximum(np.fft.rfftfreq(n, 1.0 / rate), 1e-3)
        spectrum *= (f / cutoff) ** 4 / (1.0 + (f / cutoff) ** 4)
        return np.fft.irfft(spectrum, n=n, axis=-1).T
    x = np.asarray(buffer, dtype=np.float64)
    wrapped = np.concatenate((x[-half:], x, x[:half]))  # the loop continues on both sides
    low = _fft_convolve(wrapped, kernel, key=("low_cut", rate, cutoff))
    return x - low[2 * half:2 * half + n]


def _fold(buffer, length):
    out = np.array(buffer[:length], dtype=np.float64)
    for begin in range(length, len(buffer), length):
        chunk = buffer[begin:begin + length]
        out[:len(chunk)] += chunk
    return out


def master(buffer, rate, ambience=0.25, loop=True, wrap=2.0, room="HALL"):
    """The finished sound of a whole mix: room, glue, saturation, limiter.

    With ``loop`` the buffer is one loop: reverb tails fold back onto the start
    and the dynamics see the end of the loop before its start, so the joint
    stays seamless.
    """
    if len(buffer) == 0:
        return buffer
    linear = master_linear(buffer, rate, ambience, loop, room)
    return master_dynamics([linear], rate, loop, wrap)[0]


def master_linear(buffer, rate, ambience=0.25, loop=True, room="HALL"):
    """The linear part of the master bus: the shared room and the low cut.

    Being linear, it can be applied to each layer on its own: the layers then
    add up to the same mix. Without ``loop`` the result is longer (room tail)."""
    out = np.asarray(buffer, dtype=np.float64)
    n = len(out)
    if n == 0:
        return out
    if ambience > 0:
        dry = out
        wet = reverb(out.astype(np.float32), rate, 1.0, 0.55, room=room).astype(np.float64)
        wet[:n] -= dry  # reverb() returns dry + wet
        wet *= 0.35 * float(np.clip(ambience, 0.0, 1.0))
        if loop:
            out = dry + _fold(wet, n)
        else:
            out = np.concatenate((dry, np.zeros((len(wet) - n, 2)))) + wet
    return low_cut(out, rate)


def master_dynamics(stems, rate, loop=True, wrap=2.0, want_stems=False):
    """Glue compressor, soft saturation and limiter of the sum of ``stems``
    (arrays of the same length, after :func:`master_linear`).

    Returns ``(mix, stems)``. The dynamics are computed once on the sum, then
    the same gain is applied to every stem, like a master bus: the processed
    stems still add up to the mix (they are None unless ``want_stems``)."""
    total = np.zeros((max((len(s) for s in stems), default=0), 2), dtype=np.float64)
    for stem in stems:
        total[:len(stem)] += stem
    n = len(total)
    if n == 0:
        return total.astype(np.float32), ([] if want_stems else None)
    pre = min(int(wrap * rate), n) if loop else 0
    x = np.concatenate((total[-pre:], total)) if pre else total
    glue = compress_gain(x, rate)[:, None] * MASTER_MAKEUP
    driven = x * glue
    saturated = soft_clip(driven)
    final = limit_gain(saturated, rate)[:, None]
    ceiling = 10.0 ** (LIMIT_CEILING_DB / 20.0)
    # Only the loop itself from here (the wrap was there for the dynamics).
    driven, saturated, glue, final = driven[pre:], saturated[pre:], glue[pre:], final[pre:]
    mix = saturated * final
    np.clip(mix, -ceiling, ceiling, out=mix)
    # gain = glue * (saturated / driven) * final; the ratio is exactly 1 below the knee,
    # where soft_clip is the identity, so it is computed only above it.
    gain = np.empty_like(driven)
    gain[:] = glue * final
    over = np.abs(driven) >= SOFT_CLIP_KNEE
    if over.any():
        rows = np.nonzero(over)[0]
        gain[over] = glue[rows, 0] * (saturated[over] / driven[over]) * final[rows, 0]
    outs = None
    if want_stems:
        outs = []
        for stem in stems:
            if len(stem) < n:
                stem = np.concatenate((np.asarray(stem, dtype=np.float64),
                                       np.zeros((n - len(stem), 2))))
            outs.append(np.multiply(stem, gain, dtype=np.float64).astype(np.float32))
    return mix.astype(np.float32), outs
