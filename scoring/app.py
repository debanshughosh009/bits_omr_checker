#!/usr/bin/env python3
"""
app.py – Local web UI for the scoring stage.

Serves static/index.html and JSON API endpoints on 127.0.0.1.
Opens the default browser automatically.

Usage:
    python scoring/app.py [--port 8765]
"""

import argparse
import json
import os
import socket
import sys
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from decimal import Decimal

# Allow running as ``python scoring/app.py`` from the repo root.
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scoring.scorer import (
    validate_key, parse_scheme, score_all, VALID_MULTI_POLICIES,
)
from scoring.io_utils import (
    read_results, load_key, save_key, key_file_hash,
    write_score, write_run_json, sanitize_key_name,
)

_SCORING_DIR = Path(__file__).resolve().parent
_KEYS_DIR = _SCORING_DIR / "keys"
_STATIC_DIR = _SCORING_DIR / "static"


def _repo_root():
    return _SCORING_DIR.parent


def _results_path():
    return _repo_root() / "output" / "results.csv"


def _score_path():
    return _repo_root() / "output" / "score.csv"


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------
class ScoringHandler(BaseHTTPRequestHandler):
    """HTTP handler for the scoring UI."""

    def _check_host(self):
        """Reject requests whose Host is not localhost."""
        host = self.headers.get("Host", "")
        # Strip port
        hostname = host.split(":")[0]
        if hostname not in ("127.0.0.1", "localhost"):
            self.send_error(403, "Forbidden: non-localhost host header")
            return False
        return True

    def _send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_bytes, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html_bytes)))
        self.end_headers()
        self.wfile.write(html_bytes)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length)

    # -- GET ----------------------------------------------------------------
    def do_GET(self):
        if not self._check_host():
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path in ("/", "/index.html"):
            html_path = _STATIC_DIR / "index.html"
            if not html_path.exists():
                self.send_error(404, "index.html not found")
                return
            self._send_html(html_path.read_bytes())
            return

        if path == "/api/summary":
            self._handle_summary()
            return

        if path == "/api/keys/list":
            self._handle_keys_list()
            return

        if path == "/api/keys/load":
            qs = parse_qs(parsed.query)
            name = qs.get("name", [""])[0]
            self._handle_key_load(name)
            return

        self.send_error(404)

    # -- POST ---------------------------------------------------------------
    def do_POST(self):
        if not self._check_host():
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/keys/save":
            self._handle_key_save()
            return

        if path == "/api/preview":
            self._handle_preview()
            return

        if path == "/api/score":
            self._handle_score()
            return

        self.send_error(404)

    # -- API implementations ------------------------------------------------
    def _handle_summary(self):
        rp = _results_path()
        if not rp.exists():
            self._send_json({"error": f"results.csv not found at {rp}"}, 404)
            return
        try:
            rows, q_columns, header = read_results(rp)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)
            return

        set_counts = {}
        flagged = 0
        for r in rows:
            s = r.get("Set", "").strip().upper()
            set_counts[s] = set_counts.get(s, 0) + 1
            if r.get("check", "").strip():
                flagged += 1

        self._send_json({
            "row_count": len(rows),
            "questions": len(q_columns),
            "q_columns": q_columns,
            "sets": set_counts,
            "flagged": flagged,
            "path": str(rp),
        })

    def _handle_keys_list(self):
        _KEYS_DIR.mkdir(parents=True, exist_ok=True)
        files = sorted(
            p.stem for p in _KEYS_DIR.glob("*.json")
            if p.stem != ".gitkeep"
        )
        self._send_json({"keys": files})

    def _handle_key_load(self, name):
        try:
            name = sanitize_key_name(name)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        fp = _KEYS_DIR / f"{name}.json"
        if not fp.exists():
            self._send_json({"error": f"Key '{name}' not found."}, 404)
            return
        try:
            data = load_key(fp)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        self._send_json(data)

    def _handle_key_save(self):
        try:
            body = json.loads(self._read_body())
        except Exception:
            self._send_json({"error": "Invalid JSON body."}, 400)
            return
        name = body.get("name", "")
        try:
            name = sanitize_key_name(name)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        key_data = body.get("data")
        if not key_data:
            self._send_json({"error": "Missing 'data' field."}, 400)
            return
        try:
            fp = _KEYS_DIR / f"{name}.json"
            save_key(fp, key_data)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        self._send_json({"ok": True, "path": str(fp)})

    def _handle_preview(self):
        """Score and return the first 20 rows plus summary stats."""
        try:
            body = json.loads(self._read_body())
        except Exception:
            self._send_json({"error": "Invalid JSON body."}, 400)
            return
        try:
            result = self._do_scoring(body, preview=True)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        self._send_json(result)

    def _handle_score(self):
        """Score all rows and write score.csv."""
        try:
            body = json.loads(self._read_body())
        except Exception:
            self._send_json({"error": "Invalid JSON body."}, 400)
            return
        try:
            result = self._do_scoring(body, preview=False)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        self._send_json(result)

    def _do_scoring(self, body, preview=False):
        """Common scoring logic for preview and write."""
        rp = _results_path()
        rows, q_columns, header = read_results(rp)
        num_q = len(q_columns)

        # Parse scheme
        scheme = body.get("scheme", {})
        mc, mw, mu = parse_scheme(
            scheme.get("correct", "4"),
            scheme.get("wrong", "-1"),
            scheme.get("unattempted", "0"),
        )

        multi = body.get("multi_policy", "zero")
        if multi not in VALID_MULTI_POLICIES:
            raise ValueError(f"Invalid multi-mark policy: {multi}")

        options = body.get("options", "ABCD")
        per_question = body.get("per_question", False)

        # Build keys_by_set from body
        sets_data = body.get("keys", {})
        keys_by_set = {}
        for s, kl in sets_data.items():
            validate_key(kl, num_q, options)
            keys_by_set[s.upper()] = kl

        scored = score_all(
            rows, keys_by_set, mc, mw, mu, multi, q_columns,
            options=options, per_question=per_question,
        )

        if preview:
            # Summary stats
            scores_numeric = []
            flagged_count = 0
            for r in scored:
                if r["score"] != "":
                    scores_numeric.append(Decimal(r["score"]))
                status = r.get("score_status", "")
                if status and status != "OK":
                    flagged_count += 1

            summary = {
                "total": len(scored),
                "scored": len(scores_numeric),
                "flagged": flagged_count,
            }
            if scores_numeric:
                summary["mean"] = str(
                    sum(scores_numeric) / len(scores_numeric)
                )
                summary["min"] = str(min(scores_numeric))
                summary["max"] = str(max(scores_numeric))

            return {
                "preview": scored[:20],
                "summary": summary,
            }
        else:
            # Write to disk
            out = _score_path()
            written = write_score(out, scored, q_columns,
                                  per_question=per_question)

            # Write run sidecar
            key_name = body.get("key_name", "ui_session")
            try:
                safe_name = sanitize_key_name(key_name)
            except ValueError:
                safe_name = "ui_session"
            # Save the key used to keys/ for auditability
            key_file_path = _KEYS_DIR / f"{safe_name}.json"
            key_data_for_save = {
                "version": 1,
                "questions": num_q,
                "options": options,
                "sets": sets_data,
            }
            save_key(key_file_path, key_data_for_save)
            kh = key_file_hash(key_file_path)

            run_json = write_run_json(
                out, (mc, mw, mu), multi, str(key_file_path), kh,
                len(rows), per_question=per_question,
            )
            return {
                "ok": True,
                "rows_written": len(scored),
                "path": written,
                "run_json": run_json,
            }

    def log_message(self, format, *args):
        """Quieter logging."""
        sys.stderr.write(f"[scoring] {args[0]}\n")


# ---------------------------------------------------------------------------
# Server startup
# ---------------------------------------------------------------------------
def _find_port(preferred):
    """Return *preferred* if available, else find a free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description="Scoring UI server")
    parser.add_argument("--port", type=int, default=8765,
                        help="Port (default 8765)")
    parser.add_argument("--no-browser", action="store_true",
                        help="Do not open the browser automatically.")
    args = parser.parse_args()

    port = _find_port(args.port)
    server = HTTPServer(("127.0.0.1", port), ScoringHandler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Scoring UI running at {url}")
    print("Press Ctrl+C to stop.\n")

    if not args.no_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()

