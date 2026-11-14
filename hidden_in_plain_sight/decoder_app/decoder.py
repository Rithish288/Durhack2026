"""Decoder: Mandelbrot-style PNG -> 3 words (+ overlay PNG showing what was read).

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
def find_marker(bgr, mask, labels, stats, polarity="dark"):
    """Return (cx, cy, R, rot_deg, label). The marker is the most disc-like dark blob
    with the largest inscribed radius; the antenna gives the rotation."""
    h, w = bgr.shape[:2]
    best = None
    for lab in range(1, stats.shape[0]):
        area = stats[lab, cv2.CC_STAT_AREA]
        if area < MIN_BLOB_FRACTION * h * w:
            continue
        blob = (labels == lab).astype(np.uint8)
        dist = cv2.distanceTransform(blob, cv2.DIST_L2, 5)
        dmax = float(dist.max())
        if dmax < 4:
            continue
        roundness = area / (math.pi * dmax * dmax)   # disc + antenna + bulb ~ 1.1..1.6
        if not (0.85 < roundness < 2.0):
            continue
        if best is None or dmax > best[0]:
            best = (dmax, blob, dist, lab)
    if best is None:
        raise DecodeError("no main body found")
    dmax, blob, dist, lab = best
    core = dist > 0.6 * dmax                      # erodes antenna and bulb away
    ys, xs = np.nonzero(core)
    cx, cy = float(xs.mean()), float(ys.mean())
    R = dmax + 0.5
    yy, xx = np.nonzero(blob)
    d = np.hypot(xx - cx, yy - cy)
    sel = (d > 1.15 * R) & (d < 2.2 * R)
    if sel.sum() < 3:
        raise DecodeError("no antenna found")
    vx, vy = (xx[sel] - cx).mean(), (yy[sel] - cy).mean()
    stem_angle = math.degrees(math.atan2(vy, vx))
    rot = (stem_angle - layout.UP + 180) % 360 - 180
    R = refine_radius(bgr, cx, cy, R, stem_angle, polarity)
    return cx, cy, R, rot, lab


def refine_radius(bgr, cx, cy, R0, stem_angle=None, polarity="dark"):
    """Sub-pixel disc radius from radial profiles (median over directions, skipping
    the antenna if given): where the body-likeness crosses 100. Used for the main
    disc AND for every bulb, so any threshold / JPEG / resampling bias cancels in the ratio."""
    gray = likeness(bgr, polarity)
    rs = np.linspace(0.5 * R0, 1.6 * R0, int(2.2 * R0) + 10)
    edges = []
    for a in np.arange(0, 360, 4.0):
        if stem_angle is not None and abs((a - stem_angle + 180) % 360 - 180) < 35:
            continue
        xs = (cx + rs * math.cos(math.radians(a))).astype(np.float32).reshape(1, -1)
        ys = (cy + rs * math.sin(math.radians(a))).astype(np.float32).reshape(1, -1)
        prof = cv2.remap(gray, xs, ys, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)[0]
        # crossing level = half-way between the inside plateau and the halo immediately
        # outside the edge (1.5-4.5 px out), so the fitted edge sits on the true boundary
        # for any theme, in grayscale and after JPEG
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
    return R if abs(R - R0) < 0.12 * R0 else R0      # sanity: never drift far from the inscribed radius


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
            if not (layout.DISTS[0] - 0.3 <= dist <= layout.DISTS[-1] + 0.3):
                continue
            ang = math.degrees(math.atan2(y - cy, x - cx))
            if abs((ang - a + 180) % 360 - 180) > SLOT_TOLERANCE_DEG:
                continue
            if best is None or area > best[0]:
                best = (area, x, y, dist)
        if best is None:
            slots.append(dict(symbol=0, size=0, dist=0, ok=False, pos=layout.polar(cx, cy, 2.7 * R, a), r_px=0))
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
    mask = body_mask(bgr, polarity)
    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
    cx, cy, R, rot, mlab = find_marker(bgr, mask, labels, stats, polarity)
    slots = read_bulbs(bgr, polarity, cx, cy, R, rot, mlab, stats, cents)
    return dict(centre=(cx, cy), R=R, rot=rot, slots=slots, polarity=polarity,
                symbols=[s["symbol"] for s in slots], words=None, errata=[], error=None)


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
    t = max(1, int(R / 25))
    WHITE, RED = ((255, 255, 255) if res["polarity"] == "dark" else (0, 255, 255)), (0, 0, 255)
    cv2.circle(out, (int(cx), int(cy)), int(R), WHITE, t)
    (x0, y0), (x1, y1) = layout.stem_segment(cx, cy, R, rot)
    cv2.line(out, (int(cx), int(cy)), (int(x1), int(y1)), RED, t)
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
