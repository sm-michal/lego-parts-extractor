"""End-to-end test for LEGO Parts Extractor

This script tests the complete pipeline from PDF to shopping list.
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

from lego_extractor.extractor import LegoPartsExtractor


def test_end_to_end():
    """Test complete extraction pipeline."""

    # Configuration
    sample_pdf = Path("instructions/60337_1.pdf")
    instruction_pages = [10, 12]  # Pages with parts
    pieces_pages = [32, 33]  # First 2 pieces list pages
    debug_dir = Path("debug_e2e_test")
    output_csv = Path("test_output.csv")
    output_json = Path("test_output.json")

    if not sample_pdf.exists():
        print(f"Error: Sample PDF not found at {sample_pdf}")
        return False

    print("=== End-to-End Test ===\n")
    print(f"Sample PDF: {sample_pdf}")
    print(f"Instruction pages: {instruction_pages}")
    print(f"Pieces list pages: {pieces_pages}")
    print(f"Debug output: {debug_dir}\n")

    try:
        # Create extractor
        print("Creating extractor...")
        extractor = LegoPartsExtractor(
            instruction_pdf=sample_pdf,
            pieces_pdf=sample_pdf,  # Same PDF
            instruction_pages=instruction_pages,
            pieces_pages=pieces_pages,
            match_color=True,
            confidence_threshold=0.75,
            top_n_alternatives=3,
            search_radius=80,
            min_piece_size=20,
            max_piece_size=200,
            dpi=300,
            debug_output_dir=debug_dir,
        )

        # Run extraction
        print("\n" + "=" * 50)
        print("Running extraction pipeline...")
        print("=" * 50 + "\n")

        result = extractor.extract()

        print("\n" + "=" * 50)
        print("[OK] Extraction Complete!")
        print("=" * 50 + "\n")

        # Display results
        print("=== Results Summary ===")
        print(f"  Total parts detected: {result.total_parts_count}")
        print(f"  Unique pieces: {result.unique_piece_count}")
        print(
            f"  High confidence matches: {result.high_confidence_count} ({result.high_confidence_percentage:.1f}%)"
        )
        print(
            f"  Low confidence matches: {result.low_confidence_count} ({result.low_confidence_percentage:.1f}%)"
        )
        print(f"  Unmatched: {result.unmatched_count}")

        # Display shopping list
        print("\n=== Shopping List ===")
        for piece_num, data in sorted(result.shopping_list.items())[:10]:
            conf_pct = data["avg_confidence"] * 100
            conf_indicator = "[OK]" if data["avg_confidence"] >= 0.75 else "[WARN]"
            print(
                f"  {conf_indicator} {piece_num}: {data['total_quantity']}x "
                f"(conf: {conf_pct:.1f}%, pages: {data['pages']})"
            )

        if len(result.shopping_list) > 10:
            print(f"  ... and {len(result.shopping_list) - 10} more pieces")

        # Save outputs
        print("\n=== Saving Outputs ===")
        result.save(output_csv, format="csv")
        print(f"  [OK] CSV saved to: {output_csv}")
        print(f"\n  [OK] JSON details: {output_json}")
        print(f"  [OK] JSON saved to: {output_json}")

        print(f"  [OK] Debug images saved to: {debug_dir}/")

        # Show sample CSV output
        print("\n=== Sample CSV Output ===")
        csv_content = result.format_output(format="csv")
        csv_lines = csv_content.split("\n")
        for line in csv_lines[:6]:  # Header + 5 rows
            print(f"  {line}")
        if len(csv_lines) > 6:
            print(f"  ... ({len(csv_lines) - 6} more rows)")

        return True

    except Exception as e:
        print(f"\n[ERROR] Error during extraction: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_end_to_end()
    sys.exit(0 if success else 1)
