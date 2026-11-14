"""Geometry for the Mandelbrot-style layout.

The marker is the black main body (disc) with its antenna (stem) and a period-2
bulb on the antenna, like the Mandelbrot set rotated antenna-up. The 15 data
symbols are black satellite bulbs around the body: each bulb's SIZE (4 levels,
2 bits) and DISTANCE from the centre (8 levels, 3 bits) carry one 5-bit symbol.

Everything is in units of the main disc radius R so the decoder can rescale from
the disc it measures. Angles are degrees in image coordinates (x right, y down):
-90 is straight up, increasing angle is clockwise on screen.
"""
import math

# marker
STEM_LEN = 2.0          # antenna from the disc edge to (1 + STEM_LEN) * R
STEM_WIDTH = 0.22
P2_BULB_AT = 1.75       # period-2 bulb centre along the antenna
P2_BULB_R = 0.38
TIP_DOT_R = 0.12        # tiny "mini-brot" at the antenna tip

# data bulbs: 15 slots spread over 280 degrees, leaving the antenna free
N_DATA = 15
SLOT_START = 40.0       # first slot, degrees clockwise from the antenna
SLOT_STEP = 20.0
SIZES = [0.11, 0.18, 0.25, 0.32]                       # bulb radius / R   (2 bits)
DISTS = [2.2, 2.4, 2.6, 2.8, 3.0, 3.2, 3.4, 3.6]        # bulb centre / R   (3 bits)

# decoration (black mini-brots) only outside this radius; glow is everywhere
DECOR_MIN_R = 4.5
CANVAS_HALF = 6.8
UP = -90.0


def canvas_size(R):
    return int(round(2 * CANVAS_HALF * R))


def data_angle(i):
    return UP + SLOT_START + i * SLOT_STEP


def polar(cx, cy, r, angle_deg):
    a = math.radians(angle_deg)
    return cx + r * math.cos(a), cy + r * math.sin(a)


def stem_segment(cx, cy, R, rot=0.0):
    return polar(cx, cy, 0.8 * R, UP + rot), polar(cx, cy, (1 + STEM_LEN) * R, UP + rot)


def bulb_geometry(i, size_idx, dist_idx):
    """(radius/R, distance/R, angle) for slot i with the given symbol halves."""
    return SIZES[size_idx], DISTS[dist_idx], data_angle(i)


def bulb_centre(cx, cy, R, i, dist_idx, rot=0.0):
    return polar(cx, cy, DISTS[dist_idx] * R, data_angle(i) + rot)
