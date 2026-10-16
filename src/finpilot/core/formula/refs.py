"""A1-style cell reference helpers (0-based row/col internally)."""
from __future__ import annotations

import re
from dataclasses import dataclass

MAX_ROWS = 500
MAX_COLS = 52  # A..AZ

_REF_RE = re.compile(r"^(\$?)([A-Za-z]{1,3})(\$?)(\d+)$")


def col_to_letters(col: int) -> str:
    if col < 0:
        raise ValueError("negative column")
    s = ""
    col += 1
    while col:
        col, r = divmod(col - 1, 26)
        s = chr(65 + r) + s
    return s


def letters_to_col(letters: str) -> int:
    n = 0
    for ch in letters.upper():
        n = n * 26 + (ord(ch) - 64)
    return n - 1


@dataclass(frozen=True)
class CellRef:
    row: int
    col: int
    abs_row: bool = False
    abs_col: bool = False

    @property
    def key(self) -> tuple[int, int]:
        return (self.row, self.col)

    def a1(self) -> str:
        return (("$" if self.abs_col else "") + col_to_letters(self.col)
                + ("$" if self.abs_row else "") + str(self.row + 1))

    def plain(self) -> str:
        return col_to_letters(self.col) + str(self.row + 1)

    def shifted(self, drow: int, dcol: int) -> "CellRef":
        return CellRef(self.row if self.abs_row else self.row + drow,
                       self.col if self.abs_col else self.col + dcol,
                       self.abs_row, self.abs_col)

    def in_bounds(self) -> bool:
        return 0 <= self.row < MAX_ROWS and 0 <= self.col < MAX_COLS


def parse_ref(text: str) -> CellRef:
    m = _REF_RE.match(text.strip())
    if not m:
        raise ValueError(f"Not a cell reference: {text!r}")
    abs_col, letters, abs_row, digits = m.groups()
    row = int(digits) - 1
    if row < 0:
        raise ValueError(f"Row must be 1 or more: {text!r}")
    return CellRef(row, letters_to_col(letters), bool(abs_row), bool(abs_col))


def is_ref(text: str) -> bool:
    return bool(_REF_RE.match(text.strip()))


def key_to_a1(key: tuple[int, int]) -> str:
    return col_to_letters(key[1]) + str(key[0] + 1)


def a1_to_key(text: str) -> tuple[int, int]:
    return parse_ref(text).key


def range_keys(a: CellRef, b: CellRef) -> list[list[tuple[int, int]]]:
    r0, r1 = sorted((a.row, b.row))
    c0, c1 = sorted((a.col, b.col))
    return [[(r, c) for c in range(c0, c1 + 1)] for r in range(r0, r1 + 1)]
