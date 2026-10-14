# SPDX-License-Identifier: GPL-3.0-or-later
"""App icon template: a golden-ratio construction grid in the style of Apple's icon grid.

    python tools/icon_template.py      # -> web/icon-template.svg and web/icon-template.png

Draw your logo on a 1024 x 1024 (or 2048) canvas with the PNG as a top layer, keep the
important shapes inside the circles and keylines, export as web/icon.png and run
tools/build_web.py: the web app icons are made from it. iPadOS rounds the corners itself,
so the icon itself stays a full square.
"""

import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
S = 1024
PHI = (1 + 5 ** 0.5) / 2


def squircle_path(size, n=5.0, steps=720):
    """Superellipse |x|^n + |y|^n = 1: close to iPadOS's continuous-corner mask."""
    r = size / 2
    pts = []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        c, s = math.cos(t), math.sin(t)
        x = r + r * math.copysign(abs(c) ** (2 / n), c)
        y = r + r * math.copysign(abs(s) ** (2 / n), s)
        pts.append(f"{x:.2f},{y:.2f}")
    return "M" + " L".join(pts) + " Z"


def svg():
    c = S / 2
    big, mid, small = S / PHI * 1.309, S / 2, S / PHI ** 2 * 0.809  # 828, 512, 316
    g = 1 / PHI  # 0.618
    lines = []
    add = lines.append
    stroke = 'fill="none" stroke="#0A84FF" stroke-width="2"'
    thin = 'fill="none" stroke="#0A84FF" stroke-width="1" stroke-opacity="0.55"'
    add(f'<rect x="1" y="1" width="{S - 2}" height="{S - 2}" {thin}/>')
    add(f'<path d="{squircle_path(S)}" fill="none" stroke="#FF375F" stroke-width="3"/>')
    for k in (0.191, 0.309, 0.691, 0.809):  # golden keylines
        add(f'<line x1="{S * k:.1f}" y1="0" x2="{S * k:.1f}" y2="{S}" {thin}/>')
        add(f'<line x1="0" y1="{S * k:.1f}" x2="{S}" y2="{S * k:.1f}" {thin}/>')
    add(f'<line x1="{c}" y1="0" x2="{c}" y2="{S}" {stroke}/>')
    add(f'<line x1="0" y1="{c}" x2="{S}" y2="{c}" {stroke}/>')
    add(f'<line x1="0" y1="0" x2="{S}" y2="{S}" {thin}/>')
    add(f'<line x1="{S}" y1="0" x2="0" y2="{S}" {thin}/>')
    for d in (big, mid, small):
        add(f'<circle cx="{c}" cy="{c}" r="{d / 2:.1f}" {stroke}/>')
    sq = S * g
    add(f'<rect x="{c - sq / 2:.1f}" y="{c - sq / 2:.1f}" width="{sq:.1f}" height="{sq:.1f}" {stroke}/>')
    w, h = S * g, S * 0.809
    add(f'<rect x="{c - w / 2:.1f}" y="{c - h / 2:.1f}" width="{w:.1f}" height="{h:.1f}" {thin}/>')
    add(f'<rect x="{c - h / 2:.1f}" y="{c - w / 2:.1f}" width="{h:.1f}" height="{w:.1f}" {thin}/>')
    body = "\n  ".join(lines)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{S}" height="{S}" viewBox="0 0 {S} {S}">\n'
            f'  <!-- Golden-ratio icon grid. Red: the rounded mask iPadOS applies. -->\n  {body}\n</svg>\n')


def png(size=2048):
    from PIL import Image, ImageDraw
    k = size / S
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    blue, faint, red = (10, 132, 255, 255), (10, 132, 255, 150), (255, 55, 95, 255)
    W, w = max(2, int(2 * k)), max(1, int(1 * k))
    c = size / 2
    d.rectangle([0, 0, size - 1, size - 1], outline=faint, width=w)
    for key in (0.191, 0.309, 0.691, 0.809):
        d.line([(size * key, 0), (size * key, size)], fill=faint, width=w)
        d.line([(0, size * key), (size, size * key)], fill=faint, width=w)
    d.line([(c, 0), (c, size)], fill=blue, width=W)
    d.line([(0, c), (size, c)], fill=blue, width=W)
    d.line([(0, 0), (size, size)], fill=faint, width=w)
    d.line([(size, 0), (0, size)], fill=faint, width=w)
    for diam in (S / PHI * 1.309, S / 2, S / PHI ** 2 * 0.809):
        r = diam / 2 * k
        d.ellipse([c - r, c - r, c + r, c + r], outline=blue, width=W)
    g = 1 / PHI
    sq = size * g
    d.rectangle([c - sq / 2, c - sq / 2, c + sq / 2, c + sq / 2], outline=blue, width=W)
    rw, rh = size * g, size * 0.809
    d.rectangle([c - rw / 2, c - rh / 2, c + rw / 2, c + rh / 2], outline=faint, width=w)
    d.rectangle([c - rh / 2, c - rw / 2, c + rh / 2, c + rw / 2], outline=faint, width=w)
    n, r = 5.0, size / 2
    pts = []
    for i in range(1440):
        t = 2 * math.pi * i / 1440
        cs, sn = math.cos(t), math.sin(t)
        pts.append((r + r * math.copysign(abs(cs) ** (2 / n), cs), r + r * math.copysign(abs(sn) ** (2 / n), sn)))
    d.line(pts + [pts[0]], fill=red, width=max(3, int(3 * k)))
    return img


if __name__ == "__main__":
    out = ROOT / "web"
    out.mkdir(exist_ok=True)
    (out / "icon-template.svg").write_text(svg(), encoding="utf-8")
    png().save(out / "icon-template.png")
    print(out / "icon-template.svg", out / "icon-template.png")
