"""Regenerate src/finpilot/assets/finpilot.png and a multi-size finpilot.ico from the drawn logo."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from finpilot.ui.logo import write_icon_files  # noqa: E402

app = QApplication([])
assets = ROOT / "src" / "finpilot" / "assets"
png, ico = write_icon_files(assets)
try:
    from PIL import Image
    Image.open(png).save(ico, sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
except ImportError:
    print("Pillow not installed: wrote a single-size 256px icon.")
print("Wrote", png, ico)
