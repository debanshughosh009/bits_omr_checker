"""
scorer.py – Pure scoring functions (no I/O).

All mark arithmetic uses decimal.Decimal so fractional schemes
(e.g. +2 / -0.5 / 0) never accumulate floating-point drift.
"""

import re
from decimal import Decimal, InvalidOperation

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VALID_MULTI_POLICIES = ("zero", "wrong", "credit_if_contains", "hold")
STANDARD_SETS = {"A", "B", "C", "D"}
Q_COL_RE = re.compile(r"^q(\d+)$")


# ---------------------------------------------------------------------------
# Key validation
# ---------------------------------------------------------------------------
def validate_key(key_list, num_questions, options="ABCD"):
    """Validate an answer-key list.

    Parameters
    ----------
    key_list : list[str]
        One entry per question. Each entry is a single option letter
        or "" (blank = not counted).
    num_questions : int
        Expected length (must match the CSV header).
    options : str
        Allowed option letters, e.g. "ABCD" or "ABCDE".

    Returns
    -------
    list[str]
        The validated key.

    Raises
    ------
    ValueError
        On any validation failure.
    """
    if not isinstance(key_list, list):
        raise ValueError("Key must be a list.")
    if len(key_list) != num_questions:
        raise ValueError(
            f"Key length {len(key_list)} does not match "
            f"question count {num_questions}."
        )
    option_set = set(options.upper())
    for i, entry in enumerate(key_list):
        if not isinstance(entry, str):
            raise ValueError(f"Key entry q{i+1} is not a string.")
        if entry == "":
            continue  # blank = not counted
        if len(entry) != 1:
            raise ValueError(
                f"Key entry q{i+1} must be exactly one letter or blank, "
                f"got '{entry}'."
            )
        if entry.upper() not in option_set:
            raise ValueError(
                f"Key entry q{i+1} '{entry}' is not in options '{options}'."
            )
    return key_list


# ---------------------------------------------------------------------------
# Marking-scheme helpers
# ---------------------------------------------------------------------------
def parse_scheme(marks_correct, marks_wrong, marks_unattempted=0):
    """Convert scheme values to Decimal, raising on bad input."""
    try:
        mc = Decimal(str(marks_correct))
        mw = Decimal(str(marks_wrong))
        mu = Decimal(str(marks_unattempted))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid marking-scheme value: {exc}") from exc
    return mc, mw, mu


# ---------------------------------------------------------------------------
# Single-row scoring
# ---------------------------------------------------------------------------
def score_row(row, key_list, marks_correct, marks_wrong, marks_unattempted,
              multi_policy, q_columns, options="ABCD"):
    """Score one student row.

    Parameters
    ----------
    row : dict
        A row from csv.DictReader (all values are strings).
    key_list : list[str]
        Validated answer key for the student's Set.
    marks_correct, marks_wrong, marks_unattempted : Decimal
        Scheme values.
    multi_policy : str
        One of VALID_MULTI_POLICIES.
    q_columns : list[str]
        Ordered question column names, e.g. ["q1", "q2", …].
    options : str
        Allowed option letters.

    Returns
    -------
    dict with keys:
        score       : Decimal
        max_score   : Decimal
        correct     : int
        wrong       : int
        unattempted : int
        multi       : int
        counted     : int
        review      : bool   (True if any question triggered "hold")
        q_marks     : list[Decimal | str]  per-question marks (empty string
                      for non-counted questions)
    """
    if multi_policy not in VALID_MULTI_POLICIES:
        raise ValueError(f"Unknown multi_policy '{multi_policy}'.")

    option_set = set(options.upper())
    score = Decimal("0")
    correct = 0
    wrong = 0
    unattempted = 0
    multi = 0
    counted = 0
    review = False
    q_marks = []

    for idx, qcol in enumerate(q_columns):
        key_ans = key_list[idx].upper() if key_list[idx] else ""
        student_ans = row.get(qcol, "").strip().upper()

        # Not counted: blank key entry
        if key_ans == "":
            q_marks.append("")
            continue

        counted += 1
        is_multi = len(student_ans) > 1 and all(c in option_set for c in student_ans)
        is_blank = student_ans == ""
        is_single = len(student_ans) == 1 and student_ans in option_set

        if is_blank:
            unattempted += 1
            score += marks_unattempted
            q_marks.append(marks_unattempted)
        elif is_single:
            if student_ans == key_ans:
                correct += 1
                score += marks_correct
                q_marks.append(marks_correct)
            else:
                wrong += 1
                score += marks_wrong
                q_marks.append(marks_wrong)
        elif is_multi:
            multi += 1
            if multi_policy == "zero":
                unattempted += 1
                score += marks_unattempted
                q_marks.append(marks_unattempted)
            elif multi_policy == "wrong":
                wrong += 1
                score += marks_wrong
                q_marks.append(marks_wrong)
            elif multi_policy == "credit_if_contains":
                if key_ans in student_ans:
                    correct += 1
                    score += marks_correct
                    q_marks.append(marks_correct)
                else:
                    wrong += 1
                    score += marks_wrong
                    q_marks.append(marks_wrong)
            elif multi_policy == "hold":
                # 0 marks, flag for review; still counted in max_score
                q_marks.append(Decimal("0"))
                review = True
        else:
            # Unrecognised cell content (e.g. stray characters): treat as
            # unattempted and rely on the existing check column for flagging.
            unattempted += 1
            score += marks_unattempted
            q_marks.append(marks_unattempted)

    max_score = counted * marks_correct

    return {
        "score": score,
        "max_score": max_score,
        "correct": correct,
        "wrong": wrong,
        "unattempted": unattempted,
        "multi": multi,
        "counted": counted,
        "review": review,
        "q_marks": q_marks,
    }


# ---------------------------------------------------------------------------
# Batch scoring
# ---------------------------------------------------------------------------
def score_all(rows, keys_by_set, marks_correct, marks_wrong,
              marks_unattempted, multi_policy, q_columns, options="ABCD",
              per_question=False):
    """Score every row, returning enriched dicts ready for CSV output.

    Parameters
    ----------
    rows : list[dict]
        All rows from results.csv.
    keys_by_set : dict[str, list[str]]
        Validated answer keys keyed by Set letter (e.g. {"A": [...], …}).
    marks_correct, marks_wrong, marks_unattempted : Decimal
        Scheme values.
    multi_policy : str
        One of VALID_MULTI_POLICIES.
    q_columns : list[str]
        Ordered question column names.
    options : str
        Allowed option letters.
    per_question : bool
        If True, include q1_mark..qN_mark columns in output.

    Returns
    -------
    list[dict]
        One dict per input row, in order. Keys include the output
        columns described in the spec.
    """
    mc, mw, mu = (Decimal(str(v)) for v in (marks_correct, marks_wrong,
                                             marks_unattempted))

    # Pre-compute duplicate IDs for non-empty ID NO
    id_counts = {}
    for r in rows:
        sid = r.get("ID NO", "").strip()
        if sid:
            id_counts[sid] = id_counts.get(sid, 0) + 1
    duplicate_ids = {sid for sid, count in id_counts.items() if count > 1}

    results = []
    for row in rows:
        set_val = row.get("Set", "").strip().upper()
        file_id = row.get("file_id", "")
        id_no = row.get("ID NO", "").strip()
        check = row.get("check", "")

        statuses = []
        can_score = True

        if set_val == "":
            statuses.append("NO_SET")
            can_score = False
        elif set_val not in keys_by_set:
            can_score = False
            if set_val in STANDARD_SETS:
                statuses.append(f"NO_KEY_FOR_SET:{set_val}")
            else:
                statuses.append(f"UNKNOWN_SET:{set_val}")

        # Check ALL_BLANK (all q columns empty)
        all_blank = all(row.get(qc, "").strip() == "" for qc in q_columns)
        if all_blank:
            statuses.append("ALL_BLANK")

        # Check duplicate ID (same non-empty ID NO appears on more than one row)
        if id_no and id_no in duplicate_ids:
            statuses.append(f"DUPLICATE_ID:{id_no}")

        out = {}
        out["file_id"] = _sanitize_text(file_id)
        out["Set"] = _sanitize_text(set_val)
        out["ID NO"] = _sanitize_text(id_no)

        if can_score:
            key_list = keys_by_set[set_val]
            res = score_row(row, key_list, mc, mw, mu, multi_policy,
                            q_columns, options)
            out["score"] = res["score"]
            out["max_score"] = res["max_score"]
            out["correct"] = res["correct"]
            out["wrong"] = res["wrong"]
            out["unattempted"] = res["unattempted"]
            out["multi"] = res["multi"]
            out["counted"] = res["counted"]

            if res["review"]:
                statuses.append("REVIEW")

            if not statuses:
                statuses.append("OK")
            out["score_status"] = "; ".join(statuses)
            out["check"] = check

            if per_question:
                for idx, qcol in enumerate(q_columns):
                    out[f"{qcol}_mark"] = res["q_marks"][idx]
        else:
            out["score"] = ""
            out["max_score"] = ""
            out["correct"] = ""
            out["wrong"] = ""
            out["unattempted"] = ""
            out["multi"] = ""
            out["counted"] = ""
            if not statuses:
                statuses.append("OK")
            out["score_status"] = "; ".join(statuses)
            out["check"] = check

            if per_question:
                for qcol in q_columns:
                    out[f"{qcol}_mark"] = ""

        results.append(out)

    return results


def _sanitize_text(value):
    """Prefix a text value with a single quote if it starts with a
    spreadsheet formula character (= + - @), to prevent Excel injection."""
    if isinstance(value, str) and value and value[0] in "=+-@":
        return "'" + value
    return value
