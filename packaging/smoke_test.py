"""Check the packaged app reads scans: fill a synthetic sheet (scripts/check_designer.py),
read it with the app's bundled reader, and compare with the source reader's CSV.

    python packaging/smoke_test.py

Run after packaging/build.py, with the same Python (it needs the reader's packages
and node for check_designer.py)."""
import csv
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "build" / "pyinstaller" / "dist"
APP = {
    "darwin": DIST / "OMR Checker.app" / "Contents" / "MacOS" / "OMR Checker",
    "win32": DIST / "OMR Checker" / "OMR Checker.exe",
}.get(sys.platform, DIST / "OMR Checker" / "OMR Checker")


def rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


with tempfile.TemporaryDirectory() as d:
    work = Path(d)
    for args in ([], ["--half", "--sheet", "ABCDE:20"]):
        subprocess.run([sys.executable, str(ROOT / "scripts" / "check_designer.py"), "--keep", str(work), *args], check=True)
        out = work / "packaged.csv"
        out.unlink(missing_ok=True)
        p = subprocess.run([str(APP), "--reader", "--config", str(ROOT / "scans_to_csv" / "config.json"),
                            "--scans", str(work / "scans"), "--template", str(work / "template.json"), "--out", str(out)],
                           capture_output=True, text=True)
        if p.returncode or not out.exists():
            sys.exit(f"packaged reader failed ({p.returncode}):\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}")
        want, got = rows(work / "results.csv"), rows(out)
        assert got == want, f"packaged reader disagrees with the source reader:\n{got}\n{want}"
        print(f"ok: packaged reader matches the source reader {' '.join(args) or '(full sheet)'}")
