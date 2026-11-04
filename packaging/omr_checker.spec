# PyInstaller spec for OMR Checker: app/server.py with the built web app and the
# scans_to_csv reader, as "OMR Checker.app" (macOS) or "OMR Checker\" (Windows).
# Run through packaging/build.py, which also makes the .dmg / installer.
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "app" / "server.py").read_text()).group(1)
STAGE = ROOT / "scans_to_csv"
sys.path.insert(0, str(STAGE))  # so collect_submodules("src") below finds the reader's package

a = Analysis(
    [str(ROOT / "app" / "server.py")],
    pathex=[str(STAGE)],  # omr_to_csv and its src package
    datas=[
        (str(ROOT / "web" / "dist"), "web/dist"),
        (str(STAGE / "config.json"), "scans_to_csv"),
        (str(STAGE / "template.json"), "scans_to_csv"),
        (str(ROOT / "packaging" / "tray.png"), "packaging"),
    ],
    # the reader finds its image processors by walking its package, and pystray
    # picks its backend at run time; neither import is visible to the analysis
    # (src/processors has no __init__.py, so collect_submodules skips it: list it by file)
    hiddenimports=[
        "omr_to_csv", *collect_submodules("src"), *collect_submodules("pystray"),
        *(".".join(f.relative_to(STAGE).with_suffix("").parts) for f in (STAGE / "src" / "processors").rglob("*.py")),
    ],
    module_collection_mode={"src": "py"},  # plain .py files, so pkgutil.walk_packages sees them
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="OMR Checker",
    console=False,
    icon=str(ROOT / "packaging" / ("icon.icns" if sys.platform == "darwin" else "icon.ico")),
)
coll = COLLECT(exe, a.binaries, a.datas, name="OMR Checker")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="OMR Checker.app",
        icon=str(ROOT / "packaging" / "icon.icns"),
        bundle_identifier="in.omrchecker.app",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": "OMR Checker",
            "CFBundleShortVersionString": VERSION,
            "LSUIElement": True,  # a menu bar app: no Dock icon for a window that isn't there
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSHumanReadableCopyright": "Developed by Debanshu Ghosh and Aravind Sathesh",
        },
    )
