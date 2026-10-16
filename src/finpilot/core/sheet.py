"""Spreadsheet model behind the FinPilot Modeling Lab.

A ``Sheet`` holds raw cell contents (numbers, text or formulas), cell roles
(input / calculation / output / label / check), number formats and named
assumptions. It recalculates on every change, tracks precedents and
dependents, detects circular references and supports undo/redo.
The class has no UI dependencies.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from .formula import FUNCTIONS, CellError, Evaluator, FormulaSyntaxError, parse
from .formula.parser import Name, Node, Range, Ref, references, shift, to_formula
from .formula.refs import (MAX_COLS, MAX_ROWS, CellRef, a1_to_key, key_to_a1, parse_ref,
                           range_keys)

ROLES = ("input", "calc", "output", "label", "check", "")
FORMATS = ("general", "number", "number0", "currency", "currency0", "percent", "percent0", "date", "text")

Key = tuple[int, int]

if sys.getrecursionlimit() < 20000:
    sys.setrecursionlimit(20000)


@dataclass
class Cell:
    raw: str = ""                 # exactly what the learner typed
    role: str = ""                # input / calc / output / label / check
    fmt: str = "general"
    note: str = ""                # source / assumption documentation
    node: Optional[Node] = None   # parsed formula, if raw starts with '='
    parse_error: Optional[str] = None
    literal: Any = None           # parsed constant for non-formula cells

    @property
    def is_formula(self) -> bool:
        return self.raw.startswith("=")

    def to_dict(self) -> dict:
        d = {"raw": self.raw}
        if self.role:
            d["role"] = self.role
        if self.fmt != "general":
            d["fmt"] = self.fmt
        if self.note:
            d["note"] = self.note
        return d


def parse_literal(raw: str) -> Any:
    """Interpret typed text that is not a formula: number, percentage, bool or text."""
    s = raw.strip()
    if s == "":
        return None
    t = s.replace(",", "")
    neg = False
    if t.startswith("(") and t.endswith(")"):  # accounting negative (1,200)
        t, neg = t[1:-1], True
    for sym in ("$", "€", "£"):
        t = t.replace(sym, "")
    try:
        if t.endswith("%"):
            v = float(t[:-1]) / 100.0
        else:
            v = float(t)
        return -v if neg else v
    except ValueError:
        pass
    if s.upper() in ("TRUE", "FALSE"):
        return s.upper() == "TRUE"
    return raw


class Sheet:
    def __init__(self, name: str = "Model", rows: int = 60, cols: int = 16):
        self.name = name
        self.rows = min(rows, MAX_ROWS)
        self.cols = min(cols, MAX_COLS)
        self.cells: dict[Key, Cell] = {}
        self.names: dict[str, str] = {}          # NAME -> "B2" or "B2:M2"
        self._values: dict[Key, Any] = {}
        self._undo: list[list[tuple[Key, Optional[dict], Optional[dict]]]] = []
        self._redo: list[list[tuple[Key, Optional[dict], Optional[dict]]]] = []
        self._precedents: dict[Key, set[Key]] = {}
        self._dependents: dict[Key, set[Key]] = {}
        self.listeners: list = []

    # ----------------------------------------------------------- editing

    def get(self, key: Key) -> Cell:
        return self.cells.get(key) or Cell()

    def raw(self, a1: str) -> str:
        return self.get(a1_to_key(a1)).raw

    def set(self, a1_or_key, raw: str, *, role: Optional[str] = None, fmt: Optional[str] = None,
            note: Optional[str] = None, record: bool = True) -> None:
        self.set_many([(a1_or_key, raw, role, fmt, note)], record=record)

    def set_many(self, items: Iterable[tuple], record: bool = True) -> None:
        batch = []
        for item in items:
            a1_or_key, raw = item[0], item[1]
            role = item[2] if len(item) > 2 else None
            fmt = item[3] if len(item) > 3 else None
            note = item[4] if len(item) > 4 else None
            key = a1_to_key(a1_or_key) if isinstance(a1_or_key, str) else tuple(a1_or_key)
            self._check_bounds(key)
            before = self.cells[key].to_dict() if key in self.cells else None
            cell = self.cells.get(key) or Cell()
            new = Cell(raw=raw if raw is not None else cell.raw,
                       role=cell.role if role is None else role,
                       fmt=cell.fmt if fmt is None else fmt,
                       note=cell.note if note is None else note)
            self._store(key, new)
            after = self.cells[key].to_dict() if key in self.cells else None
            if before != after:
                batch.append((key, before, after))
        if batch and record:
            self._undo.append(batch)
            self._redo.clear()
        self.recalculate()

    def clear(self, key: Key) -> None:
        self.set(key, "", role="", fmt="general", note="")

    def _check_bounds(self, key: Key) -> None:
        r, c = key
        if not (0 <= r < MAX_ROWS and 0 <= c < MAX_COLS):
            raise IndexError(f"Cell {key} is outside the sheet")
        if r >= self.rows:
            self.rows = r + 1
        if c >= self.cols:
            self.cols = c + 1

    def _store(self, key: Key, cell: Cell) -> None:
        if cell.raw == "" and not cell.role and cell.fmt == "general" and not cell.note:
            self.cells.pop(key, None)
            return
        cell.node, cell.parse_error, cell.literal = None, None, None
        if cell.is_formula:
            try:
                cell.node = parse(cell.raw)
            except FormulaSyntaxError as e:
                cell.parse_error = str(e)
        else:
            cell.literal = parse_literal(cell.raw)
        self.cells[key] = cell

    def _restore(self, key: Key, state: Optional[dict]) -> None:
        if state is None:
            self.cells.pop(key, None)
        else:
            self._store(key, Cell(raw=state.get("raw", ""), role=state.get("role", ""),
                                  fmt=state.get("fmt", "general"), note=state.get("note", "")))

    def undo(self) -> bool:
        if not self._undo:
            return False
        batch = self._undo.pop()
        for key, before, _after in reversed(batch):
            self._restore(key, before)
        self._redo.append(batch)
        self.recalculate()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        batch = self._redo.pop()
        for key, _before, after in batch:
            self._restore(key, after)
        self._undo.append(batch)
        self.recalculate()
        return True

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def fill_right(self, source: Key, to_col: int) -> None:
        """Copy a cell's formula across a row, adjusting relative references."""
        self.fill(source, [(source[0], c) for c in range(source[1] + 1, to_col + 1)])

    def fill(self, source: Key, targets: Iterable[Key]) -> None:
        src = self.get(source)
        items = []
        for t in targets:
            if src.is_formula and src.node is not None:
                moved = shift(src.node, t[0] - source[0], t[1] - source[1])
                raw = "=" + to_formula(moved)
            else:
                raw = src.raw
            items.append((t, raw, src.role, src.fmt, None))
        self.set_many(items)

    # ------------------------------------------------------------- names

    def define_name(self, name: str, target: str) -> None:
        name = name.strip()
        if not name or not (name[0].isalpha() or name[0] == "_") or not all(
                ch.isalnum() or ch in "_." for ch in name):
            raise ValueError("Names must start with a letter and use only letters, digits, '_' or '.'.")
        from .formula.refs import is_ref
        if is_ref(name) or name.upper() in ("TRUE", "FALSE") or name.upper() in FUNCTIONS:
            raise ValueError(f"'{name}' looks like a cell reference, TRUE/FALSE or a function name.")
        parts = target.replace("$", "").split(":")
        for p in parts:
            parse_ref(p)
        self.names[name.upper()] = target.replace("$", "").upper()
        self.recalculate()

    def remove_name(self, name: str) -> None:
        self.names.pop(name.upper(), None)
        self.recalculate()

    def name_keys(self, name: str) -> list[Key]:
        target = self.names.get(name.upper())
        if not target:
            return []
        parts = target.split(":")
        if len(parts) == 1:
            return [a1_to_key(parts[0])]
        return [k for row in range_keys(parse_ref(parts[0]), parse_ref(parts[1])) for k in row]

    # -------------------------------------------------------- calculation

    def recalculate(self) -> None:
        self._values = {}
        self._precedents = {k: self._direct_precedents(c) for k, c in self.cells.items() if c.is_formula}
        self._dependents = {}
        for k, pres in self._precedents.items():
            for p in pres:
                self._dependents.setdefault(p, set()).add(k)
        self._visiting: set[Key] = set()
        # Evaluate in reading order so most precedents are already cached (keeps recursion shallow).
        for key in sorted(self.cells):
            self._value(key)
        for fn in list(self.listeners):
            fn()

    def _direct_precedents(self, cell: Cell) -> set[Key]:
        out: set[Key] = set()
        if cell.node is None:
            return out
        for n in references(cell.node):
            if isinstance(n, Ref) and n.ref.in_bounds():
                out.add(n.ref.key)
            elif isinstance(n, Range) and n.start.in_bounds() and n.end.in_bounds():
                out.update(k for row in range_keys(n.start, n.end) for k in row)
            elif isinstance(n, Name):
                out.update(self.name_keys(n.name))
        return out

    def _value(self, key: Key) -> Any:
        if key in self._values:
            return self._values[key]
        cell = self.cells.get(key)
        if cell is None:
            return None
        if not cell.is_formula:
            v = cell.literal
            if isinstance(v, int) and not isinstance(v, bool):
                v = float(v)
            self._values[key] = v
            return v
        if cell.parse_error:
            v = CellError("#PARSE!", cell.parse_error)
            self._values[key] = v
            return v
        if key in self._visiting:
            return CellError("#CIRC!", f"{key_to_a1(key)} depends on itself.")
        self._visiting.add(key)
        try:
            v = Evaluator(_SheetContext(self), FUNCTIONS).evaluate(cell.node)
        finally:
            self._visiting.discard(key)
        if isinstance(v, CellError) and v.code == "#CIRC!" and not v.detail.startswith(key_to_a1(key)):
            v = CellError("#CIRC!", f"{key_to_a1(key)} is part of a circular chain of references.")
        if isinstance(v, int) and not isinstance(v, bool):
            v = float(v)
        self._values[key] = v
        return v

    def value(self, a1_or_key) -> Any:
        key = a1_to_key(a1_or_key) if isinstance(a1_or_key, str) else a1_or_key
        return self._values.get(key, self._value(key) if key in self.cells else None)

    def precedents(self, key: Key) -> set[Key]:
        return set(self._precedents.get(key, set()))

    def dependents(self, key: Key) -> set[Key]:
        return set(self._dependents.get(key, set()))

    def all_dependents(self, key: Key) -> set[Key]:
        seen: set[Key] = set()
        stack = [key]
        while stack:
            for d in self._dependents.get(stack.pop(), ()):
                if d not in seen:
                    seen.add(d)
                    stack.append(d)
        return seen

    def errors(self) -> dict[Key, CellError]:
        return {k: v for k, v in self._values.items() if isinstance(v, CellError)}

    # ----------------------------------------------------- serialization

    def to_dict(self) -> dict:
        return {
            "name": self.name, "rows": self.rows, "cols": self.cols,
            "cells": {key_to_a1(k): c.to_dict() for k, c in sorted(self.cells.items())},
            "names": dict(self.names),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Sheet":
        s = cls(data.get("name", "Model"), int(data.get("rows", 60)), int(data.get("cols", 16)))
        for a1, cd in data.get("cells", {}).items():
            if isinstance(cd, str):
                cd = {"raw": cd}
            key = a1_to_key(a1)
            s._check_bounds(key)
            s._store(key, Cell(raw=str(cd.get("raw", "")), role=cd.get("role", ""),
                               fmt=cd.get("fmt", "general"), note=cd.get("note", "")))
        for n, t in data.get("names", {}).items():
            s.names[n.upper()] = t
        s.recalculate()
        return s


class _SheetContext:
    def __init__(self, sheet: Sheet):
        self.sheet = sheet

    def cell_value(self, ref: CellRef) -> Any:
        return self.sheet._value(ref.key)

    def name_value(self, name: str) -> Any:
        target = self.sheet.names.get(name.upper())
        if target is None:
            return CellError("#NAME?", f"'{name}' is not a defined name. Define it in the Names panel.")
        parts = target.split(":")
        if len(parts) == 1:
            return self.sheet._value(a1_to_key(parts[0]))
        from .formula.evaluator import RangeValue
        rows = [[self.sheet._value(k) for k in row]
                for row in range_keys(parse_ref(parts[0]), parse_ref(parts[1]))]
        return RangeValue(rows)


def explain(sheet: Sheet, key: Key) -> list[str]:
    """Plain-English walkthrough of how a cell gets its value."""
    from .format import format_value
    cell = sheet.get(key)
    a1 = key_to_a1(key)
    if not cell.raw:
        return [f"{a1} is empty. Blank cells count as 0 in arithmetic."]
    if not cell.is_formula:
        kind = "an input (a hard-coded value)" if cell.role == "input" else "a typed value"
        return [f"{a1} contains {kind}: {cell.raw}."]
    lines = [f"{a1} contains {cell.raw}"]
    if cell.parse_error:
        return lines + [f"The formula cannot be read: {cell.parse_error}"]
    pres = sorted(sheet.precedents(key))
    if pres:
        shown = pres[:12]
        vals = ", ".join(f"{key_to_a1(p)} = {format_value(sheet.value(p), sheet.get(p).fmt)}" for p in shown)
        more = f" (and {len(pres) - len(shown)} more)" if len(pres) > len(shown) else ""
        lines.append(f"It reads: {vals}{more}.")
    v = sheet.value(key)
    if isinstance(v, CellError):
        lines.append(f"Result: {v.code}. {v.explanation}")
        bad = [p for p in pres if isinstance(sheet.value(p), CellError)]
        if bad:
            lines.append("The error comes from: " + ", ".join(key_to_a1(b) for b in bad[:6]) + ".")
    else:
        lines.append(f"Result: {format_value(v, cell.fmt)}.")
    deps = sorted(sheet.dependents(key))
    if deps:
        lines.append("Cells that use this result: " + ", ".join(key_to_a1(d) for d in deps[:12]) + ".")
    return lines
