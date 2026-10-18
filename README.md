# BITS OMR Checker: Custom Template to Scoring Pipeline

An automated, template-driven Optical Mark Recognition (OMR) processing and scoring pipeline designed for institutional examinations (BITS Pilani Hyderabad). The system reliably digitizes physical OMR answer sheets into verified structured data at scale.

---

## Project Overview

The project provides an end-to-end pipeline spanning from custom OMR sheet design to graded score exports:

```
  ┌──────────────────┐       ┌────────────────────┐       ┌─────────────────────┐
  │   OMR Template   │  ──▶  │    Scans to CSV    │  ──▶  │   Scoring & Grade   │
  │  (JSON & Specs)  │       │     (Stage 1)      │       │       Export        │
  └──────────────────┘       └────────────────────┘       └─────────────────────┘
     • Corner fiducials         • Image preprocessing        • Answer-key matching
     • 13-digit ID grid         • Perspective alignment      • Marking schemes (+4/-1)
     • Set choice (A–D)         • Bubble fill detection      • Discrepancy flagging
     • 30 MCQ bubbles           • CSV with quality flags     • Class roster validation
```

### Key Architectural Stages
1. **Template & Engine Specs ([`master/`](file:///c:/Acads/omr_checker/master/)):**
   - Reference templates (`template.json`, `config.json`, `overlay.png`) calibrated to 215 DPI canonical sheets.
   - Master architecture roadmap and reference engine.
2. **Scans to CSV ([`scans_to_csv/`](file:///c:/Acads/omr_checker/scans_to_csv/)):**
   - **Stage 1 CLI Engine:** Processes batches of scanned JPG, PNG, and PDF sheets.
   - Detects corner alignment markers, corrects skew, samples bubble fills, decodes alphanumeric IDs and sets, and writes clean CSV data.
   - Performs built-in anomaly detection (`MULTI` options, incomplete `ID_LEN`, missing `NO_SET`).
3. **Scoring & Evaluation (Subsequent Stages):**
   - Applies set-specific answer keys (+4/-1 or custom schemes).
   - Matches student IDs against official course rosters and generates review queues for flagged sheets.

---

## Repository Structure

```
omr_checker/
├── input/                  # Scan drop folder (JPG, PNG, PDF) [tracked via .gitkeep]
├── output/                 # Results directory (results.csv, overlays) [tracked via .gitkeep]
├── scans_to_csv/           # Stage 1: Standalone scan-to-CSV CLI pipeline
│   ├── omr_to_csv.py       # Main CLI script
│   ├── template.json       # Sheet layout definition
│   ├── config.json         # Threshold & tuning parameters
│   ├── requirements.txt    # Python dependencies
│   ├── src/                # Pipeline engine (alignment, detection, parser)
│   └── README.md           # Stage 1 documentation
├── master/                 # Upstream reference assets, schemas & roadmap
│   ├── templates/          # Reference template files
│   ├── scripts/            # Template generation & schema validators
│   ├── docs/               # Multi-milestone architecture plan
│   └── reference_engine/   # Upstream reference engine
└── .gitignore              # Ignores scans & result data while tracking empty folders
```

---

## Getting Started

### 1. Prerequisites & Environment Setup

Python 3.10+ is recommended. Install required packages:

```bash
pip install -r scans_to_csv/requirements.txt
pip install opencv-contrib-python
```

---

### 2. Running `scans_to_csv`

#### Default Run (Zero Arguments)
By default, the script automatically reads all scans in [`input/`](file:///c:/Acads/omr_checker/input/) and outputs to [`output/results.csv`](file:///c:/Acads/omr_checker/output/results.csv):

```bash
python scans_to_csv/omr_to_csv.py
```

*Or from inside the `scans_to_csv/` directory:*
```bash
cd scans_to_csv
python omr_to_csv.py
```

#### Custom Input / Output Paths
You can process scans from any directory or single file:
```bash
python scans_to_csv/omr_to_csv.py --scans "C:\path\to\scans" --out "C:\path\to\results.csv"
```

#### Generating Visual Verification Overlays
To produce visual debug images showing detected bubbles colored in green/red:
```bash
python scans_to_csv/omr_to_csv.py --overlays "output/overlays"
```

#### CLI Options Reference
```bash
python scans_to_csv/omr_to_csv.py --help
```
| Flag | Description | Default |
|---|---|---|
| `--scans` | Folder containing scan images/PDFs or a single file | `input/` |
| `--out` | Destination CSV file path | `output/results.csv` |
| `--template` | JSON template describing sheet layout | `scans_to_csv/template.json` |
| `--config` | JSON config with detection thresholds | `scans_to_csv/config.json` |
| `--overlays` | Output folder for annotated verification images | `None` |
| `--keep-work` | Keep temporary extraction directory | `False` |

---

## Output Format & Quality Checks

[`output/results.csv`](file:///c:/Acads/omr_checker/output/results.csv) contains one row per evaluated sheet:

```csv
"file_id","Set","ID NO","q1","q2",...,"q30","check"
"1_12.jpg","A","2021B3A70580H","D","D",...,"B",""
"cf1.jpg","A","20260347H","","C",...,"A","ID_LEN(9/13)"
"cf2.jpeg","","","C","B",...,"A","NO_SET"
"multi1.jpeg","A","2026A7PS0029H","C","AB",...,"B","MULTI(q2)"
```

### Anomaly Flags in `check` Column:
- **`MULTI(qX)`**: Multiple marks detected on a single-choice question.
- **`ID_LEN(len/13)`**: Student ID does not have exactly 13 digits/characters.
- **`NO_SET`**: Question paper set bubble (A/B/C/D) was left blank or unreadable.
- **`ALL_BLANK`**: All question responses are blank.
