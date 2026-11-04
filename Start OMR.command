#!/bin/sh
# Double-click to open the OMR designer and evaluator in your browser.
cd "$(dirname "$0")" || exit 1
for py in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$py" >/dev/null 2>&1; then "$py" app/server.py && exit 0; break; fi
done
echo; echo "Could not start. Python 3.10+ is needed: https://www.python.org/downloads/"
printf "Press Return to close."; read -r _
