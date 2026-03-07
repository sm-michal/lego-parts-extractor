"""Utility functions for LEGO Parts Extractor."""

import logging
import re
import shutil
import sys
from pathlib import Path
from typing import List, Optional


def setup_logging(level: int = logging.INFO) -> None:
    """Setup logging configuration.

    Args:
        level: Logging level (e.g., logging.INFO, logging.DEBUG)
    """
    logging.basicConfig(
        level=level,
        format="[%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_page_ranges(range_str: str) -> List[int]:
    """Parse page range string into list of page numbers.

    Examples:
        "5" -> [5]
        "5-8" -> [5, 6, 7, 8]
        "5-8,10,15-17" -> [5, 6, 7, 8, 10, 15, 16, 17]

    Args:
        range_str: Page range string (e.g., "5-8,10,15-17")

    Returns:
        List of page numbers (1-indexed)

    Raises:
        ValueError: If range string is invalid
    """
    if not range_str or not range_str.strip():
        raise ValueError("Empty page range")

    pages = []
    parts = range_str.split(",")

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Check for range (e.g., "5-8")
        if "-" in part:
            match = re.match(r"^(\d+)-(\d+)$", part)
            if not match:
                raise ValueError(f"Invalid range format: {part}")
            start, end = int(match.group(1)), int(match.group(2))
            if start > end:
                raise ValueError(f"Invalid range (start > end): {part}")
            if start < 1:
                raise ValueError(f"Page numbers must be >= 1: {part}")
            pages.extend(range(start, end + 1))
        else:
            # Single page number
            match = re.match(r"^(\d+)$", part)
            if not match:
                raise ValueError(f"Invalid page number: {part}")
            page_num = int(match.group(1))
            if page_num < 1:
                raise ValueError(f"Page numbers must be >= 1: {part}")
            pages.append(page_num)

    if not pages:
        raise ValueError("No valid pages in range")

    # Remove duplicates and sort
    return sorted(set(pages))


def format_page_ranges(pages: List[int]) -> str:
    """Format list of page numbers into compact range string.

    Examples:
        [5, 6, 7, 8] -> "5-8"
        [5, 6, 7, 8, 10, 15, 16, 17] -> "5-8, 10, 15-17"

    Args:
        pages: List of page numbers

    Returns:
        Formatted range string
    """
    if not pages:
        return ""

    pages = sorted(set(pages))
    ranges = []
    start = pages[0]
    end = pages[0]

    for page in pages[1:]:
        if page == end + 1:
            end = page
        else:
            if start == end:
                ranges.append(str(start))
            else:
                ranges.append(f"{start}-{end}")
            start = page
            end = page

    # Add final range
    if start == end:
        ranges.append(str(start))
    else:
        ranges.append(f"{start}-{end}")

    return ", ".join(ranges)


def find_poppler_path() -> Optional[str]:
    """Find Poppler installation path on Windows.

    Returns:
        Path to Poppler bin directory or None if not found
    """
    import os

    if sys.platform != "win32":
        return None

    # Check environment variable first
    if "POPPLER_PATH" in os.environ:
        poppler_path = Path(os.environ["POPPLER_PATH"])
        if poppler_path.exists():
            # Check if it's the bin directory or parent
            if (poppler_path / "pdfinfo.exe").exists():
                return str(poppler_path)
            elif (poppler_path / "Library" / "bin" / "pdfinfo.exe").exists():
                return str(poppler_path / "Library" / "bin")

    # Check if pdfinfo is directly available in PATH
    if shutil.which("pdfinfo"):
        return None  # Already in PATH, no need to specify

    # Common Poppler installation locations on Windows
    possible_paths = [
        # User's Downloads folder (common for manual downloads)
        Path.home() / "Downloads" / "poppler-25.12.0" / "Library" / "bin",
        Path("C:/Users/micha/poppler-25.12.0/Library/bin"),
        # Standard installation locations
        Path("C:/Program Files/poppler/Library/bin"),
        Path("C:/Program Files (x86)/poppler/Library/bin"),
        Path("C:/poppler/Library/bin"),
        Path("C:/Tools/poppler/Library/bin"),
        Path.home() / "poppler/Library/bin",
        # Chocolatey install location
        Path("C:/ProgramData/chocolatey/lib/poppler/tools/Library/bin"),
    ]

    for path in possible_paths:
        if path.exists() and (path / "pdfinfo.exe").exists():
            return str(path)

    return None


def find_tesseract_path() -> Optional[str]:
    """Find Tesseract installation path on Windows.

    Returns:
        Path to tesseract.exe or None if not found
    """
    import os

    if sys.platform != "win32":
        return None

    # Check environment variable first
    if "TESSERACT_PATH" in os.environ:
        tesseract_path = Path(os.environ["TESSERACT_PATH"])
        if tesseract_path.exists():
            # Check if it's the exe or directory
            if tesseract_path.name == "tesseract.exe":
                return str(tesseract_path)
            elif (tesseract_path / "tesseract.exe").exists():
                return str(tesseract_path / "tesseract.exe")

    # Check if tesseract is directly available in PATH
    found = shutil.which("tesseract")
    if found:
        return found

    # Common Tesseract installation locations on Windows
    possible_paths = [
        # User's AppData (common for user installations)
        Path.home() / "AppData/Local/Programs/Tesseract-OCR/tesseract.exe",
        # Standard installation locations
        Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
        Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
        Path("C:/Tesseract-OCR/tesseract.exe"),
        # Chocolatey install location
        Path("C:/ProgramData/chocolatey/bin/tesseract.exe"),
    ]

    for path in possible_paths:
        if path.exists():
            return str(path)

    return None


def configure_tesseract():
    """Configure pytesseract with the correct Tesseract path on Windows."""
    if sys.platform != "win32":
        return

    tesseract_path = find_tesseract_path()
    if tesseract_path:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = tesseract_path
