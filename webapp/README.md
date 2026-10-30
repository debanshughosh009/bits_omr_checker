# Web App (`webapp`)

Browser UI that runs the whole pipeline: the designer adds sheet layouts, and the professor enters answer keys, uploads scans and downloads `results.csv` and `scores.csv`.

It calls the existing stages through their normal command-line interfaces (`scans_to_csv/omr_to_csv.py` and `scoring/score_omr.py`), so results match the CLI exactly.

## Run with Docker (recommended)

From the repository root:

```bash
docker compose up -d --build
```

Open http://localhost:8000. Data (layouts, exams, scans, CSVs) is kept in the `omr-data` Docker volume, so it survives restarts and rebuilds.

```bash
docker compose logs -f        # follow logs
docker compose down           # stop (data is kept)
docker compose down -v        # stop and DELETE all data
```

## Run without Docker

```bash
pip install -r scans_to_csv/requirements.txt -r webapp/requirements.txt opencv-contrib-python
python webapp/app.py
```

Data goes to `data/` in the repo (git-ignored). Override with the `OMR_DATA_DIR` environment variable.

## Workflow

**Designer** (`/designer`)
- **Design a new sheet:** choose the number of questions (1–300), options per question (2–8), question-paper sets (none or 2–8), whether to include the BITS ID grid (`(F/H/P) 2 0 (0-4) (0-9) (0-9)×4 (H/P/G)`, the same format as `designer/`) and a title. The preview updates as you type.
  - Creating the layout saves a printable `sheet.pdf` with corner markers, plus `template.json`, `config.json` and `omr_marker.png`.
  - Print the PDF at 100% on A4. Scans of it are straightened using the markers.
  - The same generator is available on the command line: `python webapp/sheet_designer.py --help`.
- **Upload a custom template:**
  - Upload `template.json` (required), `config.json` (optional), the blank sheet as PNG/JPG/PDF (optional), and any files the template refers to, such as a `CropOnMarkers` marker image.
  - Templates saved from `designer/index.html` work as they are. Their marker image is drawn automatically.
  - Check the bubble preview: green boxes should sit on the printed circles. For marker-based templates, the blank sheet is straightened first.
- Each layout page has downloads for every file and a ZIP of all of them. The BITS Hyderabad 30Q layout from `scans_to_csv/` is installed on first start.

**Professor** (`/professor`)
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
| `app.py` | Flask routes |
| `pipeline.py` | Storage, layouts, exams, background scan-processing queue |
| `sheet_designer.py` | Generates a printable sheet + template from questions/options/sets, with the BITS ID grid (also a CLI) |
| `run_stage1.py` | Runs Stage 1 on machines with no display (supplies a stand-in monitor for screeninfo) |
| `templates/`, `static/` | Pages, styles, sheet designer preview, answer key editor and upload scripts |

Environment variables: `OMR_DATA_DIR` (data folder), `PORT` (default 8000), `OMR_MAX_UPLOAD_MB` (default 2048), `OMR_SECRET_KEY`.

There is no login. Run it on a trusted machine or network, or put it behind your institution's authentication.
