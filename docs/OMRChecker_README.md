# OMR Reader

Reads scanned OMR answer sheets that follow a predefined template and writes the marked options to a CSV file.

Built for the BITS Pilani, Hyderabad Campus 30-question sheet (Set A-D, 13-column student ID, Q1-Q30, options A-D), but the layout lives entirely in a JSON template, so other sheets only need a new template.

> **Current implementation:** the repository runs the Stage 1 reader with
> `scans_to_csv/omr_to_csv.py`. The `omr run` commands below are historical
> examples and are not the current CLI.

For the complete setup and end-to-end workflow, see the repository
[README](../README.md).

## What it does

```
scans/ (JPG, PNG, TIFF, PDF)  +  template.json   -->   results.csv
                                                        flags.csv     (sheets needing a human look)
                                                        debug/        (overlay images, optional)
```

- Aligns each scan using the corner squares, so scanner DPI and small skew don't matter
- Reads Set, the 13-column Student ID and every question
- Handles blank, single, and multiple marks, and pre-printed bubbles
- Flags anything uncertain instead of silently guessing
- Runs in parallel over folders of hundreds or thousands of sheets

## Install

```bash
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r scans_to_csv/requirements.txt
python -m pip install opencv-contrib-python
```

Requires Python 3.10+. Dependencies: `opencv-python`, `numpy`, `pandas`, `pydantic`, `pymupdf`.

## Usage

```bash
python scans_to_csv/omr_to_csv.py
```

This reads `input/` and writes `output/results.csv`. For a custom scan
directory, use `--scans`; see [scans_to_csv/README.md](../scans_to_csv/README.md).

The sheet designer is a browser app. Start it with:

```bash
python -m http.server 8000 --directory designer
```

Then open <http://localhost:8000>.

## Output

`results.csv` has one row per sheet:

| file           | page | set | student_id     | Q1 | Q2 | Q3 | Q4 | ... | Q30 | flags |
| -------------- | ---- | --- | -------------- | -- | -- | -- | -- | --- | --- | ----- |
| sample_273.jpg | 1    | D   | 2022A7PS2018H  | B  | B  | C  | D  | ... |     |       |

Rules:

- Blank question = empty cell
- Multiple marks = letters joined in order, e.g. `BC`, and the sheet gets a `Q_MULTI` flag
- A multi-marked ID column is joined the same way and flagged `ID_MULTI`

### Flags

| Flag                | Meaning                                              |
| ------------------- | ---------------------------------------------------- |
| `ALIGN_FAIL`        | Could not find the corner squares / poor alignment   |
| `ID_INCOMPLETE`     | One or more ID columns blank                         |
| `ID_MULTI`          | An ID column has more than one mark                  |
| `ID_INVALID`        | ID does not match the expected pattern or the roster |
| `SET_MISSING/MULTI` | Set bubble blank or more than one                    |
| `Q_MULTI`           | Several options marked in a single-answer question   |
| `Q_AMBIGUOUS`       | A mark is neither clearly filled nor clearly empty   |
| `DUPLICATE_ID`      | Same ID appears on more than one sheet               |

Flagged sheets are copied with an annotated image to `review/` so you can correct them quickly.

## Templates

A template is a JSON file describing the sheet in canonical pixel coordinates:

- `reference_size`: size of the reference scan
- `fiducials`: how to find the alignment marks
- `fields`: `choice` (Set), `grid` (ID with per-column symbol sets), `mcq_block` (questions)
- `bubble`: radius and the inner area used to measure fill
- `thresholds`: `mark_min`, `blank_max`, `min_gap`

Details and an example are in [plan.md](plan.md#42-template-json-v1-schema-draft).

Tips:

- Always build the template from the **blank** sheet, not a filled one (some ID labels are hidden under ink on filled sheets)
- Pre-printed bubbles (ID column 1 = `2`, column 2 = `0`, column 13 = `H`) are read like any other bubble; the baseline from the blank sheet stops them counting as marks

## Project layout

```
templates/    sheet templates (JSON)
src/omr/      alignment, bubble reading, decoding, flags, CSV
scripts/      template generator
tests/        unit + regression tests
data/         sample scans and ground_truth.csv
```

## Accuracy

Accuracy is always measured against hand-verified data using `omr evaluate`. Targets:

- Questions + Set: >= 99.5% correct
- Student ID: >= 99% exact match, with the rest flagged rather than wrong
- Near-zero **unflagged** errors, since a confident wrong answer is the costly failure

## Roadmap

1. Mark reading to CSV (this phase)
2. Answer key scoring (+4 / -1, per-set keys) and Excel report
3. OMR Designer: generate the printable sheet and its template from parameters (questions, options, single/multiple correct, ID format, number of sets)
4. Small review UI for flagged sheets

## Privacy

Everything runs locally. No scans or student data leave your machine.