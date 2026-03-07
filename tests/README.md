# Testing Guide

This directory contains test scripts for each development phase.

## Prerequisites

Before running tests, ensure system dependencies are installed:

### 1. Poppler (Required by pdf2image)
```bash
# Windows
# Download: https://github.com/oschwartz10612/poppler-windows/releases
# 1. Download latest release (e.g., Release-24.08.0-0.zip)
# 2. Extract to C:\Program Files\poppler
# 3. Add C:\Program Files\poppler\Library\bin to PATH
# 4. Verify installation:
pdfinfo -v
```

### 2. Tesseract OCR (Required by pytesseract)
```bash
# Windows
# Download: https://github.com/UB-Mannheim/tesseract/wiki
# 1. Download installer (e.g., tesseract-ocr-w64-setup-5.3.3.20231005.exe)
# 2. Run installer (default: C:\Program Files\Tesseract-OCR)
# 3. Installer should add to PATH automatically
# 4. Verify installation:
tesseract --version
```

### 3. Python Dependencies
```bash
cd lego-parts-extractor
pip install -e .
```

## Running Tests

### Test Phase 2: Pieces List Parser
```bash
cd lego-parts-extractor
python tests/test_phase2_pieces_parser.py
```

**What it tests:**
- PDF to image conversion
- OCR text extraction
- Piece number detection (6-7 digits)
- Quantity detection (1x, 2x, etc.)
- Spatial relationship matching
- Image extraction and cropping
- Reference database building

**Expected output:**
- Console: "Total unique pieces: XX"
- Debug directory: `debug_phase2_test/`
  - `pieces_page_32_original.png` - Original page
  - `pieces_page_32_annotated.png` - With bounding boxes
  - `pieces_page_32_grid.png` - Grid of extracted pieces
  - `piece_32_XXXXXXX.png` - Individual piece images

---

### Test Phase 3: Parts Detection
```bash
cd lego-parts-extractor
python tests/test_phase3_parts_detection.py
```

**What it tests:**
- Instruction page processing
- OCR quantity detection ("1x", "2x", etc.)
- Parts box identification
- Image region extraction
- Size filtering
- False positive handling

**Expected output:**
- Console: "Total parts extracted: XX"
- Debug directory: `debug_phase3_test/`
  - `instruction_page_10_original.png` - Original page
  - `instruction_page_10_quantities.png` - Detected quantities
  - `instruction_page_10_parts_detected.png` - Detected parts with boxes
  - `instruction_page_10_parts_grid.png` - Grid of extracted parts
  - `extracted_page10_qtyX_xXXX_yXXX.png` - Individual parts

---

## Troubleshooting

### "PDFInfoNotInstalledError"
**Problem:** Poppler not installed or not in PATH

**Solution:**
1. Install Poppler (see above)
2. Add to PATH: `C:\Program Files\poppler\Library\bin`
3. Restart terminal
4. Verify: `pdfinfo -v`

### "TesseractNotFoundError"
**Problem:** Tesseract not installed or not in PATH

**Solution:**
1. Install Tesseract (see above)
2. Check PATH includes: `C:\Program Files\Tesseract-OCR`
3. Restart terminal
4. Verify: `tesseract --version`

### "ModuleNotFoundError: lego_extractor"
**Problem:** Package not installed

**Solution:**
```bash
cd lego-parts-extractor
pip install -e .
```

### Low extraction rate (few pieces found)
**Problem:** OCR or detection parameters need tuning

**Solution:**
1. Check debug images in output directory
2. Adjust parameters in test script:
   - `search_radius` - increase to search larger area
   - `min_piece_size` - decrease to capture smaller pieces
   - `dpi` - increase for better quality (slower)

---

## Sample Test Data

The tests use the sample LEGO PDF located at:
```
C:\Users\michals\lego_sample.pdf
```

**LEGO Set:** 60337
**Pages:**
- Pieces list: 32-35
- Instruction pages: 1-31, 36
- Test pages for Phase 3: 10, 12 (known to have parts lists)

---

## Next Steps After Testing

Once tests pass:
1. **Phase 4:** Implement matching engine (template matching, SIFT, SSIM)
2. **Phase 5:** Implement output formatting (CSV, JSON)
3. **Phase 6:** End-to-end testing and refinement
