"""
Storage and processing for the web app.

Data lives under OMR_DATA_DIR (default: <repo>/data, /data in Docker):

    layouts/<layout_id>/          created by the designer
        layout.json               name, created, sheet file name, generator settings
        template.json             OMRChecker template
        config.json               optional detection tuning
        sheet.<ext>               blank sheet for printing (generated: sheet.pdf + sheet.png)
        omr_marker.png, ...       files the template's preprocessors reference
        preview.png               sheet with template bubbles drawn on it
    exams/<exam_id>/              created by the professor
        exam.json                 name, layout, marking scheme, answer keys, history
        key.json                  answer key in scoring/score_omr.py format
        roster.csv                optional class roster
        uploads/                  every scan uploaded for this exam
        overlays/                 annotated scans from Stage 1
        results.csv               Stage 1 output (marked options per sheet)
        scores.csv                Stage 2 output (scores per sheet)

Stage 1 and Stage 2 are run as subprocesses with their normal CLIs, so the
pipeline code is used exactly as it is from the command line.
"""

import csv
import io
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
STAGE1 = Path(__file__).resolve().parent / "run_stage1.py"
STAGE2 = REPO_ROOT / "scoring" / "score_omr.py"
DEFAULT_TEMPLATE = REPO_ROOT / "scans_to_csv" / "template.json"
DEFAULT_CONFIG = REPO_ROOT / "scans_to_csv" / "config.json"

DATA_DIR = Path(os.environ.get("OMR_DATA_DIR", REPO_ROOT / "data")).resolve()
LAYOUTS_DIR = DATA_DIR / "layouts"
EXAMS_DIR = DATA_DIR / "exams"

SCAN_EXTS = {".png", ".jpg", ".jpeg", ".pdf"}
SHEET_EXTS = {".png", ".jpg", ".jpeg", ".pdf"}
QUESTION_RE = re.compile(r"q\d+")

sys.path.insert(0, str(REPO_ROOT / "scans_to_csv"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sheet_designer  # noqa: E402
from omr_to_csv import write_marker  # noqa: E402
from src.constants.common import FIELD_TYPES  # noqa: E402
from src.schemas.constants import FIELD_STRING_REGEX_GROUPS  # noqa: E402
from src.schemas.template_schema import TEMPLATE_SCHEMA  # noqa: E402
from src.schemas.config_schema import CONFIG_SCHEMA  # noqa: E402


class PipelineError(Exception):
    """A user-facing error (bad upload, invalid template, ...)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)


def new_id(name: str, parent: Path) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "item"
    candidate, n = slug, 2
    while (parent / candidate).exists():
        candidate, n = f"{slug}-{n}", n + 1
    return candidate


def safe_name(name: str) -> str:
    """Strip directories and unsafe characters from an uploaded file name."""
    base = Path(name.replace("\\", "/")).name
    base = re.sub(r"[^A-Za-z0-9._ -]+", "_", base).strip(" .")
    return base or "file"


def unique_path(folder: Path, name: str, taken: set[str]) -> Path:
    stem, ext = Path(name).stem, Path(name).suffix
    candidate, n = name, 2
    while candidate.lower() in taken or (folder / candidate).exists():
        candidate, n = f"{stem}_{n}{ext}", n + 1
    taken.add(candidate.lower())
    return folder / candidate


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    if not path.exists():
        return [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header, quoting=csv.QUOTE_NONNUMERIC, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------------------
# Layouts (designer)
# ---------------------------------------------------------------------------

def engine_template(tpl: dict) -> dict:
    """
    The template as the engine sees it. Templates from the sheet designers carry
    "idColumns" (fixed ID characters among the bubbled columns), which
    scans_to_csv/omr_to_csv.py strips the same way before running the engine.
    """
    if "idColumns" not in tpl:
        return tpl
    engine_tpl = {k: v for k, v in tpl.items() if k not in ("idColumns", "customLabels")}
    bubbled = [c for c in tpl["idColumns"] if len(c) > 1]
    engine_tpl["outputColumns"] = [x for c in tpl["outputColumns"] for x in (bubbled if c == "ID NO" else [c])]
    return engine_tpl


def validate_template(tpl) -> None:
    import jsonschema

    if not isinstance(tpl, dict):
        raise PipelineError("template.json must be a JSON object")
    for key in ("pageDimensions", "fieldBlocks", "outputColumns"):
        if key not in tpl:
            raise PipelineError(f"template.json is missing '{key}'")
    if "idColumns" in tpl and not (isinstance(tpl["idColumns"], list)
                                   and all(isinstance(c, str) and c for c in tpl["idColumns"])):
        raise PipelineError("template.json 'idColumns' must be a list of non-empty strings")
    try:
        jsonschema.validate(engine_template(tpl), TEMPLATE_SCHEMA)
    except jsonschema.ValidationError as e:
        where = "/".join(str(p) for p in e.absolute_path) or "root"
        raise PipelineError(f"template.json is invalid at '{where}': {e.message}")
    if not any(QUESTION_RE.fullmatch(c) for c in tpl["outputColumns"]):
        raise PipelineError("template outputColumns has no question columns (q1, q2, ...)")


def validate_config(cfg) -> None:
    import jsonschema

    try:
        jsonschema.validate(cfg, CONFIG_SCHEMA)
    except jsonschema.ValidationError as e:
        where = "/".join(str(p) for p in e.absolute_path) or "root"
        raise PipelineError(f"config.json is invalid at '{where}': {e.message}")


def parse_json_upload(data: bytes, label: str):
    try:
        return json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise PipelineError(f"{label} is not valid JSON: {e}")


def expand_labels(labels: list[str]) -> list[str]:
    out = []
    for label in labels:
        m = re.fullmatch(FIELD_STRING_REGEX_GROUPS, label)
        if m:
            prefix, start, end = m.group(1), int(m.group(2)), int(m.group(3))
            out += [f"{prefix}{i}" for i in range(start, end + 1)]
        else:
            out.append(label)
    return out


def block_values(block: dict) -> tuple[list[str], str]:
    if "fieldType" in block:
        ft = FIELD_TYPES[block["fieldType"]]
        return ft["bubbleValues"], ft["direction"]
    return block["bubbleValues"], block["direction"]


def template_info(tpl: dict) -> dict:
    """Summarize a template: questions, their options, sets, ID length."""
    field_values = {}
    for block in tpl["fieldBlocks"].values():
        values, _ = block_values(block)
        for label in expand_labels(block["fieldLabels"]):
            field_values[label] = values

    questions = sorted(
        (c for c in tpl["outputColumns"] if QUESTION_RE.fullmatch(c)),
        key=lambda q: int(q[1:]),
    )
    options = {q: field_values.get(q, list("ABCD")) for q in questions}
    all_options = []
    for q in questions:
        for o in options[q]:
            if o not in all_options:
                all_options.append(o)

    custom = tpl.get("customLabels", {})
    if "idColumns" in tpl:
        id_cols = [c if len(c) == 1 else "".join(field_values.get(c, [])) for c in tpl["idColumns"]]
        id_format = sheet_designer.id_format_text(id_cols)
    else:
        id_format = ""
    return {
        "questions": questions,
        "options": options,
        "all_options": all_options,
        "sets": field_values.get("Set", []),
        "id_length": len(tpl["idColumns"]) if "idColumns" in tpl else len(custom.get("ID NO", [])),
        "id_format": id_format,
        "page": tpl["pageDimensions"],
        "blocks": len(tpl["fieldBlocks"]),
    }


def sheet_image(path: Path):
    """Load a blank sheet (image or first PDF page) as a BGR array."""
    if path.suffix.lower() == ".pdf":
        import fitz

        with fitz.open(str(path)) as doc:
            pix = doc[0].get_pixmap(dpi=200)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
            return cv2.cvtColor(img, cv2.COLOR_RGB2BGR if pix.n == 3 else cv2.COLOR_RGBA2BGR)
    return cv2.imread(str(path))


def marker_options(tpl: dict) -> dict | None:
    for pp in tpl.get("preProcessors", []):
        if pp.get("name") == "CropOnMarkers":
            return pp.get("options", {})
    return None


def crop_on_markers(img, marker_path: Path, opts: dict, size: tuple[int, int]):
    """
    Straighten a blank sheet the way CropOnMarkers does: find the marker in
    each quarter of the page and warp the marker centres to the page corners.
    Returns the warped image, or None if a marker can't be found.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    marker = cv2.imread(str(marker_path), cv2.IMREAD_GRAYSCALE)
    if marker is None:
        return None
    h, w = gray.shape
    if "sheetToMarkerWidthRatio" in opts:
        mw = w / int(opts["sheetToMarkerWidthRatio"])
        marker = cv2.resize(marker, (int(mw), int(marker.shape[0] * mw / marker.shape[1])))
    centres = []
    for qx, qy in ((0, 0), (1, 0), (1, 1), (0, 1)):         # tl, tr, br, bl
        quad = gray[qy * h // 2:(qy + 1) * h // 2, qx * w // 2:(qx + 1) * w // 2]
        best = (-1, None, None)
        for scale in np.linspace(0.6, 1.4, 17):
            m = cv2.resize(marker, None, fx=scale, fy=scale)
            if m.shape[0] >= quad.shape[0] or m.shape[1] >= quad.shape[1]:
                continue
            res = cv2.matchTemplate(quad, m, cv2.TM_CCOEFF_NORMED)
            _, score, _, loc = cv2.minMaxLoc(res)
            if score > best[0]:
                best = (score, loc, m.shape)
        score, loc, shape = best
        if loc is None or score < 0.5:
            return None
        centres.append([loc[0] + shape[1] / 2 + qx * w // 2, loc[1] + shape[0] / 2 + qy * h // 2])
    fw, fh = size
    dst = np.float32([[0, 0], [fw - 1, 0], [fw - 1, fh - 1], [0, fh - 1]])
    M = cv2.getPerspectiveTransform(np.float32(centres), dst)
    return cv2.warpPerspective(img, M, (fw, fh))


def make_preview(tpl: dict, sheet_path: Path | None, out_path: Path) -> str | None:
    """
    Draw every template bubble on the blank sheet (or a white page).
    Returns a warning if the sheet couldn't be lined up with the template.
    """
    w, h = tpl["pageDimensions"]
    img = sheet_image(sheet_path) if sheet_path else None
    warning = None
    if img is not None:
        opts = marker_options(tpl)
        if opts is not None:
            warped = crop_on_markers(img, out_path.parent / opts.get("relativePath", ""), opts, (w, h))
            if warped is None:
                warning = ("Couldn't find the four corner markers on the blank sheet, "
                           "so the preview may not line up.")
                img = cv2.resize(img, (w, h))
            else:
                img = warped
        else:
            img = cv2.resize(img, (w, h))
    else:
        img = np.full((h, w, 3), 255, np.uint8)
    bw, bh = tpl.get("bubbleDimensions", [20, 20])

    for name, block in tpl["fieldBlocks"].items():
        bw_, bh_ = block.get("bubbleDimensions", [bw, bh])
        values, direction = block_values(block)
        labels = expand_labels(block["fieldLabels"])
        ox, oy = block["origin"]
        gap, lgap = block.get("bubblesGap", 0), block.get("labelsGap", 0)
        for li, _ in enumerate(labels):
            for vi, v in enumerate(values):
                if direction == "horizontal":
                    x, y = ox + vi * gap, oy + li * lgap
                else:
                    x, y = ox + li * lgap, oy + vi * gap
                x, y = round(x), round(y)
                cv2.rectangle(img, (x, y), (x + bw_, y + bh_), (40, 170, 40), 2)
                cv2.putText(img, v, (x + 2, y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 60, 0), 1)
        cv2.putText(img, name, (round(ox), round(oy) - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 200), 2)
    cv2.imwrite(str(out_path), img)
    return warning


def list_layouts() -> list[dict]:
    if not LAYOUTS_DIR.exists():
        return []
    layouts = [get_layout(p.name) for p in LAYOUTS_DIR.iterdir() if (p / "layout.json").exists()]
    return sorted(layouts, key=lambda l: l["created"], reverse=True)


def get_layout(layout_id: str) -> dict | None:
    folder = LAYOUTS_DIR / safe_name(layout_id)
    meta = read_json(folder / "layout.json")
    if meta is None:
        return None
    tpl = read_json(folder / "template.json")
    assets = [pp["options"]["relativePath"] for pp in tpl.get("preProcessors", [])
              if pp.get("options", {}).get("relativePath")]
    return {
        **meta,
        "id": folder.name,
        "dir": folder,
        "template": tpl,
        "info": template_info(tpl),
        "has_config": (folder / "config.json").exists(),
        "assets": [a for a in assets if (folder / a).exists()],
    }


def layout_files(layout: dict) -> list[str]:
    """Files a designer can download (and that go into the layout ZIP)."""
    names = ["template.json", "config.json", layout.get("sheet"), "sheet.png", "draft.json", *layout["assets"]]
    seen, out = set(), []
    for n in names:
        if n and n not in seen and (layout["dir"] / n).exists():
            seen.add(n)
            out.append(n)
    return out


def layout_zip(layout: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in layout_files(layout):
            zf.write(layout["dir"] / name, name)
    return buf.getvalue()


def layout_in_use(layout_id: str) -> list[str]:
    return [e["name"] for e in list_exams() if e["layout"] == layout_id]


def create_layout(name, template_bytes, config_bytes=None, sheet_name=None, sheet_bytes=None,
                  assets=None) -> tuple[str, str | None]:
    """Create a layout from uploaded files. Returns (layout_id, preview warning)."""
    name = name.strip()
    if not name:
        raise PipelineError("Give the layout a name")
    tpl = parse_json_upload(template_bytes, "template.json")
    validate_template(tpl)
    assets = {safe_name(n): data for n, data in (assets or []) if data}
    draw_marker = None
    for pp in tpl.get("preProcessors", []):
        rel = pp.get("options", {}).get("relativePath")
        if rel and rel not in assets:
            if pp.get("name") == "CropOnMarkers":
                # Sheets from designer/ don't ship their marker; Stage 1 draws the
                # standard one, so draw it here too (for the preview and downloads).
                draw_marker = safe_name(rel)
            else:
                raise PipelineError(
                    f"The template's {pp['name']} step needs the file '{rel}'. Upload it under 'Template files'."
                )
    cfg = None
    if config_bytes:
        cfg = parse_json_upload(config_bytes, "config.json")
        validate_config(cfg)
    sheet_ext = None
    if sheet_bytes:
        sheet_ext = Path(sheet_name or "").suffix.lower()
        if sheet_ext not in SHEET_EXTS:
            raise PipelineError("Blank sheet must be a PNG, JPG or PDF")

    LAYOUTS_DIR.mkdir(parents=True, exist_ok=True)
    layout_id = new_id(name, LAYOUTS_DIR)
    folder = LAYOUTS_DIR / layout_id
    folder.mkdir()
    try:
        write_json(folder / "template.json", tpl)
        if cfg is not None:
            write_json(folder / "config.json", cfg)
        for asset_name, data in assets.items():
            (folder / asset_name).write_bytes(data)
        if draw_marker:
            write_marker(folder / draw_marker)
        sheet = None
        if sheet_bytes:
            sheet = f"sheet{sheet_ext}"
            (folder / sheet).write_bytes(sheet_bytes)
        warning = make_preview(tpl, folder / sheet if sheet else None, folder / "preview.png")
        write_json(folder / "layout.json", {"name": name, "created": now(), "sheet": sheet})
    except Exception as e:
        shutil.rmtree(folder, ignore_errors=True)
        if isinstance(e, PipelineError):
            raise
        raise PipelineError(f"Could not create layout: {e}")
    return layout_id, warning


def design_settings(form: dict) -> dict:
    """The designer/index.html settings from a submitted form (unchecked boxes are absent)."""
    try:
        settings = sheet_designer.clean_settings({k: form.get(k) for k in form})
    except sheet_designer.DesignError as e:
        raise PipelineError(str(e))
    settings["showSet"] = bool(form.get("showSet"))
    return settings


def design_defaults() -> dict:
    try:
        return sheet_designer.defaults()
    except sheet_designer.DesignError as e:
        raise PipelineError(str(e))


def create_generated_layout(name: str, settings: dict) -> str:
    """Make a sheet with designer/sheet.js and save it as a layout."""
    try:
        bundle = sheet_designer.generate(settings)
    except sheet_designer.DesignError as e:
        raise PipelineError(str(e))
    s = bundle["settings"]
    name = name.strip() or " ".join(x for x in (s.get("course"), s.get("exam")) if x) or s.get("title") or "Sheet"
    LAYOUTS_DIR.mkdir(parents=True, exist_ok=True)
    layout_id = new_id(name, LAYOUTS_DIR)
    folder = LAYOUTS_DIR / layout_id
    try:
        sheet_designer.write_bundle(bundle, folder)
        write_json(folder / "layout.json", {
            "name": name, "created": now(), "sheet": "sheet.pdf",
            "generated": {"settings": s, "columns": bundle["fit"]["cols"], "capacity": bundle["fit"]["capacity"]},
        })
    except Exception as e:
        shutil.rmtree(folder, ignore_errors=True)
        raise PipelineError(f"Could not create layout: {e}")
    return layout_id


def delete_layout(layout_id: str) -> None:
    layout = get_layout(layout_id)
    if layout is None:
        return
    in_use = layout_in_use(layout["id"])
    if in_use:
        raise PipelineError(f"Layout is used by exam(s): {', '.join(in_use)}")
    shutil.rmtree(layout["dir"])


def seed_default_layout() -> None:
    """Install the repo's BITS template as a layout on first start."""
    if LAYOUTS_DIR.exists() and any(LAYOUTS_DIR.iterdir()):
        return
    create_layout(
        "BITS Hyderabad 30Q",
        DEFAULT_TEMPLATE.read_bytes(),
        DEFAULT_CONFIG.read_bytes() if DEFAULT_CONFIG.exists() else None,
    )


# ---------------------------------------------------------------------------
# Exams (professor)
# ---------------------------------------------------------------------------

def list_exams() -> list[dict]:
    if not EXAMS_DIR.exists():
        return []
    exams = []
    for p in EXAMS_DIR.iterdir():
        meta = read_json(p / "exam.json")
        if meta:
            _, rows = read_csv(p / "results.csv")
            exams.append({**meta, "id": p.name, "sheets": len(rows)})
    return sorted(exams, key=lambda e: e["created"], reverse=True)


def get_exam(exam_id: str) -> dict | None:
    folder = EXAMS_DIR / safe_name(exam_id)
    meta = read_json(folder / "exam.json")
    if meta is None:
        return None
    return {**meta, "id": folder.name, "dir": folder}


def save_exam(exam: dict) -> None:
    data = {k: v for k, v in exam.items() if k not in ("id", "dir")}
    write_json(exam["dir"] / "exam.json", data)


def create_exam(name: str, layout_id: str) -> str:
    name = name.strip()
    if not name:
        raise PipelineError("Give the exam a name")
    layout = get_layout(layout_id)
    if layout is None:
        raise PipelineError("Choose a sheet layout")
    EXAMS_DIR.mkdir(parents=True, exist_ok=True)
    exam_id = new_id(name, EXAMS_DIR)
    folder = EXAMS_DIR / exam_id
    (folder / "uploads").mkdir(parents=True)
    (folder / "overlays").mkdir()
    write_json(folder / "exam.json", {
        "name": name,
        "layout": layout["id"],
        "created": now(),
        "marking": {"correct": 4, "wrong": -1, "blank": 0, "multi": "wrong", "partial": False},
        "num_questions": len(layout["info"]["questions"]),
        "keys": {},
        "roster": False,
        "history": [],
    })
    return exam_id


def delete_exam(exam_id: str) -> None:
    exam = get_exam(exam_id)
    if exam:
        shutil.rmtree(exam["dir"])


def set_roster(exam: dict, data: bytes | None) -> None:
    path = exam["dir"] / "roster.csv"
    if data is None:
        path.unlink(missing_ok=True)
        exam["roster"] = False
        return
    text = data.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(text.splitlines()))
    if len(rows) < 2 or not rows[0]:
        raise PipelineError("Roster CSV needs a header row and at least one student")
    path.write_text(text, encoding="utf-8")
    exam["roster"] = True


def normalize_key_answer(raw) -> str:
    """'' / '*' / 'AC' (any one of A, C) / 'A+C' (exactly A and C), letters sorted."""
    a = re.sub(r"[\s,/|]", "", str(raw or "").upper())
    if a in ("", "-"):
        return ""
    if a == "*":
        return "*"
    all_of = "+" in a or "&" in a
    letters = sorted(set(a.replace("+", "").replace("&", "")))
    return "+".join(letters) if all_of and len(letters) > 1 else "".join(letters)


def save_keys(exam: dict, keys: dict, num_questions: int) -> None:
    """
    keys: {set_name: [answer per question]} for the first num_questions questions.
    Answers: '' unanswered, '*' bonus, 'A', 'AC' any one of, 'A+C' all of.
    """
    layout = get_layout(exam["layout"])
    info = layout["info"]
    n_total = len(info["questions"])
    if not 1 <= num_questions <= n_total:
        raise PipelineError(f"Number of questions must be between 1 and {n_total}")

    valid_sets = set(info["sets"]) or {"*"}
    clean = {}
    for set_name, answers in keys.items():
        if set_name not in valid_sets:
            raise PipelineError(f"Unknown set '{set_name}'")
        answers = [normalize_key_answer(a) for a in answers][:num_questions]
        answers += [""] * (num_questions - len(answers))
        for q, a in zip(info["questions"], answers):
            if a and a != "*" and not set(a.replace("+", "")) <= set(info["options"][q]):
                raise PipelineError(f"Set {set_name}, {q}: '{a}' is not an option on the sheet")
        if any(answers):
            clean[set_name] = answers
    exam["keys"] = clean
    exam["num_questions"] = num_questions


def write_key_file(exam: dict, questions: list[str]) -> Path:
    """Write key.json in the format scoring/score_omr.py reads."""
    n = exam["num_questions"]
    key = {}
    for set_name, answers in exam["keys"].items():
        full = [a if a else "-" for a in answers[:n]] + ["-"] * (len(questions) - n)
        key[set_name] = full
    path = exam["dir"] / "key.json"
    write_json(path, key)
    return path


def score_exam(exam: dict) -> str:
    """Run Stage 2. Returns a short status message."""
    results = exam["dir"] / "results.csv"
    scores = exam["dir"] / "scores.csv"
    if not results.exists():
        return "No scans processed yet."
    if not exam["keys"]:
        scores.unlink(missing_ok=True)
        return "Results saved. Enter the answer key to get scores."

    questions = get_layout(exam["layout"])["info"]["questions"]
    key_path = write_key_file(exam, questions)
    m = exam["marking"]
    cmd = [
        sys.executable, str(STAGE2),
        "--results", str(results), "--key", str(key_path), "--out", str(scores),
        "--correct", str(m["correct"]), "--wrong", str(m["wrong"]),
        "--blank", str(m["blank"]), "--multi", m["multi"], "--per-question",
    ]
    if m.get("partial"):
        cmd.append("--partial")
    if exam.get("roster"):
        cmd += ["--roster", str(exam["dir"] / "roster.csv")]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise PipelineError(f"Scoring failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return "Scores updated."


def merge_results(exam: dict, new_csv: Path) -> int:
    """Add Stage 1 rows for a batch to the exam's results.csv. Returns rows added."""
    path = exam["dir"] / "results.csv"
    header, rows = read_csv(path)
    new_header, new_rows = read_csv(new_csv)
    new_ids = {r["file_id"] for r in new_rows}
    rows = [r for r in rows if r["file_id"] not in new_ids] + new_rows
    write_csv(path, header or new_header, rows)
    return len(new_rows)


def update_sheet(exam: dict, file_id: str, values: dict) -> None:
    """Manual correction of one row in results.csv (marks it as reviewed)."""
    path = exam["dir"] / "results.csv"
    header, rows = read_csv(path)
    for r in rows:
        if r["file_id"] == file_id:
            for k, v in values.items():
                if k in header and k not in ("file_id", "check"):
                    r[k] = v.strip().upper()
            r["check"] = "REVIEWED"
            break
    else:
        raise PipelineError(f"Sheet '{file_id}' not found")
    write_csv(path, header, rows)


def delete_sheet(exam: dict, file_id: str) -> None:
    path = exam["dir"] / "results.csv"
    header, rows = read_csv(path)
    write_csv(path, header, [r for r in rows if r["file_id"] != file_id])
    for folder in ("uploads", "overlays"):
        (exam["dir"] / folder / safe_name(file_id)).unlink(missing_ok=True)


def exam_summary(exam: dict) -> dict:
    _, results = read_csv(exam["dir"] / "results.csv")
    header, scores = read_csv(exam["dir"] / "scores.csv")
    values = [float(r["score"]) for r in scores if r.get("score") not in ("", None)]
    return {
        "sheets": len(results),
        "scored": len(values),
        "mean": round(sum(values) / len(values), 2) if values else None,
        "max": max(values) if values else None,
        "min": min(values) if values else None,
        "flagged": sum(1 for r in scores if r.get("check") and r.get("image_id")) if scores
        else sum(1 for r in results if r.get("check")),
        "scores_header": header,
        "scores": scores,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Background jobs (scan processing)
# ---------------------------------------------------------------------------

_jobs: dict[str, dict] = {}
_queue: "queue.Queue[str]" = queue.Queue()
_exam_locks: dict[str, threading.Lock] = {}
_worker_started = False
_worker_lock = threading.Lock()


def exam_lock(exam_id: str) -> threading.Lock:
    with _worker_lock:
        return _exam_locks.setdefault(exam_id, threading.Lock())


def stage_uploads(exam: dict, files: list[tuple[str, bytes]]) -> Path:
    """Save uploaded files (images, PDFs, ZIPs of them) into a fresh batch folder."""
    batch = Path(tempfile.mkdtemp(prefix="batch_", dir=exam["dir"]))
    taken = {p.name.lower() for p in (exam["dir"] / "uploads").iterdir()}
    count = 0

    def add(name: str, data: bytes):
        nonlocal count
        name = safe_name(name)
        if Path(name).suffix.lower() in SCAN_EXTS and data:
            unique_path(batch, name, taken).write_bytes(data)
            count += 1

    for name, data in files:
        if Path(name).suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    for info in zf.infolist():
                        if not info.is_dir() and not Path(info.filename).name.startswith("."):
                            add(info.filename, zf.read(info))
            except zipfile.BadZipFile:
                shutil.rmtree(batch, ignore_errors=True)
                raise PipelineError(f"'{name}' is not a valid ZIP file")
        else:
            add(name, data)

    if count == 0:
        shutil.rmtree(batch, ignore_errors=True)
        raise PipelineError("No PNG, JPG or PDF scans found in the upload")
    return batch


def submit_scans(exam: dict, files: list[tuple[str, bytes]]) -> str:
    batch = stage_uploads(exam, files)
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {
        "id": job_id, "exam": exam["id"], "batch": str(batch),
        "files": sorted(p.name for p in batch.iterdir()),
        "status": "queued", "message": "Waiting to start...",
        "created": time.time(), "unread": [], "log": "",
    }
    _ensure_worker()
    _queue.put(job_id)
    return job_id


def get_job(job_id: str) -> dict | None:
    job = _jobs.get(job_id)
    return {k: v for k, v in job.items() if k != "batch"} if job else None


def active_job(exam_id: str) -> dict | None:
    for job in _jobs.values():
        if job["exam"] == exam_id and job["status"] in ("queued", "running"):
            return get_job(job["id"])
    return None


def _ensure_worker():
    global _worker_started
    with _worker_lock:
        if not _worker_started:
            threading.Thread(target=_worker, daemon=True).start()
            _worker_started = True


def _worker():
    while True:
        job_id = _queue.get()
        try:
            _run_job(_jobs[job_id])
        except Exception as e:  # keep the worker alive whatever happens
            _jobs[job_id].update(status="failed", message=str(e))
        finally:
            shutil.rmtree(_jobs[job_id]["batch"], ignore_errors=True)


def _run_job(job: dict) -> None:
    exam = get_exam(job["exam"])
    if exam is None:
        job.update(status="failed", message="Exam was deleted")
        return
    batch = Path(job["batch"])
    layout = get_layout(exam["layout"])
    job.update(status="running", message=f"Reading {len(job['files'])} scan(s)...")

    with exam_lock(exam["id"]):
        batch_csv = batch.parent / f"{batch.name}.csv"
        cmd = [
            sys.executable, str(STAGE1),
            "--scans", str(batch),
            "--template", str(layout["dir"] / "template.json"),
            "--out", str(batch_csv),
            "--overlays", str(exam["dir"] / "overlays"),
        ]
        if layout["has_config"]:
            cmd += ["--config", str(layout["dir"] / "config.json")]
        env = {**os.environ, "MPLBACKEND": "Agg", "PYTHONIOENCODING": "utf-8", "COLUMNS": "200"}
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=env)
        job["log"] = (proc.stdout + proc.stderr)[-20000:]

        if proc.returncode != 0 or not batch_csv.exists():
            batch_csv.unlink(missing_ok=True)
            job.update(status="failed", message="No sheets could be read. See the log for details.")
            _record(exam, job, 0)
            return

        added = merge_results(exam, batch_csv)
        batch_csv.unlink(missing_ok=True)
        for f in batch.iterdir():
            shutil.move(str(f), exam["dir"] / "uploads" / f.name)

        _, new_rows = read_csv(exam["dir"] / "results.csv")
        read_ids = {r["file_id"] for r in new_rows}
        job["unread"] = [
            f for f in job["files"]
            if f not in read_ids and not any(i.startswith(Path(f).stem) for i in read_ids)
        ]
        exam = get_exam(exam["id"])
        score_msg = score_exam(exam)
        msg = f"Read {added} sheet(s). {score_msg}"
        if job["unread"]:
            msg += f" {len(job['unread'])} file(s) could not be read."
        job.update(status="done", message=msg)
        _record(exam, job, added)


def _record(exam: dict, job: dict, added: int) -> None:
    exam = get_exam(exam["id"])
    exam.setdefault("history", []).insert(0, {
        "time": now(), "files": len(job["files"]), "read": added,
        "unread": job["unread"], "status": job["status"],
    })
    exam["history"] = exam["history"][:50]
    save_exam(exam)
