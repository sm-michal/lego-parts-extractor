#!/usr/bin/env python3
"""Wrapper script to run the LEGO Parts Extractor CLI."""

import sys
from pathlib import Path

# Add src directory to the Python path
src_path = str(Path(__file__).parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

try:
    from lego_extractor.cli import main
except ImportError as e:
    print(f"Error: Could not import lego_extractor. {e}")
    print("Make sure you are running from the project root and 'src' directory exists.")
    sys.exit(1)

if __name__ == "__main__":
    sys.exit(main())
