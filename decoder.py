from itertools import combinations
import math
import cv2
import numpy as np

from artwork_generator import ArtworkGenerator
from encoder import Encoder


class ArtworkDecoder:

    ALPHABET = "0123456789ABCDEFGHIJKLMNOPQ"

    def __init__(self, wordlist_file="durhack_word_list.csv"):
        self.gen = ArtworkGenerator()
        self.encoder = Encoder(wordlist_file=wordlist_file)
        self.canonical_corners = np.array(
            self.gen.get_corner_vertices(), dtype=np.float32
        )

    # ------------------------------------------------------------------
    # STEP 1: CORNER L-BRACKET DETECTION & ORIENTATION-LOCKED WARP
    # ------------------------------------------------------------------
    def _preprocess_luminance(self, bgr_image):
        lab = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2LAB)
        l_chan, _, _ = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        return clahe.apply(l_chan)

    def _extract_outer_corner(self, cnt, quad_centroid):
        """
        Given an L-bracket contour and the approximate center of the 4-bracket quad,
        find the outer corner vertex (the contour point farthest from quad_centroid
        along the outward diagonal).
        """
        pts = cnt.reshape(-1, 2).astype(np.float32)
        centroid = np.mean(pts, axis=0)
        outward_dir = centroid - quad_centroid
        norm = np.linalg.norm(outward_dir)
        if norm > 0:
            outward_dir /= norm
        projections = pts @ outward_dir
        best_idx = int(np.argmax(projections))
        return pts[best_idx]

    def find_corner_brackets(self, bgr_image):
        lab = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2LAB)
        hsv = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2HSV)
        l_chan = lab[:, :, 0]
        s_chan = hsv[:, :, 1]

        l_blur = cv2.GaussianBlur(l_chan, (5, 5), 0)
        h, w = l_chan.shape
        min_dim = min(h, w)
        block_size = max(51, (min_dim // 12) | 1)

        local_dark = cv2.adaptiveThreshold(
            l_blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, block_size, 20
        )
        dark_abs = (l_blur < 135).astype(np.uint8) * 255
        neutral_mask = (s_chan < 95).astype(np.uint8) * 255
        binary = cv2.bitwise_and(local_dark, cv2.bitwise_and(dark_abs, neutral_mask))

        k_close = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k_close)

        contours, _ = cv2.findContours(
            binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        candidates = []
        for cnt in contours:
            _, _, bw, bh = cv2.boundingRect(cnt)
            bbox_area = float(bw * bh)
            # Each L-bracket bounding box spans ~8% to 25% of image width
            if not ((min_dim * 0.05) ** 2 <= bbox_area <= (min_dim * 0.30) ** 2):
                continue

            # Both arms of an L-bracket are equal length -> nearly square bounding box
            aspect = max(bw, bh) / float(min(bw, bh) + 1e-6)
            if aspect > 1.45:
                continue

            area = cv2.contourArea(cnt)
            hull_area = cv2.contourArea(cv2.convexHull(cnt))
            solidity = area / float(hull_area + 1e-6)
            # Strictly concave L-shape (0.15..0.35) or gusseted TL bracket (0.42..0.60)
            if not (0.14 <= solidity <= 0.62):
                continue

            # Must be solid dark inside the bracket contour (excludes flower outlines)
            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.drawContours(mask, [cnt], -1, 255, thickness=cv2.FILLED)
            if float(np.mean(l_chan[mask > 0])) > 105.0:
                continue

            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            cx = M["m10"] / M["m00"]
            cy = M["m01"] / M["m00"]
            candidates.append({
                "cnt": cnt,
                "centroid": np.array([cx, cy], dtype=np.float32),
                "bbox_area": bbox_area,
                "solidity": solidity,
            })

        if len(candidates) < 4:
            cv2.imwrite("debug_brackets_mask.png", binary)
            raise RuntimeError(
                f"Found only {len(candidates)} corner bracket candidates (need 4)."
            )

        # Sort by bounding-box area: the 4 corner L-brackets have by far the largest square bboxes
        candidates.sort(key=lambda c: c["bbox_area"], reverse=True)
        candidates = candidates[:8]

        best_quad = None
        best_score = 1e9

        for combo in combinations(candidates, 4):
            bboxes = [c["bbox_area"] for c in combo]
            if max(bboxes) / (min(bboxes) + 1e-6) > 2.2:
                continue

            pts = np.array([c["centroid"] for c in combo], dtype=np.float32)
            quad_center = np.mean(pts, axis=0)

            angles = np.arctan2(pts[:, 1] - quad_center[1], pts[:, 0] - quad_center[0])
            order = np.argsort(angles)
            ordered = [combo[i] for i in order]
            p = pts[order]

            d01 = np.linalg.norm(p[1] - p[0])
            d12 = np.linalg.norm(p[2] - p[1])
            d23 = np.linalg.norm(p[3] - p[2])
            d30 = np.linalg.norm(p[0] - p[3])
            diag1 = np.linalg.norm(p[2] - p[0])
            diag2 = np.linalg.norm(p[3] - p[1])

            mean_side = 0.25 * (d01 + d12 + d23 + d30)
            if mean_side < min_dim * 0.30:
                continue

            opp_err = (abs(d01 - d23) + abs(d12 - d30)) / mean_side
            diag_err = abs(diag1 - diag2) / (0.5 * (diag1 + diag2) + 1e-6)
            aspect_err = abs((d01 + d23) - (d12 + d30)) / (2.0 * mean_side)

            if opp_err > 0.25 or diag_err > 0.25 or aspect_err > 0.30:
                continue

            solidities = [c["solidity"] for c in ordered]
            tl_idx = int(np.argmax(solidities))
            other_solidities = [s for idx, s in enumerate(solidities) if idx != tl_idx]
            solidity_gap = solidities[tl_idx] - float(np.mean(other_solidities))

            score = (opp_err + diag_err + aspect_err) * 100.0 - solidity_gap * 120.0 - (mean_side / min_dim) * 50.0
            if score < best_score:
                best_score = score
                rolled = ordered[tl_idx:] + ordered[:tl_idx]
                best_quad = np.array(
                    [self._extract_outer_corner(c["cnt"], quad_center) for c in rolled],
                    dtype=np.float32,
                )

        if best_quad is None:
            cv2.imwrite("debug_brackets_mask.png", binary)
            raise RuntimeError("Could not match a valid 4-corner L-bracket frame.")

        return best_quad

    def rectify_image(self, bgr_image):
        src_corners = self.find_corner_brackets(bgr_image)
        H, _ = cv2.findHomography(src_corners, self.canonical_corners)
        return cv2.warpPerspective(
            bgr_image, H, (self.gen.CANVAS_SIZE, self.gen.CANVAS_SIZE)
        )

    # ------------------------------------------------------------------
    # STEP 2: BLOSSOM SEGMENTATION, CIELAB COLOUR CLUSTERING & LEAF COUNT
    # ------------------------------------------------------------------
    def _cluster_blossom_colours(self, valid_samples):
        """
        Cluster the 20 blossom CIELAB (a*, b*) vectors into 3 colour groups:
          - 0: Terracotta (+a*, +b*)
          - 1: Peacock Teal (-a*, -b*)
          - 2: Saffron Ochre (low |a*|, high +b*)
        Returns a dict mapping sample_idx -> (colour_id, confidence_margin).
        """
        if len(valid_samples) < 3:
            return {idx: (0, 0.0) for idx in valid_samples}

        indices = list(valid_samples.keys())
        ab_pts = np.array([valid_samples[i]["ab"] for i in indices], dtype=np.float32)

        # Deterministic initial seeds in OpenCV LAB [0..255] space (128 = neutral)
        init_centers = np.array([
            [162.0, 152.0],  # Terracotta (+a*, +b*)
            [102.0, 118.0],  # Peacock Teal (-a*, -b*)
            [134.0, 174.0],  # Saffron Ochre (~0 a*, ++b*)
        ], dtype=np.float32)

        centers = init_centers.copy()
        for _ in range(12):
            dists = np.linalg.norm(ab_pts[:, None, :] - centers[None, :, :], axis=2)
            labels = np.argmin(dists, axis=1)
            for cid in range(3):
                members = ab_pts[labels == cid]
                if len(members) > 0:
                    centers[cid] = np.median(members, axis=0)

        results = {}
        for row_i, sym_idx in enumerate(indices):
            d = np.linalg.norm(ab_pts[row_i] - centers, axis=1)
            order = np.argsort(d)
            cid = int(order[0])
            margin = float(d[order[1]] - d[order[0]])
            results[sym_idx] = (cid, margin)
        return results

    def extract_symbol_features(self, warped_bgr, x, y, size, rotation):
        """
        Extract blossom shape circularity, leaf count (0, 1, or 2), and median
        CIELAB (a*, b*) vector at canonical symbol position (x, y).
        """
        pad = int(size * 0.68)
        x0, y0 = max(0, int(round(x - pad))), max(0, int(round(y - pad)))
        x1 = min(self.gen.CANVAS_SIZE, int(round(x + pad)))
        y1 = min(self.gen.CANVAS_SIZE, int(round(y + pad)))
        roi = warped_bgr[y0:y1, x0:x1].copy()

        rh, rw = roi.shape[:2]
        # Rotate ROI back so the blossom is upright (-Y = blossom tip, +Y = stem & leaves)
        M = cv2.getRotationMatrix2D(
            (rw / 2.0, rh / 2.0), math.degrees(rotation), 1.0
        )
        upright = cv2.warpAffine(
            roi, M, (rw, rh), flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT, borderValue=self.gen.BACKGROUND
        )

        hsv = cv2.cvtColor(upright, cv2.COLOR_BGR2HSV)
        h_chan, s_chan, v_chan = cv2.split(hsv)

        # 1. Isolate high-saturation foreground pixels (excludes low-saturation background/decoys)
        fg_mask = (s_chan > 55) & (v_chan > 45)

        # 2. Separate green sage leaves (OpenCV Hue in [42, 85]) from blossom head
        leaf_mask = (fg_mask & (h_chan >= 42) & (h_chan <= 85)).astype(np.uint8) * 255
        blossom_mask = (fg_mask & ((h_chan < 42) | (h_chan > 85))).astype(np.uint8) * 255

        # Clean noise on blossom mask
        k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        blossom_mask = cv2.morphologyEx(blossom_mask, cv2.MORPH_OPEN, k3)
        blossom_mask = cv2.morphologyEx(blossom_mask, cv2.MORPH_CLOSE, k3)

        contours, _ = cv2.findContours(
            blossom_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            return None

        main_cnt = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(main_cnt)
        if area < (size * 0.18) ** 2:
            return None

        # Fill interior (including tiny stamen dot) before computing circularity
        filled_blossom = np.zeros_like(blossom_mask)
        cv2.drawContours(filled_blossom, [main_cnt], -1, 255, thickness=cv2.FILLED)
        filled_cnts, _ = cv2.findContours(
            filled_blossom, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        outer_cnt = max(filled_cnts, key=cv2.contourArea)

        f_area = cv2.contourArea(outer_cnt)
        perim = cv2.arcLength(outer_cnt, True)
        circularity = 4.0 * math.pi * f_area / (perim * perim + 1e-6)

        # 3. Classify Botanical Growth Stage from Circularity
        #    0: Closed Bud (~0.91), 1: Half-Open Bloom (~0.72), 2: Full 4-Petal Blossom (~0.44)
        if circularity > 0.81:
            stage_id = 0
            stage_margin = (circularity - 0.81) * 10.0
        elif circularity > 0.58:
            stage_id = 1
            stage_margin = min(0.81 - circularity, circularity - 0.58) * 10.0
        else:
            stage_id = 2
            stage_margin = (0.58 - circularity) * 10.0

        # 4. Count Leaves (0, 1, or 2) in the lower stem region (+Y half of upright ROI)
        leaf_mask = cv2.morphologyEx(leaf_mask, cv2.MORPH_OPEN, k3)
        # Restrict leaf search below blossom centroid
        m_blossom = cv2.moments(filled_blossom)
        bcy = (m_blossom["m01"] / m_blossom["m00"]) if m_blossom["m00"] > 0 else (rh * 0.42)
        leaf_mask[:int(bcy + size * 0.12), :] = 0

        num_labels, _, stats, _ = cv2.connectedComponentsWithStats(leaf_mask)
        min_leaf_area = max(12.0, (size * 0.11) ** 2)
        valid_leaves = [
            stats[lbl, cv2.CC_STAT_AREA]
            for lbl in range(1, num_labels)
            if stats[lbl, cv2.CC_STAT_AREA] >= min_leaf_area
        ]
        leaf_count = min(2, len(valid_leaves))
        leaf_margin = 1.0 if len(valid_leaves) <= 2 else 0.4

        # 5. Extract median CIELAB (a*, b*) of blossom head for global clustering
        lab_up = cv2.cvtColor(upright, cv2.COLOR_BGR2LAB).astype(np.float32)
        fg_pixels = lab_up[blossom_mask > 0]
        median_ab = np.median(fg_pixels[:, 1:], axis=0)

        return {
            "ab": median_ab,
            "stage_id": stage_id,
            "stage_margin": stage_margin,
            "leaf_count": leaf_count,
            "leaf_margin": leaf_margin,
        }

    # ------------------------------------------------------------------
    # STEP 3: FULL IMAGE -> REED-SOLOMON -> 3-WORD DECODE
    # ------------------------------------------------------------------
    def decode_image(self, image_path, debug_warped_path=None):
        bgr = cv2.imread(image_path)
        if bgr is None:
            raise FileNotFoundError(f"Could not read image: {image_path}")

        warped = self.rectify_image(bgr)
        if debug_warped_path:
            cv2.imwrite(debug_warped_path, warped)

        layout = self.gen.generate_ring_layout()

        extracted = {}
        for idx, (x, y, size, rotation) in enumerate(layout):
            feat = self.extract_symbol_features(warped, x, y, size, rotation)
            if feat is not None:
                extracted[idx] = feat

        colour_results = self._cluster_blossom_colours(extracted)

        digits = []
        confidences = []
        for idx in range(self.gen.SYMBOL_COUNT):
            if idx not in extracted:
                digits.append(0)
                confidences.append(0.0)  # Missing symbol -> flagged as Reed-Solomon erasure
                continue

            feat = extracted[idx]
            colour_id, col_margin = colour_results[idx]
            digit = colour_id * 9 + feat["stage_id"] * 3 + feat["leaf_count"]
            conf = min(col_margin / 12.0, feat["stage_margin"], feat["leaf_margin"])

            digits.append(digit)
            confidences.append(conf)

        symbols_str = "".join(self.ALPHABET[d] for d in digits)

        # Flag up to 4 lowest-confidence symbols as erasures (RSCodec(4) supports up to 4)
        uncertain = [
            idx for idx, c in sorted(enumerate(confidences), key=lambda kv: kv[1])
            if c < 0.35
        ][:4]

        try:
            gt = "0E8G14696I94233O7E53"
            for i, (g, p) in enumerate(zip(gt, symbols_str)):
                gd, pd = self.ALPHABET.index(g), self.ALPHABET.index(p)
                print(f"{i:2d}: GT={g} (C={gd // 9}, S={(gd % 9) // 3}, L={gd % 3}) | "
                      f"PRED={p} (C={pd // 9}, S={(pd % 9) // 3}, L={pd % 3})  conf={confidences[i]:.2f}")
            w1, w2, w3 = self.encoder.decode(
                symbols_str, uncertain_positions=uncertain
            )
        except ValueError:
            w1, w2, w3 = self.encoder.decode(symbols_str)

        words = (
            self.encoder.words[w1],
            self.encoder.words[w2],
            self.encoder.words[w3],
        )

        return {
            "symbols": symbols_str,
            "uncertain_positions": uncertain,
            "indices": (w1, w2, w3),
            "words": words,
        }