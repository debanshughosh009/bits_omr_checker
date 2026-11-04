"""Build the OMR Checker app for this platform.

    python packaging/build.py

Run with a Python that has packaging/requirements.txt installed (3.12 is what the
release workflow uses), after `npm run build` in web/. Writes to release/:
  macOS    OMR-Checker-<version>-mac-<arch>.dmg   (the .app, with an Applications link)
  Windows  OMR-Checker-<version>-windows-setup.exe (needs Inno Setup's ISCC on PATH)"""
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "release"
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "app" / "server.py").read_text()).group(1)


def run(*cmd, **kw):
    print("+", " ".join(map(str, cmd)), flush=True)
    subprocess.run(list(map(str, cmd)), check=True, **kw)


def main():
    if not (ROOT / "web" / "dist" / "index.html").exists():
        sys.exit("Build the web app first: cd web && npm ci && npm run build")
    work = ROOT / "build" / "pyinstaller"
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", work / "dist", "--workpath", work / "work", ROOT / "packaging" / "omr_checker.spec")
    OUT.mkdir(exist_ok=True)

    if sys.platform == "darwin":
        arch = "arm64" if platform.machine() == "arm64" else "x64"
        stage = work / "dmg"
        shutil.rmtree(stage, ignore_errors=True)
        stage.mkdir()
        shutil.copytree(work / "dist" / "OMR Checker.app", stage / "OMR Checker.app", symlinks=True)
        os.symlink("/Applications", stage / "Applications")
        dmg = OUT / f"OMR-Checker-{VERSION}-mac-{arch}.dmg"
        dmg.unlink(missing_ok=True)
        run("hdiutil", "create", "-volname", "OMR Checker", "-srcfolder", stage, "-format", "UDZO", "-ov", dmg)
        print("built", dmg)
    elif os.name == "nt":
        iscc = shutil.which("ISCC") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
        run(iscc, f"/DAppVersion={VERSION}", f"/DSourceDir={work / 'dist' / 'OMR Checker'}", f"/O{OUT}",
            ROOT / "packaging" / "windows-installer.iss")
        print("built", OUT / f"OMR-Checker-{VERSION}-windows-setup.exe")
    else:
        print("built", work / "dist" / "OMR Checker")


if __name__ == "__main__":
    main()
