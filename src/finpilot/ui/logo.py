"""The FinPilot mark: a compass ring with a forward-pointing amber needle.

The needle points up and slightly right (north-east): guidance plus forward
progress. Drawn with QPainter so it is crisp at every size and needs no files.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

NAVY = QColor("#101D2B")
TEAL = QColor("#59D6C0")
AMBER = QColor("#F3B65B")
CREAM = QColor("#F5F1E8")


def paint_logo(p: QPainter, rect: QRectF, background: bool = True) -> None:
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    s = min(rect.width(), rect.height())
    cx, cy = rect.center().x(), rect.center().y()
    r = s / 2
    if background:
        p.setPen(Qt.NoPen)
        p.setBrush(NAVY)
        p.drawRoundedRect(QRectF(cx - r, cy - r, s, s), s * 0.22, s * 0.22)
    ring = r * 0.70
    pen = QPen(TEAL, max(1.0, s * 0.055))
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(cx, cy), ring, ring)
    # tick marks at the four cardinal points
    tick = QPen(TEAL, max(1.0, s * 0.04))
    p.setPen(tick)
    for ang in (0, 90, 180, 270):
        a = math.radians(ang)
        p.drawLine(QPointF(cx + math.cos(a) * ring * 0.80, cy + math.sin(a) * ring * 0.80),
                   QPointF(cx + math.cos(a) * ring * 0.98, cy + math.sin(a) * ring * 0.98))
    # needle rotated 35 degrees towards north-east
    p.translate(cx, cy)
    p.rotate(35)
    north = QPainterPath()
    north.moveTo(0, -ring * 0.92)
    north.lineTo(ring * 0.24, 0)
    north.lineTo(0, ring * 0.10)
    north.lineTo(-ring * 0.24, 0)
    north.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(AMBER))
    p.drawPath(north)
    south = QPainterPath()
    south.moveTo(0, ring * 0.72)
    south.lineTo(ring * 0.17, 0)
    south.lineTo(-ring * 0.17, 0)
    south.closeSubpath()
    p.setBrush(QBrush(CREAM))
    p.drawPath(south)
    p.setBrush(QBrush(NAVY))
    p.drawEllipse(QPointF(0, 0), ring * 0.09, ring * 0.09)
    p.restore()


def logo_pixmap(size: int = 64, background: bool = True) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    paint_logo(p, QRectF(0, 0, size, size), background)
    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(logo_pixmap(s))
    return icon


def write_icon_files(folder) -> list:
    """Render the logo to PNG and ICO files (used by the build script)."""
    from pathlib import Path
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    png = folder / "finpilot.png"
    logo_pixmap(512).save(str(png), "PNG")
    out.append(png)
    ico = folder / "finpilot.ico"
    logo_pixmap(256).save(str(ico), "ICO")
    out.append(ico)
    return out
