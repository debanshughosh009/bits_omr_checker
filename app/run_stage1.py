"""
Run Stage 1 (scans_to_csv/omr_to_csv.py) on a machine with no display.

The engine reads the monitor size when it is imported (screeninfo), which
fails inside a container. This wrapper provides a stand-in monitor when no
real one is available, then runs omr_to_csv.py unchanged with the same
command-line arguments.
"""

import os
import runpy
import sys
from pathlib import Path

import screeninfo

os.environ.setdefault("MPLBACKEND", "Agg")

try:
    screeninfo.get_monitors()[0]
except Exception:
    class _Monitor:
        width, height, x, y = 1920, 1080, 0, 0

    screeninfo.get_monitors = lambda: [_Monitor()]

STAGE1 = Path(__file__).resolve().parent.parent / "scans_to_csv" / "omr_to_csv.py"
sys.argv[0] = str(STAGE1)
runpy.run_path(str(STAGE1), run_name="__main__")
