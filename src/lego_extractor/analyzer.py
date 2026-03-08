"""PDF analysis module for detecting pieces list pages and structure."""

import logging
import re
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass

import pdfplumber

from .utils import format_page_ranges


logger = logging.getLogger(__name__)


@dataclass
class PDFAnalysisResult:
    """Result of PDF analysis."""

    instruction_pdf: Path
    pieces_pdf: Path
    total_pages: int
    detected_pieces_pages: List[int]
    instruction_page_candidates: List[int]
    pieces_count_estimate: int

    def format_output(self) -> str:
        """Format analysis result as human-readable string."""
        lines = [
            "=== PDF Analysis Results ===",
            "",
            f"Instruction PDF: {self.instruction_pdf}",
            f"Pieces PDF: {self.pieces_pdf}",
            f"Total pages: {self.total_pages}",
            "",
        ]

        if self.detected_pieces_pages:
            pages_str = format_page_ranges(self.detected_pieces_pages)
            lines.append(f"Detected pieces list pages: {pages_str}")
            lines.append(f"Estimated pieces count: {self.pieces_count_estimate}")
        else:
            lines.append("Detected pieces list pages: None (auto-detection failed)")
            lines.append("Please specify --pieces-pages manually")

        lines.append("")

        if self.instruction_page_candidates:
            pages_str = format_page_ranges(self.instruction_page_candidates)
            lines.append(f"Instruction pages: {pages_str}")
        else:
            lines.append("Instruction pages: All other pages")

        lines.append("")
        lines.append("Suggestions:")
        if self.detected_pieces_pages:
            example_range = format_page_ranges(self.instruction_page_candidates[:10])
            lines.append(f"  To extract parts from first few instruction pages:")
            lines.append(f"    --instruction-pages {example_range}")
        else:
            lines.append("  Manual specification required:")
            lines.append("    --pieces-pages <pages> --instruction-pages <pages>")

        return "\n".join(lines)


class PDFAnalyzer:
    """Analyzes PDF structure to detect pieces list pages."""

    # Heuristics thresholds
    MIN_PIECE_NUMBERS = 35  # Minimum 6-7 digit numbers per page
    MIN_QUANTITIES = 35  # Minimum quantity indicators per page
    MIN_IMAGES = 50  # Minimum images per page

    def __init__(self, instruction_pdf: Path, pieces_pdf: Path):
        """Initialize PDF analyzer.

        Args:
            instruction_pdf: Path to instruction PDF
            pieces_pdf: Path to pieces list PDF (may be same as instruction_pdf)
        """
        self.instruction_pdf = instruction_pdf
        self.pieces_pdf = pieces_pdf
        self.logger = logging.getLogger(__name__)

    def analyze(self) -> PDFAnalysisResult:
        """Analyze PDF structure and detect pieces list pages.

        Returns:
            PDFAnalysisResult with detected pages and metadata
        """
        self.logger.info("Analyzing PDF structure...")

        # Analyze pieces PDF
        with pdfplumber.open(self.pieces_pdf) as pdf:
            total_pages = len(pdf.pages)
            self.logger.info(f"Total pages in pieces PDF: {total_pages}")

            # Scan from end backwards (pieces list usually near end)
            detected_pieces_pages = []
            pieces_count_estimate = 0

            for page_num in range(total_pages - 1, -1, -1):
                page = pdf.pages[page_num]
                score, piece_count = self._score_pieces_list_page(page)

                if score > 0:
                    detected_pieces_pages.append(page_num + 1)  # Convert to 1-indexed
                    pieces_count_estimate += piece_count
                    self.logger.debug(
                        f"Page {page_num + 1}: Pieces list candidate (score={score}, pieces={piece_count})"
                    )

                # Stop if we've gone too far back (pieces list usually contiguous)
                if len(detected_pieces_pages) > 0 and score == 0:
                    # Check if we have a gap - if so, stop
                    if len(detected_pieces_pages) >= 2:
                        break

            detected_pieces_pages.reverse()  # Restore ascending order

            # Additional check: if pieces list is near end of PDF, check remaining pages
            # Use lower threshold - just check if there are ANY quantities or piece numbers
            if detected_pieces_pages:
                last_detected = detected_pieces_pages[-1]
                remaining_pages = total_pages - last_detected
                if remaining_pages > 0 and remaining_pages < 5:
                    self.logger.debug(
                        f"Pieces list ends at page {last_detected}, checking {remaining_pages} remaining pages..."
                    )
                    for page_num in range(last_detected + 1, total_pages + 1):
                        page = pdf.pages[page_num - 1]
                        if self._has_any_pieces_or_quantities(page):
                            detected_pieces_pages.append(page_num)
                            self.logger.debug(f"  Added page {page_num} (has pieces/quantities)")
                        else:
                            break

        # Determine instruction page candidates
        if self.instruction_pdf == self.pieces_pdf:
            # Same PDF - instruction pages are all others
            all_pages = set(range(1, total_pages + 1))
            pieces_pages_set = set(detected_pieces_pages)
            instruction_page_candidates = sorted(all_pages - pieces_pages_set)
        else:
            # Different PDF - all pages are instruction pages
            with pdfplumber.open(self.instruction_pdf) as pdf:
                instruction_page_candidates = list(range(1, len(pdf.pages) + 1))

        result = PDFAnalysisResult(
            instruction_pdf=self.instruction_pdf,
            pieces_pdf=self.pieces_pdf,
            total_pages=total_pages,
            detected_pieces_pages=detected_pieces_pages,
            instruction_page_candidates=instruction_page_candidates,
            pieces_count_estimate=pieces_count_estimate,
        )

        if detected_pieces_pages:
            self.logger.info(
                f"Detected pieces list pages: {format_page_ranges(detected_pieces_pages)}"
            )
            self.logger.info(f"Estimated pieces: {pieces_count_estimate}")
        else:
            self.logger.warning("Could not auto-detect pieces list pages")

        return result

    def _score_pieces_list_page(self, page) -> tuple[int, int]:
        """Score a page for likelihood of being a pieces list page.

        Args:
            page: pdfplumber page object

        Returns:
            Tuple of (score, estimated_piece_count)
            Score > 0 indicates likely pieces list page
        """
        score = 0

        # Extract text
        text = page.extract_text()
        if not text:
            return 0, 0

        # Count piece numbers (6-7 digit sequences)
        piece_numbers = re.findall(r"\b\d{6,7}\b", text)
        piece_count = len(piece_numbers)

        # Count quantities (e.g., 1x, 2x, 3x, etc.)
        quantities = re.findall(r"\b\d+x\b", text, re.IGNORECASE)
        quantity_count = len(quantities)

        # Count images
        image_count = len(page.images) if page.images else 0

        # Scoring - all criteria must be reasonably met
        # Require minimum thresholds for piece numbers AND quantities
        if (
            piece_count < self.MIN_PIECE_NUMBERS * 0.7
            or quantity_count < self.MIN_QUANTITIES * 0.7
        ):
            return 0, 0  # Definitely not a pieces list page

        if piece_count >= self.MIN_PIECE_NUMBERS:
            score += 3
        elif piece_count >= self.MIN_PIECE_NUMBERS * 0.8:
            score += 2
        elif piece_count >= self.MIN_PIECE_NUMBERS * 0.7:
            score += 1

        if quantity_count >= self.MIN_QUANTITIES:
            score += 3
        elif quantity_count >= self.MIN_QUANTITIES * 0.8:
            score += 2
        elif quantity_count >= self.MIN_QUANTITIES * 0.7:
            score += 1

        if image_count >= self.MIN_IMAGES:
            score += 2
        elif image_count >= self.MIN_IMAGES * 0.7:
            score += 1

        # Piece numbers and quantities should be roughly equal
        if piece_count > 0 and abs(piece_count - quantity_count) <= max(
            5, piece_count * 0.1
        ):
            score += 1

        self.logger.debug(
            f"Page scoring - pieces:{piece_count}, qty:{quantity_count}, "
            f"img:{image_count}, score:{score}"
        )

        return score, piece_count

    def _has_any_pieces_or_quantities(self, page) -> bool:
        """Check if page has any piece numbers or quantities (low threshold check).

        Args:
            page: pdfplumber page object

        Returns:
            True if page has any piece numbers or quantities
        """
        text = page.extract_text()
        if not text:
            return False

        piece_numbers = re.findall(r"\b\d{6,7}\b", text)
        quantities = re.findall(r"\b\d+x\b", text, re.IGNORECASE)

        return len(piece_numbers) > 0 or len(quantities) > 0


def auto_detect_pieces_pages(pdf_path: Path) -> List[int]:
    """Auto-detect pieces list pages in PDF.

    Args:
        pdf_path: Path to PDF file

    Returns:
        List of detected pieces list page numbers (1-indexed)
    """
    analyzer = PDFAnalyzer(pdf_path, pdf_path)
    result = analyzer.analyze()
    return result.detected_pieces_pages
