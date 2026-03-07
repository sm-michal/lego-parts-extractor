"""Matching engine - matches extracted parts with reference database."""

import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

import numpy as np
import cv2
from skimage.metrics import structural_similarity

from .pieces_parser import PieceReference
from .parts_detector import ExtractedPart

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Result of matching an extracted part with reference pieces."""

    extracted_part: ExtractedPart
    best_match: Optional[str]  # Piece number of best match
    confidence: float  # 0-1 confidence score
    match_method: str  # Method used (template, feature, ssim)
    alternatives: List[Tuple[str, float]]  # List of (piece_number, confidence)


class MatchingEngine:
    """Engine for matching extracted parts with reference database."""

    def __init__(
        self,
        reference_database: Dict[str, PieceReference],
        confidence_threshold: float = 0.75,
        top_n_alternatives: int = 3,
        match_color: bool = True,
    ):
        """Initialize matching engine.

        Args:
            reference_database: Dictionary of piece_number -> PieceReference
            confidence_threshold: Minimum confidence for high-confidence match
            top_n_alternatives: Number of alternatives to return
            match_color: Whether to include color in matching
        """
        self.reference_database = reference_database
        self.confidence_threshold = confidence_threshold
        self.top_n_alternatives = top_n_alternatives
        self.match_color = match_color
        self.logger = logging.getLogger(__name__)

    def match_all(self, extracted_parts: List[ExtractedPart]) -> List[MatchResult]:
        """Match all extracted parts with reference database.

        Args:
            extracted_parts: List of extracted parts to match

        Returns:
            List of MatchResult objects
        """
        results = []

        for i, part in enumerate(extracted_parts, 1):
            self.logger.debug(f"    Matching part {i}/{len(extracted_parts)}...")
            result = self.match_single(part)
            results.append(result)

            if result.best_match:
                conf_pct = result.confidence * 100
                if result.confidence >= self.confidence_threshold:
                    self.logger.debug(
                        f"      ✓ Matched: {result.best_match} ({conf_pct:.1f}%)"
                    )
                else:
                    alts = ", ".join(
                        [f"{pn}({c * 100:.0f}%)" for pn, c in result.alternatives[:2]]
                    )
                    self.logger.debug(
                        f"      ⚠ Low conf: {result.best_match} ({conf_pct:.1f}%), alts: {alts}"
                    )
            else:
                self.logger.debug(f"      ✗ No match found")

        return results

    def match_single(self, extracted_part: ExtractedPart) -> MatchResult:
        """Match a single extracted part with reference database.

        Args:
            extracted_part: Part to match

        Returns:
            MatchResult with best match and alternatives
        """
        if not self.reference_database:
            return MatchResult(
                extracted_part=extracted_part,
                best_match=None,
                confidence=0.0,
                match_method="none",
                alternatives=[],
            )

        # Get normalized image from extracted part
        extracted_norm = extracted_part.normalized_image

        # Try each matching method and combine scores
        all_scores = {}

        for piece_num, piece_ref in self.reference_database.items():
            # Quick size filter
            if not self._similar_size(extracted_part.image, piece_ref.image):
                continue

            reference_norm = piece_ref.normalized_image

            # Stage 1: Template matching
            template_score = self._template_match(extracted_norm, reference_norm)

            # Stage 2: Feature matching (SIFT/ORB)
            feature_score = self._feature_match(extracted_part.image, piece_ref.image)

            # Stage 3: Structural similarity
            ssim_score = self._structural_similarity(extracted_norm, reference_norm)

            # Stage 4: Color similarity (if enabled)
            color_score = 1.0
            if self.match_color and len(extracted_part.image.shape) == 3:
                color_score = self._color_similarity(
                    extracted_part.image, piece_ref.image
                )

            # Weighted combination
            combined_score = (
                template_score * 0.4
                + feature_score * 0.3
                + ssim_score * 0.2
                + color_score * 0.1
            )

            # Determine primary method
            method_scores = {
                "template": template_score,
                "feature": feature_score,
                "ssim": ssim_score,
            }
            primary_method = max(method_scores, key=method_scores.get)

            all_scores[piece_num] = (combined_score, primary_method)

        # Sort by score
        sorted_matches = sorted(all_scores.items(), key=lambda x: x[1][0], reverse=True)

        # Get best match and alternatives
        if sorted_matches:
            best_match_num, (best_score, best_method) = sorted_matches[0]
            alternatives = [
                (piece_num, score)
                for piece_num, (score, _) in sorted_matches[
                    1 : self.top_n_alternatives + 1
                ]
            ]
        else:
            best_match_num = None
            best_score = 0.0
            best_method = "none"
            alternatives = []

        return MatchResult(
            extracted_part=extracted_part,
            best_match=best_match_num,
            confidence=best_score,
            match_method=best_method,
            alternatives=alternatives,
        )

    def _similar_size(
        self,
        img1: np.ndarray,
        img2: np.ndarray,
        tolerance: float = 0.5,
    ) -> bool:
        """Check if two images have similar size.

        Args:
            img1: First image
            img2: Second image
            tolerance: Size difference tolerance (0-1)

        Returns:
            True if sizes are similar
        """
        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]

        area1 = h1 * w1
        area2 = h2 * w2

        if area1 == 0 or area2 == 0:
            return False

        ratio = min(area1, area2) / max(area1, area2)
        return ratio >= (1 - tolerance)

    def _template_match(
        self,
        extracted: np.ndarray,
        reference: np.ndarray,
    ) -> float:
        """Template matching using normalized cross-correlation.

        Args:
            extracted: Extracted part image (normalized)
            reference: Reference piece image (normalized)

        Returns:
            Match score (0-1)
        """
        try:
            # Ensure both images are grayscale
            if len(extracted.shape) == 3:
                extracted = cv2.cvtColor(extracted, cv2.COLOR_RGB2GRAY)
            if len(reference.shape) == 3:
                reference = cv2.cvtColor(reference, cv2.COLOR_RGB2GRAY)

            # Ensure same size (they should be from normalization)
            if extracted.shape != reference.shape:
                reference = cv2.resize(
                    reference, (extracted.shape[1], extracted.shape[0])
                )

            # Use normalized cross-correlation
            result = cv2.matchTemplate(extracted, reference, cv2.TM_CCOEFF_NORMED)

            # Get maximum value
            _, max_val, _, _ = cv2.minMaxLoc(result)

            # Convert to 0-1 range (TM_CCOEFF_NORMED returns -1 to 1)
            score = (max_val + 1) / 2.0

            return max(0.0, min(1.0, score))

        except Exception as e:
            self.logger.debug(f"Template match error: {e}")
            return 0.0

    def _feature_match(
        self,
        extracted: np.ndarray,
        reference: np.ndarray,
    ) -> float:
        """Feature-based matching using ORB.

        Args:
            extracted: Extracted part image
            reference: Reference piece image

        Returns:
            Match score (0-1)
        """
        try:
            # Convert to grayscale if needed
            if len(extracted.shape) == 3:
                extracted_gray = cv2.cvtColor(extracted, cv2.COLOR_RGB2GRAY)
            else:
                extracted_gray = extracted

            if len(reference.shape) == 3:
                reference_gray = cv2.cvtColor(reference, cv2.COLOR_RGB2GRAY)
            else:
                reference_gray = reference

            # Initialize ORB detector
            orb = cv2.ORB_create(nfeatures=100)

            # Detect keypoints and compute descriptors
            kp1, des1 = orb.detectAndCompute(extracted_gray, None)
            kp2, des2 = orb.detectAndCompute(reference_gray, None)

            if des1 is None or des2 is None or len(kp1) < 2 or len(kp2) < 2:
                return 0.0

            # Match descriptors using BFMatcher
            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
            matches = bf.match(des1, des2)

            if not matches:
                return 0.0

            # Calculate score based on number of good matches
            # Normalize by minimum number of keypoints
            min_keypoints = min(len(kp1), len(kp2))
            score = len(matches) / max(min_keypoints, 1)

            return max(0.0, min(1.0, score))

        except Exception as e:
            self.logger.debug(f"Feature match error: {e}")
            return 0.0

    def _structural_similarity(
        self,
        extracted: np.ndarray,
        reference: np.ndarray,
    ) -> float:
        """Structural similarity (SSIM) matching.

        Args:
            extracted: Extracted part image (normalized)
            reference: Reference piece image (normalized)

        Returns:
            Match score (0-1)
        """
        try:
            # Ensure grayscale
            if len(extracted.shape) == 3:
                extracted = cv2.cvtColor(extracted, cv2.COLOR_RGB2GRAY)
            if len(reference.shape) == 3:
                reference = cv2.cvtColor(reference, cv2.COLOR_RGB2GRAY)

            # Ensure same size
            if extracted.shape != reference.shape:
                reference = cv2.resize(
                    reference, (extracted.shape[1], extracted.shape[0])
                )

            # Compute SSIM
            score = structural_similarity(extracted, reference)

            # SSIM returns -1 to 1, convert to 0-1
            score = (score + 1) / 2.0

            return max(0.0, min(1.0, score))

        except Exception as e:
            self.logger.debug(f"SSIM error: {e}")
            return 0.0

    def _color_similarity(
        self,
        extracted: np.ndarray,
        reference: np.ndarray,
    ) -> float:
        """Color histogram similarity.

        Args:
            extracted: Extracted part image
            reference: Reference piece image

        Returns:
            Match score (0-1)
        """
        try:
            # Ensure RGB
            if len(extracted.shape) == 2:
                extracted = cv2.cvtColor(extracted, cv2.COLOR_GRAY2RGB)
            if len(reference.shape) == 2:
                reference = cv2.cvtColor(reference, cv2.COLOR_GRAY2RGB)

            # Compute histograms for each channel
            hist_extracted = []
            hist_reference = []

            for i in range(3):  # R, G, B
                hist_e = cv2.calcHist([extracted], [i], None, [32], [0, 256])
                hist_r = cv2.calcHist([reference], [i], None, [32], [0, 256])

                # Normalize
                hist_e = cv2.normalize(hist_e, hist_e).flatten()
                hist_r = cv2.normalize(hist_r, hist_r).flatten()

                hist_extracted.append(hist_e)
                hist_reference.append(hist_r)

            # Compare histograms using correlation
            correlations = []
            for i in range(3):
                corr = cv2.compareHist(
                    hist_extracted[i].reshape(-1, 1).astype(np.float32),
                    hist_reference[i].reshape(-1, 1).astype(np.float32),
                    cv2.HISTCMP_CORREL,
                )
                correlations.append(corr)

            # Average correlation across channels
            score = np.mean(correlations)

            # Correlation returns -1 to 1, convert to 0-1
            score = (score + 1) / 2.0

            return max(0.0, min(1.0, score))

        except Exception as e:
            self.logger.debug(f"Color similarity error: {e}")
            return 0.5  # Neutral score if color matching fails
