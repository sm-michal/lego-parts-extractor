"""Command-line interface for LEGO Parts Extractor."""

import argparse
import sys
import logging
from pathlib import Path
from typing import Optional

from . import __version__
from .extractor import LegoPartsExtractor
from .analyzer import PDFAnalyzer
from .utils import setup_logging, parse_page_ranges


def create_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="lego_extractor",
        description="Extract LEGO piece lists from instruction PDFs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage (auto-detect pieces list)
  %(prog)s --pdf instructions.pdf --instruction-pages 15-18 --output parts.csv

  # Analyze PDF structure
  %(prog)s --pdf instructions.pdf --analyze

  # Batch processing
  %(prog)s --pdf instructions.pdf --instruction-pages 5-8,15-20,25-30 --output multi.json -f json

  # Debug mode
  %(prog)s --pdf instructions.pdf --instruction-pages 15-18 --debug-output debug/ -v
        """,
    )

    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    # Input files
    input_group = parser.add_argument_group("Input")
    input_mutex = input_group.add_mutually_exclusive_group(required=True)
    input_mutex.add_argument(
        "--pdf",
        type=Path,
        help="Single PDF with both pieces list and instructions",
    )
    input_mutex.add_argument(
        "--instruction-pdf",
        type=Path,
        help="Instruction PDF (requires --pieces-pdf or auto-detect)",
    )

    input_group.add_argument(
        "--pieces-pdf",
        type=Path,
        help="Separate pieces list PDF",
    )

    # Page specification
    pages_group = parser.add_argument_group("Page Specification")
    pages_group.add_argument(
        "--pieces-pages",
        type=str,
        help='Pieces list pages (e.g., "32-35"). Overrides auto-detection.',
    )
    pages_group.add_argument(
        "--instruction-pages",
        type=str,
        help='Pages to extract parts from (e.g., "15-18,22,25-30"). Required unless --analyze.',
    )

    # Output
    output_group = parser.add_argument_group("Output")
    output_group.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output file path (default: stdout)",
    )
    output_group.add_argument(
        "--format",
        "-f",
        choices=["csv", "json"],
        default="csv",
        help="Output format (default: csv)",
    )

    # Matching configuration
    matching_group = parser.add_argument_group("Matching Configuration")
    color_mutex = matching_group.add_mutually_exclusive_group()
    color_mutex.add_argument(
        "--ignore-color",
        action="store_true",
        help="Match by shape only (grayscale conversion)",
    )
    color_mutex.add_argument(
        "--match-color",
        action="store_true",
        default=True,
        help="Include color in matching (default)",
    )

    matching_group.add_argument(
        "--confidence-threshold",
        type=float,
        default=75.0,
        metavar="NUM",
        help="Minimum confidence for match (0-100, default: 75)",
    )
    matching_group.add_argument(
        "--top-n",
        type=int,
        default=3,
        metavar="NUM",
        help="Number of alternatives for low-confidence matches (default: 3)",
    )

    # Detection parameters
    detection_group = parser.add_argument_group("Detection Parameters")
    detection_group.add_argument(
        "--search-radius",
        type=int,
        default=80,
        metavar="NUM",
        help="Pixel radius for part detection around quantity (default: 80)",
    )
    detection_group.add_argument(
        "--min-piece-size",
        type=int,
        default=20,
        metavar="NUM",
        help="Minimum piece dimensions in pixels (default: 20)",
    )
    detection_group.add_argument(
        "--max-piece-size",
        type=int,
        default=250,
        metavar="NUM",
        help="Maximum piece dimensions in pixels (default: 250)",
    )
    detection_group.add_argument(
        "--dpi",
        type=int,
        default=300,
        metavar="NUM",
        help="PDF to image conversion DPI (default: 300)",
    )
    detection_group.add_argument(
        "--pieces-threshold",
        type=int,
        default=200,
        metavar="NUM",
        help="Threshold for piece detection on pieces list pages (default: 200)",
    )

    # Utilities
    utility_group = parser.add_argument_group("Utilities")
    utility_group.add_argument(
        "--analyze",
        action="store_true",
        help="Analyze PDF structure without extraction",
    )
    utility_group.add_argument(
        "--debug-output",
        type=Path,
        metavar="DIR",
        help="Save debug images to directory",
    )
    utility_group.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Detailed logging",
    )

    return parser


def main(argv: Optional[list] = None) -> int:
    """Main entry point for CLI."""
    parser = create_parser()
    args = parser.parse_args(argv)

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(log_level)
    logger = logging.getLogger(__name__)

    try:
        # Validate inputs
        if args.pdf:
            pdf_path = args.pdf
            if not pdf_path.exists():
                logger.error(f"PDF file not found: {pdf_path}")
                return 1
            instruction_pdf = pdf_path
            pieces_pdf = args.pieces_pdf if args.pieces_pdf else pdf_path
        else:
            instruction_pdf = args.instruction_pdf
            if not instruction_pdf.exists():
                logger.error(f"Instruction PDF not found: {instruction_pdf}")
                return 1
            if args.pieces_pdf:
                pieces_pdf = args.pieces_pdf
                if not pieces_pdf.exists():
                    logger.error(f"Pieces PDF not found: {pieces_pdf}")
                    return 1
            else:
                pieces_pdf = instruction_pdf

        # Analyze mode
        if args.analyze:
            logger.info(f"Analyzing PDF: {pdf_path if args.pdf else instruction_pdf}")
            analyzer = PDFAnalyzer(instruction_pdf, pieces_pdf)
            result = analyzer.analyze()
            print(result.format_output())
            return 0

        # Extraction mode - require instruction pages
        if not args.instruction_pages:
            logger.error(
                "Error: --instruction-pages is required unless using --analyze"
            )
            parser.print_help()
            return 1

        # Parse page ranges
        try:
            instruction_pages = parse_page_ranges(args.instruction_pages)
            pieces_pages = (
                parse_page_ranges(args.pieces_pages) if args.pieces_pages else None
            )
        except ValueError as e:
            logger.error(f"Invalid page range: {e}")
            return 1

        logger.info("Starting LEGO Parts Extraction")
        logger.info(f"  Instruction PDF: {instruction_pdf}")
        logger.info(f"  Pieces PDF: {pieces_pdf}")
        logger.info(f"  Instruction pages: {args.instruction_pages}")
        if pieces_pages:
            logger.info(f"  Pieces pages (manual): {args.pieces_pages}")
        else:
            logger.info("  Pieces pages: auto-detect")

        # Create extractor
        extractor = LegoPartsExtractor(
            instruction_pdf=instruction_pdf,
            pieces_pdf=pieces_pdf,
            instruction_pages=instruction_pages,
            pieces_pages=pieces_pages,
            match_color=not args.ignore_color,
            confidence_threshold=args.confidence_threshold / 100.0,  # Convert to 0-1
            top_n_alternatives=args.top_n,
            search_radius=args.search_radius,
            min_piece_size=args.min_piece_size,
            max_piece_size=args.max_piece_size,
            dpi=args.dpi,
            pieces_threshold=args.pieces_threshold,
            debug_output_dir=args.debug_output,
        )

        # Run extraction
        logger.info("Processing...")
        result = extractor.extract()

        # Output results
        if args.output:
            logger.info(f"Writing output to: {args.output}")
            result.save(args.output, format=args.format)
        else:
            print(result.format_output(format=args.format))

        # Summary
        logger.info("\n=== Extraction Complete ===")
        logger.info(f"Total unique pieces: {result.unique_piece_count}")
        logger.info(f"Total parts count: {result.total_parts_count}")
        logger.info(
            f"High confidence matches: {result.high_confidence_count} ({result.high_confidence_percentage:.1f}%)"
        )
        logger.info(
            f"Low confidence matches: {result.low_confidence_count} ({result.low_confidence_percentage:.1f}%)"
        )
        if result.unmatched_count > 0:
            logger.warning(f"Unmatched pieces: {result.unmatched_count}")

        # Show extracted parts directories if debug output is enabled
        if args.debug_output:
            parts_list_dir = args.debug_output / "parts_list_extracted"
            instruction_dir = args.debug_output / "instruction_parts_extracted"
            if parts_list_dir.exists():
                parts_count = len(list(parts_list_dir.glob("*.png")))
                logger.info(
                    f"\nExtracted parts list images: {parts_count} files in {parts_list_dir}"
                )
            if instruction_dir.exists():
                inst_count = len(list(instruction_dir.glob("*.png")))
                logger.info(
                    f"Extracted instruction parts images: {inst_count} files in {instruction_dir}"
                )

        return 0

    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=args.verbose)
        return 1


if __name__ == "__main__":
    sys.exit(main())
