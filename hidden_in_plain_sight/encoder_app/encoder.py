"""Encoder: 3 words -> fractal PNG. The words drive EVERYTHING decorative.

usage: python encoder.py words.csv out.png apple river garden [theme]
themes: auto (default: palette, fractal, shapes all chosen by the words),
        mandelbrot, space, ember, emerald (fixed presets)

Decoder contract (the only rule the art must obey):
  * data shapes ("bodies") are either very dark (max channel < 60) or very bright (luma > 200)
  * every other colour stays clear of that range:
      dark bodies   -> all other colours have max channel >= 110
      bright bodies -> all other colours have luma <= 160
"""
import colorsys
import math
import random
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

import codec
import layout

DEFAULT_U = 70          # pixels per Mandelbrot unit in the output image
DEFAULT_R = DEFAULT_U   # kept for test.py compatibility
SUPERSAMPLE = 2
DEFAULT_THEME = "auto"

JULIA_SEEDS = [(-0.8, 0.156), (-0.4, 0.6), (0.285, 0.01), (-0.70176, -0.3842),
               (-0.7269, 0.1889), (0.355, 0.355), (-0.1, 0.651), (-0.835, -0.2321)]

# fixed presets (polarity: "dark" = dark bodies, "bright" = bright bodies)
THEMES = {
    "mandelbrot": dict(polarity="dark", bg=(0, 0, 93), body=(0, 0, 0), filament=(255, 255, 255), stars=False,
                       ramp=[(0.00, (255, 255, 255)), (0.06, (210, 248, 255)), (0.18, (90, 180, 255)),
                             (0.40, (25, 50, 225)), (0.75, (0, 0, 150)), (1.30, (0, 0, 93))],
                       decor="minibrot", rays=0.0, clouds=0.0),
    "space": dict(polarity="bright", bg=(0, 0, 0), body=(255, 228, 236), filament=(120, 170, 255), stars=True,
                  ramp=[(0.00, (255, 120, 170)), (0.10, (150, 120, 230)), (0.25, (90, 130, 255)),
                        (0.55, (30, 60, 190)), (0.95, (8, 14, 60)), (1.40, (0, 0, 0))],
                  decor="minibrot", rays=0.0, clouds=0.0),
    "ember": dict(polarity="dark", bg=(90, 12, 0), body=(0, 0, 0), filament=(255, 250, 200), stars=False,
                  ramp=[(0.00, (255, 255, 240)), (0.06, (255, 240, 120)), (0.18, (255, 150, 0)),
                        (0.40, (215, 40, 0)), (0.75, (140, 20, 0)), (1.30, (90, 12, 0))],
                  decor="minibrot", rays=0.0, clouds=0.0),
    "emerald": dict(polarity="dark", bg=(0, 85, 45), body=(0, 0, 0), filament=(240, 255, 245), stars=False,
                    ramp=[(0.00, (255, 255, 255)), (0.06, (200, 255, 220)), (0.18, (60, 230, 140)),
                          (0.40, (0, 160, 90)), (0.75, (0, 110, 60)), (1.30, (0, 85, 45))],
                    decor="minibrot", rays=0.0, clouds=0.0),
}
BG = THEMES["mandelbrot"]["bg"]


# ---------------------------------------------------------------- colour helpers
def _hsv(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0, min(1, s)), max(0, min(1, v)))
    return int(r * 255), int(g * 255), int(b * 255)


def _luma(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _safe(c, polarity):
    """Push a colour out of the body range so the decoder never mistakes it for a body."""
    c = list(c)
    if polarity == "dark":
        m = max(c)
        if m < 110:
            k = 110.0 / max(m, 1)
            c = [min(255, int(v * k)) for v in c]
    else:
        L = _luma(c)
        if L > 160:
            k = 160.0 / L
            c = [int(v * k) for v in c]
    return tuple(c)


def make_style(rng):
    """A complete visual style chosen from the phrase seed."""
    polarity = rng.choice(["dark", "dark", "bright"])
    h0 = rng.random()
    scheme = rng.choice(["analogous", "complementary", "triadic", "split", "mono"])
    if scheme == "analogous":
        hues = [h0, h0 + 0.07, h0 + 0.14]
    elif scheme == "complementary":
        hues = [h0, h0 + 0.5, h0 + 0.05]
    elif scheme == "triadic":
        hues = [h0, h0 + 0.333, h0 + 0.667]
    elif scheme == "split":
        hues = [h0, h0 + 0.42, h0 + 0.58]
    else:
        hues = [h0, h0, h0 + 0.03]
    hA, hB, hC = hues
    sat = rng.uniform(0.7, 1.0)

    if polarity == "dark":
        body = (0, 0, 0)
        mode = rng.choice(["deep", "deep", "mid", "light"])
        if mode == "light":           # dark fractal on a pale paper-like field
            bg = _hsv(hC, rng.uniform(0.05, 0.2), rng.uniform(0.9, 0.98))
            ramp = [(0.00, _hsv(hA, 0.95, 0.55)), (0.07, _hsv(hA, sat, 0.95)), (0.22, _hsv(hB, sat * 0.8, 1.0)),
                    (0.5, _hsv(hC, 0.3, 0.95)), (1.3, bg)]
            filament = _hsv(hB, 0.9, 0.6)
        elif mode == "mid":
            bg = _hsv(hC, rng.uniform(0.5, 0.9), rng.uniform(0.45, 0.6))
            ramp = [(0.00, (255, 255, 255)), (0.06, _hsv(hA, 0.3, 1.0)), (0.2, _hsv(hA, sat, 1.0)),
                    (0.45, _hsv(hB, sat, 0.85)), (0.9, _hsv(hC, 0.8, 0.6)), (1.4, bg)]
            filament = _hsv(hB, 0.2, 1.0)
        else:
            bg = _hsv(hC, rng.uniform(0.7, 1.0), rng.uniform(0.38, 0.5))
            ramp = [(0.00, (255, 255, 255)), (0.06, _hsv(hA, 0.25, 1.0)), (0.18, _hsv(hA, sat, 1.0)),
                    (0.40, _hsv(hB, sat, 0.9)), (0.75, _hsv(hB, 0.9, 0.55)), (1.30, bg)]
            filament = _hsv(hC, 0.15, 1.0)
        stars = mode == "deep" and rng.random() < 0.4
    else:
        body = _hsv(hA, rng.uniform(0.0, 0.12), 1.0)        # warm/cool white core
        mode = rng.choice(["black", "black", "mid"])
        if mode == "black":
            bg = _hsv(hC, 0.9, rng.uniform(0.0, 0.08))
        else:
            bg = _hsv(hC, rng.uniform(0.6, 0.9), rng.uniform(0.3, 0.42))
        ramp = [(0.00, _hsv(hA, sat, 0.75)), (0.10, _hsv(hB, sat, 0.7)), (0.25, _hsv(hB, sat, 0.6)),
                (0.55, _hsv(hC, 0.9, 0.45)), (0.95, _hsv(hC, 0.9, 0.2)), (1.40, bg)]
        filament = _hsv(hB, 0.6, 0.65)
        stars = mode == "black" and rng.random() < 0.7

    bg = _safe(bg, polarity)
    ramp = [(d, _safe(c, polarity)) for d, c in ramp]
    ramp[-1] = (ramp[-1][0], bg)
    filament = _safe(filament, polarity)
    return dict(polarity=polarity, bg=bg, body=body, filament=filament, stars=stars, ramp=ramp,
                decor=rng.choice(["minibrot", "spiral", "rings", "stars", "comets", "mixed"]),
                rays=rng.choice([0.0, 0.0, rng.uniform(0.25, 0.6)]),
                clouds=rng.choice([0.0, rng.uniform(0.3, 0.7)]))


def style_for(words, theme=DEFAULT_THEME):
    """The style a phrase will be rendered with (deterministic). test.py uses this."""
    rng = random.Random(codec.message_seed(words))
    if theme == "auto":
        return make_style(rng)
    return THEMES[theme]


# ---------------------------------------------------------------- fractal textures
FORMULAS = ["julia", "burning_ship", "multibrot3", "tricorn", "phoenix", "celtic", "lambda", "newton", "sine"]


def _fbm(lo, rng, octaves=4):
    """Cheap value-noise fbm in [0,1] for cloudy modulation."""
    out = np.zeros((lo, lo), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        n = 4 * (2 ** o)
        grid = np.array([[rng.random() for _ in range(n + 1)] for _ in range(n + 1)], np.float32)
        out += amp * cv2.resize(grid, (lo, lo), interpolation=cv2.INTER_CUBIC)
        total += amp
        amp *= 0.5
    out /= total
    return np.clip((out - out.min()) / max(1e-6, out.max() - out.min()), 0, 1)


def fractal_field(size, c, R, rng):
    """Escape-time / basin texture in [0,1), fully seeded by the phrase."""
    lo = max(240, size // 2)
    ys, xs = np.mgrid[0:lo, 0:lo].astype(np.float32)
    k = size / lo
    px, py = xs * k - c, ys * k - c
    rad = np.hypot(px, py) / (layout.CANVAS_HALF * R)
    th = np.arctan2(py, px)

    # kaleidoscope + swirl + off-centre
    swirl = rng.choice([0, 0, rng.uniform(-2.5, 2.5)])
    th = th + swirl * np.log(rad + 0.05)
    folds = rng.choice([1, 1, 2, 3, 4, 5, 6, 7, 8, 12])
    if folds > 1:
        sector = 2 * math.pi / folds
        th = np.abs((th % sector) - sector / 2)
    th = th + rng.uniform(0, 2 * math.pi)
    zoom = rng.uniform(1.2, 2.6)
    zr = zoom * rad * np.cos(th) + rng.uniform(-0.4, 0.4)
    zi = zoom * rad * np.sin(th) + rng.uniform(-0.4, 0.4)
    z = (zr + 1j * zi).astype(np.complex64)

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
    elif formula == "celtic":
        cval = complex(rng.uniform(-1.2, 0.2), rng.uniform(-0.8, 0.8))
    elif formula == "lambda":
        cval = complex(rng.uniform(0.5, 1.2), rng.uniform(-0.9, 0.9)) + 1.0
    elif formula == "sine":
        cval = complex(rng.uniform(0.6, 1.4), rng.uniform(-0.4, 0.4))
        z = z * 2.0
    elif formula == "newton":
        cval = 0
    else:
        cre, cim = rng.choice(JULIA_SEEDS)
        cval = complex(cre + rng.uniform(-0.02, 0.02), cim + rng.uniform(-0.02, 0.02))

    n_iter = 32 if formula == "newton" else 60
    count = np.zeros(z.shape, np.float32)
    alive = np.ones(z.shape, bool)
    prev = np.zeros_like(z)
    with np.errstate(all="ignore"):
        for i in range(n_iter):
            za = z[alive]
            if formula == "julia":
                zn = za * za + cval
            elif formula == "burning_ship":
                zn = (np.abs(za.real) + 1j * np.abs(za.imag)) ** 2 + cval
            elif formula == "multibrot3":
                zn = za * za * za + cval
            elif formula == "tricorn":
                zn = np.conj(za) ** 2 + cval
            elif formula == "phoenix":
                zn = za * za + cval + p * prev[alive]
                prev[alive] = za
            elif formula == "celtic":
                sq = za * za
                zn = (np.abs(sq.real) + 1j * sq.imag) + cval
            elif formula == "lambda":
                zn = cval * za * (1 - za)
            elif formula == "sine":
                zn = cval * np.sin(za)
            else:  # newton for z^3 - 1
                zn = za - (za ** 3 - 1) / (3 * za ** 2 + 1e-9)
            z[alive] = zn
            if formula == "newton":
                done = alive & (np.abs(z ** 3 - 1) < 1e-3)
                count[done] = i
                alive &= ~done
            else:
                esc = alive & ((np.abs(z.imag) > 50) if formula == "sine" else (np.abs(z) > 4))
                count[esc] = i + 1 - np.log2(np.log(np.abs(z[esc]) + 1e-9) + 1e-9)
                alive &= ~esc
    if formula == "newton":
        root = (np.angle(z) / (2 * math.pi)) % 1.0           # which of the 3 roots -> 3 bands
        t = (np.round(root * 3) / 3 + 0.12 * (count / n_iter)) % 1.0
        t[alive] = 0.5
    else:
        t = (count / rng.uniform(3.5, 7.0)) % 1.0
        t[alive] = 0.5
    t = np.nan_to_num(t, nan=0.5)
    return cv2.resize(t.astype(np.float32), (size, size), interpolation=cv2.INTER_LINEAR)


# ---------------------------------------------------------------- decorative shapes (body colour)
def draw_minibrot(d, x, y, a, angle):
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))

    def tr(px, py):
        return x + px * ca - py * sa, y + px * sa + py * ca
    pts = [tr(a * (2 * math.cos(t) - math.cos(2 * t)) - a, a * (2 * math.sin(t) - math.sin(2 * t)))
           for t in (2 * math.pi * k / 72 for k in range(72))]
    d.polygon(pts, fill=255)
    bx, by = tr(-4.1 * a, 0)
    d.ellipse([bx - 0.95 * a, by - 0.95 * a, bx + 0.95 * a, by + 0.95 * a], fill=255)
    tx, ty = tr(-7.0 * a, 0)
    d.line([tr(-5.0 * a, 0), (tx, ty)], fill=255, width=max(1, int(0.25 * a)))
    d.ellipse([tx - 0.3 * a, ty - 0.3 * a, tx + 0.3 * a, ty + 0.3 * a], fill=255)


def draw_spiral(d, x, y, a, angle, rng):
    pts = []
    turns = rng.uniform(1.5, 3.0)
    for k in range(80):
        t = k / 79.0
        r = a * 0.15 + a * 1.6 * t
        pts.append(layout.polar(x, y, r, angle + t * 360 * turns))
    d.line(pts, fill=255, width=max(1, int(0.22 * a)), joint="curve")
    d.ellipse([pts[-1][0] - 0.3 * a, pts[-1][1] - 0.3 * a, pts[-1][0] + 0.3 * a, pts[-1][1] + 0.3 * a], fill=255)


def draw_ring(d, x, y, a, rng):
    w = max(1, int(rng.uniform(0.12, 0.3) * a))
    r = a * rng.uniform(1.0, 1.8)
    d.ellipse([x - r, y - r, x + r, y + r], outline=255, width=w)
    if rng.random() < 0.5:                       # a tiny moon on the ring
        mx, my = layout.polar(x, y, r, rng.uniform(0, 360))
        d.ellipse([mx - 0.35 * a, my - 0.35 * a, mx + 0.35 * a, my + 0.35 * a], fill=255)


def draw_star(d, x, y, a, angle, rng):
    n = rng.choice([4, 5, 6, 8])
    pts = []
    for k in range(2 * n):
        r = a * 1.6 if k % 2 == 0 else a * rng.uniform(0.4, 0.7)
        pts.append(layout.polar(x, y, r, angle + k * 180.0 / n))
    d.polygon(pts, fill=255)


def draw_comet(d, x, y, a, angle):
    hx, hy = x, y
    pts = [layout.polar(hx, hy, a * 0.8, angle + 90), layout.polar(hx, hy, a * 4.0, angle + 180),
           layout.polar(hx, hy, a * 0.8, angle - 90)]
    d.polygon(pts, fill=255)
    d.ellipse([hx - 0.8 * a, hy - 0.8 * a, hx + 0.8 * a, hy + 0.8 * a], fill=255)


def mandelbrot(size, U, ss):
    """Interior mask (full res, bool) and smooth escape band (full res, 0..1) of the real
    Mandelbrot set, antenna up: re = (y - c) / U, im = (x - c) / U. Computed at 1x."""
    lo = size // ss
    c = lo / 2.0
    u = U / ss
    ys, xs = np.mgrid[0:lo, 0:lo].astype(np.float32)
    C = ((ys - c) / u + 1j * (xs - c) / u).astype(np.complex64)
    z = np.zeros_like(C)
    alive = np.ones(C.shape, bool)
    count = np.zeros(C.shape, np.float32)
    n_iter = 160
    with np.errstate(all="ignore"):
        for i in range(n_iter):
            z[alive] = z[alive] ** 2 + C[alive]
            esc = alive & (np.abs(z) > 4)
            count[esc] = i + 1 - np.log2(np.log(np.abs(z[esc]) + 1e-9) + 1e-9)
            alive &= ~esc
    band = np.log1p(np.nan_to_num(count)) / math.log1p(n_iter)
    band[alive] = 1.0
    # keep the body only near the origin + the antenna strip (satellites live further out)
    keep = (np.abs(C) < layout.MANDEL_CLIP_R) | ((np.abs(C.imag) < layout.ANTENNA_HALF_WIDTH) & (C.real < 0))
    interior = (alive & keep).astype(np.float32)
    interior = cv2.resize(interior, (size, size), interpolation=cv2.INTER_LINEAR) > 0.5
    band = cv2.resize(band, (size, size), interpolation=cv2.INTER_LINEAR)
    return interior, band


def body_mask(symbols, U, size, rng, decor):
    """Satellites + decoration in body colour (mode L). The Mandelbrot body is added separately."""
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    c = size / 2.0
    for i, sym in enumerate(symbols):
        si, di = codec.symbol_to_glyph(sym)
        rr, dist, ang = layout.bulb_geometry(i, si, di)
        x, y = layout.polar(c, c, dist * U, ang)
        d.ellipse([x - rr * U, y - rr * U, x + rr * U, y + rr * U], fill=255)

    placed = []
    for _ in range(rng.randint(4, 10)):
        kind = decor if decor != "mixed" else rng.choice(["minibrot", "spiral", "rings", "stars", "comets"])
        for _try in range(30):
            rad = rng.uniform(layout.DECOR_MIN_R + 0.3, layout.CANVAS_HALF - 0.6) * U
            ang = rng.uniform(0, 360)
            x, y = layout.polar(c, c, rad, ang)
            if all(math.hypot(x - px, y - py) > 1.1 * U for px, py in placed):
                placed.append((x, y))
                a = rng.uniform(0.045, 0.085) * U
                if kind == "minibrot":
                    draw_minibrot(d, x, y, a, ang + 180 + rng.uniform(-25, 25))
                elif kind == "spiral":
                    draw_spiral(d, x, y, a * 1.3, ang, rng)
                elif kind == "rings":
                    draw_ring(d, x, y, a * 1.6, rng)
                elif kind == "stars":
                    draw_star(d, x, y, a * 1.1, ang, rng)
                else:
                    draw_comet(d, x, y, a * 0.9, ang + rng.uniform(-30, 30))
                break
    if rng.random() < 0.35:
        rr = rng.uniform(layout.DECOR_MIN_R + 0.2, layout.CANVAS_HALF - 0.3) * U
        d.ellipse([c - rr, c - rr, c + rr, c + rr], outline=255, width=max(1, int(0.02 * U)))
    return m


# ---------------------------------------------------------------- render
def render(words, wordlist, U=DEFAULT_U, ss=SUPERSAMPLE, theme=DEFAULT_THEME):
    symbols = codec.words_to_symbols(words, wordlist)
    rng = random.Random(codec.message_seed(words))
    st = make_style(rng) if theme == "auto" else THEMES[theme]
    size = layout.canvas_size(U) * ss
    Us = U * ss
    c = size / 2.0

    interior, band = mandelbrot(size, Us, ss)
    mask = (np.array(body_mask(symbols, Us, size, rng, st["decor"])) > 127) | interior
    dist = cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, 5) / Us

    # seeded fractal texture (re-rolled until it has structure near the shapes)
    glow_zone = (dist > 0.03) & (dist < 1.0)
    for _ in range(6):
        T = fractal_field(size, c, Us, rng)
        if float(T[glow_zone].std()) > 0.22:
            break
    reach = rng.uniform(0.6, 1.0)
    shape = 0.5 + 1.0 * T
    if st["rays"]:
        yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
        ang = np.arctan2(yy - c, xx - c)
        shape = shape * (1 + st["rays"] * np.sin(rng.choice([3, 5, 6, 8, 12]) * ang + rng.uniform(0, 6.3)))
    if st["clouds"]:
        N = cv2.resize(_fbm(size // 4, rng), (size, size), interpolation=cv2.INTER_LINEAR)
        shape = shape * (1 - st["clouds"] + 2 * st["clouds"] * N)
    u_dist = dist / reach * shape
    # authentic Mandelbrot fringe: bright where the escape count is high (near the set)
    u_mandel = 1.3 * (1 - band) ** 2 * rng.uniform(0.9, 1.6)
    u = np.minimum(u_dist, u_mandel)

    xs = np.array([s for s, _ in st["ramp"]], np.float32)
    cols = np.array([col for _, col in st["ramp"]], np.float32)
    img = np.stack([np.interp(u, xs, cols[:, k]) for k in range(3)], axis=-1)
    fil = np.clip(1 - np.abs(T - 0.5) / 0.05, 0, 1) * np.exp(-dist / (0.5 * reach)) * 0.85
    img = img * (1 - fil[..., None]) + np.array(st["filament"], np.float32) * fil[..., None]

    if st["stars"]:
        yy, xx = np.mgrid[0:size, 0:size]
        far = np.hypot(xx - c, yy - c) > 2.9 * Us
        n_star = int(size * size / 2500)
        for x, y in zip(rng.choices(range(size), k=n_star), rng.choices(range(size), k=n_star)):
            if far[y, x]:
                b = rng.uniform(120, 255)
                img[y, x] = np.maximum(img[y, x], (b, b, b))
                if rng.random() < 0.3 and y + 1 < size and x + 1 < size:
                    img[y + 1, x] = img[y, x + 1] = np.maximum(img[y, x], (b * 0.6,) * 3)

    img[mask] = st["body"]
    out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    if ss > 1:
        out = out.resize((size // ss, size // ss), Image.LANCZOS)
    return out


def main(argv):
    if len(argv) not in (6, 7):
        print(__doc__)
        return 2
    words_csv, out_png, w1, w2, w3 = argv[1:6]
    theme = argv[6] if len(argv) == 7 else DEFAULT_THEME
    if theme != "auto" and theme not in THEMES:
        print(f"unknown theme {theme!r}; use auto or one of {list(THEMES)}")
        return 2
    wordlist = codec.load_words(words_csv)
    render([w1, w2, w3], wordlist, theme=theme).save(out_png)
    print(f"wrote {out_png}  symbols={codec.words_to_symbols([w1, w2, w3], wordlist)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
