#!/usr/bin/env bash
# Double-click to start OMR Checker on macOS (or run ./omr_checker.command on Linux).
# The first start sets up a private Python environment in .venv and installs
# the requirements; later starts open the window straight away.
set -e
cd "$(dirname "$0")"
PY=.venv/bin/python

if [ ! -x "$PY" ]; then
  echo "First start: setting up OMR Checker. This takes a few minutes..."
  if ! command -v python3 >/dev/null; then
    echo "Python 3.10 or newer is needed: https://www.python.org/downloads/"
    read -r -p "Press Enter to close." _
    exit 1
  fi
  python3 -m venv .venv
fi

if ! "$PY" -c "import webview, quickjs, cv2, flask, waitress, pymupdf, pandas, screeninfo" 2>/dev/null; then
  echo "Installing requirements..."
  "$PY" -m pip install --disable-pip-version-check -q \
    -r scans_to_csv/requirements.txt -r app/requirements.txt opencv-contrib-python
fi

nohup "$PY" app/desktop.py >/dev/null 2>&1 &
