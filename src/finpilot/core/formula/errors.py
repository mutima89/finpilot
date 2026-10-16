"""Error values for the FinPilot formula engine.

FinPilot separates four kinds of problems, because a learner needs to fix each
one differently:

* FORMULA  - the formula itself is broken (syntax, unknown function, bad
             reference, circular reference, unsupported feature).
* INPUT    - an input is the wrong type or out of range (text where a number
             is expected, a negative room count).
* MISSING  - something the calculation needs has not been entered yet.
* MATH     - the formula is fine but the maths is undefined (divide by zero).

A fifth category, "valid but financially unreasonable", is not an error value
at all; it is raised by model validation checks (see ``core.validation``).
"""
from __future__ import annotations

from dataclasses import dataclass

FORMULA = "formula"
INPUT = "input"
MISSING = "missing"
MATH = "math"

# Excel-compatible codes plus two FinPilot-specific ones (#CIRC!, #UNSUPPORTED!)
CODES = {
    "#DIV/0!": (MATH, "Division by zero: the denominator is zero or blank."),
    "#VALUE!": (INPUT, "A value has the wrong type, for example text used in arithmetic."),
    "#REF!": (FORMULA, "The formula refers to a cell outside the sheet."),
    "#NAME?": (FORMULA, "Unknown function or named assumption."),
    "#N/A": (MISSING, "A lookup did not find a match, or a value is not available."),
    "#NUM!": (MATH, "The calculation produced an invalid number."),
    "#CIRC!": (FORMULA, "Circular reference: the formula depends on its own result."),
    "#UNSUPPORTED!": (FORMULA, "This function or syntax is not supported by FinPilot."),
    "#PARSE!": (FORMULA, "The formula could not be read. Check brackets, commas and operators."),
}


@dataclass(frozen=True)
class CellError:
    code: str
    detail: str = ""

    @property
    def category(self) -> str:
        return CODES.get(self.code, (FORMULA, ""))[0]

    @property
    def explanation(self) -> str:
        base = CODES.get(self.code, (FORMULA, "Unknown error."))[1]
        return f"{base} {self.detail}".strip()

    def __str__(self) -> str:  # what the grid shows
        return self.code


class ErrorSignal(Exception):
    """Raised inside evaluation to propagate a CellError up to the cell."""

    def __init__(self, error: CellError):
        super().__init__(error.code)
        self.error = error


class FormulaSyntaxError(Exception):
    """Raised by the tokenizer / parser for malformed formulas."""

    def __init__(self, message: str, position: int | None = None):
        super().__init__(message)
        self.position = position


def err(code: str, detail: str = "") -> ErrorSignal:
    return ErrorSignal(CellError(code, detail))
