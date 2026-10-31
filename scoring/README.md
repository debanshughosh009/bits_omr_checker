# OMR Checker: Stage 2 Scoring

Self-contained scoring stage that takes `output/results.csv` and professor-supplied answer keys, applies a configurable marking scheme and multi-mark policy, and outputs `output/score.csv` with an audit sidecar `output/score_run.json`.

Built using Python standard library only (`csv`, `json`, `decimal`, `http.server`, `argparse`, `pathlib`). Works fully offline.

---

## 1. Quick Start

From the repository root, activate the virtual environment used by
`scans_to_csv` (the scoring stage itself uses only the Python standard
library):
```bash
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
```

### Web UI (Offline)
Launch the local web UI on `127.0.0.1:8765`:
```bash
python scoring/app.py
```
- Opens your browser automatically to `http://127.0.0.1:8765/`.
- Rejects requests from non-localhost host headers.
- Step 1: Shows `results.csv` summary (row count, detected sets, question count, flagged count).
- Step 2: Choose a marking scheme preset (+4/-1/0, +1/0/0, +3/-1/0, +2/-0.5/0, or custom) and a multi-mark policy.
- Step 3: Enter or paste answer keys per Set (e.g. paste string `BC-DA...` where `-` or space represents an uncounted question).
- Step 4: Save / Load keys, preview first 20 rows with summary statistics, and write `score.csv`.
Stop the server with `Ctrl+C`. The UI reads `output/results.csv`, which is
normally produced by `python scans_to_csv/omr_to_csv.py`.

### Headless CLI
Score directly from the command line:
```bash
python scoring/cli.py \
  --results output/results.csv \
  --keys scoring/keys/quiz1.json \
  --out output/score.csv \
  --scheme 4,-1,0 \
  --multi zero \
  --per-question
```

CLI flags:
- `--results`: Path to `results.csv` (default: `output/results.csv`).
- `--keys`: Path to answer-key JSON file (required).
- `--out`: Output path for `score.csv` (default: `output/score.csv`).
- `--scheme`: Marking scheme as `correct,wrong,unattempted` (default: `4,-1,0`).
- `--multi`: Multi-mark policy: `zero` (default), `wrong`, `credit_if_contains`, or `hold`.
- `--per-question`: Include optional `q1_mark`..`qN_mark` columns.

---

## 2. Answer Key Format

Answer keys are saved as JSON files in `scoring/keys/<name>.json`:
```json
{
  "version": 1,
  "questions": 30,
  "options": "ABCD",
  "sets": {
    "A": ["B", "", "C", "D", "A", ...],
    "B": ["A", "C", "", "B", "D", ...]
  }
}
```

### Blank Key Rule
- An empty string `""` in the answer key indicates that question is **NOT counted** for that set.
- It contributes 0 marks to every student and is excluded from `max_score` (`max_score = counted * marks_correct`).
- A student's answer on an uncounted question is completely ignored (not counted as correct, wrong, unattempted, or multi).

---

## 3. Multi-Mark Policy

When a student marks two or more options (e.g. `AB` on a single-choice question):
- `zero` (default): Treated as unattempted (`marks_unattempted`).
- `wrong`: Treated as wrong (`marks_wrong`).
- `credit_if_contains`: Correct (`marks_correct`) if the correct key letter is among the marked letters; otherwise wrong (`marks_wrong`).
- `hold`: Question gets 0 marks, and the entire sheet is flagged with `REVIEW` in `score_status` for human verification. The question remains counted in `max_score`.

---

## 4. Sheet-Level Rules & Status Flags (`score_status`)

Output row count always equals input row count; no rows are dropped or silently altered. Issues are reported in the `score_status` column (combined with `; ` if multiple):
- `OK`: All fields valid and successfully scored.
- `NO_SET`: The Set column was blank or unreadable. Score columns are left blank.
- `NO_KEY_FOR_SET:<X>`: Set `<X>` exists in standard sets {A..D} but was missing from the supplied key file. Score columns are left blank.
- `UNKNOWN_SET:<X>`: Set `<X>` was not in {A..D} and not in the keys. Score columns are left blank.
- `ALL_BLANK`: Student left all question bubbles blank. Sheet is scored (receiving unattempted marks) and flagged.
- `DUPLICATE_ID:<id>`: The non-empty student ID appears on multiple sheets. All involved rows are flagged.
- `REVIEW`: One or more questions were held for human review under policy `hold`.

---

## 5. File Safety & Integrity

- **Exact Arithmetic:** All calculations use `decimal.Decimal` to avoid floating-point drift on fractional steps (such as 0.25 or 0.5 marks).
- **Atomic Writes:** `write_score` writes to a temporary file in the destination folder, then replaces atomically. If `score.csv` already exists, it is automatically backed up to `score_<timestamp>.csv.bak`. If a failure occurs during writing, the backup is preserved and partial files are removed.
- **Formula Safety:** Text fields (`file_id`, `Set`, `ID NO`) that begin with formula prefix characters (`=`, `+`, `-`, `@`) are prefixed with `'` to prevent spreadsheet formula execution.
- **Run Audit Sidecar:** Every write produces `output/score_run.json` containing timestamps, SHA-256 hash of the answer key file, marking scheme, multi-mark policy, and input row counts.
- **Data Privacy:** Scans, results, scores, and answer keys are ignored by git via `.gitignore`.
