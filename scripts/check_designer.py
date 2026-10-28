"""Round trip for designer/: render the default sheet, fill it in, skew it like a
scan, read it with scans_to_csv, and check the answers come back.

    python scripts/check_designer.py [--sheet ABCDE:60] [--pdf PRINTED.pdf] [--keep DIR]

--sheet sets the options and question count (default ABCD:30); a --pdf must have
been printed with the same two settings.

Needs node (to run designer/sheet.js) and the scans_to_csv requirements."""
import csv, json, subprocess, sys, tempfile
from pathlib import Path

import cv2
import numpy as np
import pymupdf

ROOT = Path(__file__).resolve().parent.parent
DPI = 200
ID = "H20271293G"   # "20" is printed, the rest is bubbled
SET = "C"

DUMP = """
const S = require(process.argv[1]);
const L = S.layout({ ...S.defaults(), options: process.argv[2], questions: +process.argv[3] });
process.stdout.write(JSON.stringify({ svg: S.sheetSvg(L), template: S.template(L), layout: L }));
"""


def main(work: Path, opts: str, n: int):
    answers = {q: opts[q % len(opts)] for q in range(1, n + 1) if q % 7}   # q7, q14, ... left blank
    answers[5] = opts[0] + opts[2]                                         # one multi-mark
    out = json.loads(subprocess.run(["node", "-e", DUMP, str(ROOT / "designer/sheet.js"), opts, str(n)],
                                    check=True, capture_output=True, text=True).stdout)
    assert not out["layout"]["issues"], out["layout"]["issues"]
    (work / "template.json").write_text(json.dumps(out["template"], indent=2))

    # --pdf: a sheet the browser printed from designer/index.html (default settings)
    doc = pymupdf.open(PDF) if PDF else pymupdf.open(stream=out["svg"].encode(), filetype="svg")
    pix = doc[0].get_pixmap(dpi=DPI)
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3].copy()
    mm = DPI / 25.4

    # fill: every bubble whose field value should be marked
    want = {"Set": SET, **{f"id{i + 1}": c for i, c in enumerate(ID)}, **{f"q{q}": a for q, a in answers.items()}}
    for f in out["layout"]["fields"]:
        if ".." in f["label"]:                     # "q1..15": one row of options per question
            a, b = map(int, f["label"][1:].split(".."))
            names = [f"q{q}" for q in range(a, b + 1)]
        else:
            names = [f["label"]]
        per_row = len(f["bubbles"]) // len(names)
        for row, name in enumerate(names):
            for b in f["bubbles"][row * per_row:(row + 1) * per_row]:
                if b["label"] in want.get(name, ""):
                    r = 0.46 * b.get("d", 4.2) * mm                 # a student fills most of the bubble
                    cv2.circle(img, (round(b["cx"] * mm), round(b["cy"] * mm)), round(r), (120, 40, 20), -1)

    # scan: shrink 3%, turn 1.2 degrees, shift, blur, on a page-sized canvas
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), 1.2, 0.97)
    m[:, 2] += (25, -18)
    scan = cv2.GaussianBlur(cv2.warpAffine(img, m, (w, h), borderValue=(255, 255, 255)), (3, 3), 0)
    (work / "scans").mkdir(exist_ok=True)
    cv2.imwrite(str(work / "scans/sheet.jpg"), scan)

    subprocess.run([sys.executable, str(ROOT / "scans_to_csv/omr_to_csv.py"), "--scans", str(work / "scans"),
                    "--template", str(work / "template.json"), "--out", str(work / "results.csv")],
                   check=True, capture_output=True)
    row = next(csv.DictReader(open(work / "results.csv")))

    expect = {"Set": SET, "ID NO": ID, **{f"q{q}": answers.get(q, "") for q in range(1, n + 1)}}
    wrong = {k: (row.get(k), v) for k, v in expect.items() if row.get(k) != v}
    assert not wrong, f"read != filled (got, want): {wrong}"
    print(f"ok: set, ID {ID} and {n} questions x {len(opts)} options read back correctly; check={row['check']!r}")


if __name__ == "__main__":
    arg = lambda k: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else None
    PDF = arg("--pdf")
    opts, n = (arg("--sheet") or "ABCD:30").split(":")
    if arg("--keep"):
        d = Path(arg("--keep")); d.mkdir(parents=True, exist_ok=True)
        main(d, opts, int(n))
    else:
        with tempfile.TemporaryDirectory() as d:
            main(Path(d), opts, int(n))
