# Stage 2: Scoring (`scoring`)

Takes an answer key from the user, scores every sheet in the Stage 1 CSV (`output/results.csv`) and writes `output/scores.csv` with one row per scan.

Uses only the Python standard library (no extra dependencies).

## Quick Start

From repository root:

```bash
# 1. Stage 1: scans -> results.csv
python scans_to_csv/omr_to_csv.py

# 2. Stage 2: results.csv + answer key -> scores.csv
python scoring/score_omr.py --key scoring/answer_key_example.csv
```

Or run both stages in one command:
```bash
python scoring/score_omr.py --scans input --key my_key.csv
```

## Giving the Answer Key

Pick one of these. If you give neither `--key` nor `--key-string`, the script asks for the key in the terminal.

| Method | Example |
|---|---|
| CSV, one column per set | `--key key.csv` (see [`answer_key_example.csv`](answer_key_example.csv)) |
| CSV, single key | header `question,answer` |
| CSV, one row per set | header `Set,q1,q2,...,q30` (same shape as `results.csv`) |
| JSON | `{"A": "BCDA...", "B": "CDAB..."}`, or just `"BCDA..."` for one key |
| Inline string | `--key-string "BCDAADCB..."` or `--key-string "B,C,A/D,B+C,*,..."` |

Answer cell values:
- `A`: the single correct option
- `A/C` (or `AC`, `A|C`): **any one** of the options is accepted
- `A+C` (or `A&C`): **multiple correct**. The sheet must mark exactly A and C. Marking only A, or A, C and D, is wrong, unless `--partial` is on (below).
- `*`: bonus/dropped question, full marks for every sheet
- `-` or empty: question not scored (0 marks, left out of `max_score`)

### Multiple-correct questions

For an `A+C` answer:

| Marked | Without `--partial` | With `--partial` |
|---|---|---|
| A and C | correct (+4) | correct (+4) |
| A only | wrong (−1) | partial: 4 × 1/2 = +2 |
| A, C and D | wrong (−1) | wrong (−1) |
| nothing | blank (0) | blank (0) |

The `--multi` setting doesn't apply to these questions, and Stage 1's `MULTI` flag is removed for them, since several marks are expected.

With per-set keys, each sheet is scored against the key for its `Set`. If a sheet's set is blank or has no key, it is not scored and gets a flag. A single common key applies to every sheet, whatever its set.

## Marking Scheme

| Flag | Meaning | Default |
|---|---|---|
| `--correct` | Marks for a correct answer | `4` |
| `--wrong` | Marks for a wrong answer | `-1` |
| `--blank` | Marks for an unattempted question | `0` |
| `--multi` | Multi-marked answer on a single-answer question counts as `wrong` or `blank` | `wrong` |
| `--partial` | Partial credit on multiple-correct (`A+C`) questions | off |
| `--per-question` | Add q1..qN status columns (`C` correct, `W` wrong, `B` blank, `M` multi, `P` partial, `-` not scored) | off |
| `--roster` | Class roster CSV: an ID column plus any details; missing students are listed as `ABSENT` | none |
| `--results` | Stage 1 CSV to score | `output/results.csv` |
| `--out` | Output CSV | `output/scores.csv` |
| `--scans` | Run Stage 1 on this folder first | none |

## Output Format

```csv
"image_id","student_id","set","score","max_score","percentage","correct","wrong","blank","multi","partial","attempted","check"
"1_12.jpg","2021B3A70580H","A",79,120,65.83,21,4,4,1,0,26,""
"cf2.jpeg","2021B3A70583H","","",120,"","","","","","","","NO_SET, NO_SET_CANNOT_SCORE"
```

With `--roster`, the roster's columns (e.g. `name`, `section`) come after `student_id`, and roster students without a sheet get a row flagged `ABSENT`.

The `check` column keeps the Stage 1 flags (`MULTI`, `ID_LEN`, `NO_SET`, `ALL_BLANK`) and adds:
- **`NO_ID`**: no student ID was read (only for sheets that have an ID field).
- **`NOT_IN_ROSTER`** / **`ABSENT`**: roster mismatches (with `--roster`).
- **`DUPLICATE_ID`**: the same student ID appears on more than one sheet.
- **`NO_SET_CANNOT_SCORE`**: per-set keys were given but the sheet has no set.
- **`NO_KEY_FOR_SET(X)`**: the sheet's set has no key.
