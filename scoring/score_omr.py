"""
score_omr.py – Stage 2: Scoring
================================
Takes the answer key from the user, scores every row of the Stage 1 CSV
(output/results.csv) and writes a scores CSV with one row per scan.

Usage:
    python score_omr.py [--results <results.csv>] [--key <key.csv|key.json>]
                        [--key-string "BCDA..."] [--out <scores.csv>]
                        [--correct 4] [--wrong -1] [--blank 0] [--multi wrong|blank]
                        [--partial]
                        [--per-question] [--roster <roster.csv>] [--scans <folder>]

Answer key sources (first one given wins):
    --key FILE        CSV or JSON answer key (supports one key per set)
    --key-string STR  one key applied to every set, e.g. "BCDA..." or "B,C,D,A,..."
    (none)            the key is asked for interactively

Answer key conventions:
    "A"      single correct option
    "A/C"    any one of the listed options is accepted ("AC" or "A|C" also work)
    "A+C"    multiple correct: the sheet must mark exactly A and C ("A&C" also works);
             with --partial, marking only some of them (and nothing wrong) earns
             a proportional share of the marks
    "*"      bonus / dropped question: full marks to every sheet
    ""/"-"   question not scored (0 marks to everyone, excluded from max score)
"""

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

BONUS = "*"
NOT_SCORED = ""
ALL_OF = "+"


# ---------------------------------------------------------------------------
# Answer key parsing
# ---------------------------------------------------------------------------

def normalize_answer(raw: str) -> str:
    """
    Turn a key cell into a canonical string:
    '' (not scored), '*' (bonus), 'AC' (any one of A, C) or 'A+C' (exactly A and C).
    """
    val = str(raw).strip().upper()
    if val in ("", "-", "NA", "N/A", "NONE", "X"):
        return NOT_SCORED
    if val in ("*", "BONUS", "ALL"):
        return BONUS
    all_of = "+" in val or "&" in val
    letters = re.sub(r"[\s,/|;+&]", "", val)
    if not re.fullmatch(r"[A-Z0-9]+", letters):
        raise ValueError(f"invalid answer '{raw}' (allowed: option letters, A/C, A+C, *, -)")
    letters = sorted(set(letters))
    return ALL_OF.join(letters) if all_of else "".join(letters)


def is_all_of(ans: str) -> bool:
    return ALL_OF in ans


def answer_letters(ans: str) -> set[str]:
    return set(ans.replace(ALL_OF, ""))


def split_key_string(text: str) -> list[str]:
    """
    Split a key string into per-question answers.
    'BCDA'            -> ['B','C','D','A']   (one letter per question)
    'B,C,A/D,*,-'     -> ['B','C','A/D','*','-']
    'B C AD * -'      -> ['B','C','AD','*','-']
    """
    text = text.strip()
    if "," in text:
        return [t.strip() for t in text.split(",")]
    if re.search(r"\s", text):
        return text.split()
    return list(text)


def key_from_list(answers: list[str], questions: list[str]) -> dict[str, str]:
    if len(answers) != len(questions):
        raise ValueError(
            f"answer key has {len(answers)} answers but the sheet has {len(questions)} questions"
        )
    return {q: normalize_answer(a) for q, a in zip(questions, answers)}


def load_key_csv(path: Path, questions: list[str]) -> dict[str, dict[str, str]]:
    """
    Two CSV layouts are accepted.

    Question-per-row (one column per set, or a single 'answer' column):
        question,A,B,C,D            question,answer
        q1,B,C,A,D                  q1,B
        q2,A,A,B,C                  q2,A

    Set-per-row (same shape as results.csv):
        Set,q1,q2,...,q30
        A,B,A,...,D
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("answer key CSV is empty")

    header = [h.strip() for h in rows[0]]
    lower = [h.lower() for h in header]

    keys: dict[str, dict[str, str]] = {}
    if lower[0] in ("question", "q", "qno", "question_no"):
        set_names = header[1:]
        for r in rows[1:]:
            q = r[0].strip().lower()
            q = q if q.startswith("q") else f"q{q}"
            for i, s in enumerate(set_names, start=1):
                keys.setdefault(s, {})[q] = r[i] if i < len(r) else ""
    elif lower[0] == "set":
        for r in rows[1:]:
            s = r[0].strip()
            keys[s] = {h.lower(): (r[i] if i < len(r) else "") for i, h in enumerate(header) if i > 0}
    else:
        raise ValueError("answer key CSV must start with a 'question' or 'Set' column")

    return {
        _set_name(s): _complete_key(k, questions, f"set {s}")
        for s, k in keys.items()
    }


def load_key_json(path: Path, questions: list[str]) -> dict[str, dict[str, str]]:
    """
    {"A": "BCDA...", "B": ["B","C",...], "C": {"q1": "B", ...}}
    or for a single key: "BCDA..." / ["B","C",...] / {"q1": "B", ...}
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    def one(v, label):
        if isinstance(v, str):
            return key_from_list(split_key_string(v), questions)
        if isinstance(v, list):
            return key_from_list([str(x) for x in v], questions)
        if isinstance(v, dict):
            return _complete_key({k.lower(): x for k, x in v.items()}, questions, label)
        raise ValueError(f"unsupported answer key value for {label}")

    if isinstance(data, dict) and data and all(k.lower() not in questions for k in data):
        return {_set_name(s): one(v, f"set {s}") for s, v in data.items()}
    return {"*": one(data, "key")}


def _set_name(s: str) -> str:
    s = s.strip()
    return "*" if s.lower() in ("answer", "all", "*", "") else s.upper()


def _complete_key(k: dict[str, str], questions: list[str], label: str) -> dict[str, str]:
    missing = [q for q in questions if q not in k]
    if missing:
        raise ValueError(f"{label}: missing answers for {', '.join(missing)}")
    return {q: normalize_answer(k[q]) for q in questions}


def prompt_key(questions: list[str]) -> dict[str, dict[str, str]]:
    """Ask the user for the answer key on the terminal."""
    print("\nNo answer key file given. Enter the key interactively.")
    print("Answers: option letters, 'A/C' either accepted, 'A+C' both required, '*' bonus, '-' not scored.")
    sets = input("Sets with different keys (e.g. 'A B C D'), or Enter for one common key: ")
    set_names = sets.replace(",", " ").split() or ["*"]

    keys = {}
    for s in set_names:
        label = "common key" if s == "*" else f"set {s.upper()}"
        while True:
            text = input(f"Key for {label} ({len(questions)} answers, e.g. BCDA... or B,C,A/D,...): ")
            try:
                keys[_set_name(s)] = key_from_list(split_key_string(text), questions)
                break
            except ValueError as e:
                print(f"  {e}. Try again.")
    return keys


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_row(row, questions, key, marks, multi_policy, partial=False):
    """
    Score one sheet. Returns (counts dict, per-question status list, score).
    Status: C correct, W wrong, B blank, M multi-marked, P partial, - not scored.
    """
    counts = {"correct": 0, "wrong": 0, "blank": 0, "multi": 0, "partial": 0}
    status = []
    score = 0.0
    for q in questions:
        ans = key[q]
        resp = "".join(sorted(set(str(row.get(q, "")).strip().upper())))

        if ans == NOT_SCORED:
            status.append("-")
            continue
        if ans == BONUS:
            counts["correct"] += 1
            score += marks["correct"]
            status.append("C")
            continue

        if is_all_of(ans):
            # Multiple-correct question: the response must be exactly the key's set
            need, got = answer_letters(ans), set(resp)
            if not got:
                counts["blank"] += 1
                score += marks["blank"]
                status.append("B")
            elif got == need:
                counts["correct"] += 1
                score += marks["correct"]
                status.append("C")
            elif partial and got < need:
                counts["partial"] += 1
                score += marks["correct"] * len(got) / len(need)
                status.append("P")
            else:
                counts["wrong"] += 1
                score += marks["wrong"]
                status.append("W")
            continue

        if not resp:
            counts["blank"] += 1
            score += marks["blank"]
            status.append("B")
        elif len(resp) > 1:
            counts["multi"] += 1
            score += marks["wrong"] if multi_policy == "wrong" else marks["blank"]
            status.append("M")
        elif resp in ans:
            counts["correct"] += 1
            score += marks["correct"]
            status.append("C")
        else:
            counts["wrong"] += 1
            score += marks["wrong"]
            status.append("W")
    return counts, status, score


def pick_key(keys, sheet_set):
    """Return (key, note). A single common key applies to every sheet."""
    if "*" in keys:
        return keys["*"], ""
    if len(keys) == 1:
        return next(iter(keys.values())), ""
    s = sheet_set.strip().upper()
    if not s:
        return None, "NO_SET_CANNOT_SCORE"
    if s not in keys:
        return None, f"NO_KEY_FOR_SET({s})"
    return keys[s], ""


def fmt(x: float):
    return int(x) if float(x).is_integer() else round(x, 2)


def load_roster(path: Path):
    """
    Read a class roster CSV. The ID column is the first one named like
    'student_id' / 'ID NO' / 'id' (else the first column); every other
    column is copied into the scores CSV. Returns (extra_columns, {id: row}).
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = [h for h in (reader.fieldnames or []) if h]
        rows = list(reader)
    if not header:
        raise ValueError("roster CSV is empty")
    id_names = ("student_id", "id no", "idno", "id", "id_no", "student id", "bits id")
    id_col = next((h for h in header if h.strip().lower() in id_names), header[0])
    extra = [h for h in header if h != id_col]
    return extra, {str(r[id_col]).strip().upper(): r for r in rows if str(r[id_col]).strip()}


def drop_expected_multi(check: str, key: dict[str, str]) -> str:
    """Remove Stage 1 MULTI flags for questions whose key has multiple correct answers."""
    def keep(m):
        qs = [q for q in m.group(1).split(",") if not is_all_of(key.get(q.strip(), ""))]
        return f"MULTI({','.join(qs)})" if qs else ""
    check = re.sub(r"MULTI\(([^)]*)\)", keep, check)
    return ", ".join(p.strip() for p in check.split(", ") if p.strip())


def score_results(results_path, keys, questions, marks, multi_policy, per_question,
                  roster=None, partial=False):
    with open(results_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    any_key = next(iter(keys.values()))
    max_score = sum(marks["correct"] for q in questions if any_key[q] != NOT_SCORED)

    header = [
        "image_id", "student_id", "set", "score", "max_score", "percentage",
        "correct", "wrong", "blank", "multi", "partial", "attempted", "check",
    ]
    if per_question:
        header += questions

    roster_cols, roster_rows = roster if roster else ([], {})
    header[2:2] = roster_cols

    has_id = bool(rows) and "ID NO" in rows[0]
    out_rows = []
    seen_ids: dict[str, int] = {}
    for row in rows:
        sid = str(row.get("ID NO", "")).strip()
        if sid:
            seen_ids[sid] = seen_ids.get(sid, 0) + 1

    for row in rows:
        sid = str(row.get("ID NO", "")).strip()
        sheet_set = str(row.get("Set", "")).strip()
        key, note = pick_key(keys, sheet_set)
        check = str(row.get("check", "")).strip()
        if key is not None:
            check = drop_expected_multi(check, key)
        notes = [check] if check else []
        if has_id and not sid:
            notes.append("NO_ID")
        elif sid and seen_ids[sid] > 1:
            notes.append("DUPLICATE_ID")

        rec = {"image_id": row.get("file_id", ""), "student_id": sid, "set": sheet_set}
        if roster:
            student = roster_rows.get(sid.upper())
            rec.update({c: (student or {}).get(c, "") for c in roster_cols})
            if sid and student is None:
                notes.append("NOT_IN_ROSTER")
        if key is None:
            notes.append(note)
            rec.update({k: "" for k in header if k not in rec})
            rec["max_score"] = fmt(max_score)
        else:
            counts, status, score = score_row(row, questions, key, marks, multi_policy, partial)
            rec.update({
                "score": fmt(score),
                "max_score": fmt(max_score),
                "percentage": round(100 * score / max_score, 2) if max_score else "",
                **counts,
                "attempted": counts["correct"] + counts["wrong"] + counts["multi"] + counts["partial"],
            })
            if per_question:
                rec.update(dict(zip(questions, status)))
        rec["check"] = ", ".join(notes)
        out_rows.append(rec)

    # Roster students with no sheet in the batch
    read_ids = {r["student_id"].upper() for r in out_rows}
    for rid, student in roster_rows.items():
        if rid not in read_ids:
            rec = {k: "" for k in header}
            rec.update({c: student.get(c, "") for c in roster_cols})
            rec.update({"student_id": rid, "max_score": fmt(max_score), "check": "ABSENT"})
            out_rows.append(rec)
    return header, out_rows


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def read_questions(results_path: Path) -> list[str]:
    with open(results_path, newline="", encoding="utf-8-sig") as f:
        header = next(csv.reader(f), [])
    qs = [h for h in header if re.fullmatch(r"q\d+", h.strip())]
    if not qs:
        print(f"ERROR: no question columns (q1, q2, ...) in {results_path}", file=sys.stderr)
        sys.exit(1)
    return sorted(qs, key=lambda q: int(q[1:]))


def main():
    stage_dir = Path(__file__).resolve().parent
    repo_root = stage_dir.parent
    default_results = repo_root / "output" / "results.csv"
    default_out = repo_root / "output" / "scores.csv"

    parser = argparse.ArgumentParser(
        description="Score Stage 1 OMR results against an answer key and write a scores CSV."
    )
    parser.add_argument("--results", default=str(default_results),
                        help=f"Stage 1 results CSV. (Default: {default_results})")
    parser.add_argument("--key", default=None,
                        help="Answer key file (.csv or .json). Supports per-set keys.")
    parser.add_argument("--key-string", default=None,
                        help='Single answer key for all sets, e.g. "BCDA..." or "B,C,A/D,...".')
    parser.add_argument("--out", default=str(default_out),
                        help=f"Output scores CSV. (Default: {default_out})")
    parser.add_argument("--correct", type=float, default=4, help="Marks for a correct answer. (Default: 4)")
    parser.add_argument("--wrong", type=float, default=-1, help="Marks for a wrong answer. (Default: -1)")
    parser.add_argument("--blank", type=float, default=0, help="Marks for an unattempted question. (Default: 0)")
    parser.add_argument("--multi", choices=["wrong", "blank"], default="wrong",
                        help="Treat multi-marked answers as wrong or as blank. (Default: wrong)")
    parser.add_argument("--partial", action="store_true", default=False,
                        help="Partial credit on multiple-correct (A+C) questions: a share of the "
                             "marks for marking some correct options and no wrong ones.")
    parser.add_argument("--per-question", action="store_true", default=False,
                        help="Add per-question status columns (C=correct, W=wrong, B=blank, M=multi, "
                             "P=partial, -=not scored).")
    parser.add_argument("--roster", default=None,
                        help="Optional class roster CSV; its columns are added and missing students listed as ABSENT.")
    parser.add_argument("--scans", default=None,
                        help="Optional: run Stage 1 (scans_to_csv/omr_to_csv.py) on this folder first.")
    args = parser.parse_args()

    results_path = Path(args.results).resolve()
    out_path = Path(args.out).resolve()

    if args.scans:
        stage1 = repo_root / "scans_to_csv" / "omr_to_csv.py"
        cmd = [sys.executable, str(stage1), "--scans", args.scans, "--out", str(results_path)]
        print(f"Running Stage 1: {' '.join(cmd)}")
        if subprocess.run(cmd).returncode != 0:
            print("ERROR: Stage 1 failed.", file=sys.stderr)
            sys.exit(1)

    if not results_path.exists():
        print(f"ERROR: Results CSV not found: {results_path}", file=sys.stderr)
        print("Run scans_to_csv/omr_to_csv.py first, or pass --scans.", file=sys.stderr)
        sys.exit(1)

    questions = read_questions(results_path)

    try:
        if args.key:
            key_path = Path(args.key).resolve()
            if key_path.suffix.lower() == ".json":
                keys = load_key_json(key_path, questions)
            else:
                keys = load_key_csv(key_path, questions)
        elif args.key_string:
            keys = {"*": key_from_list(split_key_string(args.key_string), questions)}
        else:
            keys = prompt_key(questions)
    except (ValueError, OSError) as e:
        print(f"ERROR: Could not load answer key: {e}", file=sys.stderr)
        sys.exit(1)

    roster = None
    if args.roster:
        try:
            roster = load_roster(Path(args.roster).resolve())
        except (ValueError, OSError, KeyError) as e:
            print(f"ERROR: Could not load roster: {e}", file=sys.stderr)
            sys.exit(1)

    marks = {"correct": args.correct, "wrong": args.wrong, "blank": args.blank}
    print(f"Questions: {len(questions)}  Key sets: {', '.join(keys)}  "
          f"Marking: +{fmt(args.correct)} / {fmt(args.wrong)} / {fmt(args.blank)}  Multi: {args.multi}"
          f"{'  Partial credit: on' if args.partial else ''}")

    header, rows = score_results(
        results_path, keys, questions, marks, args.multi, args.per_question, roster, args.partial
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header, quoting=csv.QUOTE_NONNUMERIC)
        w.writeheader()
        w.writerows(rows)

    scored = [r["score"] for r in rows if r["score"] != ""]
    print(f"\nScores written to: {out_path}")
    print(f"  Sheets: {len(rows)}  Scored: {len(scored)}  Not scored: {len(rows) - len(scored)}")
    if scored:
        print(f"  Mean: {sum(scored) / len(scored):.2f}  Max: {max(scored)}  Min: {min(scored)}")
    flagged = sum(1 for r in rows if r["check"])
    if flagged:
        print(f"  Flagged for review: {flagged} (see 'check' column)")


if __name__ == "__main__":
    main()
