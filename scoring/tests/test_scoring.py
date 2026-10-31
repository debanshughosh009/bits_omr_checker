"""
test_scoring.py – Unit test suite for the scoring stage.

Standard library only (unittest, tempfile, urllib, etc.).
Tests:
- Each multi-mark policy on a counted question.
- Blank key entry: excluded from counted and max_score, ignores student answer.
- Missing set key, blank Set, unknown Set, ALL_BLANK, DUPLICATE_ID.
- Fractional marks exact (e.g. 0.25 x 3 == 0.75).
- Row count preserved; leading zeros in ID NO preserved; check passes through.
- Invalid key (multi-letter, bad letter, wrong length) rejected.
- Path traversal in key name rejected; server rejects non-localhost Host header.
- Atomic write leaves the old score.csv backed up and no partial file on failure.
- Synthetic fixture testing using the sample rows provided in the specification.
"""

import csv
import io
import json
import os
import shutil
import tempfile
import unittest
from decimal import Decimal
from http.server import HTTPServer
from pathlib import Path
from threading import Thread

from scoring.scorer import (
    validate_key, parse_scheme, score_row, score_all,
    VALID_MULTI_POLICIES,
)
from scoring.io_utils import (
    read_results, load_key, save_key, key_file_hash,
    write_score, write_run_json, sanitize_key_name,
)
from scoring.app import ScoringHandler


class TestScoring(unittest.TestCase):

    def setUp(self):
        self.q_cols_30 = [f"q{i}" for i in range(1, 31)]
        self.mc, self.mw, self.mu = parse_scheme(4, -1, 0)

    # -----------------------------------------------------------------------
    # 1. Multi-mark policies on a counted question
    # -----------------------------------------------------------------------
    def test_multi_mark_policies(self):
        # 4 questions: q1 key is A, q2-q4 blank
        key = ["A", "", "", ""]
        q_cols = ["q1", "q2", "q3", "q4"]
        mc, mw, mu = Decimal("4"), Decimal("-1"), Decimal("0")

        # Student marked "AB" for q1
        row = {"file_id": "s1.jpg", "Set": "A", "ID NO": "1001",
               "q1": "AB", "q2": "", "q3": "", "q4": "", "check": ""}

        # Policy: zero
        res_zero = score_row(row, key, mc, mw, mu, "zero", q_cols)
        self.assertEqual(res_zero["score"], Decimal("0"))
        self.assertEqual(res_zero["unattempted"], 1)
        self.assertEqual(res_zero["multi"], 1)
        self.assertEqual(res_zero["correct"], 0)
        self.assertEqual(res_zero["wrong"], 0)
        self.assertFalse(res_zero["review"])

        # Policy: wrong
        res_wrong = score_row(row, key, mc, mw, mu, "wrong", q_cols)
        self.assertEqual(res_wrong["score"], Decimal("-1"))
        self.assertEqual(res_wrong["wrong"], 1)
        self.assertEqual(res_wrong["multi"], 1)
        self.assertFalse(res_wrong["review"])

        # Policy: credit_if_contains (key "A" is inside "AB" -> correct)
        res_credit = score_row(row, key, mc, mw, mu, "credit_if_contains", q_cols)
        self.assertEqual(res_credit["score"], Decimal("4"))
        self.assertEqual(res_credit["correct"], 1)
        self.assertEqual(res_credit["multi"], 1)
        self.assertFalse(res_credit["review"])

        # Policy: credit_if_contains when key is "C" (not inside "AB" -> wrong)
        key_c = ["C", "", "", ""]
        res_credit_miss = score_row(row, key_c, mc, mw, mu, "credit_if_contains", q_cols)
        self.assertEqual(res_credit_miss["score"], Decimal("-1"))
        self.assertEqual(res_credit_miss["wrong"], 1)
        self.assertEqual(res_credit_miss["multi"], 1)

        # Policy: hold (0 marks, flags review, still counted in max_score)
        res_hold = score_row(row, key, mc, mw, mu, "hold", q_cols)
        self.assertEqual(res_hold["score"], Decimal("0"))
        self.assertEqual(res_hold["max_score"], Decimal("4"))
        self.assertEqual(res_hold["counted"], 1)
        self.assertEqual(res_hold["multi"], 1)
        self.assertTrue(res_hold["review"])

        # Verify hold triggers REVIEW in score_all
        scored = score_all([row], {"A": key}, mc, mw, mu, "hold", q_cols)
        self.assertIn("REVIEW", scored[0]["score_status"])

    # -----------------------------------------------------------------------
    # 2. Blank key entry (excluded from counted and max_score, ignores answer)
    # -----------------------------------------------------------------------
    def test_blank_key_entry(self):
        # 3 questions: q1 key is "A", q2 key is "" (not counted), q3 key is "B"
        key = ["A", "", "B"]
        q_cols = ["q1", "q2", "q3"]
        mc, mw, mu = Decimal("4"), Decimal("-1"), Decimal("0")

        # Student has marks on q2: "C" (would normally be wrong) or "AB" (multi)
        row = {"file_id": "test.jpg", "Set": "A", "ID NO": "20240001",
               "q1": "A", "q2": "AB", "q3": "", "check": ""}
        res = score_row(row, key, mc, mw, mu, "zero", q_cols)

        # q2 is not counted: contributes 0 marks, not in counted, not in max_score
        # student answer on q2 must be ignored (not correct, wrong, unattempted, or multi)
        self.assertEqual(res["counted"], 2)  # only q1 and q3
        self.assertEqual(res["max_score"], Decimal("8"))  # 2 * 4
        self.assertEqual(res["score"], Decimal("4"))  # q1 correct (4) + q3 unattempted (0)
        self.assertEqual(res["correct"], 1)
        self.assertEqual(res["unattempted"], 1)
        self.assertEqual(res["wrong"], 0)
        self.assertEqual(res["multi"], 0)  # multi on q2 is ignored!
        self.assertEqual(res["q_marks"], [Decimal("4"), "", Decimal("0")])

    # -----------------------------------------------------------------------
    # 3. Sheet-level rules: missing set key, blank Set, unknown Set,
    #    ALL_BLANK, DUPLICATE_ID
    # -----------------------------------------------------------------------
    def test_sheet_level_rules(self):
        q_cols = ["q1", "q2"]
        keys_by_set = {"A": ["A", "B"]}
        mc, mw, mu = Decimal("4"), Decimal("-1"), Decimal("0")

        rows = [
            # Blank Set
            {"file_id": "f1.jpg", "Set": "", "ID NO": "001", "q1": "A", "q2": "B", "check": ""},
            # Missing key for set (Set is "B", key only for "A")
            {"file_id": "f2.jpg", "Set": "B", "ID NO": "002", "q1": "A", "q2": "B", "check": ""},
            # Unknown set (Set is "X", not in A-D)
            {"file_id": "f3.jpg", "Set": "X", "ID NO": "003", "q1": "A", "q2": "B", "check": ""},
            # ALL_BLANK (scored but flagged)
            {"file_id": "f4.jpg", "Set": "A", "ID NO": "004", "q1": "", "q2": "", "check": ""},
            # Duplicate ID: "005" appears on f5 and f6
            {"file_id": "f5.jpg", "Set": "A", "ID NO": "005", "q1": "A", "q2": "B", "check": ""},
            {"file_id": "f6.jpg", "Set": "A", "ID NO": "005", "q1": "A", "q2": "A", "check": ""},
        ]

        scored = score_all(rows, keys_by_set, mc, mw, mu, "zero", q_cols)
        self.assertEqual(len(scored), 6)

        # Row 0: NO_SET -> score columns blank
        self.assertIn("NO_SET", scored[0]["score_status"])
        self.assertEqual(scored[0]["score"], "")
        self.assertEqual(scored[0]["max_score"], "")

        # Row 1: NO_KEY_FOR_SET:B -> score columns blank
        self.assertIn("NO_KEY_FOR_SET:B", scored[1]["score_status"])
        self.assertEqual(scored[1]["score"], "")

        # Row 2: UNKNOWN_SET:X -> score columns blank
        self.assertIn("UNKNOWN_SET:X", scored[2]["score_status"])
        self.assertEqual(scored[2]["score"], "")

        # Row 3: ALL_BLANK -> scored (score 0), flagged ALL_BLANK
        self.assertIn("ALL_BLANK", scored[3]["score_status"])
        self.assertEqual(scored[3]["score"], Decimal("0"))
        self.assertEqual(scored[3]["max_score"], Decimal("8"))
        self.assertEqual(scored[3]["unattempted"], 2)

        # Rows 4 & 5: DUPLICATE_ID:005 -> both flagged
        self.assertIn("DUPLICATE_ID:005", scored[4]["score_status"])
        self.assertIn("DUPLICATE_ID:005", scored[5]["score_status"])
        self.assertEqual(scored[4]["score"], Decimal("8"))
        self.assertEqual(scored[5]["score"], Decimal("3"))  # 4 - 1

    # -----------------------------------------------------------------------
    # 4. Fractional marks exact (Decimal vs float drift)
    # -----------------------------------------------------------------------
    def test_fractional_marks_exact(self):
        mc, mw, mu = parse_scheme("0.25", "-0.25", "0")
        key = ["A", "B", "C"]
        q_cols = ["q1", "q2", "q3"]

        # 3 correct questions: 3 * 0.25 must exactly equal Decimal('0.75')
        row = {"file_id": "f.jpg", "Set": "A", "ID NO": "123",
               "q1": "A", "q2": "B", "q3": "C", "check": ""}
        res = score_row(row, key, mc, mw, mu, "zero", q_cols)
        self.assertEqual(res["score"], Decimal("0.75"))
        self.assertIsInstance(res["score"], Decimal)

        # Fractional penalty: +2 / -0.5 / 0
        mc2, mw2, mu2 = parse_scheme(2, "-0.5", 0)
        # 1 correct, 2 wrong: 2 - 0.5 - 0.5 = 1.0
        row2 = {"file_id": "f2.jpg", "Set": "A", "ID NO": "124",
                "q1": "A", "q2": "C", "q3": "D", "check": ""}
        res2 = score_row(row2, key, mc2, mw2, mu2, "zero", q_cols)
        self.assertEqual(res2["score"], Decimal("1.0"))

    # -----------------------------------------------------------------------
    # 5. Row count, leading zeros, check column, formula safety
    # -----------------------------------------------------------------------
    def test_row_count_and_data_preservation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "results.csv"
            # Write a sample results.csv with leading zeros and formula symbols
            content = (
                '"file_id","Set","ID NO","q1","q2","check"\n'
                '"1_1.jpg","A","0354","A","B","MULTI(q2)"\n'
                '"=cmd|calc.jpg","A","+0099","B","A","ID_LEN(9/13)"\n'
                '"normal.jpg","A","000123","A","A","ALL_BLANK"\n'
            )
            csv_path.write_text(content, encoding="utf-8")

            rows, q_cols, header = read_results(csv_path)
            self.assertEqual(len(rows), 3)
            # Verify leading zeros are preserved as strings
            self.assertEqual(rows[0]["ID NO"], "0354")
            self.assertEqual(rows[1]["ID NO"], "+0099")
            self.assertEqual(rows[2]["ID NO"], "000123")

            keys = {"A": ["A", "B"]}
            mc, mw, mu = parse_scheme(4, -1, 0)
            scored = score_all(rows, keys, mc, mw, mu, "zero", q_cols)
            self.assertEqual(len(scored), 3)

            # Check passes through
            self.assertEqual(scored[0]["check"], "MULTI(q2)")
            self.assertEqual(scored[1]["check"], "ID_LEN(9/13)")

            # Formula safety: file_id starting with = prefixed with '
            self.assertTrue(scored[1]["file_id"].startswith("'="))
            # ID NO starting with + prefixed with '
            self.assertTrue(scored[1]["ID NO"].startswith("'+"))

            # Write to CSV and verify reading it back preserves strings & row count
            out_csv = Path(tmpdir) / "score.csv"
            write_score(out_csv, scored, q_cols)

            with open(out_csv, newline="", encoding="utf-8") as fh:
                reader = list(csv.DictReader(fh))
                self.assertEqual(len(reader), 3)
                self.assertEqual(reader[0]["ID NO"], "0354")
                self.assertEqual(reader[0]["check"], "MULTI(q2)")

    # -----------------------------------------------------------------------
    # 6. Invalid keys rejected
    # -----------------------------------------------------------------------
    def test_invalid_keys_rejected(self):
        # Multi-letter key entry
        with self.assertRaises(ValueError):
            validate_key(["A", "BC", "D"], 3, "ABCD")

        # Bad letter not in options
        with self.assertRaises(ValueError):
            validate_key(["A", "Z", "D"], 3, "ABCD")

        # Wrong length
        with self.assertRaises(ValueError):
            validate_key(["A", "B"], 3, "ABCD")

        # Non-list key
        with self.assertRaises(ValueError):
            validate_key("ABCD", 4, "ABCD")

    # -----------------------------------------------------------------------
    # 7. Path traversal rejected & Server Host header check
    # -----------------------------------------------------------------------
    def test_path_traversal_in_key_name(self):
        for bad in ["../evil", "..\\evil", "foo/bar", "foo\\bar", "a b", "a*b", ""]:
            with self.assertRaises(ValueError):
                sanitize_key_name(bad)

        # Valid names accepted
        self.assertEqual(sanitize_key_name("quiz1"), "quiz1")
        self.assertEqual(sanitize_key_name("midterm_2026-A"), "midterm_2026-A")

    def test_server_host_header_check(self):
        class DummyRequest:
            def __init__(self, host):
                self.headers = {"Host": host}
                self.status = None

            def send_error(self, code, msg=None):
                self.status = code

        handler_local = ScoringHandler.__new__(ScoringHandler)
        handler_local.headers = {"Host": "127.0.0.1:8765"}
        self.assertTrue(handler_local._check_host())

        handler_local_name = ScoringHandler.__new__(ScoringHandler)
        handler_local_name.headers = {"Host": "localhost:8765"}
        self.assertTrue(handler_local_name._check_host())

        handler_evil = ScoringHandler.__new__(ScoringHandler)
        handler_evil.headers = {"Host": "attacker.com:8765"}
        handler_evil.send_error = lambda code, msg=None: setattr(handler_evil, "err", code)
        self.assertFalse(handler_evil._check_host())
        self.assertEqual(handler_evil.err, 403)

    # -----------------------------------------------------------------------
    # 8. Atomic write leaves old score.csv backed up and no partial file
    # -----------------------------------------------------------------------
    def test_atomic_write_and_backup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "score.csv"
            out_path.write_text("old,content\n", encoding="utf-8")

            q_cols = ["q1"]
            scored = [{"file_id": "f.jpg", "Set": "A", "ID NO": "1",
                       "score": Decimal("4"), "max_score": Decimal("4"),
                       "correct": 1, "wrong": 0, "unattempted": 0, "multi": 0,
                       "counted": 1, "score_status": "OK", "check": ""}]

            # First write: backs up existing file
            write_score(out_path, scored, q_cols)
            self.assertTrue(out_path.exists())

            # Verify backup file exists
            bak_files = list(Path(tmpdir).glob("score_*.csv.bak"))
            self.assertEqual(len(bak_files), 1)
            self.assertEqual(bak_files[0].read_text(encoding="utf-8"), "old,content\n")

            # Simulate failure during write:
            # Pass a row whose .get() raises inside DictWriter.writerow
            class FailRow(dict):
                def get(self, k, default=None):
                    raise RuntimeError("Simulated write failure")

            with self.assertRaises(RuntimeError):
                write_score(out_path, [FailRow()], q_cols)

            # Verify no partial .csv.tmp file remains
            tmp_files = list(Path(tmpdir).glob("*.csv.tmp"))
            self.assertEqual(len(tmp_files), 0)

    # -----------------------------------------------------------------------
    # 9. Synthetic fixture testing with sample rows from specification
    # -----------------------------------------------------------------------
    def test_fixture_scoring(self):
        """
        Use sample rows from spec:
          "1_19.JPG","A","20240513H","A","C","B","A","D","B","","",...
          "1793440228504_1_24.JPG","A","20240507H","A","C","D","A","A","B","","",...
        """
        header = ["file_id", "Set", "ID NO"] + [f"q{i}" for i in range(1, 31)] + ["check"]
        row1 = ["1_19.JPG", "A", "20240513H", "A", "C", "B", "A", "D", "B"] + [""] * 24 + [""]
        row2 = ["1793440228504_1_24.JPG", "A", "20240507H", "A", "C", "D", "A", "A", "B"] + [""] * 24 + [""]

        dict_rows = [dict(zip(header, row1)), dict(zip(header, row2))]
        q_cols = [f"q{i}" for i in range(1, 31)]

        # Key for Set A: q1-q6 is A, C, B, A, D, B; q7-q30 not counted ("")
        key_a = ["A", "C", "B", "A", "D", "B"] + [""] * 24
        mc, mw, mu = parse_scheme(4, -1, 0)

        scored = score_all(dict_rows, {"A": key_a}, mc, mw, mu, "zero", q_cols)

        # Row 1: All 6 counted questions match key exactly!
        # Score = 6 * 4 = 24, max_score = 24, counted = 6, correct = 6
        self.assertEqual(scored[0]["score"], Decimal("24"))
        self.assertEqual(scored[0]["max_score"], Decimal("24"))
        self.assertEqual(scored[0]["correct"], 6)
        self.assertEqual(scored[0]["wrong"], 0)
        self.assertEqual(scored[0]["counted"], 6)
        self.assertEqual(scored[0]["score_status"], "OK")

        # Row 2: q1=A(✓), q2=C(✓), q3=D(wrong, key B), q4=A(✓), q5=A(wrong, key D), q6=B(✓)
        # 4 correct, 2 wrong. Score = 4*4 - 2*1 = 14.
        self.assertEqual(scored[1]["score"], Decimal("14"))
        self.assertEqual(scored[1]["max_score"], Decimal("24"))
        self.assertEqual(scored[1]["correct"], 4)
        self.assertEqual(scored[1]["wrong"], 2)
        self.assertEqual(scored[1]["counted"], 6)
        self.assertEqual(scored[1]["score_status"], "OK")


if __name__ == "__main__":
    unittest.main()
