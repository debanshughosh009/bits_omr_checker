"""
io_utils.py – File I/O for the scoring stage.

Reads results.csv, loads/saves answer-key JSON, and writes score.csv
with atomic replacement (temp-file + os.replace).
"""

import csv
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import scorer

# ---------------------------------------------------------------------------
# results.csv reader
# ---------------------------------------------------------------------------
Q_COL_RE = re.compile(r"^q(\d+)$")


def read_results(path):
    """Read output/results.csv and return (rows, q_columns, header).

    Parameters
    ----------
    path : str | Path
        Path to results.csv.

    Returns
    -------
    rows : list[dict]
        Every row as a dict mapping column name to string value.
    q_columns : list[str]
        Sorted question column names, e.g. ["q1", "q2", …, "q30"].
    header : list[str]
        The original header field names.
    """
    path = Path(path)
    # Tolerate UTF-8 BOM, read all fields as strings (preserving leading zeros)
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        header = list(reader.fieldnames) if reader.fieldnames else []
        rows = list(reader)

    q_columns = sorted(
        [h for h in header if Q_COL_RE.match(h)],
        key=lambda c: int(Q_COL_RE.match(c).group(1)),
    )
    return rows, q_columns, header


# ---------------------------------------------------------------------------
# Answer-key JSON
# ---------------------------------------------------------------------------
KEY_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def sanitize_key_name(name):
    """Validate and return a safe key file name (no extension).

    Raises ValueError on path traversal or invalid characters.
    """
    name = str(name).strip()
    if not name:
        raise ValueError("Key name must not be empty.")
    if ".." in name or "/" in name or "\\" in name:
        raise ValueError(f"Key name '{name}' looks like a path traversal.")
    if not KEY_NAME_RE.match(name):
        raise ValueError(
            f"Key name '{name}' contains invalid characters. "
            "Only A-Z, a-z, 0-9, _ and - are allowed."
        )
    return name


def load_key(path):
    """Load an answer-key JSON file and return the parsed dict.

    Returns
    -------
    dict with keys: version, questions, options, sets
    """
    path = Path(path)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    _validate_key_data(data)
    return data


def save_key(path, data):
    """Save an answer-key dict to a JSON file."""
    _validate_key_data(data)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def _validate_key_data(data):
    """Validate the structure of a key dict."""
    if not isinstance(data, dict):
        raise ValueError("Key data must be a JSON object.")
    if data.get("version") != 1:
        raise ValueError("Unsupported key version (expected 1).")
    questions = data.get("questions")
    if not isinstance(questions, int) or questions < 1:
        raise ValueError("'questions' must be a positive integer.")
    options = data.get("options", "ABCD")
    if not isinstance(options, str) or len(options) < 2:
        raise ValueError("'options' must be a string of at least 2 letters.")
    sets = data.get("sets")
    if not isinstance(sets, dict):
        raise ValueError("'sets' must be an object mapping set letters to key lists.")
    for set_letter, key_list in sets.items():
        scorer.validate_key(key_list, questions, options)


def key_file_hash(path):
    """Return the SHA-256 hex digest of a key file."""
    path = Path(path)
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# score.csv writer (atomic)
# ---------------------------------------------------------------------------
def write_score(out_path, scored_rows, q_columns, per_question=False):
    """Write score.csv atomically.

    If out_path already exists it is backed up to
    ``score_<timestamp>.csv.bak`` in the same directory.
    If an error occurs during write, the backup is kept and any
    partial file is cleaned up.

    Parameters
    ----------
    out_path : str | Path
    scored_rows : list[dict]
        Output of scorer.score_all.
    q_columns : list[str]
    per_question : bool
    """
    out_path = Path(out_path)
    out_dir = out_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # Back up existing file
    if out_path.exists():
        base_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        bak = out_dir / f"score_{base_ts}.csv.bak"
        idx = 1
        while bak.exists():
            bak = out_dir / f"score_{base_ts}_{idx}.csv.bak"
            idx += 1
        os.replace(str(out_path), str(bak))

    fieldnames = [
        "file_id", "Set", "ID NO",
        "score", "max_score", "correct", "wrong", "unattempted",
        "multi", "counted", "score_status", "check",
    ]
    if per_question:
        for qcol in q_columns:
            fieldnames.append(f"{qcol}_mark")

    # Atomic write via temp file in the destination folder
    fd, tmp_path = tempfile.mkstemp(
        suffix=".csv.tmp", dir=str(out_dir)
    )
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=fieldnames,
                quoting=csv.QUOTE_NONNUMERIC,
                extrasaction="ignore",
            )
            writer.writeheader()
            for row in scored_rows:
                writer.writerow(row)
        os.replace(tmp_path, str(out_path))
    except BaseException:
        # Clean up partial temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return str(out_path)


# ---------------------------------------------------------------------------
# Run sidecar JSON
# ---------------------------------------------------------------------------
def write_run_json(out_path, scheme, multi_policy, key_file, key_hash,
                   result_row_count, per_question=False):
    """Write score_run.json alongside score.csv."""
    out_path = Path(out_path)
    run_path = out_path.parent / "score_run.json"
    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "marking_scheme": {
            "marks_correct": str(scheme[0]),
            "marks_wrong": str(scheme[1]),
            "marks_unattempted": str(scheme[2]),
        },
        "multi_mark_policy": multi_policy,
        "key_file": str(key_file),
        "key_file_sha256": key_hash,
        "results_csv_row_count": result_row_count,
        "per_question_marks": per_question,
    }
    with open(run_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    return str(run_path)
