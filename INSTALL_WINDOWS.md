# Windows Installation Guide

This guide will help you install all dependencies needed to run the LEGO Parts Extractor on Windows.

## Prerequisites

- Windows 10 or later
- Python 3.9+ (✓ You have Python 3.13.12)
- Administrator access for installing system dependencies

---

## Step 1: Install Tesseract OCR

Tesseract is required for text recognition in PDF pages.

### Option A: Using Chocolatey (Recommended)
If you have Chocolatey package manager:
```powershell
choco install tesseract
```

### Option B: Manual Installation
1. Download the latest installer from: https://github.com/UB-Mannheim/tesseract/wiki
   - Direct link: https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.3.3.20231005.exe
2. Run the installer
3. **Important:** During installation, note the installation path (default: `C:\Program Files\Tesseract-OCR`)
4. Add Tesseract to your PATH:
   - Open System Properties → Environment Variables
   - Edit the `Path` variable under "System variables"
   - Add: `C:\Program Files\Tesseract-OCR`
   - Click OK

### Verify Installation
Open a **new** Command Prompt and run:
```cmd
tesseract --version
```
You should see version information.

---

## Step 2: Install Poppler

Poppler is required for converting PDF pages to images.

### Option A: Using Chocolatey (Recommended)
```powershell
choco install poppler
```

### Option B: Manual Installation
1. Download Poppler for Windows: https://github.com/oschwartz10612/poppler-windows/releases
   - Download the latest `Release-XX.XX.X-X.zip` file
2. Extract the ZIP file to a permanent location, e.g., `C:\Program Files\poppler`
3. Add Poppler to your PATH:
   - Open System Properties → Environment Variables
   - Edit the `Path` variable under "System variables"
   - Add: `C:\Program Files\poppler\Library\bin`
   - Click OK

### Verify Installation
Open a **new** Command Prompt and run:
```cmd
pdfinfo -v
```
You should see version information.

---

## Step 3: Install Python Dependencies

Navigate to the project directory and install Python packages:

```cmd
cd C:\Users\michals\lego-parts-extractor

# Install dependencies
pip install -r requirements.txt

# Install the package in development mode
pip install -e .
```

This will install:
- opencv-python (image processing)
- pdf2image (PDF to image conversion)
- pdfplumber (PDF text extraction)
- pytesseract (OCR wrapper)
- scikit-image (image similarity metrics)
- Pillow (image manipulation)
- numpy (numerical operations)

And register the `lego_extractor` module so you can run it with `python -m lego_extractor`.

---

## Step 4: Verify Installation

Run the analyzer to verify everything is working:

```cmd
python -m lego_extractor.analyzer C:\Users\michals\lego_sample.pdf
```

If successful, you should see output like:
```
=== PDF Analysis Complete ===
Detected pieces list pages: 32-35
Total pages: 36
Recommended instruction pages: 1-31,36
```

---

## Troubleshooting

### Tesseract Error: "tesseract is not installed or it's not in your PATH"
- Make sure you added Tesseract to your PATH
- **Close and reopen** your command prompt after modifying PATH
- Verify: `where tesseract` should show the executable location

### Poppler Error: "Unable to get page count. Is poppler installed and in PATH?"
- Make sure you added `poppler\Library\bin` to your PATH (not just `poppler`)
- **Close and reopen** your command prompt after modifying PATH
- Verify: `where pdfinfo` should show the executable location

### Python Module Import Errors
- Make sure you're in the correct directory: `cd C:\Users\michals\lego-parts-extractor`
- Verify packages installed: `pip list | findstr opencv`
- Try reinstalling: `pip install --force-reinstall -r requirements.txt`

### Permission Errors
- Run Command Prompt as Administrator when installing to `Program Files`
- Or install to user directory (e.g., `C:\Users\michals\Tools\`)

---

## Next Steps

Once installation is complete, proceed to testing:

1. **Test pieces list parsing:**
   ```cmd
   python tests\test_phase2_pieces_parser.py
   ```

2. **Test parts detection:**
   ```cmd
   python tests\test_phase3_parts_detection.py
   ```

3. **Test full pipeline:**
   ```cmd
   python tests\test_end_to_end.py
   ```

See `tests/README.md` for detailed testing instructions.
