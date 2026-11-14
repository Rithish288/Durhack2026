"""cube_vision.py - read the 54 stickers from two fixed-camera renders.

The front end exports two SIZE x SIZE PNGs with an orthographic camera (half-width HALF)
looking at the origin from VIEWS['A'] (sees U, R, F) and VIEWS['B'] (sees D, L, B),
up vector (0, 1, 0). We replicate that projection here, so every sticker centre lands on a
known pixel. The six centre stickers are the colour reference: each other sticker is
assigned the colour of the nearest centre.
"""
import base64

import cv2
import numpy as np

import cube

SIZE = 600
HALF = 2.8
VIEWS = {"A": (1.0, 1.0, 1.0), "B": (-1.0, -1.0, -1.0)}
# pastel scheme from the UI reference (~/Downloads/rubiks_cube.html), RGB
PALETTE = {"U": (238, 238, 238), "R": (240, 169, 170), "F": (184, 220, 177),
           "D": (238, 229, 157), "L": (242, 197, 161), "B": (150, 198, 233)}
BACKGROUND = (241, 241, 241)
CUBIE = 1.0          # cubie edge length in world units
STICKER = 0.86       # sticker edge length


def _norm(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def camera_axes(direction):
    """screen-x and screen-y unit vectors for Three.js lookAt(eye=dir*k, target=0, up=(0,1,0))"""
    z = _norm(direction)
    x = _norm(np.cross([0.0, 1.0, 0.0], z))
    y = np.cross(z, x)
    return x, y


def project(points, direction, size=SIZE, half=HALF):
    """world points (N,3) -> pixel coords (N,2) as floats"""
    x, y = camera_axes(direction)
    pts = np.asarray(points, float)
    sx, sy = pts @ x, pts @ y
    return np.stack([(sx / half + 1) / 2 * size, (1 - sy / half) / 2 * size], axis=1)


def sticker_corners(i):
    """world coordinates of the centre and 4 corners of facelet i"""
    p, n = cube.GEOMETRY[i]
    p, n = np.array(p, float), np.array(n, float)
    centre = np.where(n != 0, n * 1.5 * CUBIE, p * CUBIE)
    # two in-plane axes
    a = np.array([0.0, 1.0, 0.0]) if abs(n[1]) < 0.5 else np.array([1.0, 0.0, 0.0])
    u = _norm(np.cross(n, a))
    v = np.cross(n, u)
    h = STICKER / 2
    corners = [centre + u * h + v * h, centre - u * h + v * h, centre - u * h - v * h, centre + u * h - v * h]
    return centre, corners


def visible_facelets(view):
    d = np.array(VIEWS[view], float)
    return [i for i, (p, n) in enumerate(cube.GEOMETRY) if np.dot(n, d) > 0]


def sticker_pixels(view):
    """{facelet index: (px, py)} for stickers visible in this view"""
    idx = visible_facelets(view)
    centres = [sticker_corners(i)[0] for i in idx]
    pix = project(centres, VIEWS[view])
    return {i: (float(px), float(py)) for i, (px, py) in zip(idx, pix)}


# ---------------------------------------------------------------- reading
def decode_image(data):
    """PNG/JPEG bytes -> RGB uint8 array"""
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("could not decode image")
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def _sample(img, px, py, r=6):
    h, w = img.shape[:2]
    x0, x1 = max(0, int(round(px)) - r), min(w, int(round(px)) + r + 1)
    y0, y1 = max(0, int(round(py)) - r), min(h, int(round(py)) + r + 1)
    if x1 <= x0 or y1 <= y0:
        raise ValueError("sticker position outside the image")
    patch = img[y0:y1, x0:x1].reshape(-1, 3).astype(float)
    return np.median(patch, axis=0)


def _nearest(colour, refs):
    best, best_d = None, None
    for k, c in refs.items():
        d = float(np.sum((np.asarray(c, float) - colour) ** 2))
        if best_d is None or d < best_d:
            best, best_d = k, d
    return best, best_d


def identify_view(img):
    """Which fixed view is this image? Uses the three centre stickers against the palette."""
    if img.shape[0] != SIZE or img.shape[1] != SIZE:
        img = cv2.resize(img, (SIZE, SIZE), interpolation=cv2.INTER_AREA)
    best = None
    for view in VIEWS:
        pix = sticker_pixels(view)
        score = 0.0
        for face in cube.FACES:
            c = cube.FACES.index(face) * 9 + 4
            if c in pix:
                col = _sample(img, *pix[c])
                score += float(np.sum((np.asarray(PALETTE[face], float) - col) ** 2))
        if best is None or score < best[1]:
            best = (view, score)
    return img, best[0], best[1]


def read_stickers(images):
    """two RGB images (either order) -> (facelets, info)"""
    if len(images) != 2:
        raise ValueError("need exactly two images")
    seen = {}
    for img in images:
        img, view, score = identify_view(img)
        if score > 3 * 120 ** 2:
            raise ValueError("an image does not look like an exported cube render")
        if view in seen:
            raise ValueError("both images show the same side of the cube; export views A and B")
        seen[view] = img
    # colour reference: all six centres (three per view), then classify every sticker
    refs = {}
    for view, img in seen.items():
        pix = sticker_pixels(view)
        for face in cube.FACES:
            c = cube.FACES.index(face) * 9 + 4
            if c in pix:
                refs[face] = _sample(img, *pix[c])
    f = [None] * 54
    confidence = {}
    for view, img in seen.items():
        for i, (px, py) in sticker_pixels(view).items():
            col = _sample(img, px, py)
            face, d = _nearest(col, refs)
            f[i] = face
            confidence[i] = d
    if any(c is None for c in f):
        raise ValueError("some stickers were not visible")
    return "".join(f), {"views": sorted(seen), "max_colour_distance": max(confidence.values()) ** 0.5}


def overlay(img, view):
    """debug: draw the sample points with the read colour -> PNG base64"""
    out = cv2.cvtColor(img.copy(), cv2.COLOR_RGB2BGR)
    for i, (px, py) in sticker_pixels(view).items():
        cv2.circle(out, (int(px), int(py)), 9, (0, 0, 0), 2)
        cv2.putText(out, str(i), (int(px) + 10, int(py) + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 1)
    ok, buf = cv2.imencode(".png", out)
    return base64.b64encode(buf.tobytes()).decode()


# ---------------------------------------------------------------- synthetic render (tests)
def render_synthetic(facelets, view, size=SIZE):
    """draw the cube the way the fixed camera would see it (flat colours) -> RGB image"""
    img = np.zeros((size, size, 3), np.uint8)
    img[:] = BACKGROUND
    d = np.array(VIEWS[view], float)
    # body: project the 8 cube corners' hull
    corners = np.array([[sx, sy, sz] for sx in (-1.5, 1.5) for sy in (-1.5, 1.5) for sz in (-1.5, 1.5)])
    hull = cv2.convexHull(project(corners, d, size).astype(np.int32))
    cv2.fillPoly(img, [hull], (22, 22, 22))
    for i in visible_facelets(view):
        _, quad = sticker_corners(i)
        pts = project(quad, d, size).astype(np.int32)
        col = PALETTE[facelets[i]]
        cv2.fillPoly(img, [pts], col, lineType=cv2.LINE_AA)
    return img
