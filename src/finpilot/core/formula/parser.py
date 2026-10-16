"""Tokenizer and recursive-descent parser for the FinPilot formula language.

The language is a documented subset of Excel formulas (see docs/FORMULA_REFERENCE.md).
Formulas are parsed into a small AST and evaluated by ``evaluator.py``; nothing
the learner types is ever passed to Python's ``eval``.

Operator precedence follows Excel, lowest to highest::

    =  <>  <  >  <=  >=      comparison
    &                        text concatenation
    +  -                     addition
    *  /                     multiplication
    ^                        exponent
    -  (unary)               negation   (Excel: -2^2 = 4)
    %  (postfix)             percent
    :                        range
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Union

from .errors import FormulaSyntaxError
from .refs import CellRef, parse_ref

# --------------------------------------------------------------------------- AST


@dataclass(frozen=True)
class Num:
    value: float


@dataclass(frozen=True)
class Str:
    value: str


@dataclass(frozen=True)
class Bool:
    value: bool


@dataclass(frozen=True)
class Ref:
    ref: CellRef


@dataclass(frozen=True)
class Range:
    start: CellRef
    end: CellRef


@dataclass(frozen=True)
class Name:
    name: str


@dataclass(frozen=True)
class Unary:
    op: str
    operand: "Node"


@dataclass(frozen=True)
class Percent:
    operand: "Node"


@dataclass(frozen=True)
class Binary:
    op: str
    left: "Node"
    right: "Node"


@dataclass(frozen=True)
class Call:
    name: str
    args: tuple


Node = Union[Num, Str, Bool, Ref, Range, Name, Unary, Percent, Binary, Call]

# --------------------------------------------------------------------- tokenizer

_TOKEN_SPEC = [
    ("WS", r"[ \t\r\n]+"),
    ("NUMBER", r"(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"),
    ("STRING", r'"(?:[^"]|"")*"'),
    ("REF", r"\$?[A-Za-z]{1,3}\$?\d+(?![A-Za-z0-9_(])"),
    ("IDENT", r"[A-Za-z_][A-Za-z0-9_.]*"),
    ("OP", r"<>|<=|>=|[-+*/^&=<>%(),:]"),
]
_TOKEN_RE = re.compile("|".join(f"(?P<{n}>{p})" for n, p in _TOKEN_SPEC))


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    pos: int


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m:
            ch = text[pos]
            if ch in "{}[];!'":
                raise FormulaSyntaxError(
                    f"The character '{ch}' is not supported (array constants, structured "
                    "references and cross-sheet references are outside FinPilot's formula subset).", pos)
            raise FormulaSyntaxError(f"Unexpected character '{ch}' at position {pos + 1}.", pos)
        kind = m.lastgroup
        if kind != "WS":
            tokens.append(Token(kind, m.group(), pos))
        pos = m.end()
    tokens.append(Token("END", "", pos))
    return tokens


# ------------------------------------------------------------------------ parser

_COMPARISON = {"=", "<>", "<", ">", "<=", ">="}


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.toks = tokens
        self.i = 0

    @property
    def cur(self) -> Token:
        return self.toks[self.i]

    def take(self) -> Token:
        t = self.toks[self.i]
        self.i += 1
        return t

    def expect(self, text: str) -> Token:
        if self.cur.text != text:
            found = self.cur.text or "end of formula"
            raise FormulaSyntaxError(f"Expected '{text}' but found '{found}'.", self.cur.pos)
        return self.take()

    def parse(self) -> Node:
        if self.cur.kind == "END":
            raise FormulaSyntaxError("The formula is empty.", 0)
        node = self.comparison()
        if self.cur.kind != "END":
            raise FormulaSyntaxError(
                f"Unexpected '{self.cur.text}' at position {self.cur.pos + 1}. "
                "Did you forget an operator or a comma?", self.cur.pos)
        return node

    def comparison(self) -> Node:
        node = self.concat()
        while self.cur.kind == "OP" and self.cur.text in _COMPARISON:
            op = self.take().text
            node = Binary(op, node, self.concat())
        return node

    def concat(self) -> Node:
        node = self.additive()
        while self.cur.text == "&":
            self.take()
            node = Binary("&", node, self.additive())
        return node

    def additive(self) -> Node:
        node = self.multiplicative()
        while self.cur.kind == "OP" and self.cur.text in ("+", "-"):
            op = self.take().text
            node = Binary(op, node, self.multiplicative())
        return node

    def multiplicative(self) -> Node:
        node = self.power()
        while self.cur.kind == "OP" and self.cur.text in ("*", "/"):
            op = self.take().text
            node = Binary(op, node, self.power())
        return node

    def power(self) -> Node:
        node = self.unary()
        while self.cur.text == "^":
            self.take()
            node = Binary("^", node, self.unary())
        return node

    def unary(self) -> Node:
        if self.cur.kind == "OP" and self.cur.text in ("-", "+"):
            op = self.take().text
            operand = self.unary()
            return Unary(op, operand)
        return self.postfix()

    def postfix(self) -> Node:
        node = self.primary()
        while self.cur.text == "%":
            self.take()
            node = Percent(node)
        return node

    def primary(self) -> Node:
        t = self.cur
        if t.kind == "NUMBER":
            self.take()
            return Num(float(t.text))
        if t.kind == "STRING":
            self.take()
            return Str(t.text[1:-1].replace('""', '"'))
        if t.kind == "REF":
            self.take()
            start = parse_ref(t.text)
            if self.cur.text == ":":
                self.take()
                if self.cur.kind != "REF":
                    raise FormulaSyntaxError("A range needs a cell reference after ':' (for example B2:M2).",
                                             self.cur.pos)
                end = parse_ref(self.take().text)
                return Range(start, end)
            return Ref(start)
        if t.kind == "IDENT":
            self.take()
            upper = t.text.upper()
            if self.cur.text == "(":
                return self.call(upper)
            if upper in ("TRUE", "FALSE"):
                return Bool(upper == "TRUE")
            return Name(t.text)
        if t.text == "(":
            self.take()
            node = self.comparison()
            self.expect(")")
            return node
        if t.kind == "END":
            raise FormulaSyntaxError("The formula ends too early. Is something missing after an operator?",
                                     t.pos)
        raise FormulaSyntaxError(f"Unexpected '{t.text}' at position {t.pos + 1}.", t.pos)

    def call(self, name: str) -> Node:
        self.expect("(")
        args: list[Node] = []
        if self.cur.text == ")":
            self.take()
            return Call(name, tuple(args))
        while True:
            if self.cur.text in (",", ")"):
                args.append(_EMPTY)  # omitted argument, e.g. IF(A1,,2)
            else:
                args.append(self.comparison())
            if self.cur.text == ",":
                self.take()
                continue
            if self.cur.text == ")":
                self.take()
                break
            raise FormulaSyntaxError(f"Expected ',' or ')' in {name}(...) but found "
                                     f"'{self.cur.text or 'end of formula'}'.", self.cur.pos)
        return Call(name, tuple(args))


@dataclass(frozen=True)
class Empty:
    """An omitted function argument."""


_EMPTY = Empty()


def parse(formula: str) -> Node:
    """Parse a formula. A leading '=' is optional."""
    text = formula.strip()
    if text.startswith("="):
        text = text[1:]
    return _Parser(tokenize(text)).parse()


# ----------------------------------------------------------------- AST utilities


def to_formula(node: Node) -> str:
    """Render an AST back to formula text (without the leading '=')."""
    if isinstance(node, Num):
        v = node.value
        return str(int(v)) if v.is_integer() and abs(v) < 1e15 else repr(v)
    if isinstance(node, Str):
        return '"' + node.value.replace('"', '""') + '"'
    if isinstance(node, Bool):
        return "TRUE" if node.value else "FALSE"
    if isinstance(node, Ref):
        return node.ref.a1()
    if isinstance(node, Range):
        return f"{node.start.a1()}:{node.end.a1()}"
    if isinstance(node, Name):
        return node.name
    if isinstance(node, Empty):
        return ""
    if isinstance(node, Unary):
        return node.op + _wrap(node.operand, 6)
    if isinstance(node, Percent):
        return _wrap(node.operand, 7) + "%"
    if isinstance(node, Binary):
        p = _prec(node)
        right_p = p + 1  # left-associative
        return f"{_wrap(node.left, p)}{node.op}{_wrap(node.right, right_p)}"
    if isinstance(node, Call):
        return f"{node.name}({','.join(to_formula(a) for a in node.args)})"
    raise TypeError(node)


def _prec(node: Node) -> int:
    if isinstance(node, Binary):
        if node.op in _COMPARISON:
            return 1
        return {"&": 2, "+": 3, "-": 3, "*": 4, "/": 4, "^": 5}[node.op]
    if isinstance(node, Unary):
        return 6
    if isinstance(node, Percent):
        return 7
    return 9


def _wrap(node: Node, min_prec: int) -> str:
    s = to_formula(node)
    return f"({s})" if _prec(node) < min_prec else s


def shift(node: Node, drow: int, dcol: int) -> Node:
    """Copy a formula by an offset, adjusting relative references (fill/copy)."""
    if isinstance(node, Ref):
        return Ref(node.ref.shifted(drow, dcol))
    if isinstance(node, Range):
        return Range(node.start.shifted(drow, dcol), node.end.shifted(drow, dcol))
    if isinstance(node, Unary):
        return Unary(node.op, shift(node.operand, drow, dcol))
    if isinstance(node, Percent):
        return Percent(shift(node.operand, drow, dcol))
    if isinstance(node, Binary):
        return Binary(node.op, shift(node.left, drow, dcol), shift(node.right, drow, dcol))
    if isinstance(node, Call):
        return Call(node.name, tuple(shift(a, drow, dcol) for a in node.args))
    return node


def walk(node: Node):
    yield node
    if isinstance(node, (Unary, Percent)):
        yield from walk(node.operand)
    elif isinstance(node, Binary):
        yield from walk(node.left)
        yield from walk(node.right)
    elif isinstance(node, Call):
        for a in node.args:
            yield from walk(a)


def references(node: Node) -> list[Node]:
    """All Ref, Range and Name nodes in a formula."""
    return [n for n in walk(node) if isinstance(n, (Ref, Range, Name))]


def function_names(node: Node) -> set[str]:
    return {n.name for n in walk(node) if isinstance(n, Call)}


def numeric_literals(node: Node) -> list[float]:
    return [n.value for n in walk(node) if isinstance(n, Num)]
