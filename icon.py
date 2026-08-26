#!/usr/bin/env python3
"""
Build Clanno.icns.

    python3 icon.py         # writes Clanno.icns next to this file

Pure stdlib -- no PIL, no rsvg, nothing to install, in keeping with the
rest of the project. Shapes are signed distance fields, so every size in
the iconset is rendered from the vector description instead of being
downscaled from one big bitmap; the small sizes stay as crisp as they can.
Coverage is one smoothstep over the distance, so there's no supersampling
to pay for.

Only `iconutil` (ships with macOS) is needed to pack the iconset.
"""

import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "Clanno.icns")

BG_TOP = (0x2e, 0x2e, 0x38)
BG_BOT = (0x15, 0x15, 0x19)
PINK = (0xff, 0x6f, 0xa5)
LIGHT = (0xec, 0xec, 0xf1)
GRAPHITE = (0x1f, 0x1f, 0x24)

# Apple's icon grid: the rounded plate covers 824/1024 of the canvas.
PLATE = 824 / 1024 / 2
# A superellipse of this exponent is close enough to macOS's squircle.
SQUIRCLE_N = 5.0

# Everything below is in unit coordinates on the full canvas, y downwards.
TIP = (.395, .520)          # where the pencil's point sits
PENCIL = (-45, .44, .068, .098)   # angle°, length, half-width, tip length
INK = .0265                 # half-width of an annotation stroke

# Scattered marks, as if the page had been scribbled over. Each is
# (start, end, amplitude, cycles, phase); the first runs out of the
# pencil's point so it reads as the one being drawn.
# Kept deliberately sparse: denser scatters turn to pink noise at 16px.
MARKS = [
    (TIP,           (.140, .565), .030, 1.6, 0.0),
    ((.130, .310),  (.400, .280), .028, 1.5, 1.0),
    ((.575, .400),  (.825, .372), .030, 1.6, 1.7),
    ((.250, .700),  (.610, .668), .032, 1.6, 0.9),
]


def squircle(x, y):
    """Approximate signed distance to the plate. Negative inside."""
    dx, dy = abs(x - 0.5) / PLATE, abs(y - 0.5) / PLATE
    if dx < 1e-9 and dy < 1e-9:
        return -PLATE
    n = SQUIRCLE_N
    f = dx ** n + dy ** n - 1.0
    gx = n * dx ** (n - 1) / PLATE
    gy = n * dy ** (n - 1) / PLATE
    return f / (math.hypot(gx, gy) or 1e-9)


def rrect(x, y, box, r):
    """Exact signed distance to a rounded rectangle. Negative inside."""
    x0, y0, x1, y1 = box
    qx = abs(x - (x0 + x1) / 2) - ((x1 - x0) / 2 - r)
    qy = abs(y - (y0 + y1) / 2) - ((y1 - y0) / 2 - r)
    return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r


def tri(px, py, a, b, c):
    """Exact signed distance to a triangle. Negative inside."""
    e = [(b[0]-a[0], b[1]-a[1]), (c[0]-b[0], c[1]-b[1]), (a[0]-c[0], a[1]-c[1])]
    v = [(px-a[0], py-a[1]), (px-b[0], py-b[1]), (px-c[0], py-c[1])]
    s = 1.0 if (e[0][0]*e[2][1] - e[0][1]*e[2][0]) > 0 else -1.0
    sq, sg = [], []
    for i in range(3):
        t = min(max((v[i][0]*e[i][0] + v[i][1]*e[i][1]) /
                    (e[i][0]**2 + e[i][1]**2), 0.0), 1.0)
        q = (v[i][0] - e[i][0]*t, v[i][1] - e[i][1]*t)
        sq.append(q[0]**2 + q[1]**2)
        sg.append(s * (v[i][0]*e[i][1] - v[i][1]*e[i][0]))
    return -math.sqrt(min(sq)) if min(sg) > 0 else math.sqrt(min(sq))


def _seg(px, py, a, b):
    vx, vy = b[0]-a[0], b[1]-a[1]
    wx, wy = px-a[0], py-a[1]
    t = max(0.0, min(1.0, (wx*vx + wy*vy) / (vx*vx + vy*vy)))
    return math.hypot(wx - vx*t, wy - vy*t)


def stroke(pts, r):
    """Round-capped polyline.

    The bbox early-out matters: without it every pixel tests every segment
    of every mark and a single render runs into minutes. The margin is wide
    enough that a culled pixel always falls outside the feather, at any size.
    """
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    m = r + 0.08
    x0, x1 = min(xs) - m, max(xs) + m
    y0, y1 = min(ys) - m, max(ys) + m
    segs = list(zip(pts, pts[1:]))

    def f(x, y):
        if x < x0 or x > x1 or y < y0 or y > y1:
            return 1.0
        return min(_seg(x, y, a, b) for a, b in segs) - r
    return f


def wave(a, b, amp, cycles, phase, w, n=28):
    """One hand-drawn-looking stroke: a sine offset along a to b."""
    dx, dy = b[0]-a[0], b[1]-a[1]
    length = math.hypot(dx, dy) or 1e-9
    nx, ny = -dy/length, dx/length
    pts = []
    for i in range(n + 1):
        t = i / n
        o = amp * math.sin(2*math.pi*cycles*t + phase)
        pts.append((a[0] + dx*t + nx*o, a[1] + dy*t + ny*o))
    return stroke(pts, w)


def pencil(cx, cy, ang_deg, length, half, tiplen):
    """Body, wooden tip and graphite point, with the point at (cx, cy)."""
    c, s = math.cos(math.radians(-ang_deg)), math.sin(math.radians(-ang_deg))

    def loc(x, y):
        dx, dy = x - cx, y - cy
        return dx*c - dy*s, dx*s + dy*c

    body = lambda x, y: rrect(*loc(x, y), (tiplen, -half, length, half), half*.3)
    tipf = lambda x, y: tri(*loc(x, y), (tiplen, -half), (tiplen, half), (0., 0.))
    lead = lambda x, y: tri(*loc(x, y), (tiplen*.34, -half*.34),
                            (tiplen*.34, half*.34), (0., 0.))
    return body, tipf, lead


def union(*fs):
    return lambda x, y: min(f(x, y) for f in fs)


def over(dst, src, a):
    """Straight-alpha source-over of an opaque `src` at coverage `a`."""
    if a <= 0:
        return dst
    dr, dg, db, da = dst
    out_a = a + da * (1 - a)
    if out_a <= 0:
        return (0.0, 0.0, 0.0, 0.0)
    f = da * (1 - a)
    return ((src[0]*a + dr*f) / out_a, (src[1]*a + dg*f) / out_a,
            (src[2]*a + db*f) / out_a, out_a)


def cov(d, aa):
    """Coverage from a signed distance: 1 well inside, 0 well outside."""
    return min(max(0.5 - d / aa, 0.0), 1.0)


def layers():
    """The drawing, painted in order over the plate."""
    marks = union(*(wave(a, b, amp, cyc, ph, INK) for a, b, amp, cyc, ph in MARKS))
    body, tipf, lead = pencil(TIP[0], TIP[1], *PENCIL)
    return [(PINK, marks), (LIGHT, union(body, tipf)), (GRAPHITE, lead)]


def render(size):
    """One list of RGBA rows for the icon at `size` px."""
    aa = 1.2 / size            # feather one pixel-ish, in unit space
    paint = layers()
    rows = []
    for py in range(size):
        y = (py + 0.5) / size
        # The plate's gradient only depends on y, so mix it once per row.
        t = min(max((y - 0.5 + PLATE) / (2 * PLATE), 0.0), 1.0)
        bg = tuple(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t for i in range(3))
        row = bytearray()
        for px in range(size):
            x = (px + 0.5) / size
            c = over((0.0, 0.0, 0.0, 0.0), bg, cov(squircle(x, y), aa))
            for col, f in paint:
                c = over(c, col, cov(f(x, y), aa))
            r, g, b, a = c
            # PNG wants straight alpha, not premultiplied.
            row += bytes((int(r + .5), int(g + .5), int(b + .5), int(a*255 + .5)))
        rows.append(bytes(row))
    return rows


def write_png(path, size, rows):
    raw = b"".join(b"\x00" + r for r in rows)

    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        f.write(chunk(b"IEND", b""))


def main():
    if not shutil.which("iconutil"):
        sys.exit("error: iconutil not found; this only builds on macOS.")
    tmp = tempfile.mkdtemp()
    iconset = os.path.join(tmp, "Clanno.iconset")
    os.mkdir(iconset)
    for base in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            size = base * scale
            name = "icon_%dx%d%s.png" % (base, base, "@2x" if scale == 2 else "")
            write_png(os.path.join(iconset, name), size, render(size))
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", OUT], check=True)
    shutil.rmtree(tmp)
    print("wrote %s (%d bytes)" % (OUT, os.path.getsize(OUT)))


if __name__ == "__main__":
    main()
