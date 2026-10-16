"""Reusable FinPilot UI components."""
from __future__ import annotations

from typing import Callable, Iterable, Optional

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QPushButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from .theme import palette


class FlowLayout(QLayout):
    """Lays widgets out left to right and wraps to the next line when space runs out."""

    def __init__(self, parent=None, spacing: int = 6):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        w, h = 0, 0
        for it in self._items:
            hint = it.sizeHint()
            w += hint.width() + self._spacing
            h = max(h, hint.height())
        m = self.contentsMargins()
        return QSize(max(0, w - self._spacing) + m.left() + m.right(), h + m.top() + m.bottom())

    def minimumSize(self):
        size = QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect, test_only):
        x, y, line_h = rect.x(), rect.y(), 0
        for it in self._items:
            if it.widget() is not None and not it.widget().isVisibleTo(it.widget().parentWidget()):
                continue
            hint = it.sizeHint()
            nx = x + hint.width() + self._spacing
            if nx - self._spacing > rect.x() + rect.width() and line_h > 0:
                x, y = rect.x(), y + line_h + self._spacing
                nx = x + hint.width() + self._spacing
                line_h = 0
            if not test_only:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x = nx
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y()


def label(text: str = "", kind: str = "", wrap: bool = True, rich: bool = False) -> QLabel:
    lab = QLabel(text)
    if kind:
        lab.setObjectName(kind)
    lab.setWordWrap(wrap)
    if rich:
        lab.setTextFormat(Qt.RichText)
        lab.setOpenExternalLinks(False)
    lab.setTextInteractionFlags(Qt.TextSelectableByMouse if not rich else Qt.TextBrowserInteraction)
    return lab


def button(text: str, kind: str = "", on_click: Optional[Callable] = None, tooltip: str = "") -> QPushButton:
    b = QPushButton(text.replace("&", "&&"))  # '&' is a literal (F&B), not a keyboard mnemonic
    if kind:
        b.setObjectName(kind)
    b.setCursor(Qt.PointingHandCursor)
    if on_click:
        b.clicked.connect(on_click)
    if tooltip:
        b.setToolTip(tooltip)
    return b


def hbox(*widgets, spacing: int = 8, margins=(0, 0, 0, 0), stretch_end: bool = False) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for w in widgets:
        _add(lay, w)
    if stretch_end:
        lay.addStretch(1)
    return lay


def vbox(*widgets, spacing: int = 8, margins=(0, 0, 0, 0), stretch_end: bool = False) -> QVBoxLayout:
    lay = QVBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for w in widgets:
        _add(lay, w)
    if stretch_end:
        lay.addStretch(1)
    return lay


def _add(lay, w):
    if w is None:
        return
    if w == "stretch":
        lay.addStretch(1)
    elif isinstance(w, QLayout):
        lay.addLayout(w)
    elif isinstance(lay, QHBoxLayout) and isinstance(w, QLabel) and w.wordWrap():
        lay.addWidget(w, 10)  # wrapping text takes the free width instead of collapsing to a narrow column
    else:
        lay.addWidget(w)


class Card(QFrame):
    def __init__(self, kind: str = "Card", padding: int = 18, spacing: int = 10):
        super().__init__()
        self.setObjectName(kind)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(padding, padding, padding, padding)
        self.lay.setSpacing(spacing)

    def add(self, *widgets) -> "Card":
        for w in widgets:
            _add(self.lay, w)
        return self


class Page(QWidget):
    """Scrollable page with a header (eyebrow, title, subtitle) and a content column."""

    def __init__(self, title: str, subtitle: str = "", eyebrow: str = "", scroll: bool = True):
        super().__init__()
        self.setObjectName("Page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        inner = QWidget()
        inner.setObjectName("PageInner")
        self.body = QVBoxLayout(inner)
        self.body.setContentsMargins(32, 26, 32, 26)
        self.body.setSpacing(16)
        head = QVBoxLayout()
        head.setSpacing(2)
        self.eyebrow = label(eyebrow.upper(), "Eyebrow")
        self.eyebrow.setVisible(bool(eyebrow))
        head.addWidget(self.eyebrow)
        self.title = label(title, "H1")
        head.addWidget(self.title)
        self.subtitle = label(subtitle, "Muted")
        self.subtitle.setVisible(bool(subtitle))
        head.addWidget(self.subtitle)
        self.header = head
        self.body.addLayout(head)
        if scroll:
            sa = QScrollArea()
            sa.setObjectName("PageScroll")
            sa.setWidgetResizable(True)
            sa.setWidget(inner)
            sa.setFrameShape(QFrame.NoFrame)
            outer.addWidget(sa)
        else:
            outer.addWidget(inner)

    def add(self, *widgets):
        for w in widgets:
            _add(self.body, w)

    def refresh(self):  # pages override
        pass


def clear_layout(lay: QLayout) -> None:
    while lay.count():
        item = lay.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


class StatTile(QFrame):
    def __init__(self, caption: str, value: str = "", note: str = ""):
        super().__init__()
        self.setObjectName("Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(2)
        self.caption = label(caption, "Muted")
        self.value = label(value, "Big", wrap=False)
        self.note = label(note, "Muted")
        lay.addWidget(self.caption)
        lay.addWidget(self.value)
        lay.addWidget(self.note)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def set(self, value: str, note: str = "", tone: str = ""):
        self.value.setText(value)
        self.note.setText(note)
        p = palette()
        color = {"good": p.success, "bad": p.coral, "warn": p.amber}.get(tone, p.text)
        self.value.setStyleSheet(f"color: {color};")


class Feedback(QFrame):
    """Feedback banner for answers and checks."""

    def __init__(self):
        super().__init__()
        self.setObjectName("FeedbackInfo")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(4)
        self.title = label("", "H3")
        self.msg = label("", "Body", rich=True)
        self.extra = label("", "Muted", rich=True)
        lay.addWidget(self.title)
        lay.addWidget(self.msg)
        lay.addWidget(self.extra)
        self.hide()

    def show_result(self, ok: Optional[bool], title: str, message: str, extra: str = ""):
        self.setObjectName("FeedbackGood" if ok else ("FeedbackBad" if ok is False else "FeedbackInfo"))
        self.style().unpolish(self)
        self.style().polish(self)
        self.title.setText(("✓ " if ok else ("✗ " if ok is False else "")) + title)
        self.msg.setText(message)
        self.extra.setText(extra)
        self.extra.setVisible(bool(extra))
        self.show()


class ProgressRing(QWidget):
    def __init__(self, size: int = 96, thickness: int = 9):
        super().__init__()
        self._v = 0.0
        self._text = "0%"
        self._sub = ""
        self.thickness = thickness
        self.on_dark = False  # set when drawn on a navy Hero card
        self.setFixedSize(size, size)

    def set(self, value: float, text: Optional[str] = None, sub: str = ""):
        self._v = max(0.0, min(1.0, value))
        self._text = text if text is not None else f"{self._v:.0%}"
        self._sub = sub
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = palette()
        m = self.thickness / 2 + 1
        rect = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)
        pen = QPen(QColor("#2A3B4F" if self.on_dark else pal.border), self.thickness)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, 0, 360 * 16)
        pen.setColor(QColor(pal.accent))
        p.setPen(pen)
        p.drawArc(rect, 90 * 16, int(-self._v * 360 * 16))
        p.setPen(QColor("#FFFFFF" if self.on_dark else pal.text))
        f = QFont(self.font())
        f.setPointSizeF(13 if self.width() > 80 else 10)
        f.setBold(True)
        p.setFont(f)
        p.drawText(self.rect().adjusted(0, -8 if self._sub else 0, 0, 0), Qt.AlignCenter, self._text)
        if self._sub:
            f.setPointSizeF(7.5)
            f.setBold(False)
            p.setFont(f)
            p.setPen(QColor("#C9D3DD" if self.on_dark else pal.muted))
            p.drawText(self.rect().adjusted(0, 22, 0, 0), Qt.AlignCenter, self._sub)


class StepTrack(QWidget):
    """Horizontal progress through the ten lesson steps."""

    clicked = Signal(int)

    def __init__(self, names: list[str]):
        super().__init__()
        self.names = names
        self.current = 0
        self.reached = 0
        self.setMinimumHeight(46)
        self.setMouseTracking(True)

    def set(self, current: int, reached: int):
        self.current, self.reached = current, max(reached, current)
        self.update()

    def sizeHint(self):
        return QSize(600, 46)

    def minimumSizeHint(self):
        return QSize(320, 46)

    def _pos(self, i):
        n = len(self.names)
        w = self.width() - 70
        return 35 + (w * i / (n - 1) if n > 1 else 0)

    def mousePressEvent(self, e):
        for i in range(len(self.names)):
            if abs(e.position().x() - self._pos(i)) < 14 and i <= self.reached:
                self.clicked.emit(i)
                return

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = palette()
        y = 14
        p.setPen(QPen(QColor(pal.border), 3))
        p.drawLine(int(self._pos(0)), y, int(self._pos(len(self.names) - 1)), y)
        if self.reached > 0:
            p.setPen(QPen(QColor(pal.accent), 3))
            p.drawLine(int(self._pos(0)), y, int(self._pos(self.reached)), y)
        f = QFont(self.font())
        f.setPointSizeF(7.5)
        p.setFont(f)
        for i, n in enumerate(self.names):
            x = self._pos(i)
            done = i < self.reached
            cur = i == self.current
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(pal.accent if (done or cur) else pal.surface))
            r = 7 if cur else 5
            if not (done or cur):
                p.setPen(QPen(QColor(pal.border), 2))
            p.drawEllipse(QRectF(x - r, y - r, 2 * r, 2 * r))
            p.setPen(QColor(pal.text if cur else pal.muted))
            p.drawText(QRectF(x - 40, y + 10, 80, 16), Qt.AlignHCenter | Qt.AlignTop, n)


class ChipGroup(QWidget):
    changed = Signal(str)

    def __init__(self, options: Iterable[tuple[str, str]], value: str = ""):
        super().__init__()
        lay = FlowLayout(self)
        self.buttons: dict[str, QPushButton] = {}
        for key, text in options:
            b = QPushButton(text.replace("&", "&&"))
            b.setObjectName("Chip")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.set_value(k, emit=True))
            lay.addWidget(b)
            self.buttons[key] = b
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.set_value(value or next(iter(self.buttons)), emit=False)

    def set_value(self, key: str, emit: bool = True):
        self.value = key
        for k, b in self.buttons.items():
            b.setChecked(k == key)
        if emit:
            self.changed.emit(key)


def divider() -> QFrame:
    d = QFrame()
    d.setObjectName("Divider")
    return d


def grid(items: list[QWidget], columns: int, spacing: int = 12) -> QGridLayout:
    g = QGridLayout()
    g.setSpacing(spacing)
    for i, w in enumerate(items):
        g.addWidget(w, i // columns, i % columns)
    return g


def status_dot(status: str) -> str:
    p = palette()
    return {"mastered": p.success, "completed": p.accent_text, "in_progress": p.amber, "available": p.text,
            "locked": p.muted}.get(status, p.muted)
