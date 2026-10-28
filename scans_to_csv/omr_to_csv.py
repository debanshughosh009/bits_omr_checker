"""
omr_to_csv.py – Stage 1 wrapper
================================
Reads scanned OMR answer sheets and writes the marked options to a CSV.

Usage:
    python omr_to_csv.py --scans <folder> --template <template.json> --out <results.csv>
                         [--config <config.json>] [--overlays <dir>] [--keep-work]

The wrapper builds a temporary working directory that matches the layout
OMRChecker expects, runs the engine, collects results, produces a clean CSV,
and removes the temp folder (unless --keep-work is set).
"""

import argparse
import csv
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


def validate_template(template_path: Path) -> dict:
    """Load and sanity-check template.json."""
    if not template_path.exists():
        print(f"ERROR: Template file not found: {template_path}", file=sys.stderr)
        sys.exit(1)
    try:
        with open(template_path, "r") as f:
            tpl = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in template: {e}", file=sys.stderr)
        sys.exit(1)

    for key in ("pageDimensions", "fieldBlocks", "outputColumns"):
        if key not in tpl:
            print(f"ERROR: Template missing required key '{key}'", file=sys.stderr)
            sys.exit(1)
    return tpl


def collect_scan_files(scans_path: Path) -> list[Path]:
    """Return sorted list of image/PDF files from the scans path."""
    exts = {".png", ".jpg", ".jpeg", ".pdf"}
    if scans_path.is_file():
        if scans_path.suffix.lower() in exts:
            return [scans_path]
        else:
            print(f"ERROR: '{scans_path}' is not a supported image/PDF file.", file=sys.stderr)
            sys.exit(1)

    if not scans_path.is_dir():
        print(f"ERROR: Scans path does not exist: {scans_path}", file=sys.stderr)
        sys.exit(1)

    files = sorted(
        f for f in scans_path.iterdir()
        if f.is_file() and f.suffix.lower() in exts
    )
    if not files:
        print(f"ERROR: No image/PDF files found in '{scans_path}'", file=sys.stderr)
        sys.exit(1)
    return files


def build_work_dir(
    scan_files: list[Path],
    template_path: Path,
    config_path: Path | None,
    work_root: Path,
) -> Path:
    """
    Build a temporary directory tree that OMRChecker expects:
        work_root/
            template.json
            config.json       (optional)
            inputs/
                <scan copies>
    Returns the work_root path.
    """
    work_root.mkdir(parents=True, exist_ok=True)
    inputs_dir = work_root / "inputs"
    inputs_dir.mkdir(exist_ok=True)

    # Copy template. A designer template's "idColumns" lists the ID's fixed
    # characters among its bubbled columns; the engine reads the bubbled columns
    # one by one and clean_csv puts the ID back together.
    tpl = json.loads(template_path.read_text())
    if "idColumns" in tpl:
        engine_tpl = {k: v for k, v in tpl.items() if k not in ("idColumns", "customLabels")}
        bubbled = [c for c in tpl["idColumns"] if len(c) > 1]
        engine_tpl["outputColumns"] = [x for c in tpl["outputColumns"] for x in (bubbled if c == "ID NO" else [c])]
        (work_root / "template.json").write_text(json.dumps(engine_tpl, indent=2))
    else:
        shutil.copy2(template_path, work_root / "template.json")

    # CropOnMarkers needs its marker image beside the template. Sheets from
    # designer/ name one that is not saved with the template, so draw it.
    for p in tpl.get("preProcessors", []):
        rel = p.get("options", {}).get("relativePath")
        if p.get("name") == "CropOnMarkers" and rel:
            src = template_path.parent / rel
            if src.exists():
                shutil.copy2(src, work_root / rel)
            else:
                write_marker(work_root / rel)

    # Copy config (optional)
    if config_path and config_path.exists():
        shutil.copy2(config_path, work_root / "config.json")

    # Copy / link scans
    for f in scan_files:
        dst = inputs_dir / f.name
        if not dst.exists():
            shutil.copy2(f, dst)

    return work_root


def write_marker(path: Path, size: int = 200) -> None:
    """Draw the designer's corner marker: black square, white at 62.5%, black at 31.25%.
    Keep in step with MARKER_RINGS in designer/sheet.js."""
    import cv2
    import numpy as np

    img = np.zeros((size, size), np.uint8)
    for i, k in enumerate((1, 0.625, 0.3125)):
        a = round(size * k)
        o = (size - a) // 2
        img[o:o + a, o:o + a] = 255 if i % 2 else 0
    cv2.imwrite(str(path), img)


def run_omr_engine(work_dir: Path, output_dir: Path) -> Path:
    """
    Run OMRChecker's entry_point on the work directory.
    Returns the path to the Results CSV that was created.
    """
    # Ensure src is importable from the scans_to_csv directory
    stage_dir = Path(__file__).resolve().parent
    if str(stage_dir) not in sys.path:
        sys.path.insert(0, str(stage_dir))

    from src.entry import entry_point

    args = {
        "output_dir": str(output_dir),
        "debug": True,      # True disables tracebacks (matches original logic)
        "setLayout": False,
        "autoAlign": False,
    }
    entry_point(work_dir, args)

    # Find the Results CSV
    results_dir = output_dir / "Results"
    if not results_dir.exists():
        # OMRChecker creates outputs relative to input hierarchy.
        # Walk looking for the Results folder.
        for root, dirs, _files in os.walk(output_dir):
            if "Results" in dirs:
                results_dir = Path(root) / "Results"
                break

    csv_files = sorted(results_dir.glob("Results_*.csv")) if results_dir.exists() else []
    if not csv_files:
        print("ERROR: OMRChecker did not produce a Results CSV.", file=sys.stderr)
        sys.exit(1)

    return csv_files[-1]  # most recent


def clean_csv(
    raw_csv_path: Path,
    output_columns: list[str],
    out_path: Path,
    scan_count: int,
    id_columns: list[str] | None = None,
) -> None:
    """
    Read the raw OMRChecker Results CSV and write a clean output CSV.
    Columns: file_id, <outputColumns from template>, check
    """
    import pandas as pd

    df = pd.read_csv(raw_csv_path, dtype=str)
    df.columns = df.columns.str.strip().str.strip('"')
    if id_columns:  # one-character entries are fixed, the rest are bubbled column labels
        df = df.fillna("")
        # a list, not df.apply: apply returns a DataFrame when every sheet failed and df is empty
        df["ID NO"] = ["".join(c if len(c) == 1 else r.get(c, "") for c in id_columns) for _, r in df.iterrows()]
    id_len = len(id_columns) if id_columns else 13

    # Determine columns to keep
    keep = ["file_id"] + output_columns
    for col in keep:
        if col not in df.columns:
            df[col] = ""

    clean = df[keep].copy()
    clean = clean.fillna("")  # NaN -> empty string

    # Build 'check' column
    checks = []
    for _, row in clean.iterrows():
        notes = []

        # Multi-marked questions
        multi_qs = []
        for col in output_columns:
            val = str(row.get(col, "")).strip()
            if len(val) > 1 and col.startswith("q"):
                multi_qs.append(col)
        if multi_qs:
            notes.append(f"MULTI({','.join(multi_qs)})")

        # ID length check (if ID NO column exists)
        if "ID NO" in output_columns:
            id_val = str(row.get("ID NO", "")).strip()
            if id_val and len(id_val) != id_len:
                notes.append(f"ID_LEN({len(id_val)}/{id_len})")

        # Set check
        if "Set" in output_columns:
            set_val = str(row.get("Set", "")).strip()
            if not set_val:
                notes.append("NO_SET")

        # All blank
        q_cols = [c for c in output_columns if c.startswith("q")]
        all_blank = all(str(row.get(c, "")).strip() == "" for c in q_cols) if q_cols else False
        if all_blank:
            notes.append("ALL_BLANK")

        checks.append(", ".join(notes))

    clean["check"] = checks

    # Write
    clean.to_csv(out_path, index=False, quoting=csv.QUOTE_NONNUMERIC)
    print(f"\nResults written to: {out_path}")
    print(f"  Rows: {len(clean)}  (input scan/page count: {scan_count})")

    # Warn if row count doesn't match
    if len(clean) != scan_count:
        print(
            f"  WARNING: Row count ({len(clean)}) differs from input file count "
            f"({scan_count}). Some files may have failed or PDFs had multiple pages.",
            file=sys.stderr,
        )


def main():
    stage_dir = Path(__file__).resolve().parent
    repo_root = stage_dir.parent

    default_scans = repo_root / "input" if (repo_root / "input").exists() else stage_dir / "input"
    default_out = repo_root / "output" / "results.csv"
    default_template = stage_dir / "template.json"
    default_config = stage_dir / "config.json" if (stage_dir / "config.json").exists() else None

    parser = argparse.ArgumentParser(
        description="Read scanned OMR answer sheets and write marked options to CSV."
    )
    parser.add_argument(
        "--scans",
        default=str(default_scans),
        help=f"Path to a folder of scans (JPG, PNG, PDF) or a single file. (Default: {default_scans})",
    )
    parser.add_argument(
        "--template",
        default=str(default_template),
        help=f"Path to template.json describing the OMR sheet. (Default: {default_template})",
    )
    parser.add_argument(
        "--out",
        default=str(default_out),
        help=f"Output CSV file path. (Default: {default_out})",
    )
    parser.add_argument(
        "--config",
        default=str(default_config) if default_config else None,
        help="Optional path to config.json for detection tuning.",
    )
    parser.add_argument(
        "--overlays",
        default=None,
        help="Directory to copy annotated overlay images into.",
    )
    parser.add_argument(
        "--keep-work",
        action="store_true",
        default=False,
        help="Keep the temporary working directory after processing.",
    )
    args = parser.parse_args()

    scans_path = Path(args.scans).resolve()
    template_path = Path(args.template).resolve()
    out_path = Path(args.out).resolve()
    config_path = Path(args.config).resolve() if args.config else None

    # Validate
    tpl = validate_template(template_path)
    scan_files = collect_scan_files(scans_path)
    output_columns = tpl["outputColumns"]

    print(f"Found {len(scan_files)} scan file(s)")
    print(f"Template columns: {', '.join(output_columns)}")

    # Build work directory
    work_dir = Path(tempfile.mkdtemp(prefix="omr_work_"))
    print(f"Working directory: {work_dir}")

    try:
        build_work_dir(scan_files, template_path, config_path, work_dir)

        # Set up engine output directory
        engine_output_dir = work_dir / "engine_output"
        engine_output_dir.mkdir(exist_ok=True)

        # Run OMRChecker
        raw_csv = run_omr_engine(work_dir, engine_output_dir)

        # Produce clean CSV
        out_path.parent.mkdir(parents=True, exist_ok=True)
        clean_csv(raw_csv, output_columns, out_path, len(scan_files), tpl.get("idColumns"))

        # Copy overlays if requested
        if args.overlays:
            overlays_dst = Path(args.overlays).resolve()
            overlays_dst.mkdir(parents=True, exist_ok=True)
            checked_dir = None
            for root, dirs, _files in os.walk(engine_output_dir):
                if "CheckedOMRs" in dirs:
                    checked_dir = Path(root) / "CheckedOMRs"
                    break
            if checked_dir and checked_dir.exists():
                for img in checked_dir.iterdir():
                    if img.is_file():
                        shutil.copy2(img, overlays_dst / img.name)
                print(f"Overlays copied to: {overlays_dst}")
            else:
                print("No overlay images found (CheckedOMRs directory missing).")

    finally:
        if not args.keep_work:
            shutil.rmtree(work_dir, ignore_errors=True)
            print("Temp working directory cleaned up.")
        else:
            print(f"Working directory kept at: {work_dir}")


if __name__ == "__main__":
    main()
