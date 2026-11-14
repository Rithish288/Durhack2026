"""Geometry for the Mandelbrot layout.

The marker is a REAL Mandelbrot set (rendered by iteration), antenna pointing up.
The decoder finds the two incentres of its body (distance-transform peaks): the
main cardioid and the period-2 bulb. Their distance gives the scale and their
direction gives the rotation. No artificial disc or needle.

Everything is in Mandelbrot units U (1 U = the complex-plane unit, DEFAULT_U px).
Origin = complex 0. Image coordinates: re runs DOWN the image (antenna at the
top), im runs to the right. Angles are degrees in image coordinates (x right,
y down): -90 is straight up (the antenna), increasing angle is clockwise.

The 15 data symbols are "baby" Mandelbrot sets orbiting the mother: each baby's
SIZE (area-equivalent radius, 4 levels, 2 bits) and the DISTANCE of its centroid
from the origin (8 levels, 3 bits) carry one 5-bit symbol. Babies may be rotated
freely (art); size and centroid do not depend on rotation.
"""
import math

# marker (calibrated through decoder.landmarks on a clean high-resolution render)
MANDEL_CLIP_R = 1.3        # keep the set only within this radius of the origin ...
ANTENNA_HALF_WIDTH = 0.10  # ... plus the antenna strip (|im| small, re < 0)
P1_RE = -0.2272            # cardioid incentre (distance-transform peak), coarse pass
P2_RE = -1.0001            # bulb incentre, coarse pass
PEAK_D0 = P1_RE - P2_RE
C1_RE = -0.1618            # centroid of the cardioid part (re > -0.75), precise pass
C2_RE = -1.0073            # centroid of the bulb part (-1.28 < re <= -0.75), precise pass
D0 = C1_RE - C2_RE         # 0.8454 U between the two centroids
INSCRIBED_R = 0.5033        # inscribed radius of the main body (d2/d1 = 0.489)

# data satellites: 15 slots over 280 degrees, leaving the antenna side free
N_DATA = 15
SLOT_START = 40.0
SLOT_STEP = 20.0
SIZES = [0.06, 0.095, 0.13, 0.165]                                 # area-equivalent radius / U (2 bits)
DISTS = [1.60, 1.73, 1.86, 1.99, 2.12, 2.25, 2.38, 2.51]           # centroid distance / U (3 bits)
BABY_CLIP_R = 1.3          # a baby is the Mandelbrot set within this radius of its own origin
BABY_EXTENT = 1.45         # max reach of a baby from its centroid, in units of its r_eq

DECOR_MIN_R = 2.85         # decoration only outside this
CANVAS_HALF = 3.4          # tight frame: the mother fills ~38% of the width
UP = -90.0


def canvas_size(U):
    return int(round(2 * CANVAS_HALF * U))


def data_angle(i):
    return UP + SLOT_START + i * SLOT_STEP


def polar(cx, cy, r, angle_deg):
    a = math.radians(angle_deg)
    return cx + r * math.cos(a), cy + r * math.sin(a)


def bulb_geometry(i, size_idx, dist_idx):
    """(radius/U, distance/U, angle) for slot i with the given symbol halves."""
    return SIZES[size_idx], DISTS[dist_idx], data_angle(i)
