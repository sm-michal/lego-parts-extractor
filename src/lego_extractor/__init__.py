"""LEGO Partial Build Parts Extractor

A tool to extract piece lists from LEGO instruction PDFs and match them
with piece numbers from the pieces list reference.
"""

__version__ = "1.0.0"
__author__ = "LEGO Parts Extractor Team"

from .extractor import LegoPartsExtractor

__all__ = ["LegoPartsExtractor"]
