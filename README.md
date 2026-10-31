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
1. **Scans to CSV ([`scans_to_csv/`](file:///c:/Acads/omr_checker/scans_to_csv/)):**
   - **Stage 1 CLI Engine:** Processes batches of scanned JPG, PNG, and PDF sheets.
   - Self-contained pipeline: includes its own detection engine (`src/`), `template.json`, and `config.json`.
   - Detects corner alignment markers, corrects skew, samples bubble fills, decodes alphanumeric IDs and sets, and writes clean CSV data.
   - Performs built-in anomaly detection (`MULTI` options, incomplete `ID_LEN`, missing `NO_SET`).
2. **Scoring ([`scoring/`](file:///c:/Acads/omr_checker/scoring/)):**
   - **Stage 2 Engine & UI:** Reads `output/results.csv` and answer keys, applies marking schemes and multi-mark policies, and exports `output/score.csv`.
   - Built with Python standard library only; works fully offline with an integrated local web UI and headless CLI.
3. **Template Utilities ([`scripts/`](file:///c:/Acads/omr_checker/scripts/)):**
   - Developer tools to generate and validate OMR layout templates (`make_template.py`, `validate_schema.py`, `check_template.py`).
3. **Architecture & Documentation ([`docs/`](file:///c:/Acads/omr_checker/docs/)):**
   - Multi-milestone architecture plan (`plan.md`) for future scoring, roster validation, and OMR designer phases.

---

## Repository Structure

```
omr_checker/
├── input/                  # Scan drop folder (JPG, PNG, PDF) [tracked via .gitkeep]
├── output/                 # Results directory (results.csv, overlays) [tracked via .gitkeep]
├── scoring/                # Stage 2: results.csv + keys -> score.csv
│   ├── scorer.py           # Pure scoring functions
│   ├── io_utils.py         # File I/O, validation, atomic write
│   ├── cli.py              # Headless CLI
│   ├── app.py              # Offline web UI server (127.0.0.1)
│   ├── static/index.html   # Web UI single-page interface
│   ├── keys/               # Answer-key JSON store (.gitkeep)
│   ├── tests/              # Test suite
│   └── README.md           # Stage 2 documentation
├── scans_to_csv/           # Stage 1: Standalone scan-to-CSV CLI pipeline
│   ├── omr_to_csv.py       # Main CLI script
│   ├── template.json       # Sheet layout definition
│   ├── config.json         # Threshold & tuning parameters
│   ├── requirements.txt    # Python dependencies
│   ├── src/                # Pipeline engine (alignment, detection, parser)
│   └── README.md           # Stage 1 documentation
├── docs/                   # Multi-milestone roadmap & documentation
│   ├── plan.md             # Master architecture roadmap (M0-M8)
│   ├── bits_omr_README.md  # Sheet layout calibration notes
│   └── OMRChecker_README.md
├── designer/               # Sheet designer: prints a new OMR sheet and its template.json
│   ├── index.html          # Open in a browser; form on the left, A4 sheet on the right
│   ├── sheet.js            # The layout both the printout and the template come from
│   └── app.js              # The form
├── scripts/                # Developer utilities for templates
│   ├── check_designer.py   # Round trip: designed sheet -> filled scan -> CSV
│   ├── make_template.py    # Generates template.json
│   ├── check_template.py   # Visual alignment checker
│   └── validate_schema.py  # Schema validator
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

### 3. Designing a New Sheet

Open [`designer/index.html`](designer/index.html) in a browser. There is no build step. The form on the left sets the header, instructions, set box, options, and number of questions; the right side is the A4 sheet as it will print. Questions spread over up to four columns, fewer when there are many options, and the form says how many questions fit. The ID grid is fixed to the degree (F first degree, H higher degree, P PhD), the year, the last four digits, and the campus letter (`F20231187H`): bubbles for the degree, "20" printed, then bubbles for the rest of the year, the four digits, and the campus (H/G/P/D), with a write-in box over each column; the reader puts the "20" back into `ID NO`.

- **Print / PDF** prints the sheet. Print at 100% ("Actual size"), with the browser's headers and footers off.
- **Download template** saves the matching `template.json`. Run scans of that sheet with `--template path/to/that_template.json`.
- **Save draft** / **Open…** keep the form as a `.json` file; the browser also remembers the last draft.

The template is computed from the same layout that draws the sheet, so there is nothing to calibrate. The four corner markers let the reader straighten each scan, so skew, shifted scans, and small print scaling are absorbed. Sheets printed before the designer still use the hand-calibrated `scans_to_csv/template.json`.

`python scripts/check_designer.py` renders the default sheet, fills it in, skews it like a scan, and checks `scans_to_csv` reads every answer back. Pass `--pdf sheet.pdf` to test a sheet the browser printed.

---

### 4. Scoring (Stage 2)

The scoring stage reads `output/results.csv` plus answer keys and writes `output/score.csv` alongside a run sidecar `output/score_run.json`.

#### Local Web UI (Offline)
Launch the local browser interface on `127.0.0.1:8765`:
```bash
python scoring/app.py
```
- Fully offline: standard library only, rejects non-localhost connections.
- Step 1: Summary of `results.csv` (row count, sets found, question count, anomalies).
- Step 2: Marking scheme (+4/-1/0, +1/0/0, +3/-1/0, +2/-0.5/0, custom) and multi-mark policy selection.
- Step 3: Interactive key grid and text paste (`BC-DA...`, where `-` or space denotes uncounted questions).
- Step 4: Save/load keys, preview first 20 rows with summary stats (mean, min, max, flagged count), and atomic write to `output/score.csv`.

#### Headless CLI
```bash
python scoring/cli.py \
  --results output/results.csv \
  --keys scoring/keys/quiz1.json \
  --out output/score.csv \
  --scheme 4,-1,0 \
  --multi zero \
  --per-question
```

#### Blank Key Rule
A blank key entry (`""`) means that question is **NOT counted** for that set. It contributes 0 marks to all students and is excluded from `max_score`. A student's answer on it is completely ignored.

#### Multi-Mark Policies
When a student bubbles two or more options on a question:
- `zero` (default): Treated as unattempted (`marks_unattempted`).
- `wrong`: Treated as wrong (`marks_wrong`).
- `credit_if_contains`: Marked correct if the key letter is inside the marked options; otherwise wrong.
- `hold`: Question receives 0 marks and sheet is flagged `REVIEW` for human inspection; question is still counted in `max_score`.

#### Output Files
- `output/score.csv`: Columns `file_id`, `Set`, `ID NO`, `score`, `max_score`, `correct`, `wrong`, `unattempted`, `multi`, `counted`, `score_status`, `check` (plus optional `q1_mark`..`qN_mark`). Written atomically with automatic backups of prior runs (`score_<timestamp>.csv.bak`).
- `output/score_run.json`: Sidecar recording timestamp, key file path, SHA-256 hash of the key file, scheme, policy, and row counts.

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
