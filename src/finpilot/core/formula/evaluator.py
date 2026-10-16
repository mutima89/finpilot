"""Evaluate parsed formulas against a cell/name context."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .errors import CellError, ErrorSignal, err
from .parser import (Binary, Bool, Call, Empty, Name, Node, Num, Percent, Range, Ref,
                     Str, Unary)
from .refs import CellRef, range_keys


class RangeValue:
    """A rectangular block of evaluated values (rows x cols)."""

    __slots__ = ("rows",)

    def __init__(self, rows: list[list[Any]]):
        self.rows = rows

    @property
    def height(self) -> int:
        return len(self.rows)

    @property
    def width(self) -> int:
        return len(self.rows[0]) if self.rows else 0

    def flat(self) -> list[Any]:
        return [v for row in self.rows for v in row]

    def is_vector(self) -> bool:
        return self.height == 1 or self.width == 1

    def __repr__(self) -> str:
        return f"RangeValue({self.rows!r})"


class Context(Protocol):
    def cell_value(self, ref: CellRef) -> Any: ...

    def name_value(self, name: str) -> Any: ...


# ----------------------------------------------------------------- coercion


def check(v: Any) -> Any:
    if isinstance(v, CellError):
        raise ErrorSignal(v)
    return v


def to_number(v: Any) -> float:
    v = check(v)
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        try:
            if s.endswith("%"):
                return float(s[:-1]) / 100.0
            return float(s)
        except ValueError:
            raise err("#VALUE!", f"'{v}' is text, not a number.")
    if isinstance(v, RangeValue):
        if v.height == 1 and v.width == 1:
            return to_number(v.rows[0][0])
        raise err("#VALUE!", "A range was used where a single number is expected. "
                             "Wrap it in a function such as SUM().")
    raise err("#VALUE!")


def to_bool(v: Any) -> bool:
    v = check(v)
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        if v.upper() == "TRUE":
            return True
        if v.upper() == "FALSE":
            return False
        raise err("#VALUE!", f"'{v}' is not TRUE or FALSE.")
    if isinstance(v, RangeValue) and v.height == 1 and v.width == 1:
        return to_bool(v.rows[0][0])
    raise err("#VALUE!")


def to_text(v: Any) -> str:
    v = check(v)
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, RangeValue) and v.height == 1 and v.width == 1:
        return to_text(v.rows[0][0])
    if isinstance(v, RangeValue):
        raise err("#VALUE!", "A range was used where text is expected.")
    return str(v)


def scalar(v: Any) -> Any:
    if isinstance(v, RangeValue):
        if v.height == 1 and v.width == 1:
            return v.rows[0][0]
        raise err("#VALUE!", "A range was used where a single value is expected.")
    return v


def finite(x: float) -> float:
    if math.isnan(x) or math.isinf(x):
        raise err("#NUM!", "The result is too large or not a real number.")
    return x


# ---------------------------------------------------------------- evaluator


@dataclass
class Function:
    name: str
    impl: Callable
    min_args: int
    max_args: int | None  # None = unlimited
    lazy: bool = False  # receives (evaluator, nodes) instead of values
    summary: str = ""


class Evaluator:
    def __init__(self, ctx: Context, functions: dict[str, Function]):
        self.ctx = ctx
        self.functions = functions

    def evaluate(self, node: Node) -> Any:
        """Evaluate to a value; errors are returned as CellError, never raised."""
        try:
            v = self.eval(node)
            if isinstance(v, RangeValue):
                if v.height == 1 and v.width == 1:
                    v = v.rows[0][0]
                else:
                    return CellError("#VALUE!", "A cell cannot show a whole range. "
                                                "Use SUM(), INDEX() or a single reference.")
            if isinstance(v, float):
                finite(v)
            return v
        except ErrorSignal as e:
            return e.error
        except RecursionError:
            return CellError("#CIRC!", "The chain of references is too deep or circular.")

    def eval(self, node: Node) -> Any:
        if isinstance(node, Num):
            return node.value
        if isinstance(node, Str):
            return node.value
        if isinstance(node, Bool):
            return node.value
        if isinstance(node, Empty):
            return None
        if isinstance(node, Ref):
            if not node.ref.in_bounds():
                raise err("#REF!")
            return check(self.ctx.cell_value(node.ref))
        if isinstance(node, Range):
            if not (node.start.in_bounds() and node.end.in_bounds()):
                raise err("#REF!")
            rows = [[self.ctx.cell_value(CellRef(r, c)) for (r, c) in row]
                    for row in range_keys(node.start, node.end)]
            return RangeValue(rows)
        if isinstance(node, Name):
            v = self.ctx.name_value(node.name)
            if isinstance(v, CellError):
                raise ErrorSignal(v)
            return v
        if isinstance(node, Unary):
            x = to_number(scalar(self.eval(node.operand)))
            return -x if node.op == "-" else x
        if isinstance(node, Percent):
            return to_number(scalar(self.eval(node.operand))) / 100.0
        if isinstance(node, Binary):
            return self.binary(node)
        if isinstance(node, Call):
            return self.call(node)
        raise err("#UNSUPPORTED!")

    def binary(self, node: Binary) -> Any:
        op = node.op
        a = scalar(self.eval(node.left))
        b = scalar(self.eval(node.right))
        if op == "&":
            return to_text(a) + to_text(b)
        if op in ("=", "<>", "<", ">", "<=", ">="):
            return compare(check(a), check(b), op)
        x, y = to_number(a), to_number(b)
        if op == "+":
            return x + y
        if op == "-":
            return x - y
        if op == "*":
            return x * y
        if op == "/":
            if y == 0:
                raise err("#DIV/0!")
            return x / y
        if op == "^":
            try:
                r = x ** y
            except (OverflowError, ZeroDivisionError):
                raise err("#NUM!")
            if isinstance(r, complex):
                raise err("#NUM!", "A negative number cannot be raised to a fractional power.")
            return finite(float(r))
        raise err("#UNSUPPORTED!", f"Operator {op}")

    def call(self, node: Call) -> Any:
        fn = self.functions.get(node.name)
        if fn is None:
            from .functions import KNOWN_UNSUPPORTED
            if node.name in KNOWN_UNSUPPORTED:
                raise err("#UNSUPPORTED!", f"{node.name}() is a real Excel function but is not "
                                           "supported in FinPilot yet.")
            raise err("#NAME?", f"There is no function called {node.name}().")
        n = len(node.args)
        if n < fn.min_args or (fn.max_args is not None and n > fn.max_args):
            expected = (f"{fn.min_args}" if fn.min_args == fn.max_args
                        else f"{fn.min_args} to {fn.max_args if fn.max_args is not None else 'many'}")
            raise err("#VALUE!", f"{node.name}() expects {expected} argument(s) but got {n}.")
        if fn.lazy:
            return fn.impl(self, node.args)
        return fn.impl(*[self.eval(a) for a in node.args])


def _type_rank(v: Any) -> int:
    # Excel ordering: numbers < text < logicals
    if isinstance(v, bool):
        return 2
    if isinstance(v, str):
        return 1
    return 0


def compare(a: Any, b: Any, op: str) -> bool:
    if a is None:
        a = "" if isinstance(b, str) else (False if isinstance(b, bool) else 0.0)
    if b is None:
        b = "" if isinstance(a, str) else (False if isinstance(a, bool) else 0.0)
    ra, rb = _type_rank(a), _type_rank(b)
    if ra != rb:
        diff = ra - rb
        return {"=": False, "<>": True, "<": diff < 0, ">": diff > 0,
                "<=": diff < 0, ">=": diff > 0}[op]
    if isinstance(a, str):
        a, b = a.lower(), b.lower()
    else:
        a, b = float(a), float(b)
        if op in ("=", "<>"):
            eq = math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
            return eq if op == "=" else not eq
    return {"=": a == b, "<>": a != b, "<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[op]
