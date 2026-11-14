"""cube.py - Rubik's cube model shared by the encoder and decoder.

Facelet string: 54 chars in Kociemba order  U1..U9 R1..R9 F1..F9 D1..D9 L1..L9 B1..B9,
each char one of "URFDLB" (= the colour of the face that sticker belongs to when solved).

Geometry (shared with the Three.js front end): U = +y, R = +x, F = +z, D = -y, L = -x, B = -z.
Facelet n of a face is numbered 1..9 left-to-right, top-to-bottom as drawn on Kociemba's net.

A cube state is also described by cubie coordinates (cp, co, ep, eo):
  cp  corner permutation   8!           = 40320
  co  corner orientation   3^7          = 2187
  eo  edge orientation     2^11         = 2048
  ep  edge permutation     12!/2        = 239500800 (parity must match the corners)
The product is ~2^65.2, so a 61-bit payload (45 data bits + 16 check bits) always fits:
    payload -> mixed-radix digits (cp, co, eo, ep) -> cubie state -> facelets.
"""
import kociemba

FACES = "URFDLB"
SOLVED = "".join(f * 9 for f in FACES)

CORNERS = ["URF", "UFL", "ULB", "UBR", "DFR", "DLF", "DBL", "DRB"]
EDGES = ["UR", "UF", "UL", "UB", "DR", "DF", "DL", "DB", "FR", "FL", "BL", "BR"]

N_CP, N_CO, N_EO, N_EP = 40320, 2187, 2048, 239500800
CAPACITY = N_CP * N_CO * N_EO * N_EP          # > 2**65


def fidx(face, n):
    """facelet name like ('U', 9) -> index 0..53"""
    return FACES.index(face) * 9 + (n - 1)


# Kociemba's cubie -> facelet tables
CORNER_FACELET = [
    [fidx("U", 9), fidx("R", 1), fidx("F", 3)], [fidx("U", 7), fidx("F", 1), fidx("L", 3)],
    [fidx("U", 1), fidx("L", 1), fidx("B", 3)], [fidx("U", 3), fidx("B", 1), fidx("R", 3)],
    [fidx("D", 3), fidx("F", 9), fidx("R", 7)], [fidx("D", 1), fidx("L", 9), fidx("F", 7)],
    [fidx("D", 7), fidx("B", 9), fidx("L", 7)], [fidx("D", 9), fidx("R", 9), fidx("B", 7)],
]
EDGE_FACELET = [
    [fidx("U", 6), fidx("R", 2)], [fidx("U", 8), fidx("F", 2)], [fidx("U", 4), fidx("L", 2)], [fidx("U", 2), fidx("B", 2)],
    [fidx("D", 6), fidx("R", 8)], [fidx("D", 2), fidx("F", 8)], [fidx("D", 4), fidx("L", 8)], [fidx("D", 8), fidx("B", 8)],
    [fidx("F", 6), fidx("R", 4)], [fidx("F", 4), fidx("L", 6)], [fidx("B", 6), fidx("L", 4)], [fidx("B", 4), fidx("R", 6)],
]
CORNER_COLOR = [list(c) for c in CORNERS]
EDGE_COLOR = [list(e) for e in EDGES]


# ---------------------------------------------------------------- 3D geometry of the 54 facelets
def facelet_geometry():
    """index -> ((gx, gy, gz) cubie grid position in {-1,0,1}^3, (nx, ny, nz) outward normal)"""
    geo = []
    for face in FACES:
        for k in range(9):
            row, col = divmod(k, 3)
            if face == "U":
                p, n = (col - 1, 1, row - 1), (0, 1, 0)
            elif face == "D":
                p, n = (col - 1, -1, 1 - row), (0, -1, 0)
            elif face == "F":
                p, n = (col - 1, 1 - row, 1), (0, 0, 1)
            elif face == "B":
                p, n = (1 - col, 1 - row, -1), (0, 0, -1)
            elif face == "R":
                p, n = (1, 1 - row, 1 - col), (1, 0, 0)
            else:  # L
                p, n = (-1, 1 - row, col - 1), (-1, 0, 0)
            geo.append((p, n))
    return geo


GEOMETRY = facelet_geometry()


def _rot90(v, axis, turns):
    """rotate integer vector v about axis (0=x,1=y,2=z) by turns*90deg (right-hand rule)"""
    x, y, z = v
    for _ in range(turns % 4):
        if axis == 0:
            x, y, z = x, -z, y
        elif axis == 1:
            x, y, z = z, y, -x
        else:
            x, y, z = -y, x, z
    return (x, y, z)


# face -> (axis, layer coordinate, quarter turns for a clockwise move)
MOVE_AXIS = {"U": (1, 1, -1), "D": (1, -1, 1), "R": (0, 1, -1), "L": (0, -1, 1), "F": (2, 1, -1), "B": (2, -1, 1)}


def _move_permutation(face, times):
    axis, layer, q = MOVE_AXIS[face]
    turns = q * times
    lookup = {g: i for i, g in enumerate(GEOMETRY)}
    perm = list(range(54))   # new[j] = old[perm[j]]
    for i, (p, n) in enumerate(GEOMETRY):
        if p[axis] != layer:
            continue
        j = lookup[(_rot90(p, axis, turns), _rot90(n, axis, turns))]
        perm[j] = i
    return perm


MOVES = {}
for _f in FACES:
    MOVES[_f] = _move_permutation(_f, 1)
    MOVES[_f + "2"] = _move_permutation(_f, 2)
    MOVES[_f + "'"] = _move_permutation(_f, 3)


def apply_move(facelets, move):
    perm = MOVES[move]
    return "".join(facelets[perm[j]] for j in range(54))


def apply_moves(facelets, moves):
    for m in moves:
        facelets = apply_move(facelets, m)
    return facelets


def invert_moves(moves):
    """scramble that undoes `moves` (and vice versa)"""
    out = []
    for m in reversed(moves):
        if m.endswith("2"):
            out.append(m)
        elif m.endswith("'"):
            out.append(m[0])
        else:
            out.append(m + "'")
    return out


# ---------------------------------------------------------------- facelets <-> cubies
def facelets_to_cubies(f):
    """-> (cp, co, ep, eo). Raises ValueError if the stickers do not form real cubies."""
    if len(f) != 54 or any(c not in FACES for c in f):
        raise ValueError("facelet string must be 54 chars of URFDLB")
    for k, face in enumerate(FACES):
        if f[9 * k + 4] != face:
            raise ValueError("centre stickers are not in the standard orientation")
        if f.count(face) != 9:
            raise ValueError(f"colour {face} appears {f.count(face)} times, expected 9")
    cp, co, ep, eo = [-1] * 8, [0] * 8, [-1] * 12, [0] * 12
    for i in range(8):
        ori = next((o for o in range(3) if f[CORNER_FACELET[i][o]] in "UD"), None)
        if ori is None:
            raise ValueError(f"corner {CORNERS[i]} has no U/D sticker")
        c1, c2 = f[CORNER_FACELET[i][(ori + 1) % 3]], f[CORNER_FACELET[i][(ori + 2) % 3]]
        for j in range(8):
            if c1 == CORNER_COLOR[j][1] and c2 == CORNER_COLOR[j][2]:
                cp[i], co[i] = j, ori
                break
        if cp[i] < 0:
            raise ValueError(f"corner {CORNERS[i]} has an impossible colour combination")
    for i in range(12):
        a, b = f[EDGE_FACELET[i][0]], f[EDGE_FACELET[i][1]]
        for j in range(12):
            if a == EDGE_COLOR[j][0] and b == EDGE_COLOR[j][1]:
                ep[i], eo[i] = j, 0
                break
            if a == EDGE_COLOR[j][1] and b == EDGE_COLOR[j][0]:
                ep[i], eo[i] = j, 1
                break
        if ep[i] < 0:
            raise ValueError(f"edge {EDGES[i]} has an impossible colour combination")
    check_cubies(cp, co, ep, eo)
    return cp, co, ep, eo


def cubies_to_facelets(cp, co, ep, eo):
    f = [None] * 54
    for k, face in enumerate(FACES):
        f[9 * k + 4] = face
    for i in range(8):
        for n in range(3):
            f[CORNER_FACELET[i][(n + co[i]) % 3]] = CORNER_COLOR[cp[i]][n]
    for i in range(12):
        for n in range(2):
            f[EDGE_FACELET[i][(n + eo[i]) % 2]] = EDGE_COLOR[ep[i]][n]
    return "".join(f)


def perm_parity(p):
    inv = 0
    for i in range(len(p)):
        for j in range(i + 1, len(p)):
            if p[i] > p[j]:
                inv += 1
    return inv & 1


def check_cubies(cp, co, ep, eo):
    """Raise ValueError unless the state is reachable by legal moves."""
    if sorted(cp) != list(range(8)) or sorted(ep) != list(range(12)):
        raise ValueError("a cubie is missing or duplicated")
    if sum(co) % 3:
        raise ValueError("corner twist: orientations do not sum to 0 mod 3")
    if sum(eo) % 2:
        raise ValueError("edge flip: orientations do not sum to 0 mod 2")
    if perm_parity(cp) != perm_parity(ep):
        raise ValueError("permutation parity mismatch between corners and edges")


# ---------------------------------------------------------------- integer <-> cubies (mixed radix)
def _lehmer_digits(p):
    """permutation -> Lehmer digits d_i in [0, n-1-i]"""
    return [sum(1 for j in range(i + 1, len(p)) if p[j] < p[i]) for i in range(len(p))]


def _perm_from_digits(d):
    pool = list(range(len(d)))
    return [pool.pop(x) for x in d]


def _perm_to_index(p):
    idx = 0
    for i, d in enumerate(_lehmer_digits(p)):
        idx = idx * (len(p) - i) + d
    return idx


def _perm_from_index(idx, n):
    digits = [0] * n
    for i in range(n - 1, -1, -1):     # digit i has radix n - i
        radix = n - i
        digits[i] = idx % radix
        idx //= radix
    return _perm_from_digits(digits)


def _even_perm_to_index(p):
    """12-element permutation -> index in [0, 12!/2) that ignores its parity"""
    d = _lehmer_digits(p)[:10]
    idx = 0
    for i, x in enumerate(d):
        idx = idx * (12 - i) + x
    return idx


def _even_perm_from_index(idx, parity):
    digits = [0] * 12
    for i in range(9, -1, -1):
        radix = 12 - i
        digits[i] = idx % radix
        idx //= radix
    digits[10] = (parity - sum(digits[:10])) % 2
    return _perm_from_digits(digits)


def int_to_cubies(n):
    if not 0 <= n < CAPACITY:
        raise ValueError("integer out of range for a cube state")
    n, cp_i = divmod(n, N_CP)
    n, co_i = divmod(n, N_CO)
    n, eo_i = divmod(n, N_EO)
    n, ep_i = divmod(n, N_EP)
    cp = _perm_from_index(cp_i, 8)
    co = [0] * 8
    for i in range(6, -1, -1):
        co[i] = co_i % 3
        co_i //= 3
    co[7] = (-sum(co[:7])) % 3
    eo = [(eo_i >> (10 - i)) & 1 for i in range(11)]
    eo.append(sum(eo) % 2)
    ep = _even_perm_from_index(ep_i, perm_parity(cp))
    return cp, co, ep, eo


def cubies_to_int(cp, co, ep, eo):
    check_cubies(cp, co, ep, eo)
    cp_i = _perm_to_index(cp)
    co_i = 0
    for x in co[:7]:
        co_i = co_i * 3 + x
    eo_i = 0
    for x in eo[:11]:
        eo_i = eo_i * 2 + x
    ep_i = _even_perm_to_index(ep)
    return ((ep_i * N_EO + eo_i) * N_CO + co_i) * N_CP + cp_i


def int_to_facelets(n):
    return cubies_to_facelets(*int_to_cubies(n))


def facelets_to_int(f):
    return cubies_to_int(*facelets_to_cubies(f))


# ---------------------------------------------------------------- solver
def solve(facelets):
    """move list that brings `facelets` to solved (Kociemba two-phase, <= ~22 moves)"""
    if facelets == SOLVED:
        return []
    facelets_to_cubies(facelets)          # validates
    sol = kociemba.solve(facelets).split()
    if apply_moves(facelets, sol) != SOLVED:
        raise RuntimeError("solver returned a sequence that does not solve the cube")
    return sol


def scramble(facelets):
    """move list that takes the solved cube to `facelets`"""
    scr = invert_moves(solve(facelets))
    if apply_moves(SOLVED, scr) != facelets:
        raise RuntimeError("scramble does not reproduce the state")
    return scr
