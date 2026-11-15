import hashlib
import math
import random
from PIL import Image, ImageDraw

from symbol_library import SymbolLibrary


class ArtworkGenerator:

    CANVAS_SIZE = 1200
    BACKGROUND = (246, 241, 231)  # Deep botanical slate-black (low saturation)
    CENTRE = (600, 600)

    # Concentric Dual-Ring Layout: 8 inner + 12 outer = 20 symbols
    INNER_COUNT = 8
    OUTER_COUNT = 12
    INNER_RADIUS = 245.0
    OUTER_RADIUS = 415.0
    INNER_SIZE = 112.0
    OUTER_SIZE = 128.0
    SYMBOL_COUNT = 20

    # Asymmetric Corner L-Bracket Geometry (canonical coordinates)
    BRACKET_INSET = 60.0
    BRACKET_ARM = 140.0
    BRACKET_THICKNESS = 18.0
    BRACKET_COLOUR = (28, 32, 30)
    GOLD_PRIMARY = (198, 152, 52)  # Antique Metallic Gold (low-ish saturation ~180? Wait: keep gold muted!)
    GOLD_MUTED = (188, 164, 112)

    ALPHABET = "0123456789ABCDEFGHIJKLMNOPQ"

    def __init__(self):
        self.library = SymbolLibrary()

    def get_corner_vertices(self):
        """
        Return the 4 canonical outer corner vertices of the L-bracket frame
        in order: [Top-Left (asymmetric), Top-Right, Bottom-Right, Bottom-Left].
        """
        lo = self.BRACKET_INSET
        hi = self.CANVAS_SIZE - self.BRACKET_INSET
        return [
            (lo, lo),  # Top-Left (has triangular orientation gusset)
            (hi, lo),  # Top-Right
            (hi, hi),  # Bottom-Right
            (lo, hi),  # Bottom-Left
        ]

    def generate_ring_layout(self):
        """
        Calculate (x, y, size, rotation) for all 20 data symbols:
          - Indices 0..7:   Inner ring (8 symbols, radius = 225, starting at -90 deg)
          - Indices 8..19:  Outer ring (12 symbols, radius = 385, starting at -90 deg)
        Each blossom faces radially outward from the canvas centre.
        """
        layout = []
        cx, cy = self.CENTRE

        # Inner Ring (8 symbols)
        for i in range(self.INNER_COUNT):
            theta = -math.pi / 2 + (2 * math.pi * i / self.INNER_COUNT)
            x = cx + self.INNER_RADIUS * math.cos(theta)
            y = cy + self.INNER_RADIUS * math.sin(theta)
            rotation = theta + math.pi / 2  # Local -Y (blossom tip) points radially outward
            layout.append((x, y, self.INNER_SIZE, rotation))

        # Outer Ring (12 symbols)
        for j in range(self.OUTER_COUNT):
            theta = -math.pi / 2 + (2 * math.pi * j / self.OUTER_COUNT)
            x = cx + self.OUTER_RADIUS * math.cos(theta)
            y = cy + self.OUTER_RADIUS * math.sin(theta)
            rotation = theta + math.pi / 2
            layout.append((x, y, self.OUTER_SIZE, rotation))

        return layout

    def draw_corner_brackets(self, draw):
        """
        Draw 4 isolated dark charcoal corner L-brackets (with an asymmetric Top-Left
        gusset) and decorative gold border segments that stop 22px short of the
        brackets so OpenCV always sees 4 distinct, unconnected corner contours.
        """
        lo = self.BRACKET_INSET
        hi = self.CANVAS_SIZE - self.BRACKET_INSET
        arm = self.BRACKET_ARM
        t = self.BRACKET_THICKNESS
        dark_col = (28, 32, 30)
        gold_col = (196, 154, 62)
        gold_light = (222, 192, 122)

        gap = 22  # Quiet gap so gold lines NEVER merge with dark L-brackets in OpenCV
        mid = lo + t / 2

        # 1. Decorative gold border segments ONLY in the middle between brackets
        # Top & Bottom horizontal gold rules
        for y_line in (mid - 4, mid + 4):
            draw.line([(lo + arm + gap, y_line), (hi - arm - gap, y_line)], fill=gold_col, width=3)
            draw.line([(lo + arm + gap, self.CANVAS_SIZE - y_line), (hi - arm - gap, self.CANVAS_SIZE - y_line)],
                      fill=gold_col, width=3)

        # Left & Right vertical gold rules
        for x_line in (mid - 4, mid + 4):
            draw.line([(x_line, lo + arm + gap), (x_line, hi - arm - gap)], fill=gold_col, width=3)
            draw.line([(self.CANVAS_SIZE - x_line, lo + arm + gap), (self.CANVAS_SIZE - x_line, hi - arm - gap)],
                      fill=gold_col, width=3)

        # Subtle inner filigree frame (inset safely away from the dark L-brackets)
        inner_off = lo + t + 18
        draw.rectangle(
            [(inner_off, inner_off), (self.CANVAS_SIZE - inner_off, self.CANVAS_SIZE - inner_off)],
            outline=gold_light,
            width=2,
        )

        # 2. 4 Bold Charcoal L-Brackets (Top-Left has asymmetric triangular gusset)
        gusset = arm * 0.62
        draw.polygon([
            (lo, lo), (lo + arm, lo), (lo + arm, lo + t),
            (lo + gusset, lo + t), (lo + t, lo + gusset),
            (lo + t, lo + arm), (lo, lo + arm),
        ], fill=dark_col)

        # Top-Right L-bracket
        draw.polygon([
            (hi, lo), (hi, lo + arm), (hi - t, lo + arm),
            (hi - t, lo + t), (hi - arm, lo + t), (hi - arm, lo),
        ], fill=dark_col)

        # Bottom-Right L-bracket
        draw.polygon([
            (hi, hi), (hi - arm, hi), (hi - arm, hi - t),
            (hi - t, hi - t), (hi - t, hi - arm), (hi, hi - arm),
        ], fill=dark_col)

        # Bottom-Left L-bracket
        draw.polygon([
            (lo, hi), (lo, hi - arm), (lo + t, hi - arm),
            (lo + t, hi - t), (lo + arm, hi - t), (lo + arm, hi),
        ], fill=dark_col)

    def draw_botanical_decoys(self, draw, symbols, layout):
        """
        Draw low-saturation generative botanical trellis rings, radial ribs,
        constellation chords (seeded by the passphrase), and an outer decoy ring.
        All colours stay under HSV saturation ~35 so OpenCV ignores them cleanly.
        """
        cx, cy = self.CENTRE
        seed_int = int.from_bytes(
            hashlib.sha256(symbols.encode("utf-8")).digest()[:8], "big"
        )
        rng = random.Random(seed_int)

        line_col = (224, 214, 194)
        accent_col = (210, 194, 162)
        decoy_fill = (232, 222, 202)

        # 1. Subtle architectural border hairline connecting the brackets visually
        border_inset = self.BRACKET_INSET + self.BRACKET_THICKNESS / 2
        draw.rectangle(
            [
                (border_inset, border_inset),
                (self.CANVAS_SIZE - border_inset, self.CANVAS_SIZE - border_inset),
            ],
            outline=(30, 36, 35),
            width=2,
        )

        # 2. Concentric guide rings & radial botanical spokes
        for r in (115, 225, 305, 385, 468):
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=line_col, width=2)

        for k in range(24):
            ang = math.radians(k * 15)
            x0, y0 = cx + 115 * math.cos(ang), cy + 115 * math.sin(ang)
            x1, y1 = cx + 468 * math.cos(ang), cy + 468 * math.sin(ang)
            draw.line([(x0, y0), (x1, y1)], fill=line_col, width=1)

        # 3. Seeded generative constellation web between inner and outer nodes
        for i in range(self.INNER_COUNT):
            ix, iy, _, _ = layout[i]
            # Connect to two outer ring neighbours chosen deterministically from payload hash
            o1 = self.INNER_COUNT + rng.randrange(self.OUTER_COUNT)
            o2 = self.INNER_COUNT + ((o1 - self.INNER_COUNT + rng.choice([2, 3, 9, 10])) % self.OUTER_COUNT)
            for target_idx in (o1, o2):
                ox, oy, _, _ = layout[target_idx]
                draw.line([(ix, iy), (ox, oy)], fill=accent_col, width=2)

        # 4. Central rosette medallion (r < 110, low saturation)
        for k in range(12):
            ang = math.radians(k * 30)
            px = cx + 68 * math.cos(ang)
            py = cy + 68 * math.sin(ang)
            petal = [
                (cx + 22 * math.cos(ang), cy + 22 * math.sin(ang)),
                (cx + 55 * math.cos(ang - 0.16), cy + 55 * math.sin(ang - 0.16)),
                (px + 24 * math.cos(ang), py + 24 * math.sin(ang)),
                (cx + 55 * math.cos(ang + 0.16), cy + 55 * math.sin(ang + 0.16)),
            ]
            draw.polygon(petal, fill=decoy_fill, outline=accent_col, width=1)
        draw.ellipse((cx - 26, cy - 26, cx + 26, cy + 26), fill=self.BACKGROUND, outline=accent_col, width=2)

        # 5. Decorative outer decoy ring (24 small muted leaves at r = 468)
        for k in range(24):
            ang = math.radians(-90 + k * 15)
            dx = cx + 468 * math.cos(ang)
            dy = cy + 468 * math.sin(ang)
            r_leaf = 11
            pts = [
                (dx + r_leaf * 1.4 * math.cos(ang), dy + r_leaf * 1.4 * math.sin(ang)),
                (dx + r_leaf * 0.7 * math.cos(ang + math.pi / 2), dy + r_leaf * 0.7 * math.sin(ang + math.pi / 2)),
                (dx - r_leaf * 1.1 * math.cos(ang), dy - r_leaf * 1.1 * math.sin(ang)),
                (dx + r_leaf * 0.7 * math.cos(ang - math.pi / 2), dy + r_leaf * 0.7 * math.sin(ang - math.pi / 2)),
            ]
            draw.polygon(pts, fill=decoy_fill, outline=accent_col, width=1)

    def generate(self, symbols, output_path="artwork.png"):
        if len(symbols) != self.SYMBOL_COUNT:
            raise ValueError("Expected exactly 20 encoded symbols")

        if any(char not in self.ALPHABET for char in symbols):
            raise ValueError("Invalid character in encoded message")

        image = Image.new(
            "RGB",
            (self.CANVAS_SIZE, self.CANVAS_SIZE),
            self.BACKGROUND,
        )
        draw = ImageDraw.Draw(image)
        layout = self.generate_ring_layout()

        # 1. Low-saturation generative botanical background & decoy rings
        self.draw_botanical_decoys(draw, symbols, layout)

        # 2. Asymmetric 4-corner white L-brackets for perspective rectification
        self.draw_corner_brackets(draw)

        # 3. 20 encoded botanical symbols with clean dark quiet halos
        for i, character in enumerate(symbols):
            sx, sy, size, rotation = layout[i]
            halo_r = int(size * 0.78)
            draw.ellipse(
                (sx - halo_r, sy - halo_r, sx + halo_r, sy + halo_r),
                fill=self.BACKGROUND,
            )

            digit = self.ALPHABET.index(character)
            self.library.draw_symbol(
                image,
                centre=(sx, sy),
                digit=digit,
                size=size,
                rotation=rotation,
            )

        image.save(output_path)
        return image