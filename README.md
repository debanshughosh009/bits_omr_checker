# BITS OMR Checker: Custom Template to Scoring Pipeline

An automated, template-driven Optical Mark Recognition (OMR) processing and scoring pipeline designed for institutional examinations (BITS Pilani Hyderabad). The system reliably digitizes physical OMR answer sheets into verified structured data at scale.

---

## Project Overview

The project provides an end-to-end pipeline spanning from custom OMR sheet design to graded score exports:

```
  ┌──────────────────┐       ┌────────────────────┐       ┌─────────────────────┐
  │  Sheet Designer  │  ──▶  │    Scans to CSV    │  ──▶  │   Scoring & Grade   │
  │ (sheet+template) │       │     (Stage 1)      │       │   Export (Stage 2)  │
  └──────────────────┘       └────────────────────┘       └─────────────────────┘
     • Questions/options        • Image preprocessing        • Answer key per set
     • Sets, ID digits          • Marker alignment           • +4/-1 marking, bonus
     • Printable PDF            • Bubble fill detection      • Multiple-correct answers
     • template.json            • results.csv + flags        • Roster, scores.csv
                    └──────────── Web app (Docker) runs all three ────────────┘
```

### Key Architectural Stages
1. **Scans to CSV ([`scans_to_csv/`](scans_to_csv/)):**
   - **Stage 1 CLI Engine:** Processes batches of scanned JPG, PNG, and PDF sheets.
   - Self-contained pipeline: includes its own detection engine (`src/`), `template.json`, and `config.json`.
   - Detects corner alignment markers, corrects skew, samples bubble fills, decodes alphanumeric IDs and sets, and writes clean CSV data.
   - Performs built-in anomaly detection (`MULTI` options, incomplete `ID_LEN`, missing `NO_SET`).
2. **Scoring ([`scoring/`](scoring/)):**
   - **Stage 2 CLI:** Scores `results.csv` against an answer key and writes `scores.csv`.
   - Per-set keys, configurable marking, bonus questions, "any one of" and "all of" (multiple-correct) answers with optional partial credit, class roster merge.
3. **Web App ([`webapp/`](webapp/)):**
   - Browser UI, packaged as a Docker container, that runs the whole pipeline.
   - **Designer:** generates a printable sheet and its template from the number of questions, options, sets and ID digits, or uploads a custom template.
   - **Professor:** enters the answer key on a clickable grid, uploads scans, fixes flagged sheets, downloads `results.csv` and `scores.csv`.
4. **Template Utilities ([`scripts/`](scripts/)):**
   - Developer tools to generate and validate OMR layout templates (`make_template.py`, `validate_schema.py`, `check_template.py`).
5. **Architecture & Documentation ([`docs/`](docs/)):**
   - Multi-milestone architecture plan (`plan.md`) for scoring, roster validation, and OMR designer phases.

---

## Quick Start (Web App with Docker)

```bash
docker compose up -d --build
```

Open **http://localhost:8000**. Everything (layouts, exams, scans, CSVs) is stored in the `omr-data` Docker volume and survives restarts and rebuilds.

| Command | What it does |
|---|---|
| `docker compose up -d --build` | Build and start (also after pulling code changes) |
| `docker compose logs -f` | Follow the logs |
| `docker compose down` | Stop; data is kept |
| `docker compose down -v` | Stop and **delete all data** |

Without Docker:

```bash
pip install -r scans_to_csv/requirements.txt -r webapp/requirements.txt opencv-contrib-python
python webapp/app.py            # http://localhost:8000, data in ./data (git-ignored)
```

---

## Using the Web App

### 1. Designer: create a sheet layout

**Design a new sheet** (recommended). Choose:

| Setting | Range | Notes |
|---|---|---|
| Questions | 1–300 | Bubbles shrink automatically to fit one A4 page; the form tells you the maximum if it doesn't fit |
| Options per question | 2–8 | A–B up to A–H |
| Question-paper sets | none, 2–8 | Adds a Set bubble row; each set gets its own answer key |
| Student ID digits | 0–20 | Write-in boxes over a 0–9 bubble grid per digit; 0 leaves out the ID grid |
| Title | text | Printed at the top of the sheet |

The preview updates as you type. **Create layout** saves:
- `sheet.pdf`: print this at 100% ("actual size") on A4.
- `sheet.png`
- `template.json`, `config.json` and `omr_marker.png`

All of these can be downloaded on the layout page, one at a time or as a ZIP.

The sheet has four corner markers. Scans are straightened with them (OMRChecker's `CropOnMarkers`), so slightly rotated, shifted or rescaled scans still read correctly. Keep the corner squares visible when scanning.

**Upload a custom template** for sheets designed elsewhere, such as the BITS sheet with letters in its ID. Upload:
- `template.json` (OMRChecker format)
- `config.json` (optional)
- the blank sheet (optional)
- any files the template refers to, e.g. the `CropOnMarkers` marker image

The preview draws the template's bubble boxes on the blank sheet so you can check the alignment. The BITS Hyderabad 30Q layout from `scans_to_csv/` is installed automatically on first start.

### 2. Professor: create an exam and enter the answer key

Create an exam on a layout, then enter the key on the clickable grid. There is one tab per set.

| To enter | Do this |
|---|---|
| One correct option | Click it, or click the row and type the letter (moves to the next question) |
| **Multiple correct options** | Shift+click (or Shift+letter) to add options, or switch "Clicking an option" to **selects several** |
| …all of them must be marked | Chip shows **ALL** (saved as `A+C`); the student must mark exactly those options |
| …any one of them is enough | Chip shows **ANY** (saved as `A/C`); either option earns the marks |
| Bonus / dropped question | **★**: everyone gets the marks |
| Shorter test than the sheet | "Questions in this exam": the rest are not scored |
| Whole key at once | Quick fill: `ABCD…`, or `A, B, A/C, B+D, *, -` |
| Same key for several sets | "Copy this set" |

"Several selected means" sets whether a new multiple-option answer starts as ALL or ANY. Click the chip on a row to switch it. With **partial credit** on (exam settings), a student who marks some of an ALL answer's options and no wrong one gets a proportional share of the marks: 2 of 3 earns 2/3.

### 3. Upload scans

Drag in single files, many files, multi-page PDFs or a ZIP. Each batch is added to the exam and processed in the background with a progress bar. A file whose name clashes with an earlier upload is renamed, never overwritten. Files that couldn't be read are listed, along with the processing log.

### 4. Review and download

The results table shows every sheet with its score, counts and flags. You can search it, show only flagged sheets, or show the result for each question.
- **Scan** opens the annotated image with the detected bubbles marked.
- **Fix** corrects a misread ID, set or answer by hand. The sheet is then marked `REVIEWED`.
- **Remove** drops a sheet from the exam.

Scores are recomputed automatically whenever the key, settings or a sheet changes.

Downloads:
- **`results.csv`**: marked options per sheet (Stage 1 output)
- **`scores.csv`**: scores and details per student (Stage 2 output, format below)

### 5. Exam settings

- Marking: correct / wrong / blank (default +4 / −1 / 0).
- More than one option marked on a single-answer question: count as wrong (default) or as blank.
- Partial credit on multiple-correct questions.
- Class roster CSV (optional). It needs an ID column such as `student_id`, `ID NO` or `id`. Every other column (name, section, …) is copied into `scores.csv`, and roster students without a sheet are listed as `ABSENT`.

There is no login. Run the app on a trusted machine or network. See [`webapp/README.md`](webapp/README.md) for configuration.

---

## Command-Line Usage

The web app calls the same command-line tools, which can also be used on their own.

### Prerequisites

Python 3.10+ is recommended. Install required packages:

```bash
pip install -r scans_to_csv/requirements.txt
pip install opencv-contrib-python
```

### Stage 1: `scans_to_csv`

#### Default Run (Zero Arguments)
By default, the script automatically reads all scans in [`input/`](input/) and outputs to `output/results.csv`:

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

#### Using a Generated Sheet
Point `--template` and `--config` at a layout made by the sheet designer. The marker image next to the template is picked up automatically:
```bash
python scans_to_csv/omr_to_csv.py --template my_sheet/template.json --config my_sheet/config.json
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

### Sheet Designer (command line)

```bash
python webapp/sheet_designer.py --questions 40 --options 5 --sets 2 --id-digits 10 --title "EEE Quiz 2" --out my_sheet/
```

Writes `sheet.pdf`, `sheet.png`, `template.json`, `config.json`, `omr_marker.png` and `preview.png`.

### Stage 2: Scoring

```bash
python scoring/score_omr.py --key scoring/answer_key_example.csv
```

[`scoring/score_omr.py`](scoring/) scores `output/results.csv` and writes `output/scores.csv`. If no key is given, it asks for the key in the terminal.

| Flag | Meaning | Default |
|---|---|---|
| `--key` | Answer key file (CSV or JSON, one key per set supported) | none |
| `--key-string` | One key for all sets, e.g. `"BCDA…"` or `"B,C,A/D,B+C,*,-"` | none |
| `--correct` / `--wrong` / `--blank` | Marks per outcome | `4` / `-1` / `0` |
| `--multi` | Multi-marked single-answer question counts as `wrong` or `blank` | `wrong` |
| `--partial` | Partial credit on multiple-correct (`A+C`) questions | off |
| `--per-question` | Add a C/W/B/M/P column per question | off |
| `--roster` | Class roster CSV to merge in | none |
| `--results` / `--out` | Input and output CSVs | `output/results.csv` / `output/scores.csv` |
| `--scans` | Run Stage 1 on this folder first | none |

Answer key values:
- `A`: single correct option.
- `A/C` (or `AC`, `A|C`): any one is accepted.
- `A+C` (or `A&C`): all must be marked.
- `*`: bonus.
- `-` or empty: not scored.

See [`scoring/README.md`](scoring/README.md) for key file layouts.

---

## Output Format & Quality Checks

### `results.csv` (Stage 1)

One row per evaluated sheet:

```csv
"file_id","Set","ID NO","q1","q2",...,"q30","check"
"1_12.jpg","A","2021B3A70580H","D","D",...,"B",""
"cf1.jpg","A","20260347H","","C",...,"A","ID_LEN(9/13)"
"cf2.jpeg","","","C","B",...,"A","NO_SET"
"multi1.jpeg","A","2026A7PS0029H","C","AB",...,"B","MULTI(q2)"
```

Anomaly flags in the `check` column:
- **`MULTI(qX)`**: More than one mark detected on a question.
- **`ID_LEN(len/N)`**: Student ID doesn't have the template's N characters (13 for the BITS sheet).
- **`NO_SET`**: Question paper set bubble was left blank or unreadable.
- **`ALL_BLANK`**: All question responses are blank.

### `scores.csv` (Stage 2)

```csv
"image_id","student_id","name","section","set","score","max_score","percentage","correct","wrong","blank","multi","partial","attempted","check","q1",...
"1_12.jpg","2021B3A70580H","Asha Rao","S1","A",79,120,65.83,21,4,4,1,0,26,"","C",...
"","2022A7PS0001H","Ravi K","S2","","",120,"","","","","","","","ABSENT",...
```

- Roster columns (here `name`, `section`) appear only when a roster is given.
- `multi` counts multi-marked single-answer questions, and `partial` counts multiple-correct questions given partial credit.
- Per-question columns (`--per-question`, always on in the web app) show `C` correct, `W` wrong, `B` blank, `M` multi-marked, `P` partial, `-` not scored.

Extra flags added by scoring:
- **`NO_ID`**: no student ID read.
- **`DUPLICATE_ID`**: the same ID appears on several sheets.
- **`NOT_IN_ROSTER`**: the ID isn't in the roster.
- **`ABSENT`**: a roster student has no sheet.
- **`NO_SET_CANNOT_SCORE`** / **`NO_KEY_FOR_SET(X)`**: the sheet can't be matched to a key.
- **`REVIEWED`**: corrected by hand in the web app.
- `MULTI` flags on multiple-correct (`A+C`) questions are removed, because several marks are expected there.

---

## BITS Sheet Layout Note

In `scans_to_csv/template.json` (and `scripts/make_template.py`), the ID column after the pre-printed "2 0" now has a **0** bubble above 1 and 2 (`["0", "1", "2"]`). Its rows then line up with the other 0–9 digit columns.

**The printed BITS sheet must have the same layout.** On older printed sheets, column 3 starts at 1 in the top row. The updated template reads those as one less: a filled 2 reads as 1, so `2021…` becomes `2011…`. Reprint the sheet with the 0 bubble, or use the previous template (`git show acf39ec:scans_to_csv/template.json`) for scans of the old sheets.

---

## Repository Structure

```
omr_checker/
├── input/                  # Scan drop folder (JPG, PNG, PDF) [tracked via .gitkeep]
├── output/                 # Results directory (results.csv, scores.csv, overlays) [tracked via .gitkeep]
├── scans_to_csv/           # Stage 1: Standalone scan-to-CSV CLI pipeline
│   ├── omr_to_csv.py       # Main CLI script
│   ├── template.json       # BITS sheet layout definition
│   ├── config.json         # Threshold & tuning parameters
│   ├── requirements.txt    # Python dependencies
│   ├── src/                # Pipeline engine (alignment, detection, parser)
│   └── README.md           # Stage 1 documentation
├── scoring/                # Stage 2: answer key + results.csv -> scores.csv
│   ├── score_omr.py        # Scoring CLI
│   ├── answer_key_example.csv
│   └── README.md
├── webapp/                 # Web app: designer & professor UI, runs Stage 1 + 2
│   ├── app.py              # Flask routes
│   ├── pipeline.py         # Storage, layouts, exams, background processing
│   ├── sheet_designer.py   # Generates printable sheet + template from numbers
│   ├── run_stage1.py       # Runs Stage 1 without a display (containers)
│   ├── templates/, static/ # Pages, styles, answer key editor
│   └── README.md
├── Dockerfile              # Container for the web app
├── docker-compose.yml      # `docker compose up -d --build` -> http://localhost:8000
├── docs/                   # Multi-milestone roadmap & documentation
│   ├── plan.md             # Master architecture roadmap (M0-M8)
│   ├── bits_omr_README.md  # Sheet layout calibration notes
│   └── OMRChecker_README.md
├── scripts/                # Developer utilities for templates
│   ├── make_template.py    # Generates the BITS template.json
│   ├── check_template.py   # Visual alignment checker
│   └── validate_schema.py  # Schema validator
└── .gitignore              # Ignores scans, result data and data/ while tracking empty folders
```
