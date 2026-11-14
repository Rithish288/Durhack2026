"""Decoder: Mandelbrot PNG -> 3 words (+ overlay PNG showing what was read).

Scale and rotation come from the Mandelbrot itself: the centroids of the main cardioid
and the period-2 bulb (after erosion) are 0.825 units apart and lie on the antenna axis.

usage: python decoder.py words.csv in.png overlay.png
"""
import math
import sys

import cv2
import numpy as np

import codec
import layout

DARK_MAX_CHANNEL = 60       # body pixels are "dark" if max(R,G,B) < this ...
BRIGHT_MIN_LUMA = 200       # ... or "bright" if luminance > this (theme decides, decoder auto-detects).
                            # Luminance (not min channel) for bright bodies: JPEG keeps luma at full resolution.
MIN_BLOB_FRACTION = 0.0005
SLOT_TOLERANCE_DEG = 8.0    # how far a bulb may sit from its slot direction


class DecodeError(Exception):
    pass


def likeness(bgr, polarity):
    """0 where a pixel looks like a body, large elsewhere (works for both polarities)."""
    if polarity == "dark":
        return bgr.max(axis=2).astype(np.float32)
    luma = 0.114 * bgr[:, :, 0] + 0.587 * bgr[:, :, 1] + 0.299 * bgr[:, :, 2]
    return (255.0 - luma).astype(np.float32)


def body_mask(bgr, polarity):
    thr = DARK_MAX_CHANNEL if polarity == "dark" else 255 - BRIGHT_MIN_LUMA
    m = (likeness(bgr, polarity) < thr).astype(np.uint8)
    # fill JPEG / resampling pinholes inside bodies
    return cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))


# ---------------------------------------------------------------- marker
def landmarks(blob, dist=None):
    """Two incentres of a Mandelbrot body blob from its distance transform:
    P1 = main cardioid (global peak), P2 = period-2 bulb (next peak away from P1).
    Returns (P1, d1, P2, d2) with sub-pixel peak positions, or None."""
    if dist is None:
        dist = cv2.distanceTransform(blob, cv2.DIST_L2, 5)
    d1 = float(dist.max())
    if d1 < 4:
        return None
    y1, x1 = np.unravel_index(int(np.argmax(dist)), dist.shape)
    H, W = dist.shape
    yy, xx = np.mgrid[0:H, 0:W]

    def refine(px, py, dpk, frac, radius):
        sel = (dist > frac * dpk) & ((xx - px) ** 2 + (yy - py) ** 2 < radius * radius)
        wts = (dist[sel] - frac * dpk)
        if wts.sum() <= 0:
            return float(px), float(py)
        return float((xx[sel] * wts).sum() / wts.sum()), float((yy[sel] * wts).sum() / wts.sum())
    P1 = refine(x1, y1, d1, 0.85, 0.6 * d1)
    far = dist.copy()
    far[(xx - P1[0]) ** 2 + (yy - P1[1]) ** 2 < (1.15 * d1) ** 2] = 0
    d2 = float(far.max())
    if d2 < 2:
        return None
    y2, x2 = np.unravel_index(int(np.argmax(far)), far.shape)
    P2 = refine(x2, y2, d2, 0.8, 1.2 * d2)
    return P1, d1, P2, d2


NECK_RE = -0.75          # the cardioid and the period-2 bulb touch here
BULB_END_RE = -1.28      # the bulb ends here; beyond is the antenna


def split_centroids(blob, P1, U, ux, uy):
    """Cut the body at the neck (perpendicular to the antenna axis) and return the centroids
    of the cardioid part and the bulb part. These average thousands of pixels, so they are
    far more precise than the distance-transform peaks."""
    ys, xs = np.nonzero(blob)
    dx, dy = xs - P1[0], ys - P1[1]
    re = layout.P1_RE - (dx * ux + dy * uy) / U            # estimated Mandelbrot coordinates
    im = (dx * -uy + dy * ux) / U
    card = (re > NECK_RE) & (np.abs(im) < 0.9)
    bulb = (re <= NECK_RE) & (re > BULB_END_RE) & (np.abs(im) < 0.45)
    if card.sum() < 20 or bulb.sum() < 10:
        return None
    C1 = (float(xs[card].mean()), float(ys[card].mean()))
    C2 = (float(xs[bulb].mean()), float(ys[bulb].mean()))
    return C1, C2


def find_marker(blob, dmax):
    """Given a candidate body blob, return (ox, oy, U, rot_deg) or None.
       U   = pixels per Mandelbrot unit, rot = antenna rotation clockwise from up,
       (ox, oy) = pixel position of complex 0.
    Pass 1: distance-transform peaks (cardioid + bulb incentres) give a coarse frame.
    Pass 2: cut the body at the neck, use the two part centroids (precise)."""
    lm = landmarks(blob)
    if lm is None:
        return None
    P1, d1, P2, d2 = lm
    D = math.hypot(P2[0] - P1[0], P2[1] - P1[1])
    if not (0.3 < d2 / d1 < 0.7) or not (1.3 < D / d1 < 2.2):
        return None
    U = D / layout.PEAK_D0
    ux, uy = (P2[0] - P1[0]) / D, (P2[1] - P1[1]) / D
    for _ in range(2):
        sc = split_centroids(blob, P1, U, ux, uy)
        if sc is None:
            return None
        C1, C2 = sc
        D = math.hypot(C2[0] - C1[0], C2[1] - C1[1])
        if D < 3:
            return None
        ux, uy = (C2[0] - C1[0]) / D, (C2[1] - C1[1]) / D
        U = D / layout.D0
        P1 = (C1[0] + (layout.P1_RE - layout.C1_RE) * U * -ux, C1[1] + (layout.P1_RE - layout.C1_RE) * U * -uy)
    ox, oy = C1[0] + layout.C1_RE * U * ux, C1[1] + layout.C1_RE * U * uy
    rot = (math.degrees(math.atan2(uy, ux)) - layout.UP + 180) % 360 - 180
    return ox, oy, U, rot


def refine_radius(bgr, cx, cy, R0, stem_angle=None, polarity="dark"):
    """Sub-pixel radius of a round body from radial profiles: the median crossing between
    the inside plateau and the halo immediately outside the edge (works for any theme,
    grayscale and JPEG). Used for every satellite bulb."""
    gray = likeness(bgr, polarity)
    rs = np.linspace(0.5 * R0, 1.6 * R0, int(2.2 * R0) + 10)
    edges = []
    for a in np.arange(0, 360, 4.0):
        xs = (cx + rs * math.cos(math.radians(a))).astype(np.float32).reshape(1, -1)
        ys = (cy + rs * math.sin(math.radians(a))).astype(np.float32).reshape(1, -1)
        prof = cv2.remap(gray, xs, ys, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)[0]
        p_in = float(np.median(prof[rs < 0.8 * R0]))
        near = (rs > R0 + 1.5) & (rs < R0 + 4.5)
        if near.sum() < 2:
            continue
        p_out = float(np.median(prof[near]))
        if p_out - p_in < 30:
            continue
        level = 0.5 * (p_in + p_out)
        above = np.nonzero(prof > level)[0]
        if len(above) == 0 or above[0] == 0:
            continue
        j = above[0]
        f = (level - prof[j - 1]) / max(1e-6, prof[j] - prof[j - 1])
        edges.append(rs[j - 1] + f * (rs[j] - rs[j - 1]))
    if len(edges) < 10:
        return R0
    R = float(np.median(edges))
    return R if abs(R - R0) < 0.12 * R0 else R0


# ---------------------------------------------------------------- bulbs
def read_bulbs(bgr, polarity, cx, cy, R, rot, marker_label, stats, cents):
    """For each slot pick the dark blob sitting in that direction; size and distance -> symbol."""
    min_area = 0.3 * math.pi * (layout.SIZES[0] * R) ** 2
    max_area = 2.5 * math.pi * (layout.SIZES[-1] * R) ** 2
    slots = []
    for i in range(layout.N_DATA):
        a = layout.data_angle(i) + rot
        best = None
        for lab in range(1, stats.shape[0]):
            if lab == marker_label:
                continue
            area = stats[lab, cv2.CC_STAT_AREA]
            if not (min_area <= area <= max_area):
                continue
            x, y = cents[lab]
            dist = math.hypot(x - cx, y - cy) / R
            if not (layout.DISTS[0] - 0.12 <= dist <= layout.DISTS[-1] + 0.12):
                continue
            ang = math.degrees(math.atan2(y - cy, x - cx))
            if abs((ang - a + 180) % 360 - 180) > SLOT_TOLERANCE_DEG:
                continue
            if best is None or area > best[0]:
                best = (area, x, y, dist)
        if best is None:
            slots.append(dict(symbol=0, size=0, dist=0, ok=False, pos=layout.polar(cx, cy, 2.0 * R, a), r_px=0))
            continue
        area, x, y, dist = best
        r_px = refine_radius(bgr, x, y, math.sqrt(area / math.pi), None, polarity)
        r = r_px / R
        si = int(np.argmin([abs(r - s) for s in layout.SIZES]))
        di = int(np.argmin([abs(dist - s) for s in layout.DISTS]))
        slots.append(dict(symbol=codec.glyph_to_symbol(si, di), size=si, dist=di, ok=True,
                          pos=(x, y), r_px=r_px, r=round(r, 3), d=round(dist, 3)))
    return slots


def _decode_polarity(bgr, polarity):
    """Try the three most disc-like big blobs as the Mandelbrot body; keep the reading
    that finds the most satellites."""
    mask = body_mask(bgr, polarity)
    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
    h, w = bgr.shape[:2]
    cands = []
    for lab in range(1, n):
        if stats[lab, cv2.CC_STAT_AREA] < MIN_BLOB_FRACTION * h * w:
            continue
        blob = (labels == lab).astype(np.uint8)
        dmax = float(cv2.distanceTransform(blob, cv2.DIST_L2, 5).max())
        if dmax >= 4:
            cands.append((dmax, lab, blob))
    cands.sort(key=lambda t: -t[0])
    best = None
    for dmax, lab, blob in cands[:3]:
        mk = find_marker(blob, dmax)
        if mk is None:
            continue
        ox, oy, U, rot = mk
        slots = read_bulbs(bgr, polarity, ox, oy, U, rot, lab, stats, cents)
        found = sum(s["ok"] for s in slots)
        if best is None or found > best[0]:
            best = (found, dict(centre=(ox, oy), R=U, rot=rot, slots=slots, polarity=polarity,
                                symbols=[s["symbol"] for s in slots], words=None, errata=[], error=None))
    if best is None:
        raise DecodeError("no Mandelbrot body found")
    return best[1]


def decode_image(bgr, wordlist):
    """Decode a BGR numpy image. The decoder does not know the theme: it tries dark
    bodies and bright bodies and keeps whichever finds more bulbs in their slots."""
    best, err = None, None
    for polarity in ("dark", "bright"):
        try:
            res = _decode_polarity(bgr, polarity)
        except DecodeError as e:
            err = e
            continue
        found = sum(s["ok"] for s in res["slots"])
        if best is None or found > best[0]:
            best = (found, res)
    if best is None:
        raise DecodeError(str(err))
    result = best[1]
    found = sum(s["ok"] for s in result["slots"])
    if found < layout.N_DATA - 3:
        # Reed-Solomon can only repair 3 symbols; with more bulbs missing it could
        # "succeed" on garbage, so refuse instead of guessing
        result["error"] = f"only {found} of {layout.N_DATA} bulbs found"
        return result
    try:
        result["words"], result["errata"] = codec.symbols_to_words(result["symbols"], wordlist)
    except ValueError as e:
        result["error"] = str(e)
    return result


# ---------------------------------------------------------------- overlay
def draw_overlay(bgr, res):
    out = bgr.copy()
    cx, cy = res["centre"]
    R, rot = res["R"], res["rot"]
    t = max(1, int(R / 35))
    WHITE, RED = ((255, 255, 255) if res["polarity"] == "dark" else (0, 255, 255)), (0, 0, 255)
    # landmarks: origin, cardioid centroid, period-2 bulb centroid, antenna direction
    c1 = layout.polar(cx, cy, -layout.C1_RE * R, layout.UP + rot)
    c2 = layout.polar(cx, cy, -layout.C2_RE * R, layout.UP + rot)
    cv2.line(out, (int(c1[0]), int(c1[1])), (int(c2[0]), int(c2[1])), RED, t)
    for p in (c1, c2):
        cv2.circle(out, (int(p[0]), int(p[1])), 3 * t, RED, -1)
    cv2.drawMarker(out, (int(cx), int(cy)), WHITE, cv2.MARKER_CROSS, 6 * t, t)
    errata = set(res["errata"])
    for i, s in enumerate(res["slots"]):
        a = layout.data_angle(i) + rot
        col = RED if i in errata else WHITE
        p0 = layout.polar(cx, cy, (layout.DISTS[0] - 0.35) * R, a)
        p1 = layout.polar(cx, cy, (layout.DISTS[-1] + 0.35) * R, a)
        cv2.line(out, (int(p0[0]), int(p0[1])), (int(p1[0]), int(p1[1])), (120, 120, 120), 1)
        x, y = s["pos"]
        if s["ok"]:
            cv2.circle(out, (int(x), int(y)), int(s["r_px"]) + 3, col, t)
        label = f"{i}:s{s['size']}/d{s['dist']}" + (" X" if i in errata else "")
        lx, ly = layout.polar(cx, cy, (layout.DISTS[-1] + 0.75) * R, a)
        fs = R / 120.0
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, fs, 1)
        p = (int(lx - tw / 2), int(ly + th / 2))
        cv2.rectangle(out, (p[0] - 2, p[1] - th - 2), (p[0] + tw + 2, p[1] + 3), (0, 0, 60), -1)
        cv2.putText(out, label, p, cv2.FONT_HERSHEY_SIMPLEX, fs, col, 1, cv2.LINE_AA)
    if res["words"]:
        text = " ".join(res["words"])
        if errata:
            text += f"   (corrected {len(errata)} bulb{'s' if len(errata) > 1 else ''})"
    else:
        text = f"FAILED: {res['error']}"
    fs = max(0.5, out.shape[1] / 1100.0)
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, fs, 2)
    cv2.rectangle(out, (0, 0), (tw + 20, th + 20), (0, 0, 60), -1)
    cv2.putText(out, text, (10, th + 10), cv2.FONT_HERSHEY_SIMPLEX, fs, WHITE, 2, cv2.LINE_AA)
    return out


def main(argv):
    if len(argv) != 4:
        print(__doc__)
        return 2
    words_csv, in_png, overlay_png = argv[1:]
    wordlist = codec.load_words(words_csv)
    bgr = cv2.imread(in_png, cv2.IMREAD_COLOR)
    if bgr is None:
        print(f"cannot read {in_png}")
        return 1
    try:
        res = decode_image(bgr, wordlist)
    except DecodeError as e:
        print(f"FAILED: {e}")
        return 1
    cv2.imwrite(overlay_png, draw_overlay(bgr, res))
    print(f"symbols read: {res['symbols']}")
    if res["words"]:
        print(" ".join(res["words"]))
        if res["errata"]:
            print(f"corrected bulbs: {res['errata']}")
        return 0
    print(f"FAILED: {res['error']}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
