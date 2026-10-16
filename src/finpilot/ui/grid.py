"""Spreadsheet grid widget bound to a ``core.sheet.Sheet``."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QKeySequence
from PySide6.QtWidgets import QAbstractItemView, QApplication, QHeaderView, QTableView

from ..core.format import format_value
from ..core.formula import CellError, parse, shift, to_formula
from ..core.formula.refs import col_to_letters, key_to_a1
from ..core.sheet import Sheet
from .theme import palette


class SheetModel(QAbstractTableModel):
    def __init__(self, sheet: Sheet):
        super().__init__()
        self.sheet = sheet
        self.highlight: set[tuple[int, int]] = set()   # task target cells
        self.trace: set[tuple[int, int]] = set()       # precedents being traced
        self.locked: set[tuple[int, int]] = set()      # read-only cells (task mode)

    def set_sheet(self, sheet: Sheet):
        self.beginResetModel()
        self.sheet = sheet
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return self.sheet.rows

    def columnCount(self, parent=QModelIndex()):
        return self.sheet.cols

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        return col_to_letters(section) if orientation == Qt.Horizontal else str(section + 1)

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if (index.row(), index.column()) not in self.locked:
            f |= Qt.ItemIsEditable
        return f

    def data(self, index, role=Qt.DisplayRole):
        key = (index.row(), index.column())
        cell = self.sheet.cells.get(key)
        p = palette()
        if role == Qt.DisplayRole:
            if cell is None:
                return ""
            return format_value(self.sheet.value(key), cell.fmt)
        if role == Qt.EditRole:
            return cell.raw if cell else ""
        if role == Qt.TextAlignmentRole:
            v = self.sheet.value(key) if cell else None
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        if role == Qt.ForegroundRole:
            if cell is None:
                return None
            v = self.sheet.value(key)
            if isinstance(v, CellError):
                return QBrush(QColor(p.coral))
            if cell.role == "check":
                return QBrush(QColor(p.success if v is True else p.coral))
            if cell.role == "input":
                return QBrush(QColor(p.input_text))
            if cell.role == "label":
                return QBrush(QColor(p.text))
            return QBrush(QColor(p.text))
        if role == Qt.BackgroundRole:
            if key in self.trace:
                return QBrush(QColor(p.amber_soft))
            if key in self.highlight:
                return QBrush(QColor(p.output_bg if cell and cell.raw else p.amber_soft))
            if cell is None:
                return None
            v = self.sheet.value(key)
            if isinstance(v, CellError):
                return QBrush(QColor(p.coral_soft))
            if cell.role == "input":
                return QBrush(QColor(p.input_bg))
            if cell.role == "output":
                return QBrush(QColor(p.output_bg))
            return None
        if role == Qt.FontRole:
            if cell and (cell.role == "output" or (cell.role == "label" and key[1] == 0 and key[0] in (0, 6, 13, 21, 25))):
                f = QFont()
                f.setBold(True)
                return f
            return None
        if role == Qt.ToolTipRole:
            if cell is None:
                return None
            v = self.sheet.value(key)
            tip = []
            if cell.is_formula:
                tip.append(cell.raw)
            if isinstance(v, CellError):
                tip.append(f"{v.code}: {v.explanation}")
            if cell.note:
                tip.append("Source / note: " + cell.note)
            return "\n".join(tip) or None
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole:
            return False
        key = (index.row(), index.column())
        text = str(value)
        cell = self.sheet.get(key)
        role_ = cell.role or ("calc" if text.startswith("=") else "")
        if text.startswith("=") and cell.role == "input":
            role_ = "calc"
        self.sheet.set(key, text, role=role_)
        self.refresh()
        return True

    def refresh(self):
        self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount() - 1, self.columnCount() - 1))


class SheetView(QTableView):
    cell_selected = Signal(int, int)
    edited = Signal()

    def __init__(self, sheet: Sheet):
        super().__init__()
        self.model_ = SheetModel(sheet)
        self.setModel(self.model_)
        self.setSelectionMode(QAbstractItemView.ContiguousSelection)
        self.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed |
                             QAbstractItemView.AnyKeyPressed)
        self.horizontalHeader().setDefaultSectionSize(96)
        self.verticalHeader().setDefaultSectionSize(26)
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.setColumnWidth(0, 210)
        self.setAlternatingRowColors(False)
        self.selectionModel().currentChanged.connect(self._current)
        self.model_.dataChanged.connect(lambda *_: self.edited.emit())

    @property
    def sheet(self) -> Sheet:
        return self.model_.sheet

    def set_sheet(self, sheet: Sheet):
        self.model_.set_sheet(sheet)
        self.setColumnWidth(0, 210)

    def _current(self, cur, _prev):
        if cur.isValid():
            self.cell_selected.emit(cur.row(), cur.column())

    def current_key(self) -> Optional[tuple[int, int]]:
        i = self.currentIndex()
        return (i.row(), i.column()) if i.isValid() else None

    def selected_keys(self) -> list[tuple[int, int]]:
        return sorted({(i.row(), i.column()) for i in self.selectedIndexes()})

    def keyPressEvent(self, e):
        if e.matches(QKeySequence.Delete) or e.key() == Qt.Key_Backspace:
            keys = [k for k in self.selected_keys() if k not in self.model_.locked]
            if keys:
                self.sheet.set_many([(k, "") for k in keys])
                self.model_.refresh()
            return
        if e.matches(QKeySequence.Copy):
            self._copy()
            return
        if e.matches(QKeySequence.Paste):
            self._paste()
            return
        if e.matches(QKeySequence.Undo):
            self.undo()
            return
        if e.matches(QKeySequence.Redo):
            self.redo()
            return
        super().keyPressEvent(e)

    def undo(self):
        if self.sheet.undo():
            self.model_.refresh()

    def redo(self):
        if self.sheet.redo():
            self.model_.refresh()

    def fill_right(self) -> bool:
        keys = self.selected_keys()
        if not keys:
            return False
        rows = {}
        for r, c in keys:
            rows.setdefault(r, []).append(c)
        changed = False
        for r, cols in rows.items():
            cols.sort()
            if len(cols) < 2:
                continue
            targets = [(r, c) for c in cols[1:] if (r, c) not in self.model_.locked]
            self.sheet.fill((r, cols[0]), targets)
            changed = True
        self.model_.refresh()
        return changed

    # clipboard: formulas paste with relative references adjusted, like Excel
    def _copy(self):
        keys = self.selected_keys()
        if not keys:
            return
        r0 = min(k[0] for k in keys)
        c0 = min(k[1] for k in keys)
        r1 = max(k[0] for k in keys)
        c1 = max(k[1] for k in keys)
        lines = []
        for r in range(r0, r1 + 1):
            lines.append("\t".join(self.sheet.get((r, c)).raw for c in range(c0, c1 + 1)))
        QApplication.clipboard().setText("\n".join(lines))
        self._copy_origin = (r0, c0)

    def _paste(self):
        text = QApplication.clipboard().text()
        start = self.current_key()
        if not text or start is None:
            return
        origin = getattr(self, "_copy_origin", None)
        items = []
        for dr, line in enumerate(text.rstrip("\n").split("\n")):
            for dc, raw in enumerate(line.split("\t")):
                key = (start[0] + dr, start[1] + dc)
                if key in self.model_.locked:
                    continue
                if raw.startswith("=") and origin is not None:
                    try:
                        node = parse(raw)
                        src = (origin[0] + dr, origin[1] + dc)
                        raw = "=" + to_formula(shift(node, key[0] - src[0], key[1] - src[1]))
                    except Exception:
                        pass
                items.append((key, raw))
        if items:
            self.sheet.set_many(items)
            self.model_.refresh()

    def a1(self) -> str:
        k = self.current_key()
        return key_to_a1(k) if k else ""
