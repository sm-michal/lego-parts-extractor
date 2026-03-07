"""Test script for Phase 2 - Pieces List Parser

This script tests the pieces list parser on sample pages.
Requires: Poppler and Tesseract installed.
"""

import sys
import os
from pathlib import Path

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lego_extractor.pieces_parser import PiecesListParser


def test_pieces_parser():
    """Test pieces list parser on sample pages."""

    # Configuration
    sample_pdf = Path("instructions/60337_1.pdf")
    pieces_pages = [32, 33]  # Test first 2 pieces list pages
    debug_dir = Path("debug_phase2_test")

    if not sample_pdf.exists():
        print(f"Error: Sample PDF not found at {sample_pdf}")
        return False

    print("=== Phase 2: Pieces List Parser Test ===\n")
    print(f"Sample PDF: {sample_pdf}")
    print(f"Pieces pages: {pieces_pages}")
    print(f"Debug output: {debug_dir}\n")

    # Create parser
    parser = PiecesListParser(
        pieces_pdf=sample_pdf,
        pieces_pages=pieces_pages,
        dpi=300,
        debug_output_dir=debug_dir,
    )

    try:
        # Run parsing
        print("Parsing pieces list...")
        reference_db = parser.parse()

        print(f"\n[OK] Parsing complete!")
        print(f"  Total unique pieces: {len(reference_db)}")

        # Show sample pieces
        print("\nSample pieces (first 10):")
        for i, (piece_num, piece_ref) in enumerate(list(reference_db.items())[:10], 1):
            print(
                f"  {i}. {piece_num}: {piece_ref.reference_quantity}, "
                f"image: {piece_ref.image.shape}, page: {piece_ref.page}"
            )

        # Debug output info
        print(f"\n[OK] Debug images saved to: {debug_dir}")
        print("  - pieces_page_XX_original.png")
        print("  - pieces_page_XX_annotated.png")
        print("  - pieces_page_XX_grid.png")
        print("  - piece_XX_XXXXXXX.png (individual pieces)")

        return True

    except Exception as e:
        print(f"\n[ERROR] Error during parsing: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_pieces_parser()
    sys.exit(0 if success else 1)
