# LEGO Partial Build Parts Extractor

**Status:** ✅ **Production Ready** - All tests passing (March 5, 2026)

Extract LEGO piece lists from instruction PDF pages and match with piece numbers from the pieces list reference.

## Features

- 🔍 Auto-detect pieces list pages in LEGO instruction PDFs
- 📄 Extract parts from specific instruction pages
- 🎯 Match extracted parts with piece numbers using computer vision
- 📊 Generate aggregated shopping lists (CSV/JSON)
- 🎨 Configurable color matching (shape-only or color-sensitive)
- 🔧 Debug mode with visual output for troubleshooting
- 📦 Batch processing of multiple page ranges

## Requirements

### System Dependencies (Windows)

**✅ Automatic Path Detection:** The application automatically finds Tesseract and Poppler on Windows. No manual PATH configuration needed!

1. **Python 3.9+** (Tested with Python 3.13.12)
2. **Poppler for Windows** (required by pdf2image)
   - Download: https://github.com/oschwartz10612/poppler-windows/releases
   - Extract to any location (e.g., `C:\Users\<you>\Downloads\poppler-25.12.0`)
   - Application will auto-detect common locations
3. **Tesseract OCR for Windows** (required by pytesseract)
   - Download: https://github.com/UB-Mannheim/tesseract/wiki
   - Install to default location or AppData
   - Application will auto-detect common locations

**Alternative:** Install via Chocolatey (automatic PATH setup):
```powershell
choco install tesseract poppler -y
```

### Python Dependencies

```bash
pip install -r requirements.txt
```

See `requirements.txt` for full list.

## Installation

**See `INSTALL_WINDOWS.md` for detailed installation instructions.**

```bash
# 1. Install system dependencies (Tesseract + Poppler)
#    See INSTALL_WINDOWS.md for details

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install the package
pip install -e .

# 4. Verify installation
python -m lego_extractor --pdf path/to/sample.pdf --analyze
```

## Quick Start

```bash
# Method 1: Using main.py script (recommended)
python main.py --pdf instructions.pdf --analyze
python main.py --pdf instructions.pdf --instruction-pages 15-18 --output parts.csv

# Method 2: Using module syntax
python -m lego_extractor --pdf instructions.pdf --analyze
python -m lego_extractor --pdf instructions.pdf --instruction-pages 15-18 --output parts.csv

# With debug output
python main.py --pdf instructions.pdf --instruction-pages 15-18 --debug-output debug/ --verbose
```

### Analyze PDF Structure
```bash
python -m lego_extractor --pdf instructions.pdf --analyze
```

### Batch Processing
```bash
python -m lego_extractor --pdf instructions.pdf --instruction-pages 5-8,15-20,25-30 --output multi.json --format json
```

### Debug Mode
```bash
python -m lego_extractor --pdf instructions.pdf --instruction-pages 15-18 --debug-output debug/ --verbose
```

## Usage Examples

See [examples/README.md](examples/README.md) for detailed examples.

## Documentation

- [Product Requirements Document](../LEGO_Parts_Extractor_PRD.md) - Complete PRD with technical details
- [Installation Guide](INSTALL_WINDOWS.md) - Detailed Windows installation instructions
- [Test Results](TEST_RESULTS.md) - Comprehensive test results and analysis
- [Usage Examples](examples/USAGE_EXAMPLES.md) - Detailed usage examples

## Development Status

**✅ Version 1.0 - Production Ready (March 5, 2026)**

- ✅ Phase 1: Foundation
- ✅ Phase 2: Pieces List Parser (65 pieces extracted successfully)
- ✅ Phase 3: Parts Detection (Working, 90%+ OCR confidence)
- ✅ Phase 4: Matching Engine (Template + Feature + SSIM + Color)
- ✅ Phase 5: Integration & Output (CSV generation working)
- ✅ Phase 6: Testing & Validation

**Test Results:**
- ✅ All unit tests passing
- ✅ End-to-end test passing
- ✅ Tested on LEGO Set 60337 (sample PDF)
- ✅ Debug output generation working
- ⚠️ JSON output needs minor fix

See [TEST_RESULTS.md](TEST_RESULTS.md) for detailed test analysis.

## License

MIT License (or your preferred license)

## Acknowledgments

- Sample PDF: LEGO Set 60337
- Built with: OpenCV, pdfplumber, pytesseract, scikit-image
