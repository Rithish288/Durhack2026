"""Round-trip test: 200 random triples, clean / rotated+scaled / 3 bulbs tampered over.

usage: python test.py [words.csv] [n] [theme]
"""
import math
import random
import sys
import time

import cv2
import numpy as np

import codec
import decoder
import encoder
import layout


def to_bgr(pil_img):
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def rotate_scale(bgr, angle, scale, bg=None):
    h, w = bgr.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    bg = tuple(int(v) for v in (bg or encoder.BG)[::-1])
    out = cv2.warpAffine(bgr, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=bg)
    nw, nh = max(8, int(w * scale)), max(8, int(h * scale))
    return cv2.resize(out, (nw, nh), interpolation=cv2.INTER_AREA)


def jpeg(bgr, quality=60):
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def photo_like(bgr, rng, bg):
    """Mild keystone perspective (camera not square to the screen), blur, JPEG."""
    h, w = bgr.shape[:2]
    k = 0.06
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[rng.uniform(0, k) * w, rng.uniform(0, k) * h], [w - rng.uniform(0, k) * w, rng.uniform(0, k) * h],
                      [w - rng.uniform(0, k) * w, h - rng.uniform(0, k) * h], [rng.uniform(0, k) * w, h - rng.uniform(0, k) * h]])
    H = cv2.getPerspectiveTransform(src, dst)
    bgc = tuple(int(v) for v in bg[::-1])
    out = cv2.warpPerspective(bgr, H, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=bgc)
    out = cv2.GaussianBlur(out, (0, 0), rng.uniform(0.7, 1.4))
    return jpeg(out, 75)


def grayscale(bgr):
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)


def erase_slots(bgr, symbols, n, rng, style):
    """Realistic damage: n random babies painted over with the halo colour (they vanish)."""
    out = bgr.copy()
    R = encoder.DEFAULT_R * style.get("zoom", 1.0)
    spin = style.get("spin", 0.0)
    c = bgr.shape[1] / 2.0
    bg = tuple(int(v) for v in style["ramp"][0][1][::-1])
    for i in rng.sample(range(layout.N_DATA), n):
        si, di = codec.symbol_to_glyph(symbols[i])
        rr, dist, ang = layout.bulb_geometry(i, si, di)
        x, y = layout.polar(c, c, dist * R, ang + spin)
        cv2.circle(out, (int(round(x)), int(round(y))), int((layout.BABY_EXTENT * rr + 0.06) * R), bg, -1, cv2.LINE_AA)
    return out


def paint_slots(bgr, symbols, n, rng, style):
    """Tamper with n random bulbs: erase the real one and draw a bulb of a different symbol."""
    out = bgr.copy()
    R = encoder.DEFAULT_R * style.get("zoom", 1.0)
    spin = style.get("spin", 0.0)
    c = bgr.shape[1] / 2.0
    th = style
    bg = tuple(int(v) for v in th["ramp"][0][1][::-1])     # the glow colour right next to a body
    body = tuple(int(v) for v in th["body"][::-1])
    for i in rng.sample(range(layout.N_DATA), n):
        si, di = codec.symbol_to_glyph(symbols[i])
        rr, dist, ang = layout.bulb_geometry(i, si, di)
        ang += spin
        x, y = layout.polar(c, c, dist * R, ang)
        cv2.circle(out, (int(round(x)), int(round(y))), int((layout.BABY_EXTENT * rr + 0.06) * R), bg, -1, cv2.LINE_AA)
        wrong = rng.choice([s for s in range(32) if s != symbols[i]])
        si2, di2 = codec.symbol_to_glyph(wrong)
        rr2, dist2, _ = layout.bulb_geometry(i, si2, di2)
        x2, y2 = layout.polar(c, c, dist2 * R, ang)
        cv2.circle(out, (int(round(x2)), int(round(y2))), int(rr2 * R), body, -1, cv2.LINE_AA)
    return out


def try_decode(bgr, wordlist):
    try:
        return decoder.decode_image(bgr, wordlist)
    except decoder.DecodeError as e:
        return dict(words=None, symbols=None, error=str(e))


def main(argv):
    words_csv = argv[1] if len(argv) > 1 else codec.default_word_list_path()
    n_trials = int(argv[2]) if len(argv) > 2 else 200
    theme = argv[3] if len(argv) > 3 else encoder.DEFAULT_THEME
    wordlist = codec.load_words(words_csv)
    print(f"word list: {words_csv} ({len(wordlist)} words), trials: {n_trials}, theme: {theme}")
    rng = random.Random(42)

    conditions = ["clean", "rotate+scale", "jpeg q60", "grayscale", "photo-like (keystone+blur)",
                  "3 babies erased", "3 babies swapped (adversarial)", "rotate+scale+jpeg+3 erased"]
    ok = {c: 0 for c in conditions}
    raw_err = {c: [] for c in conditions}
    failures = []
    t0 = time.time()
    for t in range(n_trials):
        words = rng.sample(wordlist, 3)
        symbols = codec.words_to_symbols(words, wordlist)
        style = encoder.style_for(words, theme)
        bg = style["bg"]
        clean = to_bgr(encoder.render(words, wordlist, theme=theme))
        angle, scale = rng.uniform(0, 360), rng.uniform(0.7, 1.0)
        painted = paint_slots(clean, symbols, 3, rng, style)
        erased = erase_slots(clean, symbols, 3, rng, style)
        variants = {
            "clean": clean,
            "rotate+scale": rotate_scale(clean, angle, scale, bg),
            "jpeg q60": jpeg(clean),
            "grayscale": grayscale(clean),
            "photo-like (keystone+blur)": photo_like(clean, rng, bg),
            "3 babies erased": erased,
            "3 babies swapped (adversarial)": painted,
            "rotate+scale+jpeg+3 erased": jpeg(rotate_scale(erased, angle, scale, bg)),
        }
        for cond, img in variants.items():
            res = try_decode(img, wordlist)
            if res["symbols"] is not None:
                raw_err[cond].append(sum(a != b for a, b in zip(res["symbols"], symbols)))
            if res["words"] == words:
                ok[cond] += 1
            else:
                failures.append((cond, words, res.get("words"), res.get("error"), round(angle), round(scale, 2)))
    dt = time.time() - t0

    print(f"\n{'condition':<34}{'accuracy':>10}{'mean raw symbol errors':>26}{'max':>6}")
    for c in conditions:
        errs = raw_err[c] or [0]
        print(f"{c:<34}{ok[c]:>5}/{n_trials:<4}{np.mean(errs):>22.2f}{max(errs):>8}")
    print(f"\n{dt:.1f}s total, {dt / (len(conditions) * n_trials) * 1000:.0f} ms per encode+decode")
    if failures:
        print(f"\n{len(failures)} failures (first 10):")
        for f in failures[:10]:
            print("  ", f)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
