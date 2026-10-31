"""
OMR Checker desktop app.

Opens the designer / professor UI in its own window (pywebview: Edge WebView2
on Windows, WebKit on macOS, GTK/Qt on Linux). The pages are served to that
window only, from 127.0.0.1 on a free port, and everything stops when the
window is closed.

Start it with the launcher in the repository root ("OMR Checker.bat" on
Windows, "omr_checker.command" on macOS/Linux), or:

    python app/desktop.py
"""

import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

import webview
from waitress import create_server

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import app as flask_app  # noqa: E402
import pipeline as pl  # noqa: E402

TITLE = "OMR Checker"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def open_in_file_manager(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])


class Api:
    """Called from app/static/desktop.js as window.pywebview.api.<name>()."""

    def __init__(self, origin: str):
        self._origin = origin

    def open_window(self, url: str, title: str = TITLE) -> None:
        """Scan images and previews (links marked target=_blank) get their own window."""
        if url.startswith(self._origin + "/"):
            webview.create_window(f"{title} · {TITLE}", url, width=1000, height=900)

    def open_folder(self, kind: str, item_id: str) -> None:
        item = pl.get_exam(item_id) if kind == "exam" else pl.get_layout(item_id) if kind == "layout" else None
        if item:
            open_in_file_manager(item["dir"])


def main():
    port = int(os.environ.get("OMR_PORT") or free_port())
    server = create_server(flask_app, host="127.0.0.1", port=port, threads=8,
                           max_request_body_size=flask_app.config["MAX_CONTENT_LENGTH"])
    threading.Thread(target=server.run, daemon=True).start()

    origin = f"http://127.0.0.1:{port}"
    webview.settings["ALLOW_DOWNLOADS"] = True              # CSVs, ZIPs and sheet PDFs (Save dialog)
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    webview.create_window(TITLE, origin + "/", js_api=Api(origin), width=1280, height=860, min_size=(900, 600))
    print(f"{TITLE} running (data: {pl.DATA_DIR}); close the window to quit")
    webview.start(private_mode=False, storage_path=str(pl.DATA_DIR / ".webview"))
    server.close()


if __name__ == "__main__":
    main()
