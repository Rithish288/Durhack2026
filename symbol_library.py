import math
from PIL import Image, ImageDraw


class SymbolLibrary:
    """
    Botanical visual encoder for base-27 digits:
      - Colour (digit // 9):   0 = Terracotta, 1 = Peacock Teal, 2 = Saffron Ochre
      - Stage ((digit % 9)//3): 0 = Closed Bud, 1 = Half-Open Bloom, 2 = Full 4-Petal Blossom
      - Leaves (digit % 3):    0 = No leaves, 1 = One leaf (right), 2 = Two leaves (left & right)
    """

    # Harmonious mid-century botanical palette (widely separated in CIELAB a*, b*)
    COLOURS = {
        0: (208, 78, 46),  # Rich Terracotta Coral
        1: (22, 138, 156),  # Deep Peacock Teal
        2: (224, 154, 34),  # Warm Saffron Ochre (darkened slightly for crisp contrast on light paper)
    }

    LEAF_COLOUR = (56, 152, 88)  # Botanical Sage-Emerald
    STEM_COLOUR = (175, 168, 154)  # Subtle warm parchment-taupe (low saturation -> ignored by CV)

    STAGES = {
        0: "closed_bud",
        1: "half_bloom",
        2: "full_blossom",
    }

    LEAVES = {
        0: "none",
        1: "one_leaf",
        2: "two_leaves",
    }

    SYMBOL_COUNT = 27

    def get_symbol_properties(self, digit):
        if not 0 <= digit < self.SYMBOL_COUNT:
            raise ValueError("Symbol digit must be between 0 and 26")

        colour_id = digit // 9
        stage_id = (digit % 9) // 3
        leaf_count = digit % 3

        return {
            "colour": self.COLOURS[colour_id],
            "colour_id": colour_id,
            "stage": self.STAGES[stage_id],
            "stage_id": stage_id,
            "leaf_count": leaf_count,
        }

    @staticmethod
    def _rotate_points(points, centre, angle_rad):
        cx, cy = centre
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        return [
            (
                cx + (px - cx) * cos_a - (py - cy) * sin_a,
                cy + (px - cx) * sin_a + (py - cy) * cos_a,
            )
            for px, py in points
        ]

    def _draw_leaf(self, draw, base_xy, side, size, rotation):
        """
        Draw a bold, pointed botanical leaf sprouting from `base_xy`.
        `side` = +1 (right) or -1 (left) in unrotated local coordinates.
        """
        bx, by = base_xy
        leaf_len = size * 0.44
        leaf_wid = size * 0.21

        # Pointed almond/vesica leaf curve in local coordinates
        local_pts = []
        steps = 16
        # Upper edge from stem base to leaf tip
        for i in range(steps + 1):
            t = i / steps
            lx = bx + side * (t * leaf_len)
            ly = by - (t * leaf_len * 0.42) - math.sin(math.pi * t) * leaf_wid
            local_pts.append((lx, ly))
        # Lower edge back from leaf tip to stem base
        for i in range(steps - 1, 0, -1):
            t = i / steps
            lx = bx + side * (t * leaf_len)
            ly = by - (t * leaf_len * 0.42) + math.sin(math.pi * t) * (leaf_wid * 0.85)
            local_pts.append((lx, ly))

        rot_pts = self._rotate_points(local_pts, base_xy, rotation)
        draw.polygon(
            rot_pts,
            fill=self.LEAF_COLOUR,
            outline=(16, 20, 19),
            width=max(2, int(size * 0.035)),
        )

    def draw_symbol(self, image, centre, digit, size=58, rotation=0.0):
        """
        Draw a botanical blossom at `centre` (cx, cy) with `leaf_count` (0, 1, or 2)
        sprouting from its short stem base, rotated by `rotation` radians.
        """
        draw = ImageDraw.Draw(image)
        cx, cy = centre
        props = self.get_symbol_properties(digit)
        colour = props["colour"]
        stage = props["stage"]
        leaf_count = props["leaf_count"]
        outline_col = (16, 20, 19)
        outline_w = max(2, int(size * 0.04))

        # Shift blossom head slightly upward (-Y) in local frame so leaves sit cleanly below (+Y)
        head_local = (cx, cy - size * 0.16)
        stem_base_local = (cx, cy + size * 0.4)
        head_xy = self._rotate_points([head_local], centre, rotation)[0]
        stem_xy = self._rotate_points([stem_base_local], centre, rotation)[0]

        # 1. Subtle low-saturation stem connecting blossom head to leaf node
        draw.line(
            [head_xy, stem_xy],
            fill=self.STEM_COLOUR,
            width=max(3, int(size * 0.06)),
        )

        # 2. Draw leaves (0, 1, or 2) around stem_xy
        if leaf_count >= 1:
            self._draw_leaf(draw, stem_xy, side=+1, size=size, rotation=rotation)
        if leaf_count == 2:
            self._draw_leaf(draw, stem_xy, side=-1, size=size, rotation=rotation)

        # 3. Draw blossom head (3 distinct circularity regimes)
        hx, hy = head_xy
        r = size * 0.38

        if stage == "closed_bud":
            # Stage 0: Smooth high-circularity oval seed/bud (circularity ~ 0.91)
            pts = []
            for i in range(36):
                a = 2 * math.pi * i / 36
                lx = hx + (r * 0.78) * math.cos(a)
                ly = hy + (r * 1.06) * math.sin(a)
                pts.append((lx, ly))
            rot_pts = self._rotate_points(pts, head_xy, rotation)
            draw.polygon(rot_pts, fill=colour, outline=outline_col, width=outline_w)

        elif stage == "half_bloom":
            # Stage 1: Crisp 4-pointed diamond/tulip silhouette (circularity ~ 0.72)
            raw_pts = [
                (hx, hy - r * 1.18),          # Top tip
                (hx + r * 0.94, hy),          # Right tip
                (hx, hy + r * 1.06),          # Bottom base
                (hx - r * 0.94, hy),          # Left tip
            ]
            rot_pts = self._rotate_points(raw_pts, head_xy, rotation)
            draw.polygon(rot_pts, fill=colour, outline=outline_col, width=outline_w)

        elif stage == "full_blossom":
            # Stage 2: Deeply indented 4-petal botanical blossom (circularity ~ 0.44)
            # Polar curve r(theta) = r_base * (0.64 + 0.48 * cos(4 * theta))
            pts = []
            steps = 72
            for i in range(steps):
                a = 2 * math.pi * i / steps
                rad = r * (0.66 + 0.48 * math.cos(4 * a))
                pts.append((hx + rad * math.cos(a), hy + rad * math.sin(a)))
            rot_pts = self._rotate_points(pts, head_xy, rotation)
            draw.polygon(rot_pts, fill=colour, outline=outline_col, width=outline_w)

        # Tiny dark stamen center dot for visual polish (kept small so blob stays filled)
        stamen_r = max(2, int(size * 0.045))
        draw.ellipse(
            (hx - stamen_r, hy - stamen_r, hx + stamen_r, hy + stamen_r),
            fill=outline_col,
        )