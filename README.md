# OMR Checker: Custom Template to Scoring Pipeline

An automated, template-driven Optical Mark Recognition (OMR) processing and scoring pipeline designed for institutional examinations. The system reliably digitizes physical OMR answer sheets into verified structured data at scale.

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
1. **Scans to CSV ([`scans_to_csv/`](scans_to_csv/)):**
   - **Stage 1 CLI Engine:** Processes batches of scanned JPG, PNG, and PDF sheets.
   - Self-contained pipeline: includes its own detection engine (`src/`), `template.json`, and `config.json`.
   - Detects corner alignment markers, corrects skew, samples bubble fills, decodes alphanumeric IDs and sets, and writes clean CSV data.
   - Performs built-in anomaly detection (`MULTI` options, incomplete `ID_LEN`, missing `NO_SET`).
2. **Scoring ([`scoring/`](scoring/)):**
   - **Stage 2 Engine & UI:** Reads `output/results.csv` and answer keys, applies marking schemes and multi-mark policies, and exports `output/score.csv`.
   - Built with Python standard library only; works fully offline with an integrated local web UI and headless CLI.
3. **Template Utilities ([`scripts/`](scripts/)):**
   - Developer tools to generate and validate OMR layout templates (`make_template.py`, `validate_schema.py`, `check_template.py`).
3. **Architecture & Documentation ([`docs/`](docs/)):**
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
├── app/server.py           # Local server: serves the web app, stores exams in data/omr.db (SQLite)
├── web/                    # The web app (React + shadcn/ui): dashboard, sheet designer, evaluator
│   ├── src/lib/sheet.js    # The sheet layout both the printout and the template come from
│   ├── src/lib/score.js    # Answer keys and marking schemes
│   └── dist/               # The built app, committed so running needs only Python
├── Start OMR.command/.bat  # Double-click to run (macOS / Windows)
├── packaging/              # Mac and Windows app builds (PyInstaller spec, installer, icons)
├── scripts/                # Developer utilities for templates
│   ├── check_designer.py   # Round trip: designed sheet -> filled scan -> CSV
│   ├── check_score.mjs     # Scoring rules
│   ├── make_template.py    # Generates template.json
│   ├── check_template.py   # Visual alignment checker
│   └── validate_schema.py  # Schema validator
└── .gitignore              # Ignores scans & result data while tracking empty folders
```

---

## Getting Started

### The app (dashboard, designer and evaluator, one click)

Double-click **`Start OMR.command`** (macOS) or **`Start OMR.bat`** (Windows). It opens the dashboard in its own window at `http://localhost:8765`. Everything stays on this machine: exams, answer keys and read sheets are kept in `data/omr.db` (SQLite), and each exam's scans and overlay images under `data/exams/<id>/`. The first start creates `.venv/` and installs the reader's packages into it (a few minutes, once; needs Python 3.10+). Keep the terminal window open while you work; close it to stop.

- **Dashboard**: a box to design a new sheet, and a table of every saved sheet with its scans read, mean and status. Click a sheet to evaluate it; edit its design or delete it from the same row. **Evaluate a sheet designed elsewhere** adds the original 30-question sheet or any `template.json`.
- **Designing**: the designer below. **Save** keeps the sheet on this computer (in the database, plus `design.json` and `template.json` in `data/exams/<id>/`) and lists it on the dashboard; **Evaluate** saves and opens it. Once scans have been read against a sheet its layout is locked; saving a changed layout offers to make a new sheet instead.
- **Evaluating**: type an answer key per set; drop scans in and press **Read** (this runs `scans_to_csv/omr_to_csv.py`); see the score distribution and which questions few got right (often a wrong key); click a scan to see the overlay and correct a misread; **Export CSV** saves the marks.

Answer keys: on a sheet's **Answer key** page, pick a set from the bar along the top, give each question a type (single correct, multiple correct, either accepted, bonus, dropped) and click its right option(s): round bubbles take one, square ones any number. **Type for all** switches a whole set between single and multiple correct. **Paste** takes a typed key instead: one answer per question, in order or numbered (`12 AC`); `B` single correct, `AC` multiple correct, `A+` multiple correct with only A right, `A/C` either accepted, `*` bonus (full marks to everyone), `-` dropped. Marking schemes:

| | Options |
|---|---|
| Single correct | marks for correct, wrong, blank; a multi-marked answer counts as wrong or scores zero |
| Multiple correct | **All or nothing**; **Partial** (JEE Advanced style: full for exactly right, per-option marks for a subset of right options, wrong marks if any wrong option); **Proportional** (full × share of right options marked); **Per option** (+ per right option, − per wrong option) |

Marks are recalculated as you change the key or the scheme, and the scheme page shows what sample answers would score. `node scripts/check_score.mjs` checks the scoring rules.

**Changing the app** (needs Node 18+): edit `web/src/`, then restart the app; it rebuilds `web/dist/` on start when the source is newer. For live reload while editing, run `python app/server.py --no-browser` alongside `cd web && npm run dev`. Commit `web/dist/` with your change so machines without Node keep working.

### Mac and Windows apps

Releases ship OMR Checker as an installed app, with no Python, Node or terminal needed:

- **macOS:** `OMR-Checker-<version>-mac-apple-silicon.dmg` or `-mac-intel.dmg`. Open it and drag OMR Checker to Applications.
- **Windows:** `OMR-Checker-<version>-windows-setup.exe`, a per-user installer (no admin rights) with Start menu and optional desktop shortcuts and an uninstaller.

Opening the app starts it in the background and opens it in its own window, with no tabs or address bar. It uses the default browser's app mode when that is Chrome, Edge or Brave, and otherwise the first of those installed; with none of them it opens a normal browser tab. Opening it again while it runs opens another window. A few minutes after the last window closes, it stops by itself, and nothing stays in the menu bar or Dock. Its data lives in `~/Library/Application Support/OMR Checker` or `%LOCALAPPDATA%\OMR Checker`. The builds are not code-signed yet, so the first launch needs right-click → Open on macOS (or System Settings → Privacy & Security → Open Anyway), and More info → Run anyway on Windows SmartScreen.

**Building one locally** (Python 3.12 recommended):

```bash
cd web && npm ci && npm run build && cd ..
python -m venv .venv-build && .venv-build/bin/pip install -r packaging/requirements.txt
.venv-build/bin/python packaging/build.py        # writes release/OMR-Checker-<version>-...
.venv-build/bin/python packaging/smoke_test.py   # the packaged app must read scans like the source
```

On Windows, install [Inno Setup 6](https://jrsoftware.org/isinfo.php) first and use `.venv-build\Scripts\python`. `packaging/omr_checker.spec` is the PyInstaller spec, `packaging/windows-installer.iss` the installer, and `packaging/make_icons.py` redraws the icons.

**Releasing:** set `__version__` in `app/server.py`, commit, then push a matching tag (`git tag v1.0.0 && git push origin v1.0.0`). `.github/workflows/release.yml` builds and checks all three apps and attaches them to a **draft** GitHub Release to review and publish. Running the workflow by hand from the Actions tab builds the apps without a release.

### 1. Prerequisites & Environment Setup

Python 3.10+ is recommended. From the repository root, create and activate a
virtual environment, then install the scan-reader dependencies:

**Windows PowerShell**
```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r scans_to_csv\requirements.txt
python -m pip install opencv-contrib-python
```

**macOS/Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r scans_to_csv/requirements.txt
python -m pip install opencv-contrib-python
```

The designer and scorer use browser/Python standard-library functionality and
do not require additional packages. Activate `.venv` in each new terminal.

---

### 2. Running `scans_to_csv`

#### Default Run (Zero Arguments)
By default, the script automatically reads all scans in [`input/`](input/) and outputs to [`output/results.csv`](output/results.csv):

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

Open **Design a sheet** in the app. The form on the left sets the header, instructions, set box, options, and number of questions; the right side is the A4 sheet as it will print. Questions spread over up to four columns, fewer when there are many options, and the form says how many questions fit. The ID grid is fixed to the degree (F first degree, H higher degree, P PhD), the year, the last four digits, and the campus letter, written like the campus email (`F20231187@H`): bubbles for the degree, "20" printed, then bubbles for the rest of the year (each digit level with the same digit in the other columns), the four digits, "@" printed, and the campus (H/G/P/D), with a write-in box over each column; the reader puts the "20" and "@" back into `ID NO`. The grid is headed EMAIL; beside it the student writes their name and ID number on two lines, and the quiz date is printed in the header, so there are no signature or date blanks.

**Two sheets per page** (in the Questions card) prints two half-height sheets one above the other on an A4, with a dotted cut line and scissors between them. Bubbles stay full size, so a half holds fewer questions (25 with four options, 20 with five); the question count is capped at what fits. Each half has its own corner markers: cut the pages and scan the halves like any other sheet.

- **Print / PDF** prints the sheet. Print at 100% ("Actual size"), with the browser's headers and footers off.
- **Template** saves the matching `template.json`. Run scans of that sheet with `--template path/to/that_template.json`.
- **Save draft** / **Open** keep the form as a `.json` file; the browser also remembers the last draft.

The template is computed from the same layout that draws the sheet, so there is nothing to calibrate. The four corner markers let the reader straighten each scan, so skew, shifted scans, and small print scaling are absorbed. Sheets printed before the designer still use the hand-calibrated `scans_to_csv/template.json`.

`python scripts/check_designer.py` renders the default sheet, fills it in, skews it like a scan, and checks `scans_to_csv` reads every answer back. Pass `--pdf sheet.pdf` to test a sheet the browser printed, and `--half` (optionally `--on-a4`) to test a cut-out half of a two-per-page sheet.

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

The scorer expects `output/results.csv` from Stage 1. Open the displayed
`http://127.0.0.1:8765/` address, load or enter an answer key, and save the
scores. Use `Ctrl+C` to stop the server.

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

[`output/results.csv`](output/results.csv) contains one row per evaluated sheet:

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
