# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the recorded reverb rooms of the web app from the HybridReverb2 impulse responses.

    git clone https://github.com/jpcima/hybridreverb2-impulse-response-database   # CC BY-SA 4.0
    python tools/build_rooms.py path/to/hybridreverb2-impulse-response-database   # -> docs/app/rooms/

The responses (Institute of Communication Acoustics, Ruhr-Universität Bochum, made with the
tinyAVE auralisation software) are stereo pairs: the left loudspeaker heard by the left ear and
the right one by the right ear. Each is cut where the energy still to come falls 60 dB below the whole, faded
out and written as a stereo MP3. The page brings every room to unit energy when it loads it.
Needs ffmpeg and numpy.
"""

import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "app" / "rooms"
SR = 44100
# id: (folder in RIR_Database, longest seconds)
ROOMS = {
    "room": ("livingroom/music/2m", 1.5),
    "concert": ("large_concert_hall/music/4m", 2.5),
    "church": ("church/music/4m", 6.0),
}


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def main(src):
    db = Path(src) / "RIR_Database"
    OUT.mkdir(parents=True, exist_ok=True)
    for ident, (folder, longest) in ROOMS.items():
        left, right = load(db / folder / "left_fl.flac"), load(db / folder / "right_fr.flac")
        n = min(len(left), len(right))
        x = np.stack([left[:n], right[:n]])
        energy = np.cumsum(np.sum(x ** 2, axis=0)[::-1])[::-1]  # energy still to come (Schroeder)
        end = min(int(np.argmax(energy < energy[0] * 1e-6)) or n, int(SR * longest))  # -60 dB
        x = x[:, :end]
        fade = min(end, int(SR * 0.15))
        x[:, end - fade:] *= np.linspace(1, 0, fade) ** 2
        x *= 0.9 / (np.max(np.abs(x)) or 1)
        pcm = (np.clip(x.T, -1, 1) * 32767).astype("<i2").tobytes()
        path = OUT / f"{ident}.mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", "-",
                        "-codec:a", "libmp3lame", "-b:a", "160k", str(path)], input=pcm, check=True)
        print(f"{ident}: {end / SR:.2f} s, {path.stat().st_size / 1e3:.0f} kB")
    (OUT / "LICENSE.txt").write_text(
        "Room impulse responses from the HybridReverb2 impulse response database\n"
        "(https://github.com/jpcima/hybridreverb2-impulse-response-database), by Christian Borß,\n"
        "Institute of Communication Acoustics, Ruhr-Universität Bochum, Germany.\n"
        "Licensed under Creative Commons Attribution-ShareAlike 4.0 International\n"
        "(https://creativecommons.org/licenses/by-sa/4.0/). Shortened, faded and converted to MP3\n"
        "by tools/build_rooms.py; these files are shared under the same license.\n", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
