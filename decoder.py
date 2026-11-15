from itertools import combinations
from collections import Counter
import math
import os
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
    def _find_quad_candidate(
        self,
        binary,
        min_dim,
        min_box_fraction=0.30,
        min_area_fraction=0.10,
        min_side_fraction=0.30,
        contour_mode=cv2.RETR_EXTERNAL,
    ):
        h, w = binary.shape
        contours, _ = cv2.findContours(
            binary, contour_mode, cv2.CHAIN_APPROX_SIMPLE
        )

        hull_candidates = []
        for cnt in contours:
            hull = cv2.convexHull(cnt)
            x, y, bw, bh = cv2.boundingRect(hull)
            if bw < min_dim * min_box_fraction or bh < min_dim * min_box_fraction:
                continue
            if x <= 1 or y <= 1 or x + bw >= w - 1 or y + bh >= h - 1:
                continue
            aspect = bw / float(bh + 1e-6)
            if not 0.55 <= aspect <= 1.8:
                continue
            hull_area = cv2.contourArea(hull)
            if hull_area < min_dim * min_dim * min_area_fraction:
                continue
            hull_candidates.append((hull_area, hull))

        best_quad = None
        best_score = float("inf")
        hull_candidates.sort(key=lambda candidate: candidate[0], reverse=True)
        for _, hull in hull_candidates[:30]:
            perimeter = cv2.arcLength(hull, True)
            epsilon = max(2.0, perimeter * 0.01)
            approximated = cv2.approxPolyDP(hull, epsilon, True).reshape(-1, 2)
            while len(approximated) > 12 and epsilon < perimeter * 0.10:
                epsilon *= 1.5
                approximated = cv2.approxPolyDP(hull, epsilon, True).reshape(-1, 2)
            if not 4 <= len(approximated) <= 12:
                continue

            for points in combinations(approximated, 4):
                points = np.asarray(points, dtype=np.float32)
                center = np.mean(points, axis=0)
                angles = np.arctan2(
                    points[:, 1] - center[1], points[:, 0] - center[0]
                )
                quad = points[np.argsort(angles)]

                sides = [
                    np.linalg.norm(quad[(i + 1) % 4] - quad[i])
                    for i in range(4)
                ]
                mean_side = float(np.mean(sides))
                if mean_side < min_dim * min_side_fraction:
                    continue

                diagonal_1 = np.linalg.norm(quad[2] - quad[0])
                diagonal_2 = np.linalg.norm(quad[3] - quad[1])
                opposite_error = (
                    abs(sides[0] - sides[2]) + abs(sides[1] - sides[3])
                ) / (mean_side + 1e-6)
                diagonal_error = abs(diagonal_1 - diagonal_2) / (
                    0.5 * (diagonal_1 + diagonal_2) + 1e-6
                )
                aspect_error = abs(
                    (sides[0] + sides[2]) - (sides[1] + sides[3])
                ) / (2.0 * mean_side + 1e-6)
                if (
                    opposite_error > 0.40
                    or diagonal_error > 0.40
                    or aspect_error > 0.40
                ):
                    continue

                quad_area = abs(cv2.contourArea(quad))
                if quad_area < min_dim * min_dim * min_area_fraction:
                    continue

                score = (
                    (opposite_error + diagonal_error + aspect_error) * 100.0
                    - (mean_side / min_dim) * 25.0
                )
                if score < best_score:
                    best_score = score
                    best_quad = quad

        return best_quad

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

        best_quad = self._find_quad_candidate(binary, min_dim)
        marker_mask = cv2.adaptiveThreshold(
            l_blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, block_size, 20
        )

        if best_quad is None:
            fallback_mask = cv2.morphologyEx(
                marker_mask, cv2.MORPH_CLOSE, k_close, iterations=2
            )
            best_quad = self._find_quad_candidate(
                fallback_mask,
                min_dim,
                min_box_fraction=0.18,
                min_area_fraction=0.025,
                min_side_fraction=0.18,
                contour_mode=cv2.RETR_LIST,
            )

        if best_quad is None:
            raise RuntimeError(
                "Could not locate a clear four-corner artwork frame. "
                "Include all corner markers, move closer, and reduce glare or reflections."
            )

        # Adaptive luminance thresholding is less sensitive to shadows and screen glare.
        marker_scores = []
        for shift in range(4):
            ordered = np.roll(best_quad, -shift, axis=0).astype(np.float32)
            transform = cv2.getPerspectiveTransform(ordered, self.canonical_corners)
            normalized = cv2.warpPerspective(
                marker_mask,
                transform,
                (self.gen.CANVAS_SIZE, self.gen.CANVAS_SIZE),
                flags=cv2.INTER_NEAREST,
            )
            inset = int(self.gen.BRACKET_INSET)
            arm = int(self.gen.BRACKET_ARM)
            corner = normalized[inset:inset + arm, inset:inset + arm]
            marker_scores.append(float(np.mean(corner > 0)))

        best_shift = int(np.argmax(marker_scores))
        ordered_scores = sorted(marker_scores, reverse=True)
        if ordered_scores[0] - ordered_scores[1] < 0.01:
            raise RuntimeError(
                "Found the artwork frame, but its orientation marker is ambiguous. "
                "Make sure the asymmetric corner marker is visible and unobstructed."
            )

        return np.roll(best_quad, -best_shift, axis=0).astype(np.float32)

    def rectify_image(self, bgr_image):
        src_corners = self.find_corner_brackets(bgr_image)
        H = cv2.getPerspectiveTransform(src_corners, self.canonical_corners)
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
        raw_blossom_mask = blossom_mask.copy()

        # Smooth screen and print noise before measuring the blossom contour.
        k7 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        blossom_mask = cv2.morphologyEx(blossom_mask, cv2.MORPH_OPEN, k7)
        blossom_mask = cv2.morphologyEx(blossom_mask, cv2.MORPH_CLOSE, k7)

        contours, _ = cv2.findContours(
            blossom_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            return None

        main_cnt = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(main_cnt)
        min_area = (size * 0.18) ** 2
        if area < min_area:
            k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            blossom_mask = cv2.morphologyEx(
                raw_blossom_mask, cv2.MORPH_OPEN, k3
            )
            blossom_mask = cv2.morphologyEx(
                blossom_mask, cv2.MORPH_CLOSE, k3
            )
            contours, _ = cv2.findContours(
                blossom_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            if not contours:
                return None
            main_cnt = max(contours, key=cv2.contourArea)
            if cv2.contourArea(main_cnt) < min_area:
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
        #    0: Closed Bud, 1: Half-Open Bloom, 2: Full 4-Petal Blossom
        if circularity > 0.78:
            stage_id = 0
            stage_margin = (circularity - 0.78) * 10.0
        elif circularity > 0.69:
            stage_id = 1
            stage_margin = min(0.78 - circularity, circularity - 0.69) * 10.0
        else:
            stage_id = 2
            stage_margin = (0.69 - circularity) * 10.0

        # 4. Count Leaves (0, 1, or 2) in the lower stem region (+Y half of upright ROI)
        k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
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
            if os.path.realpath(debug_warped_path) == os.path.realpath(image_path):
                raise ValueError("Debug warp path must not overwrite the source image")
            if not cv2.imwrite(debug_warped_path, warped):
                raise OSError(f"Could not write debug warp: {debug_warped_path}")

        layout = self.gen.generate_ring_layout()

        extracted = {}
        for idx, (x, y, size, rotation) in enumerate(layout):
            feat = self.extract_symbol_features(warped, x, y, size, rotation)
            if feat is not None:
                extracted[idx] = feat

        missing = self.gen.SYMBOL_COUNT - len(extracted)
        if missing > self.encoder.PARITY_BYTES:
            raise ValueError(
                f"Could not detect {missing} symbols; at most "
                f"{self.encoder.PARITY_BYTES} erasures can be recovered."
            )

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

        # Group uncertain symbols by byte: either base-27 digit makes that byte an erasure.
        low_confidence = [
            idx for idx, c in sorted(enumerate(confidences), key=lambda kv: kv[1])
            if c < 0.35
        ]
        uncertain_by_byte = {}
        for idx in low_confidence:
            uncertain_by_byte.setdefault(idx // 2, idx)
        uncertain_candidates = list(uncertain_by_byte.values())

        if len(uncertain_candidates) <= self.encoder.PARITY_BYTES:
            uncertain = uncertain_candidates
            try:
                indices = self.encoder.decode(
                    symbols_str, uncertain_positions=uncertain
                )
            except ValueError as exc:
                raise ValueError(
                    "Could not decode the artwork reliably: symbol errors exceeded "
                    "the correction limit. Use a sharper image with less glare and "
                    "the complete artwork in frame."
                ) from exc
        else:
            # Test bounded alternatives for the low-confidence bytes. A stable
            # Reed-Solomon result is safer than accepting a single possible miscorrection.
            candidates = uncertain_candidates[:8]
            attempts = []
            for count in range(self.encoder.PARITY_BYTES + 1):
                for subset in combinations(candidates, count):
                    try:
                        decoded_indices = self.encoder.decode(
                            symbols_str, uncertain_positions=list(subset)
                        )
                    except ValueError:
                        continue
                    attempts.append((decoded_indices, subset))

            if not attempts:
                raise ValueError(
                    "Could not decode the artwork reliably: symbol errors exceeded "
                    "the correction limit. Use a sharper image with less glare and "
                    "the complete artwork in frame."
                )

            votes = Counter(decoded_indices for decoded_indices, _ in attempts)
            indices, vote_count = votes.most_common(1)[0]
            if vote_count / len(attempts) < 0.60 or list(votes.values()).count(vote_count) > 1:
                raise ValueError(
                    "Could not decode confidently: plausible symbol corrections "
                    "disagree. Use a sharper image with less glare and the complete "
                    "artwork in frame."
                )

            winning_subsets = [
                subset for decoded_indices, subset in attempts
                if decoded_indices == indices
            ]
            uncertain = list(min(
                winning_subsets,
                key=lambda subset: (len(subset), sum(confidences[idx] for idx in subset)),
            ))

        w1, w2, w3 = indices

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