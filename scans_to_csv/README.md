# Stage 1: Scans to CSV (`scans_to_csv`)

Standalone CLI pipeline that reads scanned OMR sheets, applies template matching via OMRChecker, and produces a clean, structured CSV with verification flags.

## Default Directories
- **Inputs**: `../input/` (or `C:\Acads\omr_checker\input`)
- **Outputs**: `../output/results.csv` (or `C:\Acads\omr_checker\output\results.csv`)

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
pip install opencv-contrib-python
```

### 2. Run conversion (defaults to `../input` and `../output/results.csv`)
From repository root:
```bash
python scans_to_csv/omr_to_csv.py
```
Or from inside `scans_to_csv/`:
```bash
python omr_to_csv.py
```

### 3. Custom options
```bash
python omr_to_csv.py --scans "C:\path\to\scans" --out "C:\path\to\results.csv" --overlays "C:\path\to\overlays"
```
- `--scans`: Folder of JPG/PNG/PDF scans or a single file.
- `--template`: Path to `template.json` (defaults to local `template.json`).
- `--config`: Path to `config.json` (defaults to local `config.json`).
- `--out`: Destination CSV file path.
- `--overlays`: Optional directory where annotated overlay verification images are saved.
- `--keep-work`: Keep the temporary directory for debugging.
