"""
test_cli_and_app.py – Tests for cli.py and app.py HTTP endpoints.
"""

import json
import subprocess
import sys
import tempfile
import unittest
import urllib.request
import urllib.error
from decimal import Decimal
from pathlib import Path
from threading import Thread
from http.server import HTTPServer

from scoring.app import ScoringHandler


class TestCliAndApp(unittest.TestCase):

    def test_cli_end_to_end(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            res_path = tdp / "results.csv"
            with open(res_path, "w", encoding="utf-8") as f:
                f.write(
                    '"file_id","Set","ID NO","q1","q2","check"\n'
                    '"1.jpg","A","20240001","A","B",""\n'
                    '"2.jpg","A","20240002","C","B",""\n'
                )

            key_path = tdp / "key.json"
            with open(key_path, "w", encoding="utf-8") as f:
                json.dump({
                    "version": 1,
                    "questions": 2,
                    "options": "ABCD",
                    "sets": {"A": ["A", "B"]}
                }, f)

            out_path = tdp / "score.csv"
            cmd = [
                sys.executable, "scoring/cli.py",
                "--results", str(res_path),
                "--keys", str(key_path),
                "--out", str(out_path),
                "--scheme", "4,-1,0",
                "--multi", "zero",
                "--per-question"
            ]
            p = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, f"CLI failed: {p.stderr}")
            self.assertTrue(out_path.exists())
            self.assertTrue((tdp / "score_run.json").exists())

            content = out_path.read_text(encoding="utf-8")
            self.assertIn('"file_id","Set","ID NO"', content)
            self.assertIn('"1.jpg","A","20240001",8,8,2,0,0,0,2,"OK",""', content)
            self.assertIn('"2.jpg","A","20240002",3,8,1,1,0,0,2,"OK",""', content)

    def test_app_server_endpoints(self):
        # Start server on a free port on 127.0.0.1
        server = HTTPServer(("127.0.0.1", 0), ScoringHandler)
        port = server.server_address[1]
        t = Thread(target=server.serve_forever, daemon=True)
        t.start()

        base_url = f"http://127.0.0.1:{port}"

        try:
            # 1. GET / (index.html)
            req = urllib.request.Request(f"{base_url}/")
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                html = resp.read().decode("utf-8")
                self.assertIn("<title>OMR Scoring</title>", html)

            # 2. GET /api/summary
            req = urllib.request.Request(f"{base_url}/api/summary")
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                summary_data = json.loads(resp.read().decode("utf-8"))
                self.assertIn("row_count", summary_data)
                self.assertIn("questions", summary_data)
                self.assertIn("sets", summary_data)

            # 3. GET /api/keys/list
            req = urllib.request.Request(f"{base_url}/api/keys/list")
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                keys_data = json.loads(resp.read().decode("utf-8"))
                self.assertIn("keys", keys_data)

            # 4. Non-localhost host header rejected with 403
            req = urllib.request.Request(f"{base_url}/api/summary", headers={"Host": "evil.com"})
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req)
            self.assertEqual(ctx.exception.code, 403)

            # 5. POST /api/preview
            num_q = summary_data["questions"]
            payload = {
                "scheme": {"correct": "4", "wrong": "-1", "unattempted": "0"},
                "multi_policy": "zero",
                "options": "ABCD",
                "per_question": False,
                "keys": {
                    "A": ["A"] * num_q,
                    "B": ["B"] * num_q
                }
            }
            req = urllib.request.Request(
                f"{base_url}/api/preview",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                prev = json.loads(resp.read().decode("utf-8"))
                self.assertIn("preview", prev)
                self.assertIn("summary", prev)
                self.assertEqual(len(prev["preview"]), min(20, summary_data["row_count"]))
                self.assertIn("preview", prev)
                self.assertIn("summary", prev)
                self.assertEqual(len(prev["preview"]), min(20, summary_data["row_count"]))

        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
