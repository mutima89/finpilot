"""FinPilot formula engine: a safe, documented subset of Excel formulas."""
from __future__ import annotations

from typing import Any, Mapping

from .errors import CODES, CellError, FormulaSyntaxError
from .evaluator import Evaluator, RangeValue
from .functions import FUNCTIONS, KNOWN_UNSUPPORTED
from .parser import parse, references, shift, to_formula
from .refs import CellRef, a1_to_key, col_to_letters, key_to_a1, parse_ref

__all__ = [
    "CODES", "CellError", "FormulaSyntaxError", "Evaluator", "RangeValue", "FUNCTIONS",
    "KNOWN_UNSUPPORTED", "parse", "references", "shift", "to_formula", "CellRef", "a1_to_key",
    "col_to_letters", "key_to_a1", "parse_ref", "evaluate", "DictContext",
]


class DictContext:
    """Evaluation context backed by plain dicts (used by lessons and tests).

    ``cells`` maps "B2" -> value (numbers, text, bools or None).
    ``names`` maps a named assumption -> value.
    """

    def __init__(self, cells: Mapping[str, Any] | None = None, names: Mapping[str, Any] | None = None):
        self.cells = {a1_to_key(k): v for k, v in (cells or {}).items()}
        self.names = {k.upper(): v for k, v in (names or {}).items()}

    def cell_value(self, ref: CellRef) -> Any:
        return self.cells.get(ref.key)

    def name_value(self, name: str) -> Any:
        if name.upper() not in self.names:
            return CellError("#NAME?", f"'{name}' is not a named assumption.")
        return self.names[name.upper()]


def evaluate(formula: str, cells: Mapping[str, Any] | None = None,
             names: Mapping[str, Any] | None = None) -> Any:
    """Parse and evaluate a formula. Returns a value or a CellError (never raises)."""
    try:
        node = parse(formula)
    except FormulaSyntaxError as e:
        return CellError("#PARSE!", str(e))
    return Evaluator(DictContext(cells, names), FUNCTIONS).evaluate(node)
