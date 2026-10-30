"""
Generate a printable OMR sheet and its matching template from a few numbers.

    python webapp/sheet_designer.py --questions 40 --options 5 --sets 2 --id-digits 10 --out my_sheet/

Writes sheet.pdf (print this), sheet.png, template.json, config.json,
omr_marker.png and preview.png. The sheet has four corner markers; the
template uses OMRChecker's CropOnMarkers preprocessor to straighten scans
with them, so template coordinates are measured from the marker centres.
"""

import argparse
import io
import json
import math
from pathlib import Path

import matplotlib
from PIL import Image, ImageDraw, ImageFont

# Page: A4 portrait. 1640 px wide = 198.3 dpi; chosen so the marker crop is
# exactly 1/20 of the page width (CropOnMarkers takes an integer ratio).
PAGE_W, PAGE_H = 1640, 2320
DPI = PAGE_W / 8.27
MARKER_RATIO = 20
MARKER_CROP = PAGE_W // MARKER_RATIO      # 82 px marker image, incl. white margin
MARKER_SIZE = 62                          # printed black square
MARKER_INSET = 75                         # marker centre distance from page edge
FRAME = (PAGE_W - 2 * MARKER_INSET, PAGE_H - 2 * MARKER_INSET)  # template pageDimensions

X0, X1 = 130, PAGE_W - 130                # content area
Y_TOP, Y_BOTTOM = 120, PAGE_H - 140

LIMITS = {"questions": (1, 300), "options": (2, 8), "sets": (0, 8), "id_digits": (0, 20)}
OPTION_LETTERS = "ABCDEFGH"
SET_LETTERS = "ABCDEFGH"

# Question grid sizes tried from roomiest to most compact:
# (row pitch, bubble diameter, detection box)
QUESTION_SIZES = [(48, 36, 30), (44, 34, 28), (40, 32, 26), (36, 28, 23), (32, 25, 21)]
GROUP = 5           # questions per group; a small gap separates groups
GROUP_GAP = 12
NUM_W = 62          # width reserved for the question number
COL_GAP = 48

ID_PITCH_X, ID_PITCH_Y, ID_D, ID_BOX = 46, 44, 34, 28
SET_PITCH, SET_D, SET_BOX = 54, 36, 30

INK = 0
LINE = 70
FAINT = 150


class DesignError(ValueError):
    pass


def _font(size: int, bold: bool = False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    path = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / name
    return ImageFont.truetype(str(path), size)


def _text(draw, xy, text, size, fill=INK, bold=False, anchor="la"):
    draw.text(xy, text, fill=fill, font=_font(size, bold), anchor=anchor)


def _bubble(draw, cx, cy, d, label):
    r = d / 2
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=LINE, width=2, fill=255)
    _text(draw, (cx, cy), label, max(10, int(d * 0.5)), fill=FAINT, anchor="mm")


def _marker(draw, cx, cy):
    s = MARKER_SIZE / 2
    draw.rectangle([cx - s, cy - s, cx + s, cy + s], fill=INK)
    s2 = MARKER_SIZE * 0.3
    draw.rectangle([cx - s2, cy - s2, cx + s2, cy + s2], fill=255)
    s3 = MARKER_SIZE * 0.13
    draw.rectangle([cx - s3, cy - s3, cx + s3, cy + s3], fill=INK)


def _box(cx, cy, box):
    """Template origin (top-left of the detection box) in frame coordinates."""
    return [round(cx - box / 2 - MARKER_INSET), round(cy - box / 2 - MARKER_INSET)]


def _range_label(prefix, a, b):
    return f"{prefix}{a}" if a == b else f"{prefix}{a}..{b}"


def validate(questions, options, sets, id_digits, title):
    for name, val in (("questions", questions), ("options", options), ("sets", sets), ("id_digits", id_digits)):
        lo, hi = LIMITS[name]
        if not isinstance(val, int) or not lo <= val <= hi:
            raise DesignError(f"{name.replace('_', ' ').capitalize()} must be between {lo} and {hi}")
    if len(title) > 80:
        raise DesignError("Title must be at most 80 characters")


def plan_questions(n, k, top):
    """Pick the roomiest grid that fits n questions with k options below y=top."""
    avail_h = Y_BOTTOM - top
    avail_w = X1 - X0
    for rp, d, box in QUESTION_SIZES:
        op = d + 12
        col_w = NUM_W + k * op
        cols_max = (avail_w + COL_GAP) // (col_w + COL_GAP)
        rows_max = 0
        while (rows_max + 1) * rp + (rows_max // GROUP) * GROUP_GAP <= avail_h:
            rows_max += 1
        if cols_max < 1 or rows_max < 1:
            continue
        if n <= cols_max * rows_max:
            cols = math.ceil(n / rows_max)
            rows = math.ceil(n / cols)
            return {"rp": rp, "d": d, "box": box, "op": op, "col_w": col_w, "cols": cols, "rows": rows}
    # Report what does fit with the most compact size
    rp, d, box = QUESTION_SIZES[-1]
    col_w = NUM_W + k * (d + 12)
    cols_max = max(0, (avail_w + COL_GAP) // (col_w + COL_GAP))
    rows_max = 0
    while (rows_max + 1) * rp + (rows_max // GROUP) * GROUP_GAP <= avail_h:
        rows_max += 1
    raise DesignError(
        f"{n} questions with {k} options don't fit on one page with this header; "
        f"the maximum is {cols_max * rows_max}. Reduce questions, options or ID digits."
    )


def generate(questions=30, options=4, sets=0, id_digits=0, title="Answer Sheet"):
    """Return a dict with template, config and the image/PDF bytes for a new sheet."""
    title = (title or "Answer Sheet").strip()
    validate(questions, options, sets, id_digits, title)
    opts = list(OPTION_LETTERS[:options])
    set_values = list(SET_LETTERS[:sets])

    img = Image.new("L", (PAGE_W, PAGE_H), 255)
    draw = ImageDraw.Draw(img)
    blocks, boxes = {}, []      # boxes: (cx, cy, size, label) for the preview

    for cx in (MARKER_INSET, PAGE_W - MARKER_INSET):
        for cy in (MARKER_INSET, PAGE_H - MARKER_INSET):
            _marker(draw, cx, cy)

    # Header
    _text(draw, (PAGE_W / 2, Y_TOP + 20), title, 42, bold=True, anchor="mm")
    _text(draw, (PAGE_W / 2, Y_TOP + 72),
          "Use a dark pen. Fill the bubble completely. Do not write near the corner squares.",
          20, fill=90, anchor="mm")
    y = Y_TOP + 120
    _text(draw, (X0, y), "Name", 24)
    draw.line([X0 + 80, y + 28, X0 + 700, y + 28], fill=LINE, width=2)
    _text(draw, (X0 + 760, y), "Signature", 24)
    draw.line([X0 + 890, y + 28, X1, y + 28], fill=LINE, width=2)
    y += 75

    # Student ID: write-in boxes above a 0-9 bubble grid per digit
    section_h = 0
    if id_digits:
        _text(draw, (X0, y), "Student ID", 24, bold=True)
        box_top = y + 40
        for i in range(id_digits):
            cx = X0 + ID_PITCH_X / 2 + i * ID_PITCH_X
            draw.rectangle([cx - 20, box_top, cx + 20, box_top + 44], outline=LINE, width=2)
        first_cy = box_top + 44 + 34
        for i in range(id_digits):
            cx = X0 + ID_PITCH_X / 2 + i * ID_PITCH_X
            for v in range(10):
                cy = first_cy + v * ID_PITCH_Y
                _bubble(draw, cx, cy, ID_D, str(v))
                boxes.append((cx, cy, ID_BOX, str(v)))
        blocks["ID"] = {
            "fieldType": "QTYPE_INT",
            "fieldLabels": [_range_label("id", 1, id_digits)],
            "bubblesGap": ID_PITCH_Y,
            "labelsGap": ID_PITCH_X,
            "origin": _box(X0 + ID_PITCH_X / 2, first_cy, ID_BOX),
        }
        section_h = first_cy + 9 * ID_PITCH_Y + ID_D / 2 - y

    # Set: one row of bubbles, to the right of the ID grid
    if set_values:
        sx = X0 + (id_digits * ID_PITCH_X + 90 if id_digits else 0)
        _text(draw, (sx, y), "Set", 24, bold=True)
        cy = y + 40 + SET_D / 2
        for i, v in enumerate(set_values):
            cx = sx + SET_D / 2 + i * SET_PITCH
            _bubble(draw, cx, cy, SET_D, v)
            boxes.append((cx, cy, SET_BOX, v))
        blocks["Set"] = {
            "bubbleValues": set_values,
            "direction": "horizontal",
            "fieldLabels": ["Set"],
            "bubblesGap": SET_PITCH,
            "labelsGap": 0,
            "origin": _box(sx + SET_D / 2, cy, SET_BOX),
        }
        section_h = max(section_h, 40 + SET_D)

    if section_h:
        y += section_h + 30

    # Questions: columns of groups of five
    _text(draw, (X0, y), "Answers", 24, bold=True)
    draw.line([X0, y + 36, X1, y + 36], fill=200, width=1)
    y += 56
    plan = plan_questions(questions, options, y)
    rp, d, box, op, col_w = plan["rp"], plan["d"], plan["box"], plan["op"], plan["col_w"]
    total_w = plan["cols"] * col_w + (plan["cols"] - 1) * COL_GAP
    x_start = X0 + (X1 - X0 - total_w) / 2

    q = 1
    for c in range(plan["cols"]):
        col_x = x_start + c * (col_w + COL_GAP)
        first_bubble_x = col_x + NUM_W + d / 2
        for g in range(math.ceil(plan["rows"] / GROUP)):
            a = q
            group_y = y + rp / 2 + g * (GROUP * rp + GROUP_GAP)
            for r in range(GROUP):
                if q > questions or g * GROUP + r >= plan["rows"]:
                    break
                cy = group_y + r * rp
                _text(draw, (col_x + NUM_W - 14, cy), str(q), max(14, int(d * 0.55)), bold=True, anchor="rm")
                for i, o in enumerate(opts):
                    cx = first_bubble_x + i * op
                    _bubble(draw, cx, cy, d, o)
                    boxes.append((cx, cy, box, o))
                q += 1
            if q > a:
                blocks[f"Q{a}_{q - 1}"] = {
                    "bubbleValues": opts,
                    "direction": "horizontal",
                    "fieldLabels": [_range_label("q", a, q - 1)],
                    "bubblesGap": op,
                    "labelsGap": rp,
                    "origin": _box(first_bubble_x, group_y, box),
                }

    _text(draw, (PAGE_W / 2, PAGE_H - 40),
          f"{questions} questions · options {opts[0]}–{opts[-1]}"
          + (f" · sets {', '.join(set_values)}" if set_values else "")
          + (f" · {id_digits}-digit ID" if id_digits else ""),
          16, fill=FAINT, anchor="mm")

    # Marker image: the printed marker with a white margin, MARKER_CROP px square
    marker = Image.new("L", (MARKER_CROP, MARKER_CROP), 255)
    _marker(ImageDraw.Draw(marker), MARKER_CROP / 2, MARKER_CROP / 2)

    template = {
        "pageDimensions": list(FRAME),
        "bubbleDimensions": [box, box],
        "preProcessors": [{
            "name": "CropOnMarkers",
            "options": {
                "relativePath": "omr_marker.png",
                "sheetToMarkerWidthRatio": MARKER_RATIO,
                "marker_rescale_range": [80, 120],
                "marker_rescale_steps": 8,
            },
        }],
        "customLabels": {"ID NO": [f"id{i}" for i in range(1, id_digits + 1)]} if id_digits else {},
        "fieldBlocks": blocks,
        "outputColumns": (["Set"] if set_values else []) + (["ID NO"] if id_digits else [])
        + [f"q{i}" for i in range(1, questions + 1)],
    }
    # ID and Set blocks use their own bubble sizes
    if "ID" in blocks:
        blocks["ID"]["bubbleDimensions"] = [ID_BOX, ID_BOX]
    if "Set" in blocks:
        blocks["Set"]["bubbleDimensions"] = [SET_BOX, SET_BOX]

    config = {
        "dimensions": {
            "display_height": 2480, "display_width": 1640,
            "processing_height": PAGE_H, "processing_width": PAGE_W,
        },
        "threshold_params": {
            "MIN_GAP": 30, "MIN_JUMP": 25, "CONFIDENT_SURPLUS": 5,
            "JUMP_DELTA": 30, "PAGE_TYPE_FOR_THRESHOLD": "white",
        },
        "alignment_params": {"auto_align": False},
        "outputs": {"show_image_level": 0, "save_image_level": 2, "save_detections": True,
                    "filter_out_multimarked_files": False},
    }

    preview = img.convert("RGB")
    pdraw = ImageDraw.Draw(preview)
    for cx, cy, b, _ in boxes:
        pdraw.rectangle([cx - b / 2, cy - b / 2, cx + b / 2, cy + b / 2], outline=(40, 170, 40), width=2)
    for cx in (MARKER_INSET, PAGE_W - MARKER_INSET):
        for cy in (MARKER_INSET, PAGE_H - MARKER_INSET):
            pdraw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], outline=(220, 40, 40), width=3)

    def to_bytes(image, fmt, **kw):
        buf = io.BytesIO()
        image.save(buf, fmt, **kw)
        return buf.getvalue()

    return {
        "template": template,
        "config": config,
        "sheet_png": to_bytes(img, "PNG"),
        "sheet_pdf": to_bytes(img, "PDF", resolution=DPI),
        "marker_png": to_bytes(marker, "PNG"),
        "preview_png": to_bytes(preview, "PNG"),
        "params": {"questions": questions, "options": options, "sets": sets,
                   "id_digits": id_digits, "title": title},
        "layout": {"columns": plan["cols"], "rows": plan["rows"], "bubble": d},
    }


def write_bundle(bundle: dict, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "template.json").write_text(json.dumps(bundle["template"], indent=2))
    (folder / "config.json").write_text(json.dumps(bundle["config"], indent=2))
    for key, name in (("sheet_pdf", "sheet.pdf"), ("sheet_png", "sheet.png"),
                      ("marker_png", "omr_marker.png"), ("preview_png", "preview.png")):
        (folder / name).write_bytes(bundle[key])


def main():
    parser = argparse.ArgumentParser(description="Generate a printable OMR sheet and its template.")
    parser.add_argument("--questions", type=int, default=30)
    parser.add_argument("--options", type=int, default=4, help="Options per question (2-8)")
    parser.add_argument("--sets", type=int, default=0, help="Number of question-paper sets (0 = none)")
    parser.add_argument("--id-digits", type=int, default=0, help="Digits in the student ID (0 = no ID grid)")
    parser.add_argument("--title", default="Answer Sheet")
    parser.add_argument("--out", required=True, help="Output folder")
    args = parser.parse_args()
    try:
        bundle = generate(args.questions, args.options, args.sets, args.id_digits, args.title)
    except DesignError as e:
        parser.error(str(e))
    write_bundle(bundle, Path(args.out))
    lay = bundle["layout"]
    print(f"Sheet written to {args.out}: {lay['columns']} column(s) x {lay['rows']} row(s), "
          f"bubble {lay['bubble']} px")


if __name__ == "__main__":
    main()
