"""Test script for Phase 3 - Parts Detection

This script tests the parts detector on sample instruction pages.
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

from lego_extractor.parts_detector import PartsDetector


def test_parts_detection():
    """Test parts detection on sample pages."""

    # Configuration
    sample_pdf = Path(r"C:\Users\michals\lego_sample.pdf")
    test_pages = [10, 12]  # Pages known to have parts lists
    debug_dir = Path("debug_phase3_test")

    if not sample_pdf.exists():
        print(f"Error: Sample PDF not found at {sample_pdf}")
        return False

    print("=== Phase 3: Parts Detection Test ===\n")
    print(f"Sample PDF: {sample_pdf}")
    print(f"Test pages: {test_pages}")
    print(f"Debug output: {debug_dir}\n")

    # Create detector
    detector = PartsDetector(
        instruction_pdf=sample_pdf,
        instruction_pages=test_pages,
        search_radius=80,
        min_piece_size=20,
        max_piece_size=200,
        dpi=300,
        match_color=True,
        debug_output_dir=debug_dir,
    )

    try:
        # Run detection
        print("Running detection...")
        parts = detector.detect()

        print(f"\n[OK] Detection complete!")
        print(f"  Total parts extracted: {len(parts)}")

        # Show details
        print("\nExtracted parts by page:")
        for page_num in test_pages:
            page_parts = [p for p in parts if p.page == page_num]
            print(f"\n  Page {page_num}: {len(page_parts)} parts")
            for i, part in enumerate(page_parts[:5], 1):
                print(
                    f"    {i}. {part.quantity} - size: {part.image.shape[:2]}, conf: {part.confidence:.2f}"
                )
            if len(page_parts) > 5:
                print(f"    ... and {len(page_parts) - 5} more")

        # Debug output info
        print(f"\n[OK] Debug images saved to: {debug_dir}")
        print("  - instruction_page_XX_original.png")
        print("  - instruction_page_XX_quantities.png")
        print("  - instruction_page_XX_parts_detected.png")
        print("  - instruction_page_XX_parts_grid.png")
        print("  - extracted_pageXX_qtyX_xXXX_yXXX.png (individual parts)")

        return True

    except Exception as e:
        print(f"\n[ERROR] Error during detection: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_parts_detection()
    sys.exit(0 if success else 1)
