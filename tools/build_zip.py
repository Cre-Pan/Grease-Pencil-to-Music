# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the installable extension zip.

    python tools/build_zip.py                    # dist/grease_pencil_to_music-<version>-windows_x64.zip
    python tools/build_zip.py --platform linux-x64 --out <dir>   # e.g. for local tests

Install in Blender: Edit > Preferences > Get Extensions > ▾ > Install from Disk.

Python wheels for the target platform (``wheels/<platform>/*.whl``, e.g. rtmidi2 for
MIDI keyboards) are bundled and listed in the manifest's ``wheels`` field.
"""

import argparse
import pathlib
import re
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "grease_pencil_to_music"
MANIFEST = "blender_manifest.toml"
WHEELS = ROOT / "wheels"


def read_manifest():
    text = (PACKAGE / MANIFEST).read_text(encoding="utf-8")
    version = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M).group(1)
    ident = re.search(r'^id\s*=\s*"([^"]+)"', text, re.M).group(1)
    platforms = re.search(r'^platforms\s*=\s*\[([^\]]*)\]', text, re.M).group(1)
    return text, ident, version, [p.strip().strip('"') for p in platforms.split(",") if p.strip()]


def build(out_dir, platform=None):
    text, ident, version, platforms = read_manifest()
    if platform:
        text = re.sub(r'^platforms\s*=\s*\[[^\]]*\]', f'platforms = ["{platform}"]', text,
                      flags=re.M)
        platforms = [platform]
    suffix = "-".join(p.replace("-", "_") for p in platforms)
    wheels = sorted(w for p in platforms for w in (WHEELS / p).glob("*.whl"))
    if wheels:
        listed = ", ".join(f'"./wheels/{w.name}"' for w in wheels)
        text = re.sub(r'^(platforms\s*=.*)$', rf'\1\n\nwheels = [{listed}]', text, count=1,
                      flags=re.M)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{ident}-{version}-{suffix}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(PACKAGE.rglob("*")):
            if path.is_dir() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            name = path.relative_to(PACKAGE).as_posix()
            if name == MANIFEST:
                archive.writestr(name, text)
            else:
                archive.write(path, name)
        for wheel in wheels:
            archive.write(wheel, f"wheels/{wheel.name}")
        archive.write(ROOT / "LICENSE", "LICENSE")
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", help="override manifest platforms (e.g. linux-x64)")
    parser.add_argument("--out", type=pathlib.Path, default=ROOT / "dist")
    args = parser.parse_args(argv)
    print(build(args.out, args.platform))


if __name__ == "__main__":
    sys.exit(main())
