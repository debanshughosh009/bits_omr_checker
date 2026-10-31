# Desktop App (`app`)

A desktop window that runs the whole pipeline: the designer adds sheet layouts, and the professor enters answer keys, uploads scans and downloads `results.csv` and `scores.csv`.

It calls the existing stages through their normal command-line interfaces (`scans_to_csv/omr_to_csv.py` and `scoring/score_omr.py`), so results match the CLI exactly.

## Start

Double-click **`OMR Checker.bat`** (Windows) or **`omr_checker.command`** (macOS; run it from a terminal on Linux) in the repository root.
- The first start creates `.venv/` and installs the requirements.
- After that the window opens directly. Close it to quit.

Or, with the requirements installed:

```bash
pip install -r scans_to_csv/requirements.txt -r app/requirements.txt opencv-contrib-python
python app/desktop.py
```

Data goes to `data/` in the repo (git-ignored). Override with the `OMR_DATA_DIR` environment variable.

## How it works

`desktop.py` opens a [pywebview](https://pywebview.flowrl.com/) window: Edge WebView2 on Windows (built into Windows 10/11), WebKit on macOS, Qt or GTK on Linux.
- **Pages:** they are served to that window by Flask (`app.py`) on 127.0.0.1, on a free port. Nothing is reachable from other machines, and the server stops with the window.
- **Downloads:** they open a Save dialog.
- **Links:** scan images and previews open in a second app window.
- **Open folder:** shows a layout's or an exam's files in Explorer / Finder.

## Workflow

**Designer** (Designer tab)
- **Design a new sheet:** the same form and sheet as `designer/index.html`: header, instructions, set box, ID heading, option letters and number of questions. The live preview is drawn in the window by `designer/sheet.js`, and **Open draft** loads a draft saved there.
  - Creating the layout runs the same `sheet.js` in Python (embedded QuickJS engine, no Node.js needed) and saves a printable `sheet.pdf` with corner markers, plus `template.json`, `omr_marker.png` and `draft.json`.
  - The ID grid is fixed: `(F/H/P) 2 0 (0-4) (0-9) (0-9)×4 (H/P/G)`.
  - Print the PDF at 100% on A4. Scans of it are straightened using the markers.
  - The same generator is available on the command line: `python app/sheet_designer.py --help`.
- **Upload a custom template:**
  - Upload `template.json` (required), `config.json` (optional), the blank sheet as PNG/JPG/PDF (optional), and any files the template refers to, such as a `CropOnMarkers` marker image.
  - Templates saved from `designer/index.html` work as they are. Their marker image is drawn automatically.
  - Check the bubble preview: green boxes should sit on the printed circles. For marker-based templates, the blank sheet is straightened first.
- Each layout page has downloads for every file and a ZIP of all of them. The BITS Hyderabad 30Q layout from `scans_to_csv/` is installed on first start.

**Professor** (Professor tab)
1. Create an exam and choose a layout.
2. Enter the answer key on the clickable grid, one tab per set:
   - Click an option to set the answer.
   - **Multiple correct options:** Shift+click another option, or switch "Clicking an option" to "selects several". The chip on the row says what it means. **ALL**: the student must mark exactly those options. **ANY**: any one of them earns the marks. Click the chip to switch. "Several selected means" sets the default.
   - **★** marks a bonus question (everyone gets the marks).
   - Keyboard entry: click a row and type `A`, `B`, ... to answer and move to the next question.
   - Quick fill: paste `ABCD...` or `A, B, A/C, B+D, *, -` (`/` any one, `+` all).
   - "Copy this set" copies the current set's key to other sets.
   - "Questions in this exam" leaves the remaining questions out of the score.
3. Upload scans: single files, many files, multi-page PDFs or a ZIP. Batches add to the exam, and a clashing file name is renamed rather than overwritten.
4. Review the results table. Filter flagged sheets, open the annotated scan, and use **Fix** to correct a misread ID, set or answer. Use **Remove** to drop a sheet.
5. Download `results.csv` (marked options per sheet) and `scores.csv`. The scores file has student ID, roster details, set, score, percentage, correct/wrong/blank/multi/partial counts, per-question C/W/B/M/P and flags.

**Settings** (on the exam page): marking scheme (+4 / -1 / 0 by default), how multi-marked answers on single-answer questions count, partial credit on multiple-correct questions, and an optional class roster CSV. The roster needs an ID column such as `student_id`. Its other columns (name, section, ...) are added to `scores.csv`, and roster students without a sheet are listed as `ABSENT`.

Scores are recomputed automatically whenever the key, settings or a sheet changes.

## Files

| File | Purpose |
|---|---|
| `desktop.py` | Opens the app window and serves the pages to it |
| `app.py` | Flask routes (the pages) |
| `pipeline.py` | Storage, layouts, exams, background scan-processing queue |
| `sheet_designer.py` | Runs `designer/sheet.js` (QuickJS, or Node.js if QuickJS is missing) and draws its SVG as the sheet PDF/PNG (also a CLI) |
| `run_stage1.py` | Runs Stage 1 without opening display windows (supplies a stand-in monitor for screeninfo) |
| `templates/`, `static/` | Pages, styles, sheet designer preview, answer key editor, upload and desktop scripts |

Environment variables: `OMR_DATA_DIR` (data folder), `OMR_PORT` (fixed port instead of a free one), `OMR_MAX_UPLOAD_MB` (default 2048).
