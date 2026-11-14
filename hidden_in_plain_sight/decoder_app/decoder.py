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
EDGE_ADDBACK_PX = 0.35      # thresholding sits slightly inside the true edge
MAX_HOLE_FRACTION = 0.0015  # holes inside bodies larger than this fraction of the image are not filled


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
    # close JPEG / resampling pinholes, then fill every enclosed hole: bodies may carry
    # a pattern inside, and JPEG can lift a few of those pixels over the threshold
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    inv = cv2.copyMakeBorder((1 - m).copy(), 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=1)
    cv2.floodFill(inv, None, (0, 0), 2)              # mark background reachable from the border
    holes = (inv[1:-1, 1:-1] == 1).astype(np.uint8)  # non-body pixels not reachable = holes
    # only fill SMALL holes (pinholes inside bodies); a big enclosed region (e.g. inside a
    # decorative ring drawn in body colour) is background, not body
    n, labels, stats, _ = cv2.connectedComponentsWithStats(holes, connectivity=4)
    limit = MAX_HOLE_FRACTION * m.shape[0] * m.shape[1]
    for lab in range(1, n):
        if stats[lab, cv2.CC_STAT_AREA] < limit:
            m[labels == lab] = 1
    return m


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
    rot = (math.degrees(math.atan2(uy, ux)) - layout.UP + 180) % 360 - 180
    r = math.radians(rot)
    Rm = np.array([[math.cos(r), -math.sin(r)], [math.sin(r), math.cos(r)]])   # canonical (x=im,y=re) -> image

    # --- affine correction for photos: the eroded mother is a known shape, so its measured
    # covariance gives the stretch / shear S of the picture (S = U * I for a clean file)
    dist = cv2.distanceTransform(blob, cv2.DIST_L2, 5)
    region = dist > layout.ER_FRAC * dmax
    ys, xs = np.nonzero(region)
    cm = np.array([xs.mean(), ys.mean()])
    cov_px = np.cov(np.vstack([xs - cm[0], ys - cm[1]]))
    S0 = np.array(layout.ER_COV)
    M = Rm.T @ cov_px @ Rm
    S = _solve_affine(S0, M)
    ev = np.linalg.eigvalsh(S)
    stretch = float(ev.max() / max(ev.min(), 1e-9)) if ev.min() > 0 else 99.0
    if ev.min() <= 0 or stretch > 1.3 or stretch < 1.03:
        S = U * np.eye(2)                                  # clean file (or implausible): pure similarity
    else:
        S = S * (U / math.sqrt(float(np.linalg.det(S))))  # keep the precise centroid-based scale,
                                                          # use the covariance only for the anisotropy
    q1 = np.array([0.0, layout.C1_RE])                    # the cardioid-part centroid in canonical coords
    O = np.array(C1) - Rm @ S @ q1
    detS = float(np.linalg.det(S))
    U_eff = math.sqrt(detS)
    A = np.linalg.inv(S) @ Rm.T
    return dict(ox=float(O[0]), oy=float(O[1]), U=U_eff, rot=rot, R=Rm, S=S, Sinv=np.linalg.inv(S),
                C1=(float(C1[0]), float(C1[1])), C2=(float(C2[0]), float(C2[1])),
                # image px -> canonical units, and the local area scale (px^2 per unit^2) at a canonical point
                to_canon=lambda p, A=A, O=O: A @ (np.asarray(p, float) - O),
                area_scale=lambda q, detS=detS: detS,
                stretch=float(np.linalg.eigvalsh(S).max() / np.linalg.eigvalsh(S).min()))


def angular_rms(mk, slots):
    """RMS deviation (degrees) of the found babies from their slot directions: ~0 for a clean
    file, degrees for a photograph taken at an angle."""
    errs = []
    for i, s in enumerate(slots):
        if not s["ok"]:
            continue
        q = mk["to_canon"](s["pos"])
        ang = math.degrees(math.atan2(q[1], q[0]))
        errs.append((ang - layout.data_angle(i) + 180) % 360 - 180)
    return float(np.sqrt(np.mean(np.square(errs)))) if errs else 0.0


def refine_homography(mk, slots):
    """Photos: fit a full homography (canonical units -> image px) from the mother's two
    landmarks plus every found baby, whose DIRECTION is known exactly (slot angle) even though
    its distance is data. Returns a new marker dict with perspective-aware mappings, or mk."""
    src, dst = [], []
    src += [(0.0, layout.C1_RE), (0.0, layout.C2_RE)]
    dst += [mk["C1"], mk["C2"]]
    for i, s in enumerate(slots):
        if not s["ok"]:
            continue
        a = math.radians(layout.data_angle(i))
        src.append((s["d"] * math.cos(a), s["d"] * math.sin(a)))     # canonical (x=im, y=re)
        dst.append(s["pos"])
    if len(src) < 8:
        return mk
    H, _ = cv2.findHomography(np.float32(src), np.float32(dst), 0)
    if H is None:
        return mk
    Hi = np.linalg.inv(H)

    def to_canon(p, Hi=Hi):
        v = Hi @ np.array([p[0], p[1], 1.0])
        return v[:2] / v[2]

    def area_scale(q, H=H):
        eps = 1e-3
        def fwd(x, y):
            v = H @ np.array([x, y, 1.0])
            return v[:2] / v[2]
        jx = (fwd(q[0] + eps, q[1]) - fwd(q[0] - eps, q[1])) / (2 * eps)
        jy = (fwd(q[0], q[1] + eps) - fwd(q[0], q[1] - eps)) / (2 * eps)
        return abs(float(jx[0] * jy[1] - jx[1] * jy[0]))
    out = dict(mk)
    out["to_canon"] = to_canon
    out["area_scale"] = area_scale
    out["H"] = H
    return out


def _solve_affine(S0, M):
    """Symmetric positive S with S @ S0 @ S = M."""
    w, V = np.linalg.eigh(S0)
    S0h = V @ np.diag(np.sqrt(w)) @ V.T
    S0hi = V @ np.diag(1 / np.sqrt(w)) @ V.T
    inner = S0h @ M @ S0h
    w2, V2 = np.linalg.eigh(inner)
    w2 = np.clip(w2, 1e-9, None)
    return S0hi @ (V2 @ np.diag(np.sqrt(w2)) @ V2.T) @ S0hi


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
def read_bulbs(mk, marker_label, stats, cents):
    """For each slot pick the body blob sitting in that direction, in canonical coordinates
    (rotation, scale and any photo distortion undone by mk["to_canon"]); area -> size,
    radius -> distance."""
    U = mk["U"]
    to_canon, area_scale = mk["to_canon"], mk["area_scale"]
    min_area = 0.3 * math.pi * (layout.SIZES[0] * U) ** 2
    max_area = 2.2 * math.pi * (layout.SIZES[-1] * U) ** 2
    cand = []
    for lab in range(1, stats.shape[0]):
        if lab == marker_label:
            continue
        area = stats[lab, cv2.CC_STAT_AREA]
        if not (min_area <= area <= max_area):
            continue
        # babies are compact; ring arcs, streak-like debris and antennas are not
        w, h = stats[lab, cv2.CC_STAT_WIDTH], stats[lab, cv2.CC_STAT_HEIGHT]
        if area < 0.3 * w * h or max(w, h) > 4.0 * math.sqrt(area / math.pi):
            continue
        q = to_canon(cents[lab])
        dist = float(math.hypot(q[0], q[1]))
        if not (layout.DISTS[0] - 0.14 <= dist <= layout.DISTS[-1] + 0.14):
            continue
        cand.append((lab, area, q, dist, math.degrees(math.atan2(q[1], q[0]))))
    slots = []
    for i in range(layout.N_DATA):
        a = layout.data_angle(i)
        best = None
        for lab, area, q, dist, ang in cand:
            if abs((ang - a + 180) % 360 - 180) > SLOT_TOLERANCE_DEG:
                continue
            if best is None or area > best[1]:
                best = (lab, area, q, dist)
        if best is None:
            slots.append(dict(symbol=0, size=0, dist=0, ok=False, pos=(float(cents[0][0]), float(cents[0][1])), r_px=0))
            continue
        lab, area, q, dist = best
        r_px = math.sqrt(area / math.pi) + EDGE_ADDBACK_PX
        r = math.sqrt((r_px ** 2) / area_scale(q))           # radius in units (local scale)
        si = int(np.argmin([abs(r - s) for s in layout.SIZES]))
        di = int(np.argmin([abs(dist - s) for s in layout.DISTS]))
        slots.append(dict(symbol=codec.glyph_to_symbol(si, di), size=si, dist=di, ok=True,
                          pos=(float(cents[lab][0]), float(cents[lab][1])), r_px=r_px, r=round(r, 3), d=round(dist, 3)))
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
        slots = read_bulbs(mk, lab, stats, cents)
        found = sum(s["ok"] for s in slots)
        rms = angular_rms(mk, slots)
        degraded = found < layout.N_DATA or rms > 1.0 or mk["stretch"] > 1.02
        if found >= 8 and degraded:
            # second pass: perspective-aware (photographs). Skipped for clean files.
            mk2 = refine_homography(mk, slots)
            slots2 = read_bulbs(mk2, lab, stats, cents)
            if sum(s["ok"] for s in slots2) >= found:
                mk, slots, found = mk2, slots2, sum(s["ok"] for s in slots2)
        if best is None or found > best[0]:
            best = (found, dict(centre=(mk["ox"], mk["oy"]), R=mk["U"], rot=mk["rot"], slots=slots, polarity=polarity,
                                stretch=round(mk["stretch"], 3), perspective="H" in mk, degraded=degraded, angular_rms=round(rms, 2),
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
    missing = [i for i, s in enumerate(result["slots"]) if not s["ok"]]
    if found < layout.N_DATA - 3:
        # with more than 3 babies missing the code could "succeed" on garbage: refuse
        result["error"] = f"only {found} of {layout.N_DATA} bulbs found"
        return result
    try:
        # missing babies are erasures (known positions): they cost half as much as errors
        words, errata = codec.symbols_to_words(result["symbols"], wordlist, erasures=missing)
    except ValueError as e:
        result["error"] = str(e)
        return result
    # plausibility: a correction at a baby we DID measure must be a neighbouring grid cell of
    # the measurement (one size step and/or one distance step away). A miscorrection lands on
    # an arbitrary cell, so this rejects most of them instead of returning a wrong phrase.
    corrected = codec.words_to_symbols(words, wordlist)
    for i in (errata if result.get("degraded") else []):
        s = result["slots"][i]
        if not s["ok"]:
            continue
        si0, di0 = codec.symbol_to_glyph(s["symbol"])
        si1, di1 = codec.symbol_to_glyph(corrected[i])
        if abs(si1 - si0) > 1 or abs(di1 - di0) > 1:
            result["error"] = f"unreliable read: correction at baby {i} is not a neighbouring cell"
            return result
    result["words"], result["errata"] = words, errata
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
