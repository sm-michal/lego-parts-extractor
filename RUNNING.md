# Running the LEGO Parts Extractor

You can run the LEGO Parts Extractor in two ways:

---

## Method 1: Using main.py (Recommended - Simpler)

This is the easiest method, just run the script directly:

```bash
# Analyze PDF
python main.py --pdf instructions.pdf --analyze

# Extract parts
python main.py --pdf instructions.pdf \
  --instruction-pages 1-10 \
  --output shopping_list.csv

# With debug output
python main.py --pdf instructions.pdf \
  --instruction-pages 1-10 \
  --debug-output debug/ \
  --verbose
```

**Advantages:**
- Simpler syntax
- No module installation needed (if you don't want to install)
- Works directly from the project directory

---

## Method 2: Using Module Syntax

After installing with `pip install -e .`, you can use:

```bash
# Analyze PDF
python -m lego_extractor --pdf instructions.pdf --analyze

# Extract parts
python -m lego_extractor --pdf instructions.pdf \
  --instruction-pages 1-10 \
  --output shopping_list.csv

# With debug output
python -m lego_extractor --pdf instructions.pdf \
  --instruction-pages 1-10 \
  --debug-output debug/ \
  --verbose
```

**Advantages:**
- Can be run from any directory
- Standard Python package convention
- Enables `lego_extractor` command (if installed globally)

---

## Complete Examples

### Example 1: Quick Analysis
```bash
# Find pieces list pages automatically
python main.py --pdf "C:\path\to\instructions.pdf" --analyze
```

### Example 2: Extract First Build (Pages 1-10)
```bash
python main.py --pdf "C:\path\to\instructions.pdf" \
  --instruction-pages 1-10 \
  --output vehicle1_parts.csv
```

### Example 3: Extract with Manual Pieces List
```bash
python main.py --pdf "C:\path\to\instructions.pdf" \
  --instruction-pages 1-10 \
  --pieces-pages 32-35 \
  --output parts.csv
```

### Example 4: Debug Mode (Visual Validation)
```bash
python main.py --pdf "C:\path\to\instructions.pdf" \
  --instruction-pages 1-10 \
  --pieces-pages 32-35 \
  --output parts.csv \
  --debug-output debug_images/ \
  --verbose
```

### Example 5: Shape-Only Matching
```bash
# Ignore color, match by shape only (useful for similar-colored pieces)
python main.py --pdf "C:\path\to\instructions.pdf" \
  --instruction-pages 1-10 \
  --ignore-color \
  --output parts.csv
```

### Example 6: Multiple Page Ranges
```bash
# Extract from multiple discontinuous page ranges
python main.py --pdf "C:\path\to\instructions.pdf" \
  --instruction-pages "1-5,10-15,20-25" \
  --output complex_build.csv
```

---

## Windows Tips

### Using Quotes for Paths with Spaces
```bash
# Always quote paths with spaces
python main.py --pdf "C:\Users\My Name\Downloads\instructions.pdf" --analyze

# Or use forward slashes
python main.py --pdf "C:/Users/My Name/Downloads/instructions.pdf" --analyze
```

### Running from Different Directory
```bash
# If you're not in the project directory:
cd C:\path\to\lego-parts-extractor
python main.py --pdf "path\to\instructions.pdf" --analyze
```

---

## All Command-Line Options

Run with `--help` to see all options:

```bash
python main.py --help
```

### Key Options:
- `--pdf FILE` - Input PDF file (required)
- `--instruction-pages X-Y` - Pages to extract (e.g., "1-10,15-20")
- `--pieces-pages X-Y` - Pieces list pages (auto-detected if not specified)
- `--output FILE` - Output CSV file (default: stdout)
- `--analyze` - Just analyze PDF, don't extract
- `--debug-output DIR` - Save debug images for validation
- `--verbose` - Show detailed progress
- `--ignore-color` - Match by shape only
- `--confidence-threshold N` - Minimum match confidence (0-100, default: 75)

---

## Troubleshooting

### Command Not Working?

**If using main.py:**
```bash
# Make sure you're in the project directory
cd C:\Users\michals\lego-parts-extractor

# Run with full path to Python
C:\Path\To\Python\python.exe main.py --help
```

**If using module syntax:**
```bash
# Make sure package is installed
pip install -e .

# Then run from anywhere
python -m lego_extractor --help
```

---

## Recommendation

**Use `python main.py`** - It's simpler and works immediately without package installation!
