"""
server.py - OMR Checker: dashboard, designer and evaluator in one browser window
===================================================================================
Serves the built web app (web/dist) on http://127.0.0.1:8765 and keeps exams,
answer keys and read sheets in data/omr.db (SQLite), with each exam's scans and
overlay images under data/exams/<id>/. Nothing leaves this machine.

Reading a batch runs scans_to_csv/omr_to_csv.py unchanged. Scoring happens in the
browser (web/src/lib/score.js) so rule changes rescore instantly.

    python app/server.py          # or double-click "Start OMR" in the repo root

The first run creates .venv/ and installs scans_to_csv's requirements into it.

Packaged by PyInstaller (packaging/), it runs as a menu bar / tray app instead:
the app's files are read from the bundle, data lives in the user's app-data
folder, and the reader runs as this same executable with --reader.
"""

import csv
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import urlopen

__version__ = "1.0.0"  # the release version; packaging/ and the release workflow read it from here


def user_data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "OMR Checker"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "OMR Checker"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "omr-checker"


FROZEN = getattr(sys, "frozen", False)  # running from the packaged app
ROOT = Path(__file__).resolve().parent.parent
RES = Path(getattr(sys, "_MEIPASS", ROOT))  # the app's own read-only files: the repo, or the bundle
VENV = ROOT / ".venv"
DATA = user_data_dir() if FROZEN else ROOT / "data"
STAGE = RES / "scans_to_csv"
REQUIREMENTS = STAGE / "requirements.txt"
PORT = 8765  # fixed so the designer's saved draft (browser storage is per address) is found again
if "--port" in sys.argv:  # for testing a second copy beside a running one
    PORT = int(sys.argv[sys.argv.index("--port") + 1])
URL = f"http://127.0.0.1:{PORT}/"
WEB = RES / "web" / "dist"  # built by `npm run build` in web/, committed so only Python is needed
SCAN_EXTS = {".png", ".jpg", ".jpeg", ".pdf"}


# ---------- first run: a private virtualenv with the reader's dependencies ----------

def bootstrap():
    """Re-run this script inside .venv, creating it and installing requirements when needed."""
    if FROZEN:  # the packaged app carries its own Python and packages
        return
    if sys.version_info < (3, 10):
        sys.exit(f"Python 3.10 or newer is needed (this is {sys.version.split()[0]}). Install it from python.org.")
    py = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if Path(sys.prefix).resolve() == VENV.resolve():
        return
    stamp = VENV / ".installed"
    want = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    if not py.exists() or not stamp.exists() or stamp.read_text() != want:
        print("First run: setting up Python packages in .venv (a few minutes, once)...", flush=True)
        if not py.exists():
            subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
        subprocess.run([str(py), "-m", "pip", "install", "-q", "--disable-pip-version-check",
                        "-r", str(REQUIREMENTS), "opencv-contrib-python"], check=True)
        stamp.write_text(want)
    sys.exit(subprocess.call([str(py), __file__, *sys.argv[1:]]))


# ---------- the web app: rebuilt when its source is newer than the build ----------

def build_web():
    """Run `npm run build` in web/ when the source changed since web/dist was built.
    Without npm the committed build is served as it is."""
    if FROZEN:
        return
    src = ROOT / "web"
    built = WEB / "index.html"
    sources = [src / "index.html", src / "package.json", src / "vite.config.js", *(src / "src").rglob("*")]
    newest = max(f.stat().st_mtime for f in sources if f.is_file())
    if built.exists() and newest <= built.stat().st_mtime:
        return
    npm = shutil.which("npm")
    if not npm:
        if not built.exists():
            sys.exit("The web app is not built and npm is missing: install Node.js 18+, then start again.")
        print("web/src changed but npm is missing, so the existing build is served.", flush=True)
        return
    print("Building the web app (it changed since the last build)...", flush=True)
    if not (src / "node_modules").exists():
        subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=src, check=True)
    if subprocess.run([npm, "run", "build"], cwd=src).returncode:
        if not built.exists():
            sys.exit("Building the web app failed; see the errors above.")
        print("Building the web app failed; serving the previous build.", flush=True)


# ---------- storage ----------

SCHEMA = """
CREATE TABLE IF NOT EXISTS exams (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  created TEXT NOT NULL,
  template TEXT NOT NULL,              -- template.json the sheets were printed from
  keys TEXT NOT NULL DEFAULT '{}',     -- {"A": "B C AC ...", ...}, one answer key per set
  rules TEXT NOT NULL DEFAULT '{}',    -- marking scheme, see web/src/lib/score.js
  design TEXT                          -- the designer's form for this sheet; NULL when a template.json was imported
);
CREATE TABLE IF NOT EXISTS sheets (
  id INTEGER PRIMARY KEY,
  exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
  file TEXT NOT NULL,                  -- file_id from the reader; also the overlay's name
  data TEXT NOT NULL,                  -- the CSV row: Set, ID NO, q1.., check
  edited INTEGER NOT NULL DEFAULT 0,   -- 1 once someone corrected the read by hand
  UNIQUE (exam_id, file)
);
"""


def db():
    con = sqlite3.connect(DATA / "omr.db")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def exam_dir(exam_id: int) -> Path:
    return DATA / "exams" / str(exam_id)


def exam_json(con, exam_id: int):
    e = con.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    if not e:
        return None
    sheets = con.execute("SELECT id, file, data, edited FROM sheets WHERE exam_id = ? ORDER BY file", (exam_id,))
    overlays, incoming = exam_dir(exam_id) / "overlays", exam_dir(exam_id) / "incoming"
    return {
        "id": e["id"], "name": e["name"], "created": e["created"],
        "waiting": sum(1 for f in incoming.glob("*") if f.suffix.lower() in SCAN_EXTS) if incoming.exists() else 0,
        "template": json.loads(e["template"]), "keys": json.loads(e["keys"]), "rules": json.loads(e["rules"]),
        "design": json.loads(e["design"]) if e["design"] else None,
        "sheets": [{
            "id": s["id"], "file": s["file"], "data": json.loads(s["data"]), "edited": bool(s["edited"]),
            "overlay": f"/data/exams/{exam_id}/overlays/{s['file']}" if (overlays / s["file"]).exists() else None,
        } for s in sheets],
    }


def write_sheet_files(exam_id: int, template: dict, design):
    """Keep the sheet's template.json (and the designer form, design.json) beside its scans."""
    d = exam_dir(exam_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "template.json").write_text(json.dumps(template, indent=2))
    if design is not None:
        (d / "design.json").write_text(json.dumps(design, indent=2))


def is_template(tpl) -> bool:
    return isinstance(tpl, dict) and all(k in tpl for k in ("pageDimensions", "fieldBlocks", "outputColumns"))


# ---------- reading scans with scans_to_csv ----------

read_lock = threading.Lock()  # ponytail: one batch at a time across exams; per-exam locks if several people share a machine


def read_scans(exam_id: int, template: dict):
    """Run omr_to_csv.py over the exam's uploaded scans and store a row per sheet."""
    d = exam_dir(exam_id)
    incoming, scans = d / "incoming", d / "scans"
    files = [f for f in incoming.glob("*") if f.suffix.lower() in SCAN_EXTS] if incoming.exists() else []
    if not files:
        return {"error": "Add some scans first."}
    (d / "template.json").write_text(json.dumps(template, indent=2))
    out = d / "results.csv"
    out.unlink(missing_ok=True)
    with read_lock:
        # the packaged app has no separate Python, so it runs itself as the reader
        reader = [sys.executable, "--reader"] if FROZEN else [sys.executable, str(STAGE / "omr_to_csv.py")]
        p = subprocess.run([*reader, "--config", str(STAGE / "config.json"), "--scans", str(incoming), "--template", str(d / "template.json"),
                            "--out", str(out), "--overlays", str(d / "overlays")],
                           capture_output=True, text=True, cwd=d, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if p.returncode or not out.exists():
        return {"error": "The reader failed:\n" + "\n".join((p.stderr or p.stdout).strip().splitlines()[-15:])}

    with open(out, newline="") as f:
        rows = list(csv.DictReader(f))
    with db() as con:
        for r in rows:
            con.execute("INSERT INTO sheets (exam_id, file, data) VALUES (?, ?, ?) "
                        "ON CONFLICT (exam_id, file) DO UPDATE SET data = excluded.data, edited = 0",
                        (exam_id, r["file_id"], json.dumps(r)))
    # The reader drops sheets it cannot align; name the images among them (PDF pages get new names)
    read = {r["file_id"] for r in rows}
    missed = [f.name for f in files if f.suffix.lower() != ".pdf" and f.name not in read]
    scans.mkdir(exist_ok=True)
    for f in files:
        if f.name not in missed:
            shutil.move(str(f), scans / f.name)
    return {"read": len(rows), "missed": missed}


# ---------- HTTP ----------

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def translate_path(self, path):
        # Overlay images and the pre-designer template come from the repo; everything else is the web app
        p = unquote(urlparse(path).path)
        if p == "/scans_to_csv/template.json":
            return str(STAGE / "template.json")
        if p.startswith("/data/"):
            f = (DATA / p[len("/data/"):]).resolve()
            return str(f) if f.is_relative_to((DATA / "exams").resolve()) else str(WEB / "missing")
        return super().translate_path(path)

    def log_message(self, *a):  # keep the console for errors
        pass

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def route(self, method):
        u = urlparse(self.path)
        parts = u.path.strip("/").split("/")
        if parts[0] != "api":
            return False
        try:
            self.api(method, parts[1:], parse_qs(u.query))
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            self.send_json({"error": f"Bad request: {e}"}, 400)
        return True

    def api(self, method, p, q):
        if p == ["version"] and method == "GET":
            return self.send_json({"version": __version__})
        if p == ["exams"] and method == "GET":
            with db() as con:
                rows = con.execute("SELECT e.id, e.name, e.created, COUNT(s.id) AS sheets FROM exams e "
                                   "LEFT JOIN sheets s ON s.exam_id = e.id GROUP BY e.id ORDER BY e.id DESC")
                return self.send_json([dict(r) for r in rows])
        if p == ["exams"] and method == "POST":
            b = json.loads(self.body())
            tpl, design = b["template"], b.get("design")
            if not is_template(tpl):
                return self.send_json({"error": "That is not a template.json."}, 400)
            with db() as con:
                cur = con.execute("INSERT INTO exams (name, created, template, design) VALUES (?, ?, ?, ?)",
                                  (str(b.get("name") or "Untitled sheet"), datetime.now().isoformat(timespec="seconds"),
                                   json.dumps(tpl), json.dumps(design) if design is not None else None))
            write_sheet_files(cur.lastrowid, tpl, design)
            return self.send_json({"id": cur.lastrowid})

        if len(p) >= 2 and p[0] == "exams":
            exam_id = int(p[1])
            with db() as con:
                if not con.execute("SELECT 1 FROM exams WHERE id = ?", (exam_id,)).fetchone():
                    return self.send_json({"error": "No such exam."}, 404)
                if len(p) == 2 and method == "GET":
                    return self.send_json(exam_json(con, exam_id))
                if len(p) == 2 and method == "PUT":
                    b = json.loads(self.body())
                    if "template" in b:  # a redesign: only before any scan was read against the old layout
                        if not is_template(b["template"]):
                            return self.send_json({"error": "That is not a template.json."}, 400)
                        old = json.loads(con.execute("SELECT template FROM exams WHERE id = ?", (exam_id,)).fetchone()[0])
                        read = con.execute("SELECT COUNT(*) FROM sheets WHERE exam_id = ?", (exam_id,)).fetchone()[0]
                        if read and b["template"] != old:
                            return self.send_json({"error": "Scans were already read against this layout."}, 409)
                        con.execute("UPDATE exams SET template = ?, design = ? WHERE id = ?",
                                    (json.dumps(b["template"]), json.dumps(b.get("design")), exam_id))
                        write_sheet_files(exam_id, b["template"], b.get("design"))
                    for col in ("name", "keys", "rules"):
                        if col in b:
                            con.execute(f"UPDATE exams SET {col} = ? WHERE id = ?",
                                        (b[col] if col == "name" else json.dumps(b[col]), exam_id))
                    return self.send_json({"ok": True})
                if len(p) == 2 and method == "DELETE":
                    con.execute("DELETE FROM exams WHERE id = ?", (exam_id,))
                    shutil.rmtree(exam_dir(exam_id), ignore_errors=True)
                    return self.send_json({"ok": True})
                if p[2:] == ["scans"] and method == "POST":
                    name = Path(q["name"][0]).name
                    if Path(name).suffix.lower() not in SCAN_EXTS:
                        return self.send_json({"error": f"{name}: only JPG, PNG and PDF scans."}, 400)
                    incoming = exam_dir(exam_id) / "incoming"
                    incoming.mkdir(parents=True, exist_ok=True)
                    (incoming / name).write_bytes(self.body())
                    return self.send_json({"ok": True})
                if p[2:] == ["read"] and method == "POST":
                    tpl = json.loads(con.execute("SELECT template FROM exams WHERE id = ?", (exam_id,)).fetchone()[0])
            if p[2:] == ["read"] and method == "POST":  # outside the connection: reading takes a while
                res = read_scans(exam_id, tpl)
                return self.send_json(res, 500 if "error" in res else 200)

        if len(p) == 2 and p[0] == "sheets":
            with db() as con:
                if method == "PUT":
                    con.execute("UPDATE sheets SET data = ?, edited = 1 WHERE id = ?", (json.dumps(json.loads(self.body())["data"]), int(p[1])))
                    return self.send_json({"ok": True})
                if method == "DELETE":
                    con.execute("DELETE FROM sheets WHERE id = ?", (int(p[1]),))
                    return self.send_json({"ok": True})
        self.send_json({"error": "Not found."}, 404)

    def do_GET(self):
        self.route("GET") or super().do_GET()

    def do_POST(self):
        self.route("POST") or self.send_error(405)

    def do_PUT(self):
        self.route("PUT") or self.send_error(405)

    def do_DELETE(self):
        self.route("DELETE") or self.send_error(405)


def run_tray(server):
    """Serve in the background behind a menu bar (macOS) / notification area (Windows) icon."""
    import pystray
    from PIL import Image

    threading.Thread(target=server.serve_forever, daemon=True).start()

    def quit_app(icon):
        server.shutdown()
        icon.stop()

    pystray.Icon("OMR Checker", Image.open(RES / "packaging" / "tray.png"), f"OMR Checker {__version__}", menu=pystray.Menu(
        pystray.MenuItem("Open OMR Checker", lambda: webbrowser.open(URL), default=True),
        pystray.MenuItem(f"Version {__version__}", None, enabled=False),
        pystray.MenuItem("Quit", quit_app),
    )).run()


def main():
    if sys.argv[1:2] == ["--reader"]:  # the packaged app reading a batch for itself (see read_scans)
        sys.path.insert(0, str(STAGE))
        import omr_to_csv
        sys.argv = ["omr_to_csv", *sys.argv[2:]]
        return omr_to_csv.main()
    bootstrap()
    build_web()
    DATA.mkdir(parents=True, exist_ok=True)
    with db() as con:
        con.executescript(SCHEMA)
        if "design" not in {r[1] for r in con.execute("PRAGMA table_info(exams)")}:  # databases from before designs were stored
            con.execute("ALTER TABLE exams ADD COLUMN design TEXT")
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:  # already running (another double-click): just open it
        try:
            urlopen(f"http://127.0.0.1:{PORT}/api/exams", timeout=2)
        except OSError:
            sys.exit(f"Port {PORT} is taken by another program; close it and try again.")
        print(f"Already running at {URL}", flush=True)
        if "--no-browser" not in sys.argv:
            webbrowser.open(URL)
        return
    if "--no-browser" not in sys.argv:
        webbrowser.open(URL)
    if FROZEN or "--tray" in sys.argv:
        return run_tray(server)
    print(f"OMR Checker running at {URL}\nLeave this window open while you work; close it (or Ctrl+C) to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
