"""Main extractor class - coordinates all extraction phases."""

import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from .analyzer import auto_detect_pieces_pages
from .pieces_parser import PiecesListParser
from .parts_detector import PartsDetector
from .matching_engine import MatchingEngine
from .utils import format_page_ranges


logger = logging.getLogger(__name__)


class ExtractionResult:
    """Result of extraction process."""

    def __init__(self):
        """Initialize extraction result."""
        self.shopping_list = {}  # piece_number -> data
        self.metadata = {}
        self.unique_piece_count = 0
        self.total_parts_count = 0
        self.high_confidence_count = 0
        self.low_confidence_count = 0
        self.unmatched_count = 0

    @property
    def high_confidence_percentage(self) -> float:
        """Calculate percentage of high confidence matches."""
        total = (
            self.high_confidence_count
            + self.low_confidence_count
            + self.unmatched_count
        )
        if total == 0:
            return 0.0
        return (self.high_confidence_count / total) * 100.0

    @property
    def low_confidence_percentage(self) -> float:
        """Calculate percentage of low confidence matches."""
        total = (
            self.high_confidence_count
            + self.low_confidence_count
            + self.unmatched_count
        )
        if total == 0:
            return 0.0
        return (self.low_confidence_count / total) * 100.0

    def format_output(self, format: str = "csv") -> str:
        """Format result for output.

        Args:
            format: Output format ("csv" or "json")

        Returns:
            Formatted output string
        """
        if format == "csv":
            return self._format_csv()
        elif format == "json":
            return self._format_json()
        else:
            raise ValueError(f"Unknown format: {format}")

    def _format_csv(self) -> str:
        """Format result as CSV."""
        lines = [
            "piece_number,total_quantity,occurrences,avg_confidence,match_method,notes"
        ]

        for piece_num, data in sorted(self.shopping_list.items()):
            notes = data.get("notes", "")
            lines.append(
                f"{piece_num},{data['total_quantity']},{data['occurrences']},"
                f'{data["avg_confidence"]:.2f},{data["match_method"]},"{notes}"'
            )

        return "\n".join(lines)

    def _format_json(self) -> str:
        """Format result as JSON."""
        import json

        output = {
            "metadata": self.metadata,
            "shopping_list": self.shopping_list,
            "summary_list": [
                f"{piece_num}: {data['total_quantity']}x"
                for piece_num, data in sorted(self.shopping_list.items())
            ],
        }
        return json.dumps(output, indent=2)

    def save(self, path: Path, format: str = "csv") -> None:
        """Save result to file.

        Args:
            path: Output file path
            format: Output format ("csv" or "json")
        """
        content = self.format_output(format)
        path.write_text(content, encoding="utf-8")
        logger.info(f"Saved results to: {path}")


class LegoPartsExtractor:
    """Main extractor class that coordinates all phases."""

    def __init__(
        self,
        instruction_pdf: Path,
        pieces_pdf: Path,
        instruction_pages: List[int],
        pieces_pages: Optional[List[int]] = None,
        match_color: bool = True,
        confidence_threshold: float = 0.75,
        top_n_alternatives: int = 3,
        search_radius: int = 80,
        min_piece_size: int = 20,
        max_piece_size: int = 250,
        dpi: int = 300,
        debug_output_dir: Optional[Path] = None,
    ):
        """Initialize LEGO Parts Extractor.

        Args:
            instruction_pdf: Path to instruction PDF
            pieces_pdf: Path to pieces list PDF
            instruction_pages: List of instruction pages to process
            pieces_pages: List of pieces list pages (None for auto-detect)
            match_color: Include color in matching
            confidence_threshold: Minimum confidence (0-1)
            top_n_alternatives: Number of alternatives for low confidence
            search_radius: Pixel radius for part detection
            min_piece_size: Minimum piece dimensions
            max_piece_size: Maximum piece dimensions
            dpi: PDF to image conversion DPI
            debug_output_dir: Directory for debug output (None to disable)
        """
        self.instruction_pdf = instruction_pdf
        self.pieces_pdf = pieces_pdf
        self.instruction_pages = instruction_pages
        self.pieces_pages = pieces_pages
        self.match_color = match_color
        self.confidence_threshold = confidence_threshold
        self.top_n_alternatives = top_n_alternatives
        self.search_radius = search_radius
        self.min_piece_size = min_piece_size
        self.max_piece_size = max_piece_size
        self.dpi = dpi
        self.debug_output_dir = debug_output_dir

        self.logger = logging.getLogger(__name__)

        # To be populated during extraction
        self.reference_database = {}

    def extract(self) -> ExtractionResult:
        """Run full extraction pipeline.

        Returns:
            ExtractionResult with shopping list and metadata
        """
        result = ExtractionResult()

        # Phase 1: Auto-detect pieces pages if needed
        if self.pieces_pages is None:
            self.logger.info("Auto-detecting pieces list pages...")
            self.pieces_pages = auto_detect_pieces_pages(self.pieces_pdf)
            if not self.pieces_pages:
                raise ValueError(
                    "Could not auto-detect pieces list pages. "
                    "Please specify --pieces-pages manually."
                )
            self.logger.info(f"Detected pieces pages: {self.pieces_pages}")

        # Phase 2: Parse pieces list (to be implemented)
        self.logger.info(f"Loading pieces list from pages {self.pieces_pages}...")
        self._parse_pieces_list()
        self.logger.info(f"Parsed {len(self.reference_database)} pieces")

        # Phase 3: Extract parts from instruction pages (to be implemented)
        self.logger.info(
            f"Processing {len(self.instruction_pages)} instruction pages..."
        )
        extracted_parts = self._extract_parts_from_instructions()
        self.logger.info(f"Extracted {len(extracted_parts)} parts")

        # Phase 4: Match parts (to be implemented)
        self.logger.info("Matching parts with reference database...")
        matches = self._match_parts(extracted_parts)

        # Phase 5: Aggregate results
        self.logger.info("Aggregating results...")
        self._aggregate_results(matches, result)

        return result

    def _parse_pieces_list(self):
        """Parse pieces list and build reference database.

        Implemented in Phase 2.
        """
        parser = PiecesListParser(
            pieces_pdf=self.pieces_pdf,
            pieces_pages=self.pieces_pages,
            dpi=self.dpi,
            debug_output_dir=self.debug_output_dir,
        )
        self.reference_database = parser.parse()

    def _extract_parts_from_instructions(self):
        """Extract parts from instruction pages.

        Implemented in Phase 3.
        """
        detector = PartsDetector(
            instruction_pdf=self.instruction_pdf,
            instruction_pages=self.instruction_pages,
            search_radius=self.search_radius,
            min_piece_size=self.min_piece_size,
            max_piece_size=self.max_piece_size,
            dpi=self.dpi,
            match_color=self.match_color,
            debug_output_dir=self.debug_output_dir,
        )
        return detector.detect()

    def _match_parts(self, extracted_parts):
        """Match extracted parts with reference database.

        Implemented in Phase 4.
        """
        engine = MatchingEngine(
            reference_database=self.reference_database,
            confidence_threshold=self.confidence_threshold,
            top_n_alternatives=self.top_n_alternatives,
            match_color=self.match_color,
        )
        return engine.match_all(extracted_parts)

    def _aggregate_results(self, matches, result: ExtractionResult):
        """Aggregate matches into shopping list.

        Implemented in Phase 5.
        """
        # Build shopping list from matches
        piece_data = {}  # piece_number -> list of matches

        for match in matches:
            if match.best_match:
                if match.best_match not in piece_data:
                    piece_data[match.best_match] = []
                piece_data[match.best_match].append(match)

        # Aggregate quantities and calculate statistics
        for piece_num, piece_matches in piece_data.items():
            total_quantity = sum(m.extracted_part.quantity_value for m in piece_matches)
            occurrences = len(piece_matches)
            avg_confidence = sum(m.confidence for m in piece_matches) / occurrences

            # Determine most common match method
            methods = [m.match_method for m in piece_matches]
            match_method = max(set(methods), key=methods.count)

            # Get pages where piece appears
            pages = sorted(set(m.extracted_part.page for m in piece_matches))

            # Build notes for low confidence or alternatives
            notes = ""
            low_conf_matches = [
                m for m in piece_matches if m.confidence < self.confidence_threshold
            ]
            if low_conf_matches:
                # Collect all alternatives
                all_alts = {}
                for m in low_conf_matches:
                    for alt_piece, alt_conf in m.alternatives:
                        if alt_piece not in all_alts:
                            all_alts[alt_piece] = []
                        all_alts[alt_piece].append(alt_conf)

                # Average confidence for each alternative
                alt_avgs = [(p, sum(cs) / len(cs)) for p, cs in all_alts.items()]
                alt_avgs.sort(key=lambda x: x[1], reverse=True)

                if alt_avgs:
                    alt_strs = [f"{p}({c * 100:.0f}%)" for p, c in alt_avgs[:3]]
                    notes = f"Low confidence - alternatives: {', '.join(alt_strs)}"

            result.shopping_list[piece_num] = {
                "total_quantity": total_quantity,
                "occurrences": occurrences,
                "avg_confidence": avg_confidence,
                "match_method": match_method,
                "pages": pages,
                "notes": notes,
            }

            # Update counters
            if avg_confidence >= self.confidence_threshold:
                result.high_confidence_count += occurrences
            else:
                result.low_confidence_count += occurrences

        # Count unmatched
        result.unmatched_count = sum(1 for m in matches if not m.best_match)

        # Update totals
        result.unique_piece_count = len(piece_data)
        result.total_parts_count = len(matches)

        # Update metadata
        result.metadata = {
            "instruction_pdf": str(self.instruction_pdf),
            "pieces_pdf": str(self.pieces_pdf),
            "instruction_pages": format_page_ranges(self.instruction_pages),
            "pieces_pages": format_page_ranges(self.pieces_pages)
            if self.pieces_pages
            else "auto-detected",
            "processing_date": datetime.now().isoformat(),
            "total_pieces_detected": len(matches),
            "total_unique_pieces": len(piece_data),
            "high_confidence_matches": result.high_confidence_count,
            "low_confidence_matches": result.low_confidence_count,
            "unmatched": result.unmatched_count,
            "confidence_threshold": self.confidence_threshold,
        }
