"""Formula engine: parsing, precedence, functions, references and error values."""

import pytest

from finpilot.core.formula import CellError, FormulaSyntaxError, evaluate, parse, to_formula
from finpilot.core.formula.parser import shift
from finpilot.core.formula.refs import a1_to_key, col_to_letters, key_to_a1


def ev(f, **cells):
    return evaluate(f, cells)


def code(v):
    assert isinstance(v, CellError), f"expected an error value, got {v!r}"
    return v.code


@pytest.mark.parametrize("formula,expected", [
    ("=1+2*3", 7), ("=(1+2)*3", 9), ("=2^3^2", 64), ("=-2^2", 4), ("=10/4", 2.5),
    ("=5%", 0.05), ("=1+2=3", True), ("=\"a\"&\"b\"", "ab"), ("=2<>3", True), ("=7-2-1", 4),
])
def test_arithmetic_and_precedence_match_excel(formula, expected):
    assert ev(formula) == expected


def test_cell_references_and_ranges():
    assert ev("=A1*B1", A1=180, B1=31) == 5580
    assert ev("=SUM(A1:A3)", A1=1, A2=2, A3=3) == 6
    assert ev("=AVERAGE(A1:A3)", A1=1, A2=2, A3=6) == 3
    assert ev("=$A$1+A$1+$A1", A1=2) == 6


@pytest.mark.parametrize("formula,cells,expected", [
    ("=IF(A1>0,\"pos\",\"neg\")", {"A1": -1}, "neg"),
    ("=IFERROR(A1/B1,0)", {"A1": 1, "B1": 0}, 0),
    ("=ROUND(2.345,2)", {}, 2.35),
    ("=ROUNDDOWN(-2.5,0)", {}, -2),
    ("=MAX(A1:A3)-MIN(A1:A3)", {"A1": 4, "A2": 9, "A3": 1}, 8),
    ("=COUNTIF(A1:A4,\">2\")", {"A1": 1, "A2": 3, "A3": 5, "A4": 2}, 2),
    ("=SUMIF(A1:A3,\"x\",B1:B3)", {"A1": "x", "A2": "y", "A3": "x", "B1": 1, "B2": 2, "B3": 4}, 5),
    ("=SUMPRODUCT(A1:A2,B1:B2)", {"A1": 2, "A2": 3, "B1": 10, "B2": 100}, 320),
    ("=INDEX(B1:B3,MATCH(\"b\",A1:A3,0))", {"A1": "a", "A2": "b", "A3": "c", "B1": 1, "B2": 2, "B3": 3}, 2),
    ("=XLOOKUP(\"c\",A1:A3,B1:B3)", {"A1": "a", "A2": "b", "A3": "c", "B1": 1, "B2": 2, "B3": 3}, 3),
    ("=VLOOKUP(\"b\",A1:B3,2,FALSE)", {"A1": "a", "A2": "b", "A3": "c", "B1": 1, "B2": 2, "B3": 3}, 2),
    ("=AND(TRUE,A1>1)", {"A1": 2}, True),
    ("=LEFT(\"FinPilot\",3)", {}, "Fin"),
])
def test_functions(formula, cells, expected):
    assert evaluate(formula, cells) == expected


def test_date_functions():
    serial = evaluate("=DATE(2026,2,15)")
    assert evaluate("=DAY(EOMONTH(A1,0))", {"A1": serial}) == 28
    assert evaluate("=MONTH(EDATE(A1,1))", {"A1": serial}) == 3
    assert evaluate("=YEAR(A1)", {"A1": serial}) == 2026
    assert serial == 46068  # Excel serial for 15 Feb 2026


def test_financial_functions_match_known_values():
    assert evaluate("=PMT(0.05/12,360,200000)") == pytest.approx(-1073.643246, rel=1e-6)
    assert evaluate("=NPV(0.1,100,100,100)") == pytest.approx(248.685199, rel=1e-6)
    assert evaluate("=IRR(A1:A4)", {"A1": -1000, "A2": 400, "A3": 400, "A4": 400}) == pytest.approx(0.0970, abs=1e-4)
    assert evaluate("=FV(0.05,10,0,-1000)") == pytest.approx(1628.894627, rel=1e-6)


@pytest.mark.parametrize("formula,cells,err", [
    ("=A1/B1", {"A1": 1, "B1": 0}, "#DIV/0!"),
    ("=A1/B1", {"A1": 1}, "#DIV/0!"),               # blank denominator counts as zero
    ("=A1+\"x\"", {"A1": 1}, "#VALUE!"),
    ("=NOSUCHFN(1)", {}, "#NAME?"),
    ("=MATCH(\"z\",A1:A2,0)", {"A1": "a", "A2": "b"}, "#N/A"),
    ("=SQRT(-1)", {}, "#NUM!"),
    ("=OFFSET(A1,1,1)", {}, "#UNSUPPORTED!"),
    ("=INDIRECT(\"A1\")", {}, "#UNSUPPORTED!"),
    ("=UNKNOWN_NAME*2", {}, "#NAME?"),
])
def test_error_values_are_explicit(formula, cells, err):
    assert code(evaluate(formula, cells)) == err


def test_errors_propagate_and_can_be_trapped():
    assert code(ev("=A1/B1+5", A1=1, B1=0)) == "#DIV/0!"
    assert ev("=IFERROR(A1/B1,\"n/a\")", A1=1, B1=0) == "n/a"


def test_unsupported_error_has_explanation():
    v = evaluate("=OFFSET(A1,1,1)")
    assert "OFFSET" in v.detail or "not supported" in v.explanation.lower()


def test_syntax_errors_are_reported_not_executed():
    with pytest.raises(FormulaSyntaxError):
        parse("=SUM(A1:A3")
    with pytest.raises(FormulaSyntaxError):
        parse("=1+")
    # Python code is never executed: it is simply not a valid formula
    v = evaluate("=__import__('os').system('echo hacked')")
    assert isinstance(v, CellError)


def test_round_trip_and_reference_shifting():
    def sh(f, dr, dc):
        return "=" + to_formula(shift(parse(f), dr, dc))
    assert "=" + to_formula(parse("=$B$4*B9")) == "=$B$4*B9"
    assert sh("=$B$4*B9", 0, 1) == "=$B$4*C9"
    assert sh("=B$4*$B9", 1, 1) == "=C$4*$B10"
    assert sh("=SUM(B21:M21)", 1, 0) == "=SUM(B22:M22)"


def test_reference_helpers():
    assert col_to_letters(0) == "A" and col_to_letters(25) == "Z" and col_to_letters(26) == "AA"
    assert a1_to_key("B15") == (14, 1)
    assert key_to_a1((14, 1)) == "B15"
