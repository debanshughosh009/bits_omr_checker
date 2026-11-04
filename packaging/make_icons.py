"""Draw the app icons from lucide's BadgeCheck: white on a dark rounded square.

    .venv/bin/python packaging/make_icons.py

Writes icon.png (1024 px), icon.icns (macOS, needs iconutil), icon.ico (Windows)
and tray.png (menu bar / notification area) beside this script. Run it again only
if the icon changes; the results are committed."""
import shutil
import subprocess
import tempfile
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
BADGE = ('<path d="M3.85 8.62a4 4 0 0 1 4.78-4.77 4 4 0 0 1 6.74 0 4 4 0 0 1 4.78 4.78 4 4 0 0 1 0 6.74 '
         '4 4 0 0 1-4.77 4.78 4 4 0 0 1-6.75 0 4 4 0 0 1-4.78-4.77 4 4 0 0 1 0-6.76Z"/><path d="m16 9-5.5 5.5L8 12"/>')


def render(size: int, inset: float, radius: float, glyph: float = 0.58) -> Image.Image:
    """The badge on a rounded square that leaves `inset` of the canvas free on each side (macOS icon grid)."""
    s = 1024
    pad = round(s * inset)
    img = Image.new("RGBA", (s, s))
    ImageDraw.Draw(img).rounded_rectangle((pad, pad, s - pad - 1, s - pad - 1), radius=round((s - 2 * pad) * radius), fill="#18181b")
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{s}" height="{s}" viewBox="0 0 {s} {s}">
<g transform="translate({s * (0.5 - glyph / 2)} {s * (0.5 - glyph / 2)}) scale({s * glyph / 24})" fill="none" stroke="#fafafa"
   stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{BADGE}</g></svg>'''
    pix = pymupdf.open(stream=svg.encode(), filetype="svg")[0].get_pixmap(alpha=True)
    img.alpha_composite(Image.frombytes("RGBA", (pix.width, pix.height), pix.samples))
    return img.resize((size, size), Image.LANCZOS)


app = render(1024, 0.1, 0.225)
app.save(HERE / "icon.png")
render(256, 0.0, 0.2).save(HERE / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
render(64, 0.0, 0.25, glyph=0.74).save(HERE / "tray.png")

if shutil.which("iconutil"):
    with tempfile.TemporaryDirectory() as d:
        iconset = Path(d) / "icon.iconset"
        iconset.mkdir()
        for px in (16, 32, 128, 256, 512):
            app.resize((px, px), Image.LANCZOS).save(iconset / f"icon_{px}x{px}.png")
            app.resize((px * 2, px * 2), Image.LANCZOS).save(iconset / f"icon_{px}x{px}@2x.png")
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "icon.icns")], check=True)
print("icons written to", HERE)
