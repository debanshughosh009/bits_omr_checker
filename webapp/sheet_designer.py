"""
Make a printable OMR sheet and its template with designer/sheet.js.

designer/sheet.js owns the layout, the printed sheet (SVG) and the template,
for designer/index.html and for this module alike, so a sheet made in the web
app is the same sheet designer/index.html prints. This module runs sheet.js
with node and turns its SVG into a PDF and PNG.

    python webapp/sheet_designer.py --out my_sheet/ [--draft draft.json] [--questions 40 --options ABCDE ...]

--draft takes a draft saved from designer/index.html ("Save"). Writes sheet.pdf
(print at 100%), sheet.png, template.json, omr_marker.png, preview.png and
draft.json.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pymupdf

REPO = Path(__file__).resolve().parent.parent
SHEET_JS = REPO / "designer" / "sheet.js"
sys.path.insert(0, str(REPO / "scans_to_csv"))
from omr_to_csv import write_marker  # noqa: E402  (the marker sheet.js prints)

MM = 72 / 25.4          # PDF points per millimetre (sheet.js works in mm)
PNG_DPI = 200

# The designer form's settings (designer/index.html), by type
TEXT_FIELDS = ("title", "exam", "course", "date", "instructions", "sets", "idTitle", "options")
BOOL_FIELDS = ("showSet",)
INT_FIELDS = ("questions",)

_DUMP = """
const S = require(process.argv[1]);
const s = { ...S.defaults(), ...JSON.parse(process.argv[2]) };
const L = S.layout(s);
process.stdout.write(JSON.stringify({
  settings: s, svg: S.sheetSvg(L), template: S.template(L),
  issues: L.issues, fit: L.fit, markers: L.markers,
}));
"""


class DesignError(ValueError):
    pass


def node_path() -> str:
    node = shutil.which("node")
    if not node:
        raise DesignError("Node.js is needed to run designer/sheet.js; install it or use the Docker image.")
    return node


def clean_settings(raw: dict) -> dict:
    """Keep only the designer's settings, with the right types."""
    out = {}
    for k in TEXT_FIELDS:
        if raw.get(k) is not None:
            out[k] = str(raw[k])
    for k in BOOL_FIELDS:
        if k in raw:
            v = raw[k]
            out[k] = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "on", "yes")
    for k in INT_FIELDS:
        if k in raw and str(raw[k]).strip():
            try:
                out[k] = int(raw[k])
            except (TypeError, ValueError):
                raise DesignError(f"{k.capitalize()} must be a whole number")
    return out


def run_sheet_js(settings: dict) -> dict:
    """Run designer/sheet.js: settings -> {settings, svg, template, issues, fit, markers}."""
    proc = subprocess.run([node_path(), "-e", _DUMP, str(SHEET_JS), json.dumps(clean_settings(settings))],
                          capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise DesignError(f"designer/sheet.js failed: {proc.stderr.strip()[-500:]}")
    return json.loads(proc.stdout)


def defaults() -> dict:
    return run_sheet_js({})["settings"]


# ---------------------------------------------------------------------------
# SVG (from sheetSvg) -> PDF. MuPDF's own SVG import ignores font-family and
# sets every word in Times, so draw sheetSvg's elements with Helvetica instead.
# sheetSvg only emits rect, line, circle and text with explicit attributes.
# ---------------------------------------------------------------------------

def _color(value):
    if not value or value == "none":
        return None
    v = value.lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    return tuple(int(v[i:i + 2], 16) / 255 for i in (0, 2, 4))


def svg_to_pdf(svg: str) -> bytes:
    root = ET.fromstring(svg)
    ns = "{http://www.w3.org/2000/svg}"
    vb = [float(x) for x in root.get("viewBox").split()]
    doc = pymupdf.open()
    page = doc.new_page(width=vb[2] * MM, height=vb[3] * MM)
    num = lambda el, k, d=0.0: float(el.get(k, d))
    for el in root:
        tag = el.tag.replace(ns, "")
        if tag == "rect":
            x, y = num(el, "x"), num(el, "y")
            rect = pymupdf.Rect(x * MM, y * MM, (x + num(el, "width")) * MM, (y + num(el, "height")) * MM)
            fill, stroke = _color(el.get("fill", "#000")), _color(el.get("stroke"))
            page.draw_rect(rect, color=stroke, fill=fill, width=num(el, "stroke-width") * MM if stroke else 0)
        elif tag == "line":
            page.draw_line((num(el, "x1") * MM, num(el, "y1") * MM), (num(el, "x2") * MM, num(el, "y2") * MM),
                           color=_color(el.get("stroke", "#000")), width=num(el, "stroke-width", 1) * MM)
        elif tag == "circle":
            page.draw_circle((num(el, "cx") * MM, num(el, "cy") * MM), num(el, "r") * MM,
                             color=_color(el.get("stroke")), fill=_color(el.get("fill")),
                             width=num(el, "stroke-width") * MM)
        elif tag == "text":
            text = "".join(el.itertext())
            if not text:
                continue
            font = "hebo" if el.get("font-weight") == "bold" else "helv"
            size = num(el, "font-size") * MM
            x, y = num(el, "x") * MM, num(el, "y") * MM
            anchor = el.get("text-anchor", "start")
            if anchor in ("middle", "end"):
                w = pymupdf.get_text_length(text, fontname=font, fontsize=size)
                x -= w / 2 if anchor == "middle" else w
            page.insert_text((x, y), text, fontname=font, fontsize=size, color=_color(el.get("fill", "#000")))
    data = doc.tobytes(deflate=True, garbage=3)
    doc.close()
    return data


def pdf_to_png(pdf: bytes, dpi: int = PNG_DPI) -> bytes:
    with pymupdf.open("pdf", pdf) as doc:
        return doc[0].get_pixmap(dpi=dpi).tobytes("png")


def expand_labels(labels):
    out = []
    for label in labels:
        m = re.fullmatch(r"([^\.\d]+)(\d+)\.{2,3}(\d+)", label)
        out += [f"{m[1]}{i}" for i in range(int(m[2]), int(m[3]) + 1)] if m else [label]
    return out


def preview_png(png: bytes, out: dict) -> bytes:
    """The sheet with the template's bubble boxes (green) and marker centres (red) drawn on it."""
    import cv2
    import numpy as np

    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    tpl, markers = out["template"], out["markers"]
    px_per_mm = PNG_DPI / 25.4
    x0, y0 = min(m["cx"] for m in markers), min(m["cy"] for m in markers)
    tpl_per_mm = tpl["pageDimensions"][0] / (max(m["cx"] for m in markers) - x0)

    def to_img(tx, ty):
        return round((x0 + tx / tpl_per_mm) * px_per_mm), round((y0 + ty / tpl_per_mm) * px_per_mm)

    for b in tpl["fieldBlocks"].values():
        bw, bh = b.get("bubbleDimensions", tpl["bubbleDimensions"])
        ox, oy = b["origin"]
        for li in range(len(expand_labels(b["fieldLabels"]))):
            for vi in range(len(b["bubbleValues"])):
                if b["direction"] == "horizontal":
                    tx, ty = ox + vi * b["bubblesGap"], oy + li * b["labelsGap"]
                else:
                    tx, ty = ox + li * b["labelsGap"], oy + vi * b["bubblesGap"]
                cv2.rectangle(img, to_img(tx, ty), to_img(tx + bw, ty + bh), (40, 170, 40), 2)
    for m in markers:
        cv2.circle(img, (round(m["cx"] * px_per_mm), round(m["cy"] * px_per_mm)), 9, (40, 40, 220), 3)
    return cv2.imencode(".png", img)[1].tobytes()


def id_format_text(columns) -> str:
    """'(F/H/P) 2 0 (0-4) (0-9) ... (H/P/G)' from each ID column's symbols."""
    def col(c):
        if len(c) == 1:
            return c
        if c.isdigit() and c == "".join(str(d) for d in range(int(c[0]), int(c[0]) + len(c))):
            return f"({c[0]}-{c[-1]})"
        return f"({'/'.join(c)})"
    return " ".join(col(c) for c in columns)


def generate(settings: dict) -> dict:
    """Settings -> template, PDF, PNG, marker and preview. Raises DesignError if the sheet has issues."""
    out = run_sheet_js(settings)
    if out["issues"]:
        raise DesignError(" ".join(out["issues"]))
    pdf = svg_to_pdf(out["svg"])
    png = pdf_to_png(pdf)
    with tempfile.TemporaryDirectory() as d:
        write_marker(Path(d) / "omr_marker.png")
        marker = (Path(d) / "omr_marker.png").read_bytes()
    return {
        "settings": out["settings"],
        "template": out["template"],
        "sheet_pdf": pdf,
        "sheet_png": png,
        "marker_png": marker,
        "preview_png": preview_png(png, out),
        "fit": out["fit"],
    }


def write_bundle(bundle: dict, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "template.json").write_text(json.dumps(bundle["template"], indent=2))
    (folder / "draft.json").write_text(json.dumps(bundle["settings"], indent=2))
    for key, name in (("sheet_pdf", "sheet.pdf"), ("sheet_png", "sheet.png"),
                      ("marker_png", "omr_marker.png"), ("preview_png", "preview.png")):
        (folder / name).write_bytes(bundle[key])


def main():
    parser = argparse.ArgumentParser(description="Make a printable OMR sheet and its template with designer/sheet.js.")
    parser.add_argument("--out", required=True, help="Output folder")
    parser.add_argument("--draft", help="Draft saved from designer/index.html")
    parser.add_argument("--questions", type=int)
    parser.add_argument("--options", help="Option letters, e.g. ABCDE")
    parser.add_argument("--sets", help="Set letters, e.g. ABCD")
    parser.add_argument("--no-set", action="store_true", help="Leave out the set box")
    for k in ("title", "exam", "course", "date"):
        parser.add_argument(f"--{k}")
    args = parser.parse_args()
    settings = json.loads(Path(args.draft).read_text()) if args.draft else {}
    for k in ("questions", "options", "sets", "title", "exam", "course", "date"):
        if getattr(args, k) is not None:
            settings[k] = getattr(args, k)
    if args.no_set:
        settings["showSet"] = False
    try:
        bundle = generate(settings)
    except DesignError as e:
        parser.error(str(e))
    write_bundle(bundle, Path(args.out))
    print(f"Sheet written to {args.out}: {bundle['fit']['cols']} column(s), "
          f"up to {bundle['fit']['capacity']} questions fit")


if __name__ == "__main__":
    main()
