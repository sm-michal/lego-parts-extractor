# Quick Start Guide

Get up and running with LEGO Parts Extractor in 5 minutes!

---

## Step 1: Install Dependencies (5 minutes)

### Option A: Using Chocolatey (Easiest)
```powershell
# Open PowerShell as Administrator
choco install tesseract poppler -y
```

### Option B: Manual Installation
1. **Tesseract:** Download from https://github.com/UB-Mannheim/tesseract/wiki and install
2. **Poppler:** Download from https://github.com/oschwartz10612/poppler-windows/releases and extract

**Note:** The app automatically detects both tools in common locations - no PATH setup needed!

---

## Step 2: Install Python Packages (1 minute)

```bash
cd lego-parts-extractor

# Install dependencies
pip install -r requirements.txt

# Install the package in development mode
pip install -e .
```

---

## Step 3: Analyze Your PDF (30 seconds)

```bash
# Method 1: Using main.py script (recommended)
python main.py --pdf your_lego_instructions.pdf --analyze

# Method 2: Using module syntax
python -m lego_extractor --pdf your_lego_instructions.pdf --analyze
```

**Output:**
```
=== PDF Analysis Complete ===
Detected pieces list pages: 32-35
Total pages: 36
Recommended instruction pages: 1-31,36
```

---

## Step 4: Extract Parts (1-2 minutes)

### Example 1: Build just the first vehicle (pages 1-10)

```bash
# Using main.py (recommended)
python main.py --pdf your_lego_instructions.pdf \
  --instruction-pages 1-10 \
  --pieces-pages 32-35 \
  --output my_shopping_list.csv \
  --debug-output debug/

# Or using module syntax
python -m lego_extractor --pdf your_lego_instructions.pdf \
  --instruction-pages 1-10 \
  --pieces-pages 32-35 \
  --output my_shopping_list.csv \
  --debug-output debug/
```

### Example 2: Auto-detect pieces list

```bash
python main.py --pdf your_lego_instructions.pdf \
  --instruction-pages 1-10 \
  --output my_shopping_list.csv
```

---

## Step 5: Check Results

### CSV Output (my_shopping_list.csv)
```csv
piece_number,total_quantity,occurrences,avg_confidence,match_method,notes
6172149,2,2,0.87,template,"High confidence match"
302401,8,5,0.92,feature,"High confidence match"
6170567,4,3,0.65,template,"Low confidence - alternatives: 379521(44%)"
```

### Debug Output (debug/ folder)
- **Visual validation:** Check `instruction_page_XX_parts_detected.png` to see detected parts
- **Reference pieces:** See `piece_XX_XXXXXXX.png` for all pieces in database
- **Grids:** View `pieces_page_XX_grid.png` for complete pieces list layout

---

## Tips for Best Results

### ✅ Do:
- Use pages 32+ for pieces list (usually at the end)
- Use early instruction pages (1-10) for testing (more parts boxes)
- Check debug output visually to verify detection
- Use `--verbose` flag to see detailed progress

### ❌ Don't:
- Use the cover page or index pages as instruction pages
- Forget to specify `--pieces-pages` if auto-detection fails
- Use very high DPI (>300) - slower with minimal quality gain

---

## Common Commands

### Full Build Extraction
```bash
# Extract all instruction pages for complete build
python main.py --pdf instructions.pdf \
  --instruction-pages 1-31 \
  --pieces-pages 32-35 \
  --output complete_build.csv
```

### Multiple Partial Builds
```bash
# Vehicle 1 (pages 1-10)
python main.py --pdf instructions.pdf \
  --instruction-pages 1-10 \
  --pieces-pages 32-35 \
  --output vehicle1.csv

# Vehicle 2 (pages 11-20)  
python main.py --pdf instructions.pdf \
  --instruction-pages 11-20 \
  --pieces-pages 32-35 \
  --output vehicle2.csv
```

### Ignore Color Matching
```bash
# Match by shape only (faster, more lenient)
python main.py --pdf instructions.pdf \
  --instruction-pages 1-10 \
  --ignore-color \
  --output shapelist.csv
```

---

## Troubleshooting

### "Tesseract not found" error
- Verify installation: Run `tesseract --version` in a new terminal
- Set path manually: `set TESSERACT_PATH=C:\path\to\tesseract.exe`

### "Poppler not found" error  
- Verify Poppler bin folder contains `pdfinfo.exe`
- Set path manually: `set POPPLER_PATH=C:\path\to\poppler\Library\bin`

### Low detection rate
- Try different instruction pages (early pages usually have more parts)
- Use `--debug-output-dir` to visually check what's being detected
- Adjust `--search-radius 100` if parts boxes are far from quantities

### Low matching confidence
- Use `--ignore-color` if pieces are similar in shape
- Check `pieces_page_XX_grid.png` to verify pieces list was parsed correctly
- Some pieces naturally look similar - check "alternatives" in CSV notes

---

## Next Steps

- ✅ Read [USAGE_EXAMPLES.md](examples/USAGE_EXAMPLES.md) for 10 detailed scenarios
- ✅ Check [TEST_RESULTS.md](TEST_RESULTS.md) for validation data
- ✅ See [INSTALL_WINDOWS.md](INSTALL_WINDOWS.md) for detailed setup

---

## Support

**Having issues?** Check:
1. `TEST_RESULTS.md` - Known issues and solutions
2. `debug/` folder - Visual validation of detection
3. `--verbose` flag - Detailed execution logs

**Success?** Share your results and improvements!
