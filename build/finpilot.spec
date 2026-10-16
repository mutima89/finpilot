# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for FinPilot (one-folder build: fast start-up, no temp extraction).
# Run from the repository root:  pyinstaller --noconfirm --clean build/finpilot.spec
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
PKG = SRC / "finpilot"
IS_WIN = sys.platform == "win32"

datas = [
    (str(PKG / "curriculum" / "content"), "finpilot/curriculum/content"),
    (str(PKG / "assets"), "finpilot/assets"),
]

a = Analysis(
    [str(ROOT / "build" / "launch_finpilot.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=["matplotlib.backends.backend_qtagg", "finpilot.ui.pages.lab", "finpilot.ui.pages.lesson",
                   "finpilot.ui.pages.simulation"],
    hookspath=[],
    runtime_hooks=[],
    # Not used by FinPilot: keep the bundle small.
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "pandas", "scipy", "IPython", "pytest",
              "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick",
              "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FinPilot",
    icon=str(PKG / "assets" / "finpilot.ico") if IS_WIN else None,
    version=str(ROOT / "build" / "version_info.txt") if IS_WIN else None,
    console=False,            # GUI app: no console window
    disable_windowed_traceback=False,
    upx=False,                # UPX-packed files trigger antivirus false positives
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="FinPilot")
