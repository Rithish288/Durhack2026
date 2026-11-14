"""Encoder: 3 words -> Mandelbrot-style PNG.

usage: python encoder.py words.csv out.png apple river garden [theme]
themes: mandelbrot (default), space, ember, emerald
"""
import math
import random
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

import codec
import layout

DEFAULT_R = 50           # main disc radius in pixels of the output image
SUPERSAMPLE = 2

JULIA_SEEDS = [(-0.8, 0.156), (-0.4, 0.6), (0.285, 0.01), (-0.70176, -0.3842),
               (-0.7269, 0.1889), (0.355, 0.355), (-0.1, 0.651), (-0.835, -0.2321)]

# Themes. "body" is the colour of the data-carrying shapes (marker + bulbs); the decoder
# only needs it to be either very dark (max channel < 60) or very bright (min channel > 200),
# and the background / glow must stay well clear of that range (dark themes: every other
# colour has max channel >= 135; bright themes: every other colour has min channel <= 120).
# Ramp = (distance in units of R, rgb).
THEMES = {
    "mandelbrot": dict(                      # the classic poster: black set, blue-white glow
        bg=(0, 0, 93), body=(0, 0, 0), filament=(255, 255, 255), stars=False,
        ramp=[(0.00, (255, 255, 255)), (0.06, (210, 248, 255)), (0.18, (90, 180, 255)),
              (0.40, (25, 50, 225)), (0.75, (0, 0, 150)), (1.30, (0, 0, 93))]),
    "space": dict(                           # black sky, blue nebula, pink-white cores
        bg=(0, 0, 0), body=(255, 228, 236), filament=(120, 170, 255), stars=True,
        ramp=[(0.00, (255, 120, 170)), (0.10, (150, 120, 230)), (0.25, (90, 130, 255)),
              (0.55, (30, 60, 190)), (0.95, (8, 14, 60)), (1.40, (0, 0, 0))]),
    "ember": dict(                           # black set, fire glow
        bg=(90, 12, 0), body=(0, 0, 0), filament=(255, 250, 200), stars=False,
        ramp=[(0.00, (255, 255, 240)), (0.06, (255, 240, 120)), (0.18, (255, 150, 0)),
              (0.40, (215, 40, 0)), (0.75, (140, 20, 0)), (1.30, (90, 12, 0))]),
    "emerald": dict(                         # black set, green glow
        bg=(0, 85, 45), body=(0, 0, 0), filament=(240, 255, 245), stars=False,
        ramp=[(0.00, (255, 255, 255)), (0.06, (200, 255, 220)), (0.18, (60, 230, 140)),
              (0.40, (0, 160, 90)), (0.75, (0, 110, 60)), (1.30, (0, 85, 45))]),
}
DEFAULT_THEME = "mandelbrot"
BG = THEMES[DEFAULT_THEME]["bg"]        # used by test.py for rotation borders


FORMULAS = ["julia", "burning_ship", "multibrot3", "tricorn", "phoenix"]


def julia_field(size, c, R, rng):
    """Escape-time band texture in [0,1), seeded from the phrase.

    Three phrase-driven modifiers make every message look different:
      1. the fractal FORMULA family (Julia, Burning Ship, cubic multibrot, Tricorn, Phoenix)
      2. a KALEIDOSCOPE fold (n-fold mirror symmetry) plus a SWIRL of the plane
      3. the Julia constant, spin, zoom and band period
    Only the glow texture changes; the shapes that carry the data are untouched.
    """
    lo = max(240, size // 2)
    ys, xs = np.mgrid[0:lo, 0:lo].astype(np.float32)
    k = size / lo
    px, py = xs * k - c, ys * k - c
    rad = np.hypot(px, py) / (layout.CANVAS_HALF * R)
    th = np.arctan2(py, px)

    # --- modifier 2: swirl + kaleidoscope -------------------------------------------
    swirl = rng.choice([0, 0, rng.uniform(-2.5, 2.5)])
    th = th + swirl * np.log(rad + 0.05)
    folds = rng.choice([1, 1, 3, 4, 5, 6, 7, 8])
    if folds > 1:
        sector = 2 * math.pi / folds
        th = np.abs((th % sector) - sector / 2)        # mirror inside each sector
    th = th + rng.uniform(0, 2 * math.pi)
    zoom = rng.uniform(1.3, 2.4)
    z = (zoom * rad * np.cos(th) + 1j * zoom * rad * np.sin(th)).astype(np.complex64)

    # --- modifier 1: formula family --------------------------------------------------
    formula = rng.choice(FORMULAS)
    p = 0.0
    if formula == "multibrot3":
        cval = complex(rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6))
    elif formula == "burning_ship":
        cval = complex(rng.uniform(-1.8, -0.2), rng.uniform(-0.1, 0.9))
    elif formula == "tricorn":
        cval = complex(rng.uniform(-1.0, 0.4), rng.uniform(-0.8, 0.8))
    elif formula == "phoenix":
        cval = complex(rng.uniform(0.3, 0.6), 0.0)
        p = rng.uniform(-0.6, -0.3)
    else:
        cre, cim = rng.choice(JULIA_SEEDS)
        cval = complex(cre + rng.uniform(-0.02, 0.02), cim + rng.uniform(-0.02, 0.02))

    count = np.zeros(z.shape, np.float32)
    alive = np.ones(z.shape, bool)
    prev = np.zeros_like(z)
    for i in range(60):
        za = z[alive]
        if formula == "julia":
            zn = za * za + cval
        elif formula == "burning_ship":
            zn = (np.abs(za.real) + 1j * np.abs(za.imag)) ** 2 + cval
        elif formula == "multibrot3":
            zn = za * za * za + cval
        elif formula == "tricorn":
            zn = np.conj(za) ** 2 + cval
        else:  # phoenix: z_{n+1} = z^2 + c + p * z_{n-1}
            zn = za * za + cval + p * prev[alive]
            prev[alive] = za
        z[alive] = zn
        esc = alive & (np.abs(z) > 4)
        count[esc] = i + 1 - np.log2(np.log(np.abs(z[esc]) + 1e-9))
        alive &= ~esc
    t = (count / rng.uniform(3.5, 7.0)) % 1.0
    t[alive] = 0.5
    return cv2.resize(t, (size, size), interpolation=cv2.INTER_LINEAR)


def draw_minibrot(d, x, y, a, angle):
    """Little Mandelbrot silhouette (cardioid + bulb + antenna), scale a, pointing `angle`."""
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))

    def tr(px, py):
        return x + px * ca - py * sa, y + px * sa + py * ca
    pts = []
    for k in range(72):
        t = 2 * math.pi * k / 72
        pts.append(tr(a * (2 * math.cos(t) - math.cos(2 * t)) - a, a * (2 * math.sin(t) - math.sin(2 * t))))
    d.polygon(pts, fill=255)
    bx, by = tr(-4.1 * a, 0)
    d.ellipse([bx - 0.95 * a, by - 0.95 * a, bx + 0.95 * a, by + 0.95 * a], fill=255)
    tx, ty = tr(-7.0 * a, 0)
    d.line([tr(-5.0 * a, 0), (tx, ty)], fill=255, width=max(1, int(0.25 * a)))
    d.ellipse([tx - 0.3 * a, ty - 0.3 * a, tx + 0.3 * a, ty + 0.3 * a], fill=255)


def black_mask(symbols, R, size, rng):
    """Everything that is black: marker, data bulbs, decorative mini-brots (mode L)."""
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    c = size / 2.0

    # marker: main disc + antenna + period-2 bulb + tip dot
    (x0, y0), (x1, y1) = layout.stem_segment(c, c, R)
    d.line([(x0, y0), (x1, y1)], fill=255, width=int(layout.STEM_WIDTH * R))
    bx, by = layout.polar(c, c, layout.P2_BULB_AT * R, layout.UP)
    r = layout.P2_BULB_R * R
    d.ellipse([bx - r, by - r, bx + r, by + r], fill=255)
    r = layout.TIP_DOT_R * R
    d.ellipse([x1 - r, y1 - r, x1 + r, y1 + r], fill=255)
    d.ellipse([c - R, c - R, c + R, c + R], fill=255)

    # data bulbs
    for i, sym in enumerate(symbols):
        si, di = codec.symbol_to_glyph(sym)
        rr, dist, ang = layout.bulb_geometry(i, si, di)
        x, y = layout.polar(c, c, dist * R, ang)
        d.ellipse([x - rr * R, y - rr * R, x + rr * R, y + rr * R], fill=255)

    # decoration: mini-brots outside the data zone, never touching each other
    placed = []
    for _ in range(rng.randint(5, 9)):
        for _try in range(30):
            rad = rng.uniform(layout.DECOR_MIN_R + 0.4, layout.CANVAS_HALF - 0.9) * R
            ang = rng.uniform(0, 360)
            x, y = layout.polar(c, c, rad, ang)
            if all(math.hypot(x - px, y - py) > 1.6 * R for px, py in placed):
                placed.append((x, y))
                draw_minibrot(d, x, y, rng.uniform(0.07, 0.13) * R, ang + 180 + rng.uniform(-25, 25))
                break
    return m


def render(words, wordlist, R=DEFAULT_R, ss=SUPERSAMPLE, theme=DEFAULT_THEME):
    th = THEMES[theme]
    symbols = codec.words_to_symbols(words, wordlist)
    rng = random.Random(codec.message_seed(words))
    size = layout.canvas_size(R) * ss
    Rs = R * ss
    c = size / 2.0

    mask = np.array(black_mask(symbols, Rs, size, rng)) > 127
    dist = cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, 5) / Rs

    # fractal glow: distance field warped by a seeded fractal texture, plus bright filaments.
    # Re-roll the texture (same seeded stream) until it has real structure near the shapes,
    # so no phrase ends up with plain round halos.
    glow_zone = (dist > 0.05) & (dist < 1.4)
    for _ in range(6):
        T = julia_field(size, c, Rs, rng)
        if float(T[glow_zone].std()) > 0.22:
            break
    reach = rng.uniform(0.85, 1.35)            # modifier 3: how far the glow spreads
    u = dist / reach * (0.5 + 1.0 * T)
    xs = np.array([s for s, _ in th["ramp"]], np.float32)
    cols = np.array([col for _, col in th["ramp"]], np.float32)
    img = np.stack([np.interp(u, xs, cols[:, k]) for k in range(3)], axis=-1)
    fil = np.clip(1 - np.abs(T - 0.5) / 0.05, 0, 1) * np.exp(-dist / (0.7 * reach)) * 0.85
    img = img * (1 - fil[..., None]) + np.array(th["filament"], np.float32) * fil[..., None]

    if th["stars"]:
        # star field, kept outside the data zone
        yy, xx = np.mgrid[0:size, 0:size]
        far = np.hypot(xx - c, yy - c) > 4.2 * Rs
        n_star = int(size * size / 2500)
        sx = rng.choices(range(size), k=n_star)
        sy = rng.choices(range(size), k=n_star)
        for x, y in zip(sx, sy):
            if far[y, x]:
                b = rng.uniform(120, 255)
                img[y, x] = np.maximum(img[y, x], (b, b, b))
                if rng.random() < 0.3 and y + 1 < size and x + 1 < size:
                    img[y + 1, x] = img[y, x + 1] = np.maximum(img[y, x], (b * 0.6,) * 3)

    img[mask] = th["body"]
    out = Image.fromarray(img.astype(np.uint8))
    if ss > 1:
        out = out.resize((size // ss, size // ss), Image.LANCZOS)
    return out


def main(argv):
    if len(argv) not in (6, 7):
        print(__doc__)
        return 2
    words_csv, out_png, w1, w2, w3 = argv[1:6]
    theme = argv[6] if len(argv) == 7 else DEFAULT_THEME
    words = [w1, w2, w3]
    wordlist = codec.load_words(words_csv)
    render(words, wordlist, theme=theme).save(out_png)
    print(f"wrote {out_png}  symbols={codec.words_to_symbols(words, wordlist)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
